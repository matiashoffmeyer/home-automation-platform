#!/usr/bin/env python3
"""Serves single JPEG frames from RTSP sub-streams on the /api/<camera>/latest.jpg
path that the hand_recognition add-on fetches, reports whether a body tall
enough to reach the frame is moving in it, and listens on the same stream's
audio track for a short list of spoken commands.

ffmpeg is only kept alive while frames are actually being requested, so an idle
kitchen costs nothing. Within a burst the stream is already warm, so frames after
the first are served without paying RTSP connect + keyframe latency again.

The voice side deliberately shares the motion detector's ffmpeg process rather
than opening its own: the camera allows only a handful of concurrent RTSP
sessions, and this add-on already holds one of them.
"""

import array
import json
import logging
import math
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import wave
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Only the gaze detector needs these, and the offline test rigs import this file
# on machines that have neither. Missing opencv disables that one feature and
# leaves frames, motion and voice untouched.
try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None
    np = None

SOI = b"\xff\xd8"
EOI = b"\xff\xd9"

# Both models are baked into the image by the Dockerfile.
YUNET_PATH = "/models/yunet.onnx"
GAZE_PATH = "/models/mobileone_s0_gaze.onnx"
PALM_PATH = "/models/palm_detection_full.tflite"
PALM_LOG = "/share/gesture_frame_shim/palms.jsonl"
# MobileGaze answers in 90 bins of 4 degrees, centred on straight ahead, and
# wants ImageNet normalisation on a 448 px crop. These are the model's, not ours.
GAZE_BINS, GAZE_BINW, GAZE_OFFSET = 90, 4, 180
GAZE_MEAN = (0.485, 0.456, 0.406)
GAZE_STD = (0.229, 0.224, 0.225)
# Narrower than this and the eyes are a handful of pixels. The labelled frames
# that the separation was measured on ran 100-160 px wide.
GAZE_MIN_FACE = 60

# A camera that loses power mid-stream leaves the TCP connection half-open, so
# ffmpeg's read blocks forever and the reader thread never reaches its idle
# check again — the stream then looks "alive" while serving nothing until the
# add-on is restarted by hand. A watchdog on ffmpeg's byte flow is the only
# version-independent way out.
CONNECT_TIMEOUT = 15.0
STALL_TIMEOUT = 6.0

# Coarse enough that one person covers several cells and JPEG noise covers none.
GRID_W, GRID_H = 32, 18
FRAME_BYTES = GRID_W * GRID_H
MOTION_FPS = 2
BEAT_INTERVAL = 60

# The camera sends 8 kHz A-law; ffmpeg resamples to what the STT server wants.
VOICE_RATE = 16000
VOICE_FRAME_MS = 30
VOICE_FRAME_SAMPLES = VOICE_RATE * VOICE_FRAME_MS // 1000
VOICE_FRAME_BYTES = VOICE_FRAME_SAMPLES * 2
VOICE_PAD_S = 0.35
VOICE_CARRY_S = 0.35
VOICE_GAP_S = 0.45
# Frames this quiet carry no usable pitch, so letting them into the median would
# just measure the room tone. 200 RMS is where the reference measurement drew it.
VOICE_FEAT_MIN_RMS = 200
# 100 ms per read: small enough that a phrase is not held hostage by the buffer,
# large enough that the pump is not woken hundreds of times a second.
VOICE_PUMP_BYTES = VOICE_RATE * 2 // 10
VOICE_STALE_S = 6.0
# Calibration trail (2026-09-28). A transcript alone cannot tell a badly CUT
# phrase from a badly HEARD one: "timer twenty minutes" said twice came back as
# 'pause timer' (1.17 s) and 'timer eleven minutes' (2.04 s), and the regions
# around them had already scrolled out of the 15-entry reject list. Only audio
# the cook deliberately addressed to the lens is kept — clips inside an open
# arming window — so an unarmed kitchen still writes nothing to disk.
VOICE_CLIP_DIR = "/share/gesture_frame_shim/clips"
VOICE_CLIP_KEEP = 80
AUDIO_RETRY_AFTER = 600

NUMBERS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
}

log = logging.getLogger("shim")


def frame_stats(buf):
    """RMS, its dBFS value, and zero crossings for one frame.

    Written out by hand rather than using audioop, which is gone in Python 3.13
    and would tie the add-on to whatever the base image happens to ship. Checked
    against audioop on 1334 real frames: crossings identical, dBFS within 1.3 dB
    and only down at the silence floor, where audioop's integer RMS rounds to
    zero. The threshold sits at -35 dBFS, far above that.
    """
    samples = array.array("h")
    samples.frombytes(buf)
    if sys.byteorder != "little":
        samples.byteswap()
    total = 0
    crossings = 0
    prev = samples[0]
    for value in samples:
        total += value * value
        if (value < 0) != (prev < 0):
            crossings += 1
        prev = value
    rms = math.sqrt(total / len(samples))
    db = -200.0 if rms < 1 else 20 * math.log10(rms / 32768.0)
    return rms, db, crossings


def parse_command(text):
    """Map a transcript onto the allowed commands, or reject it.

    An exact allowlist rather than a search, because the STT server's grammar is
    the whole of HA's sentence set: kitchen noise transcribes as 'pause' or
    "what's the current time" often enough to matter (measured 2026-09-16, two
    hits in 150 s of an empty room). Anything that is not one of ours is noise.
    """
    words = text.lower().split()
    if not words:
        return None
    joined = " ".join(words)
    if joined in ("party time", "partytime"):
        return "party_time", 0
    if joined in ("auto mode", "automode"):
        return "auto_mode", 0
    # Cancelling. The forms below are exactly the ones speech-to-phrase is
    # trained to emit — sentences.yaml:1072 is "(cancel|stop) [the|my] timer"
    # and :1074 is "(cancel|stop) all [[of ](the|my)] timers" — so nothing
    # outside this list can reach us, and enumerating them beats a regex that
    # would also accept forms the engine can never produce.
    if joined in (
        "stop timer",
        "stop the timer",
        "stop my timer",
        "cancel timer",
        "cancel the timer",
        "cancel my timer",
        "stop all timers",
        "stop all the timers",
        "stop all my timers",
        "stop all of the timers",
        "stop all of my timers",
        "cancel all timers",
        "cancel all the timers",
        "cancel all my timers",
        "cancel all of the timers",
        "cancel all of my timers",
    ):
        return "stop_timer", 0
    # TWO grammars in HA's sentence set reach us, and only the bare one was
    # handled. Counted over the whole add-on log 2026-09-20: 20 utterances came
    # as "timer <word> minute(s)" and were accepted, while 8 came as
    # "(set|create) [a|the] timer for <digits> minute(s)" and were dropped in
    # silence — among them the user's "18 minutter". The two spellings travel
    # together: the digit form ONLY ever appears with the "set ... for"
    # envelope, and the word form only ever without it, so accepting one
    # without the other leaves a third of real commands on the floor.
    if len(words) >= 2 and words[0] in ("set", "create", "start"):
        rest = words[1:]
        if rest[0] in ("a", "the"):
            rest = rest[1:]
        if rest[:1] == ["timer"]:
            rest = rest[1:]
            if rest[:1] == ["for"]:
                rest = rest[1:]
            words = ["timer"] + rest
    # The trailing "minute(s)" is required, not decoration. Overlapping VAD
    # windows cut one utterance into several, and a truncated "timer thirteen
    # minutes" came back as 'timer one' — a valid-looking command with the wrong
    # number. The final word is what proves the whole sentence was heard. It is
    # also the only thing rejecting the nine measured HOUR forms, which the
    # envelope above now lets this far in ("set timer for 2 and a half hours").
    if len(words) >= 3 and words[0] == "timer" and words[-1] in ("minute", "minutes"):
        total = 0
        for word in words[1:-1]:
            if word in NUMBERS:
                total += NUMBERS[word]
            elif word.isdigit():
                total += int(word)
            else:
                return None
        # The number/noun agreement check that used to sit here is removed
        # (2026-09-17). It rested on one noise sample and one real sample, and
        # real use falsified it: the user spoke to this microphone twice at
        # 10:21 and both came back 'timer five minute'. The singular is the STT
        # clipping a trailing sibilant, not a person misspeaking — so the check
        # rejected speech while keeping exactly the form it was built to catch.
        # The house's own Assist grammar accepts both (voice_commands.yaml:398),
        # so this was the only place in the house where the two disagreed.
        # Truncation is still guarded: the trailing minute(s) token above stays
        # required, and that is what caught 'timer one'.
        if 1 <= total <= 60:
            return "timer", total
    return None


def watch_stream(proc, started, progress, name):
    """Kill ffmpeg if its byte flow stops, so its reader thread can exit.

    Connecting is allowed to be slow, but once bytes flow a gap means the camera
    is gone, not that it is being quiet.
    """

    def run():
        while proc.poll() is None:
            last = progress()
            flowing = last > started
            since = time.monotonic() - (last if flowing else started)
            if since > (STALL_TIMEOUT if flowing else CONNECT_TIMEOUT):
                log.error(
                    "[%s] no data for %.0fs (%s) — killing stalled stream",
                    name,
                    since,
                    "stalled" if flowing else "never connected",
                )
                proc.kill()
                return
            time.sleep(1)

    threading.Thread(target=run, daemon=True).start()


def push_state(entity, state, attributes):
    """Write a state straight into HA. Lost on restart, which is correct here:
    this signal is only meaningful while the camera is actually streaming."""
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        return
    body = json.dumps({"state": state, "attributes": attributes}).encode()
    req = urllib.request.Request(
        f"http://supervisor/core/api/states/{entity}",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=5).close()
    except (urllib.error.URLError, OSError) as err:
        log.warning("could not push %s: %s", entity, err)


def read_state(entity):
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        return None
    req = urllib.request.Request(
        f"http://supervisor/core/api/states/{entity}",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.load(resp).get("state")
    except (urllib.error.URLError, OSError, ValueError):
        return None


def render_template(template):
    """Render a Jinja template in HA and return the raw text, or None.

    Used instead of one read_state() per slider: polling six numbers costs one
    round trip rather than six.
    """
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        return None
    body = json.dumps({"template": template}).encode()
    req = urllib.request.Request(
        "http://supervisor/core/api/template",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.read().decode()
    except (urllib.error.URLError, OSError) as err:
        log.debug("template render failed: %s", err)
        return None


def call_service(domain, service, data):
    """Call an HA service with the add-on's own token."""
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        return False
    req = urllib.request.Request(
        f"http://supervisor/core/api/services/{domain}/{service}",
        data=json.dumps(data).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=5).close()
        return True
    except (urllib.error.URLError, OSError) as err:
        log.warning("could not call %s.%s: %s", domain, service, err)
        return False


class Tunables:
    """Voice thresholds, re-read from HA's sliders while the add-on runs.

    All six also exist as add-on options, and those stay the FLOOR: they seed
    the values at startup and stand in whenever HA cannot answer. The polling
    exists because the alternative is worse — changing an add-on option takes a
    restart, and a restart tears down the RTSP session, so tuning by option
    would cost a reconnect per nudge.

    Every failure path keeps the last known good value rather than falling back
    to a default: an unreadable slider must not quietly reset the tuning. A
    slider that is genuinely `unknown` — the seconds after a restart, or a
    helper that was never created — renders as the add-on option through
    `| float(default)`, which is the same number the option would have given.
    """

    TTL = 20

    # Key as this class exposes it -> the slider that owns it. Defaults are
    # deliberately NOT here: they come from the add-on options, so there is
    # exactly one place a default can be wrong.
    SPEC = {
        "threshold": "input_number.stemme_taerskel_dbfs",
        "zcr_max": "input_number.stemme_zcr_max",
        "min_utt": "input_number.stemme_min_laengde_sek",
        "max_utt": "input_number.stemme_max_laengde_sek",
        "cooldown": "input_number.stemme_cooldown_sek",
        "body_window": "input_number.stemme_krop_vindue_sek",
        "arm_window": "input_number.stemme_arm_vindue_sek",
    }

    def __init__(self, fallback, live=True):
        self._values = dict(fallback)
        # live=False is how the offline test rigs keep their own numbers. A
        # sweep that silently picked up the house's live sliders would be
        # measuring the house instead of the combination under test.
        self._live = live and bool(os.environ.get("SUPERVISOR_TOKEN"))
        self._checked = -999.0
        self._tpl = (
            "{"
            + ", ".join(
                "\"%s\": {{ states('%s') | float(%s) }}" % (key, entity, fallback[key])
                for key, entity in self.SPEC.items()
            )
            + "}"
        )

    def get(self, key):
        if self._live and time.monotonic() - self._checked > self.TTL:
            self._checked = time.monotonic()
            self._refresh()
        return self._values[key]

    def _refresh(self):
        raw = render_template(self._tpl)
        if raw is None:
            return
        try:
            fresh = json.loads(raw)
        except ValueError:
            log.warning("tunables template did not render JSON: %r", raw[:120])
            return
        changed = {
            key: (self._values[key], fresh[key])
            for key in self._values
            if key in fresh and fresh[key] != self._values[key]
        }
        for key in self._values:
            if key in fresh:
                self._values[key] = fresh[key]
        if changed:
            log.info(
                "voice tuning changed: %s",
                ", ".join(f"{k} {was}->{now}" for k, (was, now) in changed.items()),
            )

    def snapshot(self):
        return {key: self._values[key] for key in self.SPEC}


class ArmGate:
    """A raised hand is what makes the microphone worth listening to.

    Measured 2026-09-17: 81 transcripts across 56.1 minutes of ordinary Danish
    kitchen conversation, 14 of which passed the command allowlist — about one
    false command every four minutes, all day long. Speech-to-Phrase snaps every
    utterance onto its nearest trained sentence and hands over text with no
    confidence attached, so a clattering pan that came out as 'timer eight
    minute' and a person who said it are literally the same string. No filter on
    the text can separate them; the rejection has to come from outside the audio.

    The only deliberate signal this camera can see is a hand — it is angled at
    the wall above the counter, so faces sit outside the frame. HA writes epoch
    seconds here when it recognises the arming gesture; epoch rather than a
    formatted time because time.time() below is epoch too, which leaves no
    timezone or DST trap between them.

    consume() is what makes one gesture worth one command: a stamp that has
    already fired cannot fire again, so a hand raised once cannot be spent twice
    by two overlapping regions of the same noise.

    An unreachable HA closes this gate. That is the opposite of VoiceGate in
    this same file, and deliberate: VoiceGate protects CPU, where staying open
    costs nothing, while this one is the entire defence against a false command
    every four minutes.
    """

    # Two seconds, not the thirty the other gates use. This one is read at the
    # end of an utterance to decide whether that utterance may exist at all, so
    # a stale answer is a wrong answer — and the arming gesture happens seconds
    # before the words, not minutes.
    TTL = 2

    # How early the first word may start before the look that arms it. The
    # stamp is floored to whole seconds and the region carries 0.35 s of
    # lead-in, so a cook who speaks the instant the light answers is already
    # "before" the stamp.
    SLACK = 2.0

    def __init__(self, entity):
        self._entity = entity
        self._checked = -999.0
        self._stamp = 0.0
        self._used = 0.0
        # Every stamp seen, not just the latest (2026-09-28). With only the
        # latest, a look taken WHILE the previous phrase was being transcribed
        # replaced the stamp that phrase was armed by — the phrase still passed
        # (its first word lay before the new stamp, which read as "in window"),
        # and consume() then spent the NEW look. Measured: look 17:34:06 ->
        # 'timer twenty minutes' handled 17:34:20.3, look 17:34:19.9 eaten by
        # it, and the four phrases the second look was meant for all dropped as
        # unarmed. Each region is now matched to the look that preceded it.
        self._history = deque(maxlen=6)
        # Two threads write the history since 2026-10-03: the HA poll, and
        # note() from the audio thread (a look taken WHILE speaking).
        self._lock = threading.Lock()

    def _poll(self):
        if time.monotonic() - self._checked > self.TTL:
            self._checked = time.monotonic()
            raw = read_state(self._entity)
            try:
                self._stamp = float(raw)
                with self._lock:
                    # Membership, not "differs from the last": a stamp note()
                    # put in locally is echoed back by HA a poll later and must
                    # not be appended a second time, out of order.
                    if self._stamp not in self._history:
                        self._history.append(self._stamp)
            except (TypeError, ValueError):
                # 'unknown' before the first ever arming, or HA unreachable.
                # Both mean "no hand has been raised", which is the closed
                # answer, and closed is the safe direction here.
                self._stamp = 0.0
        return self._stamp

    def armed(self, window, at=None):
        # `at` is when the words BEGAN. Measured 2026-09-23: armed 15:44:45,
        # 'stop timer' spoken from ~15:44:55.7, dropped at 15:44:57.6 — the
        # 1.1 s phrase plus 0.8 s of transcription spent the last of the window
        # on something the cook cannot see. The promise is "look, then speak
        # within N seconds", so N is measured to the first word.
        return self._match(window, at) is not None

    def _match(self, window, at=None):
        """The newest unspent look that this phrase could have been armed by."""
        self._poll()
        when = time.time() if at is None else at
        with self._lock:
            history = list(self._history)
        for stamp in reversed(history):
            if stamp > self._used and stamp - self.SLACK <= when and when - stamp <= window:
                return stamp
        return None

    def consume(self, window, at=None):
        stamp = self._match(window, at)
        # Spending a look also spends every older one: a phrase armed by the
        # second look proves the first is no longer wanted.
        if stamp is not None:
            self._used = max(self._used, stamp)

    def note(self, stamp):
        """Arm from a look the shim saw itself, without waiting for HA's echo.

        The look-while-speaking path (GazeWatcher.heard_while_looking) decides
        while the phrase it arms is already in hand; the 2 s poll would leave
        that phrase unarmed. Returns whether this is the newest stamp known —
        only then may HA's stamp be overwritten, or a look written by the gaze
        thread a moment later would be replaced by an older one.
        """
        stamp = float(stamp)
        with self._lock:
            newest = not self._history or stamp > max(self._history)
            if stamp not in self._history:
                ordered = sorted(list(self._history) + [stamp])
                self._history.clear()
                self._history.extend(ordered[-self._history.maxlen :])
        return newest

    def snapshot(self, window):
        stamp = self._poll()
        return {
            "entity": self._entity,
            "stamp": int(stamp),
            "alder": round(time.time() - stamp, 1) if stamp else None,
            "brugt": stamp <= self._used,
            "armeret": self.armed(window),
        }


class GuestModeGate:
    """Filming is banned outright while the flat is let out, and this add-on is
    the thing that actually opens the RTSP socket — so the ban is enforced here
    rather than in the automations that merely consume frames.

    An unknown answer counts as banned, but only after the last known one has
    had time to go stale: HA is unreachable for about a minute during every
    restart, and tearing the stream down for that would be pure churn.
    """

    TTL = 30
    GRACE = 300

    def __init__(self):
        self._checked = 0.0
        self._answered = 0.0
        self._banned = True

    def banned(self):
        now = time.monotonic()
        if now - self._checked < self.TTL:
            return self._banned
        self._checked = now
        mode = read_state("input_select.house_mode")
        if mode is None:
            if now - self._answered > self.GRACE:
                if not self._banned:
                    log.warning("house_mode unreachable for %ds — stopping camera", self.GRACE)
                self._banned = True
            return self._banned
        self._answered = now
        was = self._banned
        self._banned = mode == "AirBnB"
        if was != self._banned:
            log.info("house_mode=%s — camera %s", mode, "blocked" if self._banned else "allowed")
        return self._banned


class VoiceGate:
    """Caches the kill switch so the recogniser can skip work while it is off.

    This is an optimisation, not the enforcement. The automation that reads the
    sensor carries the real condition, so a stale "on" here costs CPU and
    nothing else — which is why an unreachable HA leaves the last answer
    standing instead of closing. Closing would silence the feature during every
    restart, and a command that goes unanswered is the failure the user notices.

    The legal ban on listening is a different question with a different answer:
    it lives in GuestModeGate, which stops the stream itself.
    """

    TTL = 30

    def __init__(self, entity, label="voice commands"):
        self._entity = entity
        self._label = label
        self._checked = -999.0
        self._on = True

    def enabled(self):
        now = time.monotonic()
        if now - self._checked < self.TTL:
            return self._on
        self._checked = now
        state = read_state(self._entity)
        if state is None:
            return self._on
        was = self._on
        self._on = state == "on"
        if was != self._on:
            log.info(
                "%s=%s — %s %s",
                self._entity,
                state,
                self._label,
                "listening" if self._on else "idle",
            )
        return self._on


class PresenceEcho:
    """The radar's half of "is anybody in the kitchen".

    The camera's body detector reports MOVEMENT — it has to, because the light
    chain hangs in shot and a still frame cannot be told from a relit one. But
    somebody who stops at the counter to speak a command is exactly the case it
    goes blind on: measured 2026-09-16, the room read empty seconds after the
    user had walked in and spoken. The radar holds a still target, so the two
    instruments are blind in opposite directions and only their OR is a fair
    answer to the question the voice gate is actually asking.
    """

    TTL = 10

    def __init__(self, entity):
        self._entity = entity
        self._checked = -999.0
        self._on = False

    def occupied(self):
        if not self._entity:
            return False
        now = time.monotonic()
        if now - self._checked < self.TTL:
            return self._on
        self._checked = now
        state = read_state(self._entity)
        if state is not None:
            # unavailable is neither on nor off; keeping the last reading is
            # better than letting a radio dropout mute the microphone.
            self._on = state == "on"
        return self._on


class GazeTunables(Tunables):
    """The gaze sliders, polled the same way the voice ones are.

    Kitchen entity names, like the voice SPEC above: there is one camera that
    can see a face, and inventing a per-camera naming scheme for a helper that
    would have exactly one instance is the more expensive kind of general.
    """

    SPEC = {
        "taersk": "input_number.koekken_blik_taerskel_grader",
        "frames": "input_number.koekken_blik_frames",
        # Deliberately the SAME slider the spoken window uses: one look opens
        # the microphone for exactly as long as one raised hand does, and the
        # window doubles as this detector's re-arm cooldown.
        "window": "input_number.stemme_arm_vindue_sek",
        # 2026-09-23 (user-bug: "face detection trigger også ofte utilsigtet,
        # selv når jeg står med nakken til"). Measured on 18-22/09: 43 of 47
        # armings were never followed by speech, and 21 of those 43 read BELOW
        # 15 degrees — inside the genuine-look range. The angle cannot separate
        # them; these two gates are independent of it (see _face):
        "score_min": "input_number.koekken_blik_ansigt_score",
        "frontal_max": "input_number.koekken_blik_frontal_max",
        # 2026-10-03: the looser limit for a look taken WHILE speaking — see
        # GazeWatcher.heard_while_looking. 0 switches that path off.
        "tale": "input_number.koekken_blik_tale_taerskel_grader",
    }


class HandTunables(Tunables):
    """How large the frame the hand add-on sees is, as a percentage.

    2026-09-24 (user: "den ser min hånd på lang afstand når jeg tager krukker
    … den burde kun tage fagter ind som er tæt på"). The add-on reports no
    landmarks or box, only gesture/score/facing, so size cannot be gated in
    HA. Measured on its own snapshots: a deliberate hand close to the lens is
    ~400 px tall in the 1280x720 frame, a hand reaching for a jar on the
    shelf ~100 px. MediaPipe's palm detector sees the whole frame at a fixed
    192 px input, so what decides detection is the hand's size RELATIVE to
    the frame. Shrinking the frame into a black canvas of the same size
    shrinks every hand by the same factor: the far ones fall under the
    detector's smallest anchor, the near ones stay well above it.
    100 = frame untouched (the old behaviour).

    2026-10-05: the scale could not hold the line — see PalmGate, which now
    owns "only near hands", and reads `min_px` from this same poll.
    """

    SPEC = {
        "scale": "input_number.gestus_haand_skala_pct",
        "min_px": "input_number.gestus_min_haand_px",
    }


def shrink_frame(jpeg, scale):
    """The same frame, `scale` of its size, centred on black. None on failure."""
    if cv2 is None:
        return None
    img = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return None
    height, width = img.shape[:2]
    small_w, small_h = max(1, int(width * scale)), max(1, int(height * scale))
    small = cv2.resize(img, (small_w, small_h), interpolation=cv2.INTER_AREA)
    canvas = np.zeros_like(img)
    top, left = (height - small_h) // 2, (width - small_w) // 2
    canvas[top : top + small_h, left : left + small_w] = small
    ok, out = cv2.imencode(".jpg", canvas, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return out.tobytes() if ok else None


def palm_anchors():
    """MediaPipe's SSD anchor centres for the 192 px palm detector.

    24x24 cells with 2 anchors each (stride 8), then 12x12 with 6 (the three
    stride-16 layers merged), all fixed-size, so a centre is all an anchor is.
    Generated rather than pasted: checked against the 2016-row table in
    opencv_zoo's mp_palmdet.py, largest difference 7e-8.
    """
    rows = []
    for grid, per_cell in ((24, 2), (12, 6)):
        for y in range(grid):
            for x in range(grid):
                rows.extend([((x + 0.5) / grid, (y + 0.5) / grid)] * per_cell)
    return np.array(rows, dtype=np.float32)


class PalmGate:
    """Smears out every hand too small to be a deliberate gesture, before the
    hand add-on sees the frame.

    2026-10-05 (user: "tapo registrerer igen finger gestures på alt for lang
    afstand … utilsigtet på 1.5m afstand"). Three timers fired from one left
    hand at the counter, and the add-on's own log shows why neither old guard
    could have stopped them: the far hand read `four_fingers` for SIX frames in
    a row (ec:09:9b-6a:c0:11, score 0.90-0.94, palm toward the lens), so no
    hold requirement separates it from a deliberate one, and the frame scale
    (HandTunables) cannot either — on 28/9 a fist at 50 cm needed the full
    frame to be seen at all (3/14 frames), while an open hand at 1.5 m is the
    easiest thing the palm detector finds. What decides detection there is the
    hand's SHAPE; only its SIZE says how far away it is.

    So the size is measured directly, with the add-on's own first stage: the
    very palm_detection_full.tflite that mediapipe 0.10.14 ships (same
    sha256), run on the same whole frame, letterboxed to the same 192 px with
    the same [0,1] range and zero border. Not opencv_zoo's ONNX: that one is
    the LITE model, and on the real kitchen frame it missed 30 of the 61
    palms under 50 px that the add-on's full model finds — the far ones, the
    exact population this gate exists for. A palm box is ~1.1x the wrist to
    middle-knuckle length for a fist and an open hand alike, which is what
    the scale lacked. A palm whose box is narrower than `min_px` is far; as
    soon as one is found, the add-on sees ONLY the near hands' ROIs (2.6x the
    box, pushed half a box toward the fingers — MediaPipe's own hand ROI) and
    a flat grey everywhere else; a frame with only far palms goes out grey
    (see `_only_near`). Hiding just the far hand failed twice.

    It fails OPEN, on purpose. Same model, same input, and a score floor
    below the add-on's 0.5: a far palm the add-on would see is found here
    first and masked. A missing model, a decode error or `min_px` 0 all mean
    the old frame — a gate that breaks must not cost the near fist too.
    """

    SCORE_MIN = 0.3
    NMS = 0.3
    INPUT = 192
    ROI_SCALE = 2.6
    ROI_SHIFT = 0.5
    # Feathered edge around the near ROIs that survive (0.16.2). Must stay odd.
    FEATHER = 31
    GREY = 128
    # A long cooking session at 1 fps; the file is the calibration table, so it
    # outlives the add-on log (which rotates within hours).
    LOG_MAX_BYTES = 4_000_000

    def __init__(self, log_path=None, keep=300):
        self._net = None
        self._anchors = None
        self._broken = False
        self._lock = threading.Lock()
        self._recent = deque(maxlen=keep)
        self._log_path = log_path
        self.frames = self.with_palms = self.masked_frames = 0

    def _ready(self):
        if self._net is not None:
            return True
        if self._broken or cv2 is None:
            return False
        try:
            self._net = cv2.dnn.readNetFromTFLite(PALM_PATH)
            self._anchors = palm_anchors()
        except Exception as err:  # cv2.error, or an OpenCV without the TFLite importer
            log.error("could not load the palm model, hands go through unmeasured: %s", err)
            self._broken = True
            return False
        return True

    def palms(self, img):
        """Palms in `img`: box width/height, wrist->middle-knuckle length, score
        and the 4 corners of the hand ROI, all in the frame's own pixels."""
        height, width = img.shape[:2]
        ratio = self.INPUT / max(height, width)
        rw, rh = int(width * ratio), int(height * ratio)
        left, top = (self.INPUT - rw) // 2, (self.INPUT - rh) // 2
        blob = cv2.copyMakeBorder(
            cv2.resize(img, (rw, rh)),
            top,
            self.INPUT - rh - top,
            left,
            self.INPUT - rw - left,
            cv2.BORDER_CONSTANT,
            value=(0, 0, 0),
        )
        blob = cv2.cvtColor(blob, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        # OpenCV's TFLite importer wants NCHW even though the model is NHWC;
        # handed NHWC it dies on a convolution assertion (OpenCV 4.10).
        with self._lock:
            self._net.setInput(blob[np.newaxis].transpose(0, 3, 1, 2).copy())
            outs = self._net.forward(self._net.getUnconnectedOutLayersNames())
        # Two outputs, regressors (.., 18) and scores (.., 1); told apart by
        # shape so a reordered export cannot swap them silently.
        reg, raw = (outs[0], outs[1]) if outs[0].shape[-1] == 18 else (outs[1], outs[0])
        reg, raw = reg.reshape(-1, 18), raw.reshape(-1).astype(np.float64)
        score = 1.0 / (1.0 + np.exp(-np.clip(raw, -60, 60)))
        keep = np.flatnonzero(score >= self.SCORE_MIN)
        if keep.size == 0:
            return []
        scale = float(max(height, width))
        pad = np.array([left, top], dtype=np.float32) / ratio
        centre = (reg[keep, 0:2] / self.INPUT + self._anchors[keep]) * scale - pad
        size = reg[keep, 2:4] / self.INPUT * scale
        boxes = [
            [float(cx - w / 2), float(cy - h / 2), float(w), float(h)]
            for (cx, cy), (w, h) in zip(centre, size)
        ]
        picked = cv2.dnn.NMSBoxes(boxes, score[keep].tolist(), self.SCORE_MIN, self.NMS)
        found = []
        for i in np.array(picked).reshape(-1):
            row = keep[i]
            cx, cy = centre[i]
            w, h = size[i]
            # Keypoint 0 is the wrist, 2 the middle-finger knuckle — the pair
            # MediaPipe itself turns into the hand's rotation.
            kps = (reg[row, 4:].reshape(7, 2) / self.INPUT + self._anchors[row]) * scale - pad
            ux, uy = kps[2] - kps[0]
            norm = math.hypot(ux, uy) or 1.0
            ux, uy = ux / norm, uy / norm
            side = self.ROI_SCALE * max(w, h)
            rx, ry = cx + self.ROI_SHIFT * h * ux, cy + self.ROI_SHIFT * h * uy
            corners = [
                (rx + (a * ux - b * uy) * side / 2, ry + (a * uy + b * ux) * side / 2)
                for a, b in ((-1, -1), (-1, 1), (1, 1), (1, -1))
            ]
            found.append(
                {
                    "px": round(float(max(w, h)), 1),
                    "len": round(float(norm), 1),
                    "score": round(float(score[row]), 3),
                    "x": int(cx),
                    "y": int(cy),
                    "roi": np.array(corners, dtype=np.int32),
                }
            )
        return found

    def apply(self, jpeg, min_px, camera):
        """`jpeg` reduced to its near hands whenever a palm under `min_px`
        is in it; the original bytes whenever nothing was masked or anything
        went wrong."""
        if min_px <= 0 or not self._ready():
            return jpeg
        try:
            img = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                return jpeg
            found = self.palms(img)
        except Exception as err:  # fail open: any surprise means the old frame
            log.warning("[%s] palm pass failed, frame served as is: %s", camera, err)
            return jpeg
        self.frames += 1
        if not found:
            return jpeg
        self.with_palms += 1
        for palm in found:
            palm["masked"] = palm["px"] < min_px
        self._note(camera, min_px, found)
        if not any(p["masked"] for p in found):
            return jpeg
        keep = np.zeros(img.shape[:2], dtype=np.uint8)
        for palm in found:
            if not palm["masked"]:
                cv2.fillConvexPoly(keep, palm["roi"], 255)
        img = self._only_near(img, keep)
        ok, out = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
        if not ok:
            return jpeg
        self.masked_frames += 1
        return out.tobytes()

    def _only_near(self, img, keep):
        """`img` with everything outside `keep` (the near hands' ROIs) flat
        grey, faded in over a soft edge; all grey when there is no near hand.

        0.16.2 — hiding only the far hand failed twice. Black (0.16.0): the
        knife rack, masked in every frame as a 60 px palm, came back from the
        add-on as `four_fingers` (2026-10-15 20:42). A ~90 px blur (0.16.1):
        a far hand at ~2 m (51 px palm, masked in all 7 frames of the burst)
        came back as `four_fingers` at 0.90-0.99, upright, 2026-10-16 06:26 —
        another 4-minute timer. Whatever the add-on finds in a masked region,
        it cannot find it in pixels that are not there. The near hand keeps
        MediaPipe's own ROI, which is all its landmark stage reads; frames
        with no far palm (incl. no palm at all) are never touched.
        """
        if not keep.any():
            return np.full_like(img, self.GREY)
        soft = cv2.GaussianBlur(keep.astype(np.float32) / 255.0, (self.FEATHER, self.FEATHER), 0)
        a = np.clip(soft * 1.6, 0.0, 1.0)[..., None]
        return (img * a + self.GREY * (1.0 - a)).astype(np.uint8)

    def _note(self, camera, min_px, found):
        stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
        rows = [[p["px"], p["len"], p["score"], p["x"], p["y"], int(p["masked"])] for p in found]
        for row in rows:
            self._recent.append(
                {
                    "t": stamp[11:],
                    "px": row[0],
                    "len": row[1],
                    "score": row[2],
                    "x": row[3],
                    "y": row[4],
                    "maskeret": bool(row[5]),
                }
            )
        if not self._log_path:
            return
        try:
            os.makedirs(os.path.dirname(self._log_path), exist_ok=True)
            if (
                os.path.exists(self._log_path)
                and os.path.getsize(self._log_path) > self.LOG_MAX_BYTES
            ):
                os.replace(self._log_path, self._log_path + ".1")
            with open(self._log_path, "a") as out:
                out.write(
                    json.dumps({"t": stamp, "cam": camera, "min": min_px, "palms": rows}) + "\n"
                )
        except OSError as err:
            log.warning("[%s] could not log palms: %s", camera, err)

    def snapshot(self, min_px):
        return {
            "min_px": min_px,
            "frames": self.frames,
            "med_haand": self.with_palms,
            "maskeret": self.masked_frames,
            "seneste": list(self._recent)[-60:],
        }


class GazeWatcher:
    """A face looking into the lens arms the microphone, exactly as a hand does.

    Measured 2026-09-18 on this camera's own sub-stream: faces ARE in frame —
    15 of 25 sampled frames, boxes 100-160 px wide — which refutes the note
    this feature was first rejected on. What does not work is head POSE:
    solvePnP on YuNet's five landmarks cannot separate "looking up at the
    camera" from "looking down at the counter", because the camera hangs high
    and both are yaw-symmetric. Four geometric formulations were tried on
    labelled frames and all four overlapped.

    A gaze model separates them. MobileGaze (mobileone_s0, Gaze360-trained), on
    27 labelled "looking in" and 48 "looking away" frames of the user himself —
    14 and 9 of which held a face wide enough to measure:
    looking in 4.4-17.0 degrees off the optical axis, looking away 31.2-46.0, a
    14.2 degree gap. Two details are load-bearing, not polish — a single pass
    without the mirrored second one does not separate at all, and without the
    three-frame median one blink frame (closed eyelids read as a downward gaze,
    31.1 deg) lands inside the other set.

    THE GAP IS NOT WHERE THAT MEASUREMENT SAID IT WAS. The threshold was first
    set to 24 deg, halfway between the two labelled sets, and the first evening
    in production armed ten times in 95 minutes while nobody was looking. The
    labelled negative set was a single POSE — looking down at the counter — and
    it lands far out at 31-46. Ordinary movement around the kitchen fills the
    20-31 band that the set never sampled: production ambient measured
    20.7-40.2, median 23.8, and never once went below 20.7. A deliberate look
    measured 15.4. The threshold therefore belongs just above the looking-in
    range and far below ambient, not between two hand-picked poses: 16 deg.

    The lesson generalises past this feature. A negative class you POSE for the
    camera is the easy half of the real one, so the gap you measure is wider
    than the gap you get. Signature: every false positive clusters just under
    the threshold instead of scattering.

    Every median is logged at CAL_EVERY seconds precisely so the next person to
    move this number has the ambient distribution, not a posed one.

    The median runs over CONSECUTIVE detections, so a face seen once cannot pair
    up with one from minutes later.

    It writes the same epoch stamp into the same input_text the hand gesture
    writes (#2): ArmGate, the window and consume() then apply unchanged, and
    "one deliberate signal, one command" stays one rule with two ways in.

    LOOK WHILE SPEAKING (2026-10-03, user: "brugte lige mange forsøg på at få en
    timer igang"). The camera hangs ~30 cm above the user's head, so eye
    contact from the counter takes a tilted-back head (user's own words). On
    that day five phrases were dropped as unarmed in two minutes with the user
    standing close (face 111-142 px, score 0.85-0.93, frontal <= 0.2 — every
    other gate passed) and the three-frame median read 29.4, 27.6, 24.3, 26.1,
    23.9, 25.8, 18.5, 25.5 before one 14.5 finally armed. Two days earlier the
    same kind of look read 6-10. A deliberate look up into this lens is
    therefore NOT reliably under 16, and lowering the face-score slider (also
    tried that day) cannot help: the face that armed scored 0.91.

    Loosening the look-first threshold would re-open the 2026-09-18 problem
    (false windows with nobody talking). A look that coincides with the words
    is a different, stronger signal: noise has to land on the allowlist AND a
    confident frontal face has to look up toward the lens in the same four
    seconds. So that path gets its own, looser limit (`tale`). Ambient medians
    of faces that passed the score/frontal gates, 23/09-03/10: 32.1-58.1.
    """

    # One frame a second is the cadence the separation was measured at, and a
    # frame costs ~255 ms of one core (YuNet 145 ms plus two gaze passes) — so
    # this only runs while the radar says somebody is in the room, per user-spec.
    PACE = 1.0
    # Longer than one missed detection, shorter than a walk out and back: past
    # this the buffered angles describe a different visit.
    STALE = 5.0
    # The recorder does not need a degree per second (#24). Arming always writes.
    PUSH_EVERY = 30
    PUSH_DELTA = 2.0
    # Calibration trail. The pushed sensor is force-written on every arming, so
    # its history over-represents angles that passed the gate and cannot answer
    # "how often is ambient near the threshold?" — the question that got this
    # wrong the first time. The log can.
    CAL_EVERY = 5.0
    # Look-while-speaking. A look usually starts before the first word, so the
    # frames that count reach this far back from it; with the shortest phrase
    # (0.9 s) and its closing silence that is ~3.4 s, three frames at PACE.
    TALK_PRE = 2.0
    # Two frames under the limit, not one: a single frame is where the noise
    # lives (a blink alone reads 31 deg), and two is what a 3-frame median
    # demands of the look-first path as well.
    TALK_FRAMES = 2
    # Comfortably longer than the longest phrase (4 s) plus TALK_PRE.
    SEEN_KEEP = 15.0

    def __init__(self, name, grabber, gate, presence, voice_gate, switch, arm_entity, tunables):
        self.name = name
        self._grabber = grabber
        self._gate = gate
        self._presence = presence
        self._voice = voice_gate
        self._switch = switch
        self._arm_entity = arm_entity
        self._tune = tunables
        self._entity = f"sensor.{name}_kamera_blik"
        self._angles = deque(maxlen=8)
        self._last_face = -999.0
        self._cool_until = 0.0
        self._armed_at = 0
        self._armings = 0
        self._pushed = -999.0
        self._logged = -999.0
        self._pushed_val = -999.0
        self._det = None
        self._gaze = None
        self._complained = False
        self._feat_logged = -999.0
        self._last_feat = (0, 0.0, 0.0)
        # Every gated frame as (wall time, angle, w, score, frontal), for
        # heard_while_looking — which runs on the audio thread, hence the lock.
        self._seen = deque()
        self._seen_lock = threading.Lock()
        self._talk_armings = 0

    # -- model plumbing ----------------------------------------------------
    def _load(self):
        if self._gaze is not None:
            return True
        if cv2 is None:
            if not self._complained:
                log.error("[%s] opencv is missing — gaze arming stays off", self.name)
                self._complained = True
            return False
        try:
            det = cv2.FaceDetectorYN.create(YUNET_PATH, "", (320, 320), score_threshold=0.5)
            gaze = cv2.dnn.readNetFromONNX(GAZE_PATH)
        except cv2.error as err:
            if not self._complained:
                log.error("[%s] could not load the gaze models: %s", self.name, err)
                self._complained = True
            return False
        self._names = gaze.getUnconnectedOutLayersNames()
        self._idx = np.arange(GAZE_BINS, dtype=np.float32)
        self._mean = np.array(GAZE_MEAN, dtype=np.float32)
        self._std = np.array(GAZE_STD, dtype=np.float32)
        self._det, self._gaze = det, gaze
        log.info("[%s] gaze models loaded", self.name)
        return True

    @staticmethod
    def frontal(face):
        """How far the nose sits from the midpoint of the eyes, in eye-widths.

        YuNet row: x y w h, right eye, left eye, nose, right mouth, left mouth
        (x, y each), score. A face turned toward the lens has its nose between
        its eyes (~0); a profile pushes it toward one eye (0.5+). This is the
        horizontal axis only — the one solvePnP could not get wrong: the high
        camera makes up/down ambiguous (see the class docstring), not left/right.
        A misdetection on the back of a head or on a pattern also tends to put
        its "landmarks" somewhere other than a symmetric face would.
        """
        rx, lx, nx = float(face[4]), float(face[6]), float(face[8])
        eyes = abs(lx - rx)
        if eyes < 1.0:
            return 9.9
        return abs(nx - (rx + lx) / 2.0) / eyes

    def _face(self, img):
        """The widest face big enough, sure enough and frontal enough, or None."""
        height, width = img.shape[:2]
        self._det.setInputSize((width, height))
        _, faces = self._det.detect(img)
        if faces is None:
            return None
        score_min = self._tune.get("score_min") / 100.0
        frontal_max = self._tune.get("frontal_max") / 100.0
        best = None
        for face in faces:
            if float(face[2]) < GAZE_MIN_FACE:
                continue
            score, sym = float(face[14]), self.frontal(face)
            now = time.monotonic()
            if now - self._feat_logged >= self.CAL_EVERY:
                self._feat_logged = now
                log.info(
                    "[%s] gaze face w=%d score=%.2f frontal=%.2f",
                    self.name,
                    int(face[2]),
                    score,
                    sym,
                )
            if score < score_min or sym > frontal_max:
                continue
            if best is None or float(face[2]) > float(best[2]):
                best = face
        if best is not None:
            self._last_feat = (int(best[2]), float(best[14]), self.frontal(best))
        return best

    def _vector(self, crop, flip):
        """One forward pass, as a unit gaze direction in camera coordinates."""
        img = cv2.flip(crop, 1) if flip else crop
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = cv2.resize(img, (448, 448)).astype(np.float32) / 255.0
        img = (img - self._mean) / self._std
        self._gaze.setInput(np.transpose(img, (2, 0, 1))[None, ...].astype(np.float32))
        out = dict(zip(self._names, self._gaze.forward(self._names)))
        pitch = self._expect(out["pitch"])
        yaw = self._expect(out["yaw"])
        if flip:
            # The mirrored crop is a mirrored person; only the yaw flips sign.
            yaw = -yaw
        rad_p, rad_y = math.radians(pitch), math.radians(yaw)
        return np.array(
            [
                -math.cos(rad_p) * math.sin(rad_y),
                -math.sin(rad_p),
                -math.cos(rad_p) * math.cos(rad_y),
            ]
        )

    def _angle(self, img, face):
        """Degrees between this face's gaze and the lens, or None.

        Two passes, the second on the mirrored crop with its yaw negated, and
        the vectors summed. That is not an ensemble for its own sake: a single
        pass does not separate the two labelled sets at all, because the model
        carries a left/right bias that the mirror cancels.
        """
        width, height = float(face[2]), float(face[3])
        left, top = float(face[0]), float(face[1])
        crop = img[
            int(max(0, top)) : int(min(img.shape[0], top + height)),
            int(max(0, left)) : int(min(img.shape[1], left + width)),
        ]
        if crop.size == 0:
            return None
        vector = self._vector(crop, False) + self._vector(crop, True)
        return math.degrees(
            math.acos(max(-1.0, min(1.0, -float(vector[2]) / float(np.linalg.norm(vector)))))
        )

    def _expect(self, logits):
        """The model answers in 90 four-degree bins; take their expectation."""
        exp = np.exp(logits - logits.max(axis=1, keepdims=True))
        probs = exp / exp.sum(axis=1, keepdims=True)
        return float((probs * self._idx).sum(1)[0] * GAZE_BINW - GAZE_OFFSET)

    # -- the loop ----------------------------------------------------------
    def wanted(self):
        if self._gate.banned():
            return False
        if not self._switch.enabled():
            return False
        # Arming a microphone that is not listening is work for nobody.
        if not self._voice.enabled():
            return False
        # user-spec 2026-09-18: only while the radar reports a body. An empty
        # presence_entity therefore means no gaze detection at all, which is the
        # right way round — this opens a microphone.
        return self._presence.occupied()

    def supervise(self):
        while True:
            try:
                self._tick()
            except Exception:  # noqa: BLE001 - a bad frame must not end the thread
                log.exception("[%s] gaze detection failed", self.name)
                time.sleep(5)

    def _tick(self):
        if not self.wanted():
            self._angles.clear()
            # Also what makes the kill switches hold for the look-while-
            # speaking path (#21): with no frames, it cannot arm.
            with self._seen_lock:
                self._seen.clear()
            time.sleep(2)
            return
        if not self._load():
            time.sleep(60)
            return
        started = time.monotonic()
        grabbed = time.time()
        frame = self._grabber.get(5)
        if frame is None:
            time.sleep(2)
            return
        img = cv2.imdecode(np.frombuffer(frame, np.uint8), cv2.IMREAD_COLOR)
        face = None if img is None else self._face(img)
        now = time.monotonic()
        if now - self._last_face > self.STALE:
            self._angles.clear()
        if face is None:
            self._pace(started)
            return
        self._last_face = now
        angle = self._angle(img, face)
        if angle is None:
            self._pace(started)
            return
        self._angles.append(angle)
        w, score, sym = self._last_feat
        with self._seen_lock:
            self._seen.append((grabbed, angle, w, score, sym))
            while self._seen and grabbed - self._seen[0][0] > self.SEEN_KEEP:
                self._seen.popleft()

        need = max(1, int(self._tune.get("frames")))
        median = None
        if len(self._angles) >= need:
            window = sorted(list(self._angles)[-need:])
            median = window[len(window) // 2]
        if median is not None and now - self._logged >= self.CAL_EVERY:
            self._logged = now
            log.info("[%s] gaze cal %.1f deg", self.name, median)
        if median is not None and median <= self._tune.get("taersk"):
            if now >= self._cool_until:
                self._arm(median)
        self._publish(median)
        self._pace(started)

    def _pace(self, started):
        time.sleep(max(0.0, self.PACE - (time.monotonic() - started)))

    def _arm(self, median):
        stamp = int(time.time())
        if not call_service(
            "input_text", "set_value", {"entity_id": self._arm_entity, "value": str(stamp)}
        ):
            return
        # One look is one arming. The window doubles as the cooldown, so a cook
        # who happens to face the camera cannot hold the microphone open for as
        # long as he stands there — he gets one window, then has to look away
        # and back. The acknowledgement flash is HA's, on the stamp itself, so
        # both ways in are confirmed by the same light (#2).
        self._cool_until = time.monotonic() + self._tune.get("window")
        self._angles.clear()
        self._armed_at = stamp
        self._armings += 1
        w, score, sym = self._last_feat
        log.info(
            "[%s] gaze %.1f deg — microphone armed (face w=%d score=%.2f frontal=%.2f)",
            self.name,
            median,
            w,
            score,
            sym,
        )
        self._publish(median, force=True)

    def heard_while_looking(self, began, arm):
        """Arm for a phrase whose speaker looked up at the lens while saying it.

        Called by VoiceWatcher, on the audio thread, for a phrase that passed
        every other gate and was about to be dropped as unarmed. See the class
        docstring for why this path may use a looser angle than the look-first
        one. Arming here is the same arming as _arm(): the stamp goes into
        ArmGate at once (the phrase in hand needs it) and into HA, so the
        acknowledgement pulse, the window and the cooldown all behave as if the
        look had come first — and a phrase the recogniser came back empty on
        can simply be said again.
        """
        ended = time.time()
        with self._seen_lock:
            seen = [s for s in self._seen if began - self.TALK_PRE <= s[0] <= ended]
        # Faces first: most unarmed phrases have none, and the slider read
        # below can cost an HA round trip on this (audio) thread.
        if not seen:
            return False
        limit = self._tune.get("tale")
        if limit <= 0:
            return False
        angles = ", ".join(f"{s[1]:.1f}" for s in seen)
        hits = [s for s in seen if s[1] <= limit]
        if len(hits) < self.TALK_FRAMES:
            # The near misses are the calibration trail for `tale`: a face that
            # passed the score/frontal gates during speech, and how far off the
            # lens it read. Rare enough to log every one.
            log.info(
                "[%s] spoke facing the lens, not looking in: %s deg (limit %g, need %d)",
                self.name,
                angles,
                limit,
                self.TALK_FRAMES,
            )
            return False
        stamp = int(began)
        if arm.note(stamp):
            threading.Thread(
                target=call_service,
                daemon=True,
                args=(
                    "input_text",
                    "set_value",
                    {"entity_id": self._arm_entity, "value": str(stamp)},
                ),
            ).start()
        # One look, one window — the same cooldown _arm() sets, so the
        # look-first path does not arm a second time on the same look.
        self._cool_until = time.monotonic() + self._tune.get("window")
        self._angles.clear()
        self._armed_at = stamp
        self._armings += 1
        self._talk_armings += 1
        best = min(hits, key=lambda s: s[1])
        log.info(
            "[%s] look while speaking %s deg — microphone armed (face w=%d "
            "score=%.2f frontal=%.2f, limit %g)",
            self.name,
            angles,
            best[2],
            best[3],
            best[4],
            limit,
        )
        return True

    def _publish(self, median, force=False):
        if median is None:
            return
        now = time.monotonic()
        if not force and (
            now - self._pushed < self.PUSH_EVERY or abs(median - self._pushed_val) < self.PUSH_DELTA
        ):
            return
        self._pushed, self._pushed_val = now, median
        push_state(
            self._entity,
            round(median, 1),
            {
                "friendly_name": f"{self.name.title()} kamera — blikvinkel",
                "unit_of_measurement": "°",
                "icon": "mdi:eye-outline",
                "taerskel": self._tune.get("taersk"),
                "frames": int(self._tune.get("frames")),
                "armeringer": self._armings,
                "sidst_armeret": self._armed_at,
                "kilde": "gesture_frame_shim",
            },
        )

    def snapshot(self):
        return {
            "kigger": self.wanted(),
            "vinkler": [round(a, 1) for a in self._angles],
            "armeringer": self._armings,
            "heraf_mens_tale": self._talk_armings,
            "sidst_armeret": self._armed_at,
            "taerskel": self._tune.get("taersk"),
            "tale_taerskel": self._tune.get("tale"),
            "frames": int(self._tune.get("frames")),
            "vindue": self._tune.get("window"),
            "cooldown_tilbage": round(max(0.0, self._cool_until - time.monotonic()), 1),
        }


class VoiceWatcher:
    """Turns the camera's audio track into a small set of allow-listed commands.

    Three measurements shape this, and all three are load-bearing:

    * The STT server returns an empty string for anything much longer than a
      sentence — 9 to 14 second windows recognised nothing at all, with the
      phrase sitting plainly in the middle. Cutting utterances out is therefore
      a precondition, not a refinement.
    * Transcribing every candidate region costs more than the audio took to
      record: 21 regions in 45 s of kitchen cost 51 s of STT, so a naive design
      falls behind for ever and never catches up. The cheap filter in front is
      what makes the feature possible at all.
    * Speech and kitchen noise separate cleanly on zero-crossing rate. Over
      150 s of an empty kitchen (76 regions) against six known commands, all
      six sat at or below 95 crossings per 30 ms frame and every noise region in
      the same duration band sat at or above 118. The threshold is put at 110
      rather than in the middle of that gap on purpose: a missed command is
      something the user notices and retries, while noise slipping through
      costs only CPU, since the allowlist still refuses to act on it.

    All six numbers above are live sliders since 2026-09-16 (Tapo dashboard,
    packages/tapo_tuning.yaml); the add-on options are the floor they start
    from. The measurements stay the justification for the defaults — a slider
    makes a value easy to nudge, it does not make the measurement optional.

    HA remains the authority. This class pushes what it heard and nothing else;
    the kill switch and the mode gates live in the automation that reads it.
    """

    def __init__(
        self,
        name,
        host,
        port,
        threshold,
        zcr_max,
        min_utt,
        max_utt,
        cooldown,
        gate,
        body_window=60,
        arm_window=12,
        live_tuning=False,
    ):
        self.name = name
        self.body_seen = None
        # Assigned from main() the same way body_seen is, so the offline rigs
        # keep a constructor they can call without knowing about HA at all.
        # None means "no arming required", which is what those rigs need.
        self.arm = None
        # GazeWatcher.heard_while_looking, when the camera runs gaze arming:
        # the second chance for a phrase that arrived before its look armed.
        self.look = None
        self._host = host
        self._port = port
        self._gate = gate
        self._entity = f"sensor.{name}_stemme_kommando"
        # The six numbers passed in are the add-on options, and they are the
        # floor — the sliders on the Tapo dashboard override them while the
        # add-on runs. Constructor signature is unchanged on purpose so the
        # offline rigs keep working; they pass live_tuning=False.
        #
        # body_window is the odd one out and needs its own note. Nobody in shot,
        # nobody talking: measured 2026-09-16, an empty kitchen transcribed
        # 'timer eight minute' — a complete command, from clatter alone, with
        # the room unoccupied for eleven minutes. The recogniser has no
        # confidence score to reject it with (the transcript event carries text
        # and nothing else), so the rejection has to come from a different
        # instrument. Across all four reference recordings the body detector
        # separates them perfectly: every real command had a body in frame
        # within ten seconds, and both silent stretches had none for minutes.
        self._tun = Tunables(
            {
                "threshold": threshold,
                "zcr_max": zcr_max,
                "min_utt": min_utt,
                "max_utt": max_utt,
                "cooldown": cooldown,
                "body_window": body_window,
                "arm_window": arm_window,
            },
            live=live_tuning,
        )

        self._pad_frames = int(VOICE_PAD_S * 1000 / VOICE_FRAME_MS)
        self._carry_frames = int(VOICE_CARRY_S * 1000 / VOICE_FRAME_MS)
        self._gap_frames = int(VOICE_GAP_S * 1000 / VOICE_FRAME_MS)
        self._lead = deque(maxlen=self._pad_frames)
        self._cur = None
        self._buf = b""

        self._sock = None
        self._file = None
        self._last_fire = {}
        self._cond = threading.Condition()
        # A busy kitchen produces regions faster than STT can answer, and the
        # first version simply dropped whatever no longer fit — which cost two
        # of three spoken commands in the reference recording, because clatter
        # had taken the worker's turn. Regions are therefore thrown away by AGE
        # when they come up, not blindly on arrival: a stale one costs nothing
        # to skip, and acting on a command from six seconds ago would be worse
        # than missing it anyway.
        self._queue = deque(maxlen=3)
        self._stats = {
            "regions": 0,
            "sent": 0,
            "dropped": 0,
            "stale": 0,
            "short": 0,
            "long": 0,
            "silent": 0,
            "noisy": 0,
            "no_body": 0,
            "unarmed": 0,
            "hits": 0,
            "last": None,
            "last_ms": 0,
        }
        # A count says how many were thrown away; it never says whether the one
        # that mattered was among them. A spoken command that vanishes leaves no
        # other trace, so each rejection keeps its measurements — the near misses
        # are what tell a badly cut phrase from a genuinely closed gate.
        self._rejects = deque(maxlen=15)
        # Set from main(); the rigs never write clips.
        self.save_clips = False
        self._clips = 0
        # Calibration mode (GET /kalibrer?min=N): every region of speech length
        # is transcribed and kept, with no look, body or zcr gate — and nothing
        # is pushed, so a session of thirty phrases cannot start one timer. It
        # expires by itself; a forgotten session must not leave the kitchen
        # recorded. AirBnB still stops the stream underneath it (GuestModeGate).
        self._calib_until = 0.0

    def calibrate(self, minutes):
        self._calib_until = time.monotonic() + max(0.0, minutes) * 60
        log.info(
            "[%s] calibration %s", self.name, f"on for {minutes:g} min" if minutes > 0 else "off"
        )

    def calibrating(self):
        return time.monotonic() < self._calib_until

    # Read on every use rather than cached in __init__, so moving a slider
    # takes effect on the next utterance instead of the next add-on restart.
    # Tunables does the caching; a get() is a dict lookup between polls.
    @property
    def _threshold(self):
        return self._tun.get("threshold")

    @property
    def _zcr_max(self):
        return self._tun.get("zcr_max")

    @property
    def _cooldown(self):
        return self._tun.get("cooldown")

    @property
    def _body_window(self):
        return self._tun.get("body_window")

    @property
    def _arm_window(self):
        return self._tun.get("arm_window")

    @property
    def _min_frames(self):
        return int(self._tun.get("min_utt") * 1000 / VOICE_FRAME_MS)

    @property
    def _max_frames(self):
        return int(self._tun.get("max_utt") * 1000 / VOICE_FRAME_MS)

    def snapshot(self):
        out = dict(self._stats)
        out["enabled"] = self._gate.enabled()
        out["queued"] = len(self._queue)
        out["body_ok"] = self.body_seen is None or self.body_seen(self._body_window)
        out["afvist"] = list(self._rejects)
        out["klip_gemt"] = self._clips
        out["kalibrering_sek_tilbage"] = max(0, round(self._calib_until - time.monotonic()))
        # Without this, a user who says a command into a closed window sees
        # nothing but silence — the same symptom as a broken microphone.
        out["arm"] = None if self.arm is None else self.arm.snapshot(self._arm_window)
        # The whole live tuning, not just the two that used to be here. When a
        # threshold is adjustable the diagnostics have to say which value was
        # actually in force, or a report of "it stopped hearing me" cannot be
        # told from a slider someone moved.
        out["tuning"] = self._tun.snapshot()
        out["zcr_max"] = self._zcr_max
        out["body_window"] = self._body_window
        return out

    def _reject(self, reason, seconds, zcr):
        self._stats[reason] += 1
        self._rejects.append(
            {"t": time.strftime("%H:%M:%S"), "grund": reason, "sek": round(seconds, 2), "zcr": zcr}
        )

    def _save_clip(self, pcm, began, tag):
        """Keep one region as a WAV next to what became of it.

        The filename carries the verdict so a directory listing is already the
        calibration table; scripts/stemme_replay.py re-sends them to the STT.
        """
        if not self.save_clips:
            return
        try:
            os.makedirs(VOICE_CLIP_DIR, exist_ok=True)
            safe = "".join(c if c.isalnum() else "-" for c in tag.lower())[:60]
            stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(began))
            path = os.path.join(VOICE_CLIP_DIR, f"{stamp}_{self.name}_{safe}.wav")
            with wave.open(path, "wb") as out:
                out.setnchannels(1)
                out.setsampwidth(2)
                out.setframerate(VOICE_RATE)
                out.writeframes(pcm)
            self._clips += 1
            names = sorted(n for n in os.listdir(VOICE_CLIP_DIR) if n.endswith(".wav"))
            for old in names[:-VOICE_CLIP_KEEP]:
                os.remove(os.path.join(VOICE_CLIP_DIR, old))
        except OSError as err:
            log.warning("[%s] could not save clip: %s", self.name, err)

    def _reject_armed(self, reason, seconds, zcr, frames, began):
        """A reject inside an open arming window is a near miss worth keeping.

        Outside the window these are clatter and stay uncounted beyond the
        stats; inside it they are the pieces a split phrase fell into.
        """
        self._reject(reason, seconds, zcr)
        if self.arm is None or not self.arm.armed(self._arm_window, began):
            return
        log.info("[%s] armed region rejected: %s (%.2fs, zcr %d)", self.name, reason, seconds, zcr)
        self._save_clip(b"".join(f for f, _, _ in frames), began, f"afvist-{reason}-{seconds:.2f}s")

    def start(self):
        threading.Thread(target=self._work, daemon=True).start()

    def reset(self):
        """Forget a half-captured utterance when the stream drops."""
        self._buf = b""
        self._cur = None
        self._lead.clear()

    # ---------------------------------------------------------------- capture

    def feed(self, chunk):
        self._buf += chunk
        while len(self._buf) >= VOICE_FRAME_BYTES:
            frame = self._buf[:VOICE_FRAME_BYTES]
            self._buf = self._buf[VOICE_FRAME_BYTES:]
            self._frame(frame)

    def _frame(self, frame):
        rms, db, crossings = frame_stats(frame)
        loud = db > self._threshold
        if self._cur is None:
            self._lead.append((frame, rms, crossings))
            if loud:
                # The lead-in is part of the utterance: a word's first consonant
                # is quieter than the threshold and cutting it off costs the
                # recogniser the start of the phrase.
                self._cur = [list(self._lead), 0, time.time()]
                self._lead.clear()
            return

        self._cur[0].append((frame, rms, crossings))
        self._cur[1] = 0 if loud else self._cur[1] + 1
        overlong = len(self._cur[0]) > self._max_frames + self._gap_frames
        if self._cur[1] > self._gap_frames or overlong:
            frames, silence, began = self._cur
            self._cur = None
            # Carry the tail over as the next utterance's lead-in. Starting the
            # buffer empty here cost a whole command: a phrase spoken within a
            # third of a second of the previous sound began mid-word, and the
            # recogniser returned nothing at all rather than something wrong.
            # Re-sending a little audio is free — the cooldown absorbs it.
            self._lead.clear()
            if self._carry_frames:
                self._lead.extend(frames[-self._carry_frames :])
            if overlong:
                # Continuous sound is a running tap or a conversation, not one of
                # three fixed phrases. Dropping it also bounds memory.
                return
            trim = max(0, silence - self._pad_frames)
            self._close(frames[: len(frames) - trim] if trim else frames, began)

    def _close(self, frames, began):
        self._stats["regions"] += 1
        seconds = len(frames) * VOICE_FRAME_MS / 1000.0
        if len(frames) < self._min_frames:
            self._reject_armed("short", seconds, -1, frames, began)
            return
        if len(frames) > self._max_frames:
            self._reject_armed("long", seconds, -1, frames, began)
            return
        voiced = sorted(c for _, rms, c in frames if rms >= VOICE_FEAT_MIN_RMS)
        if not voiced:
            self._reject("silent", seconds, -1)
            return
        zcr = voiced[len(voiced) // 2]
        if self.calibrating() and self._gate.enabled():
            self._enqueue(frames, zcr, began, calib=True)
            return
        if zcr > self._zcr_max:
            self._reject_armed("noisy", seconds, zcr, frames, began)
            return
        if self.body_seen is not None and not self.body_seen(self._body_window):
            self._reject_armed("no_body", seconds, zcr, frames, began)
            return
        # Checked HERE, before the audio is queued, so an unarmed kitchen costs
        # no transcription at all — which is most of the day. It is checked
        # AGAIN at firing time. Both measure the window to the first word, so
        # neither the phrase's length nor the queue can close it.
        #
        # 2026-10-03: before dropping it, ask whether the speaker looked up at
        # the lens WHILE saying it — that arms too (GazeWatcher docstring).
        # Last in the chain on purpose: zcr and body have already passed, so
        # this costs nothing for clatter or an empty room.
        if self.arm is not None and not self.arm.armed(self._arm_window, began):
            if self.look is None or not self.look(began, self.arm):
                self._reject("unarmed", seconds, zcr)
                return
        if not self._gate.enabled():
            return
        self._enqueue(frames, zcr, began)

    def _enqueue(self, frames, zcr, began, calib=False):
        pcm = b"".join(f for f, _, _ in frames)
        with self._cond:
            if len(self._queue) == self._queue.maxlen:
                self._stats["dropped"] += 1
            self._queue.append(
                (pcm, len(frames) * VOICE_FRAME_MS / 1000.0, zcr, time.monotonic(), began, calib)
            )
            self._cond.notify()

    # --------------------------------------------------------------- recognise

    def _work(self):
        while True:
            with self._cond:
                while not self._queue:
                    self._cond.wait()
                pcm, seconds, zcr, queued, began, calib = self._queue.popleft()
            if time.monotonic() - queued > VOICE_STALE_S and not calib:
                self._stats["stale"] += 1
                continue
            try:
                if calib:
                    self._handle_calib(pcm, seconds, zcr, began)
                else:
                    self._handle(pcm, seconds, zcr, began)
            except Exception:  # noqa: BLE001 - a bad utterance must not kill the thread
                log.exception("[%s] voice worker failed", self.name)

    def _handle_calib(self, pcm, seconds, zcr, began):
        started = time.monotonic()
        text = self._transcribe(pcm)
        elapsed = int((time.monotonic() - started) * 1000)
        log.info(
            "[%s] calibration heard %r (%.2fs, zcr %d, %d ms)",
            self.name,
            text,
            seconds,
            zcr,
            elapsed,
        )
        self._save_clip(pcm, began, f"kal-{text or 'tom'}-{seconds:.2f}s")

    def _handle(self, pcm, seconds, zcr, began):
        started = time.monotonic()
        text = self._transcribe(pcm)
        elapsed = int((time.monotonic() - started) * 1000)
        self._stats["sent"] += 1
        self._stats["last_ms"] = elapsed
        log.info("[%s] heard %r (%.2fs, zcr %d, %d ms)", self.name, text, seconds, zcr, elapsed)
        # Only armed regions reach the STT, so this is the whole armed trail.
        # An EMPTY answer is logged and kept too: on 2026-09-28 three of six
        # armed regions came back empty and left no trace at all.
        self._save_clip(pcm, began, f"{text or 'tom'}-{seconds:.2f}s")
        if not text:
            return
        parsed = parse_command(text)
        if parsed is None:
            return
        command, minutes = parsed
        now = time.monotonic()
        # One spoken phrase lands in several overlapping windows, so the same
        # command arrives more than once. Suppressing per command rather than
        # globally keeps "party time" from swallowing an "auto mode" said right
        # after it.
        if now - self._last_fire.get(command, -999) < self._cooldown:
            log.info("[%s] %s still in cooldown", self.name, command)
            return
        # The second half of the arming check, and the one that actually spends
        # the hand. Re-reading it here rather than trusting the check in
        # _close() matters because several noise regions can pass _close() on
        # the same raised hand — consume() lets only the first of them through.
        # One hand, one command.
        if self.arm is not None:
            if not self.arm.armed(self._arm_window, began):
                log.info("[%s] %s dropped — arming window closed", self.name, command)
                self._stats["unarmed"] += 1
                return
            self.arm.consume(self._arm_window, began)
        self._last_fire[command] = now
        self._stats["hits"] += 1
        self._stats["last"] = text
        push_state(
            self._entity,
            int(time.time()),
            {
                "friendly_name": f"{self.name.title()} — talt kommando",
                "kommando": command,
                "minutter": minutes,
                "tekst": text,
                "varighed": round(seconds, 2),
                "zcr": zcr,
                "kilde": "gesture_frame_shim",
            },
        )

    def _close_sock(self):
        for handle in (self._file, self._sock):
            try:
                if handle is not None:
                    handle.close()
            except OSError:
                pass
        self._file = self._sock = None

    def _transcribe(self, pcm):
        # Measured 2026-09-16: a fresh connection costs about 1.85 s for a 1.4 s
        # clip, a reused one about 1.15 s. The retry exists because the saved
        # 0.7 s is only worth having if a server restart cannot wedge us.
        for attempt in (1, 2):
            try:
                if self._sock is None:
                    self._sock = socket.create_connection((self._host, self._port), timeout=30)
                    self._file = self._sock.makefile("rb")
                return self._exchange(pcm)
            except (OSError, ValueError) as err:
                self._close_sock()
                if attempt == 2:
                    log.warning("[%s] STT unreachable: %s", self.name, err)
        return None

    def _send(self, kind, data=None, payload=None):
        event = {"type": kind, "data": data or {}}
        if payload:
            event["payload_length"] = len(payload)
        self._sock.sendall((json.dumps(event) + "\n").encode())
        if payload:
            self._sock.sendall(payload)

    def _exchange(self, pcm):
        audio = {"rate": VOICE_RATE, "width": 2, "channels": 1, "timestamp": 0}
        self._send("transcribe")
        self._send("audio-start", audio)
        step = VOICE_RATE * 2 // 10  # 100 ms
        stamp = 0
        for i in range(0, len(pcm), step):
            self._send("audio-chunk", dict(audio, timestamp=stamp), pcm[i : i + step])
            stamp += 100
        self._send("audio-stop", {"timestamp": stamp})
        while True:
            line = self._file.readline()
            if not line:
                raise OSError("STT closed the connection")
            event = json.loads(line)
            # A Wyoming header can carry a JSON block and a binary block, and
            # both have to be consumed or the next read starts mid-message.
            if event.get("data_length"):
                event["data"] = json.loads(self._file.read(event["data_length"]))
            if event.get("payload_length"):
                self._file.read(event["payload_length"])
            if event["type"] == "transcript":
                return event.get("data", {}).get("text", "")


class MotionWatcher:
    """Reports whether something at counter height or above is moving in frame.

    The kitchen radar sees the whole room, including a child running past below
    the camera's field of view; the camera sees only what reaches the frame. The
    gap between the two is the entire point of this signal, so it must not fire
    on light changes — the light chain hangs in shot, and a timer burst would
    otherwise look exactly like a person.
    """

    def __init__(
        self,
        name,
        url,
        idle_timeout,
        cell_delta,
        min_cells,
        hold,
        ignore_top,
        min_frames,
        max_shift,
        always,
        gate,
        voice=None,
    ):
        self.name = name
        self._url = url
        self._idle_timeout = idle_timeout
        self._always = always
        self._gate = gate
        self._voice = voice
        # The camera has a limited number of concurrent RTSP sessions and the
        # JPEG grabber already wants one, so the microphone rides along on this
        # process rather than opening its own. That ties the two together: an
        # output whose map matches nothing kills the entire process, video
        # included (measured — ffmpeg exits 234 and writes no frames). Two
        # consecutive quick failures are therefore read as "this stream has no
        # audio any more" and the body detector goes on without it.
        self._audio_fails = 0
        self._audio_blocked_until = 0.0
        # Kept separately from the published state, which goes off three seconds
        # after movement stops — a cook standing still at the counter is still
        # somebody who might speak.
        self._last_body = 0.0
        self._cell_delta = cell_delta
        self._min_cells = min_cells
        self._hold = hold
        self._min_frames = min_frames
        self._max_shift = max_shift
        # The light chain hangs across the top of the kitchen frame. Subtracting
        # the median cancels a relight spread over the whole frame, but not the
        # chain's own cells, which swing further than anything else in shot — so
        # a timer burst would read as a person. Bodies stand below it anyway.
        self._skip = ignore_top * GRID_W

        self._entity = f"binary_sensor.{name}_kamera_krop"
        # "The camera saw nobody" and "the camera was not looking" are the same
        # reading, and telling them apart is the whole basis of the child test.
        # last_changed cannot carry that (it resets on every HA restart), so the
        # detector writes its own clock and lets HA judge the freshness.
        self._beat_entity = f"sensor.{name}_kamera_vagt"
        self._beat = 0.0
        self._lock = threading.Lock()
        self._last_poke = 0.0
        self._last_progress = 0.0
        self._thread = None
        self._state = None
        # Only state CHANGES are pushed to HA, so the raw counts have nowhere to
        # be read from during calibration. Keeping the last two minutes here
        # makes the threshold measurable without writing 2 Hz into the recorder.
        self._recent = deque(maxlen=240)

    def seen_recently(self, seconds):
        return self._last_body > 0 and time.monotonic() - self._last_body <= seconds

    def snapshot(self):
        out = {
            "state": self._state,
            "min_celler": self._min_cells,
            "cell_delta": self._cell_delta,
            "hold": self._hold,
            "min_frames": self._min_frames,
            "max_shift": self._max_shift,
            "skip_celler": self._skip,
            "recent": list(self._recent),
        }
        if self._voice is not None:
            out["voice"] = self._voice.snapshot()
        return out

    def poke(self):
        """Ask for the detector on demand. Only matters with motion_always off,
        where the detector lives exactly as long as the JPEG stream."""
        self._last_poke = time.monotonic()

    def _publish(self, on, cells):
        if on == self._state:
            return
        self._state = on
        push_state(
            self._entity,
            "on" if on else "off",
            {
                "friendly_name": f"{self.name.title()} kamera — krop i billedet",
                "device_class": "motion",
                "celler": cells,
                "min_celler": self._min_cells,
                "kilde": "gesture_frame_shim",
            },
        )

    def _heartbeat(self, running):
        now = time.monotonic()
        if running and now - self._beat < BEAT_INTERVAL:
            return
        self._beat = now if running else 0.0
        if running and self._state is not None:
            # HA forgets pushed states on restart, and the detector only pushes
            # on change — so an empty kitchen would leave the sensor missing for
            # hours, which reads as "no body" to anyone who forgets #9. The beat
            # is the natural place to notice and put it back.
            if read_state(self._entity) != ("on" if self._state else "off"):
                published, self._state = self._state, None
                self._publish(published, -1)
        push_state(
            self._beat_entity,
            int(time.time()) if running else 0,
            {
                "friendly_name": f"{self.name.title()} kamera — vagt",
                "kilde": "gesture_frame_shim",
            },
        )

    def _hot_cells(self, prev, cur):
        """Cells whose content changed, ignoring how bright the room got.

        Measured 2026-09-14: a single timer burst lit 76 of 384 cells, because
        the chain floods the wall below it and not just its own row. Rescaling
        each frame to the other's overall brightness cancels that, since a lamp
        multiplies the whole picture while a body rearranges part of it.
        """
        p = prev[self._skip :]
        c = cur[self._skip :]
        total = sum(c)
        base = sum(p)
        if not total or not base:
            return 0
        # Rescaling cannot undo a relight: the chain floods the wall beside it
        # far harder than the wall across the room, so turning it on really is a
        # structural change. Measured 2026-09-14: a burst moved the frame mean
        # by tens of percent and lit up to 114 of 384 cells, while a body only
        # rearranges a patch. A frame pair straddling a relight is therefore not
        # evidence of anything, and saying so beats guessing.
        if abs(total - base) > self._max_shift * base:
            return -1
        k = base / total
        diffs = sorted(abs(a - b * k) for a, b in zip(p, c))
        median = diffs[len(diffs) // 2]
        return sum(1 for d in diffs if d - median >= self._cell_delta)

    def wanted(self):
        if self._gate.banned():
            return False
        if self._always:
            return True
        return time.monotonic() - self._last_poke <= self._idle_timeout

    def supervise(self):
        """Keep the detector alive whenever it is allowed to run.

        Tying the detector to the JPEG stream left it blind except during a
        gesture scan, which is useless for both consumers: a session has to
        start from a body walking in, and the child test needs the camera to
        have been watching at the moment the radar fired.
        """
        backoff = 2
        while True:
            if not self.wanted():
                self._heartbeat(False)
                self._publish(False, 0)
                time.sleep(2)
                continue
            started = time.monotonic()
            self._stream()
            backoff = 2 if time.monotonic() - started > 30 else min(backoff * 2, 60)
            time.sleep(backoff)

    def _audio_pump(self, handle):
        """Drain the audio pipe for as long as ffmpeg holds it open.

        This thread is not optional even when nobody is listening: the two
        outputs share one process, so a pipe that stops being read blocks the
        muxer and takes the video down with it.
        """
        try:
            while True:
                chunk = handle.read(VOICE_PUMP_BYTES)
                if not chunk:
                    return
                try:
                    self._voice.feed(chunk)
                except Exception:  # noqa: BLE001 - never stop draining
                    log.exception("[%s] voice capture failed", self.name)
        except OSError:
            return
        finally:
            try:
                handle.close()
            except OSError:
                pass

    def _stream(self):
        want_audio = self._voice is not None and time.monotonic() >= self._audio_blocked_until
        cmd = [
            "ffmpeg",
            "-nostdin",
            "-loglevel",
            "error",
            "-rtsp_transport",
            "tcp",
            "-i",
            self._url,
            "-map",
            "0:v:0",
            "-an",
            "-vf",
            f"fps={MOTION_FPS},scale={GRID_W}:{GRID_H}",
            "-pix_fmt",
            "gray",
            "-f",
            "rawvideo",
            "pipe:1",
        ]
        read_fd = write_fd = None
        if want_audio:
            read_fd, write_fd = os.pipe()
            cmd += [
                "-map",
                "0:a:0",
                "-vn",
                "-ac",
                "1",
                "-ar",
                str(VOICE_RATE),
                "-f",
                "s16le",
                f"pipe:{write_fd}",
            ]
        log.info(
            "[%s] starting motion detector%s", self.name, " with microphone" if want_audio else ""
        )
        self._last_progress = 0.0
        started = time.monotonic()
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                pass_fds=(write_fd,) if want_audio else (),
            )
        except OSError as err:
            log.error("[%s] could not start motion ffmpeg: %s", self.name, err)
            if want_audio:
                os.close(read_fd)
                os.close(write_fd)
            return

        if want_audio:
            # The parent's copy has to go, or the reader never sees EOF when
            # ffmpeg dies and the pump thread outlives the stream.
            os.close(write_fd)
            self._voice.reset()
            threading.Thread(
                target=self._audio_pump,
                args=(os.fdopen(read_fd, "rb", 0),),
                daemon=True,
            ).start()

        watch_stream(proc, started, lambda: self._last_progress, self.name)

        prev = None
        last_hot = 0.0
        run = 0
        try:
            while self.wanted():
                # rawvideo frames are fixed size, so a full read is exactly one.
                buf = proc.stdout.read(FRAME_BYTES)
                self._last_progress = time.monotonic()
                if len(buf) < FRAME_BYTES:
                    break
                self._heartbeat(True)

                if prev is not None:
                    cells = self._hot_cells(prev, buf)
                    self._recent.append(cells)
                    if cells < 0:
                        prev = buf
                        continue
                    # A blink is over in a frame or two; a person is not. This
                    # is the second guard against the chain, independent of the
                    # brightness maths, so neither has to be perfect alone.
                    run = run + 1 if cells >= self._min_cells else 0
                    if run >= self._min_frames:
                        last_hot = self._last_body = time.monotonic()
                        self._publish(True, cells)
                    elif time.monotonic() - last_hot > self._hold:
                        # A cook standing still makes no difference at all, so
                        # the hold is what separates "gone" from "not moving".
                        self._publish(False, cells)
                prev = buf
        finally:
            log.info("[%s] stopping motion detector", self.name)
            self._heartbeat(False)
            self._publish(False, 0)
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            if want_audio:
                self._audio_verdict(time.monotonic() - started)

    def _audio_verdict(self, ran_for):
        """Decide whether the audio output is what just killed the stream.

        A camera reboot also fails fast, so one failure proves nothing; and the
        answer is a timed retreat rather than a permanent one, because the
        alternative is a firmware blip silently costing the microphone until
        somebody thinks to restart the add-on.
        """
        if ran_for > 15:
            self._audio_fails = 0
            return
        self._audio_fails += 1
        if self._audio_fails < 2:
            return
        self._audio_fails = 0
        self._audio_blocked_until = time.monotonic() + AUDIO_RETRY_AFTER
        log.warning(
            "[%s] stream died twice within 15s with the microphone attached — "
            "continuing without it for %d min",
            self.name,
            AUDIO_RETRY_AFTER // 60,
        )


class Grabber:
    """Holds at most one ffmpeg process per camera and publishes its latest frame."""

    def __init__(self, name, url, fps, quality, idle_timeout):
        self.name = name
        self._url = url
        self._fps = fps
        self._quality = quality
        self._idle_timeout = idle_timeout
        # A gesture is transient, so a cached frame is only reusable for about two
        # frame intervals — beyond that, wait for a fresh one rather than serve the past.
        self._max_age = max(2.0 / fps, 0.4)

        self._cond = threading.Condition()
        self._frame = None
        self._frame_time = 0.0
        self._last_request = 0.0
        self._last_progress = 0.0
        self._thread = None

    def get(self, timeout):
        """Return the newest frame, starting the stream if it is not running."""
        deadline = time.monotonic() + timeout
        with self._cond:
            self._last_request = time.monotonic()
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, daemon=True)
                self._thread.start()

            # A frame older than the request is a leftover from a previous burst.
            while self._frame is None or self._frame_time < self._last_request - self._max_age:
                if not self._cond.wait(timeout=deadline - time.monotonic()):
                    return None
                if time.monotonic() > deadline:
                    return None
            return self._frame

    def _run(self):
        cmd = [
            "ffmpeg",
            "-nostdin",
            "-loglevel",
            "error",
            "-rtsp_transport",
            "tcp",
            "-i",
            self._url,
            "-an",
            "-vf",
            f"fps={self._fps}",
            "-q:v",
            str(self._quality),
            "-f",
            "mjpeg",
            "-",
        ]
        log.info("[%s] starting stream", self.name)
        self._last_progress = 0.0
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except OSError as err:
            log.error("[%s] could not start ffmpeg: %s", self.name, err)
            return

        watch_stream(proc, time.monotonic(), lambda: self._last_progress, self.name)

        buf = b""
        try:
            while True:
                with self._cond:
                    if time.monotonic() - self._last_request > self._idle_timeout:
                        log.info("[%s] idle, stopping stream", self.name)
                        break

                # read1, not read: read() blocks until the full buffer is filled,
                # which at low fps means waiting for several frames' worth of bytes.
                chunk = proc.stdout.read1(65536)
                self._last_progress = time.monotonic()
                if not chunk:
                    err = proc.stderr.read(2048).decode("utf-8", "replace").strip()
                    # The URL carries the camera password, so report only the reason.
                    log.error("[%s] stream ended: %s", self.name, err or "no output")
                    break

                buf += chunk
                # MJPEG is concatenated JPEGs; keep only the most recent complete one.
                end = buf.rfind(EOI)
                if end == -1:
                    continue
                start = buf.rfind(SOI, 0, end)
                if start != -1:
                    with self._cond:
                        self._frame = buf[start : end + 2]
                        self._frame_time = time.monotonic()
                        self._cond.notify_all()
                buf = buf[end + 2 :]
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    grabbers = {}
    watchers = {}
    gazers = {}
    hand_tune = None
    palm_gate = None
    read_timeout = 10

    def do_GET(self):
        path = self.path.split("?", 1)[0]

        if path in ("/health", "/"):
            body = json.dumps({"cameras": sorted(self.grabbers)}).encode()
            self._send(200, "application/json", body)
            return

        if path == "/motion":
            # Polling this keeps the stream warm, which is what calibration needs.
            for watcher in self.watchers.values():
                watcher.poke()
            body = json.dumps({n: w.snapshot() for n, w in self.watchers.items()}).encode()
            self._send(200, "application/json", body)
            return

        if path == "/kalibrer":
            # GET /kalibrer?min=10 — min=0 stops it. Capped at 30 minutes.
            query = dict(
                p.split("=", 1) for p in (self.path.split("?", 1) + [""])[1].split("&") if "=" in p
            )
            try:
                minutes = min(30.0, float(query.get("min", "10")))
            except ValueError:
                minutes = 0.0
            for watcher in self.watchers.values():
                watcher.poke()
                if watcher._voice is not None:
                    watcher._voice.calibrate(minutes)
            self._send(200, "application/json", json.dumps({"min": minutes}).encode())
            return

        if path == "/gaze":
            # The sensor only carries the latest angle; the threshold is set off
            # the spread, so calibration needs the recent ones too.
            body = json.dumps({n: g.snapshot() for n, g in self.gazers.items()}).encode()
            self._send(200, "application/json", body)
            return

        if path == "/haand":
            # The palm sizes behind every mask, so the threshold is set off the
            # spread of real hands rather than a posed few.
            min_px = self.hand_tune.get("min_px") if self.hand_tune else 0
            body = json.dumps(self.palm_gate.snapshot(min_px) if self.palm_gate else {}).encode()
            self._send(200, "application/json", body)
            return

        parts = path.strip("/").split("/")
        # Looked up in a dict, so an unknown or crafted name can never reach ffmpeg.
        if len(parts) != 3 or parts[0] != "api" or parts[2] != "latest.jpg":
            self._send(404, "text/plain", b"not found")
            return

        grabber = self.grabbers.get(parts[1])
        if grabber is None:
            self._send(404, "text/plain", b"unknown camera")
            return

        watcher = self.watchers.get(parts[1])
        if watcher is not None:
            watcher.poke()

        frame = grabber.get(self.read_timeout)
        if frame is None:
            self._send(503, "text/plain", b"no frame available")
            return

        # Only this endpoint is masked and shrunk: motion, gaze and voice read
        # the grabber directly and keep the full frame. Masking comes first —
        # min_px is measured in the camera's own pixels, not the shrunk ones.
        if self.palm_gate is not None and self.hand_tune is not None:
            frame = self.palm_gate.apply(frame, self.hand_tune.get("min_px"), parts[1])
        scale = self.hand_tune.get("scale") / 100.0 if self.hand_tune else 1.0
        if scale < 0.995:
            frame = shrink_frame(frame, max(scale, 0.1)) or frame

        self._send(200, "image/jpeg", frame)

    def _send(self, status, content_type, body):
        # The fetcher gives up on its own timeout, so a closed socket here is
        # routine — left unhandled it buries the stream log in tracebacks.
        try:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            log.debug("client went away before the response was sent")

    def log_message(self, fmt, *args):
        log.debug("%s - %s", self.address_string(), fmt % args)


def main():
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    with open(os.environ.get("OPTIONS_PATH", "/data/options.json")) as handle:
        opts = json.load(handle)

    fps = opts.get("fps", 4)
    quality = opts.get("jpeg_quality", 5)
    idle_timeout = opts.get("idle_timeout", 30)
    motion = opts.get("motion", True)
    cell_delta = opts.get("motion_cell_delta", 12)
    min_cells = opts.get("motion_min_cells", 8)
    hold = opts.get("motion_hold", 3)
    ignore_top = opts.get("motion_ignore_top_rows", 6)
    min_frames = opts.get("motion_min_frames", 3)
    max_shift = opts.get("motion_max_mean_shift_pct", 6) / 100.0
    always = opts.get("motion_always", True)
    voice = opts.get("voice", False)
    gaze = opts.get("gaze", False)
    gate = GuestModeGate()
    voice_gate = VoiceGate(opts.get("voice_switch", "input_boolean.voice_kommandoer_enabled"))

    Handler.hand_tune = HandTunables({"scale": 100, "min_px": opts.get("palm_min_px", 0)})
    Handler.palm_gate = PalmGate(PALM_LOG if opts.get("palm_log", True) else None)
    for cam in opts.get("cameras", []):
        Handler.grabbers[cam["name"]] = Grabber(
            cam["name"], cam["rtsp_url"], fps, quality, idle_timeout
        )
        listener = None
        if motion:
            listener = None
            if voice:
                listener = VoiceWatcher(
                    cam["name"],
                    opts.get("stt_host", "core-speech-to-phrase"),
                    opts.get("stt_port", 10300),
                    opts.get("voice_threshold_dbfs", -35),
                    opts.get("voice_zcr_max", 110),
                    opts.get("voice_min_utt", 0.9),
                    opts.get("voice_max_utt", 4.0),
                    opts.get("voice_cooldown", 8),
                    voice_gate,
                    opts.get("voice_body_window", 120),
                    opts.get("voice_arm_window", 12),
                    # Opt IN here and nowhere else. The default is off so that
                    # a rig which builds a VoiceWatcher to measure a specific
                    # combination gets exactly the numbers it passed, instead of
                    # whatever the sliders happen to say right now.
                    live_tuning=True,
                )
                listener.save_clips = opts.get("voice_save_clips", False)
                listener.start()
            watcher = MotionWatcher(
                cam["name"],
                cam["rtsp_url"],
                idle_timeout,
                cell_delta,
                min_cells,
                hold,
                ignore_top,
                min_frames,
                max_shift,
                always,
                gate,
                listener,
            )
            if listener is not None:
                # Camera and radar are blind in opposite directions: the camera
                # cannot see a person who holds still, the radar cannot tell
                # counter height from floor height. Either one saying "occupied"
                # is enough — the gate only has to rule out an EMPTY room, which
                # is the case both agreed on when the false command arrived.
                echo = PresenceEcho(cam.get("presence_entity", ""))
                listener.body_seen = lambda seconds, w=watcher, p=echo: (
                    w.seen_recently(seconds) or p.occupied()
                )
                # An empty entity name means this camera has no arming gate and
                # listens the way it always did — the rigs and any future camera
                # that cannot see hands need that escape hatch.
                arm_entity = cam.get("arm_entity", "")
                if arm_entity:
                    listener.arm = ArmGate(arm_entity)
            Handler.watchers[cam["name"]] = watcher
            threading.Thread(target=watcher.supervise, daemon=True).start()

        # The gaze detector needs somewhere to write its arming stamp and a
        # radar to tell it when to look at all; without either it would be a
        # camera watching faces for nobody's benefit, so it simply does not run.
        if gaze and cam.get("arm_entity") and cam.get("presence_entity"):
            gazer = GazeWatcher(
                cam["name"],
                Handler.grabbers[cam["name"]],
                gate,
                PresenceEcho(cam["presence_entity"]),
                voice_gate,
                VoiceGate(
                    opts.get("gaze_switch", "input_boolean.koekken_blik_arm_enabled"),
                    label="gaze arming",
                ),
                cam["arm_entity"],
                GazeTunables(
                    {
                        "taersk": opts.get("gaze_threshold_deg", 24),
                        "frames": opts.get("gaze_frames", 3),
                        "window": opts.get("voice_arm_window", 12),
                        # Percent / hundredths, as the sliders are. YuNet's own
                        # default floor is 50 %; 80 % and 0.30 are starting points
                        # pending the logged distribution (B158).
                        "score_min": opts.get("gaze_face_score_pct", 80),
                        "frontal_max": opts.get("gaze_frontal_max_pct", 30),
                        # Look-while-speaking (2026-10-03). 26 catches the looks
                        # that took five tries that day (23.9-25.8 among them) and
                        # stays 6 deg under the lowest gated ambient median (32.1).
                        "tale": opts.get("gaze_talk_threshold_deg", 26),
                    }
                ),
            )
            if listener is not None and listener.arm is not None:
                listener.look = gazer.heard_while_looking
            Handler.gazers[cam["name"]] = gazer
            threading.Thread(target=gazer.supervise, daemon=True).start()

    if not Handler.grabbers:
        log.error("No cameras configured — nothing to serve")
        return

    port = opts.get("port", 8090)
    log.info("Serving %s on port %d", sorted(Handler.grabbers), port)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
