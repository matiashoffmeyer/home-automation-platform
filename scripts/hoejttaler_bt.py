#!/usr/bin/env python3
"""hoejttaler_bt.py — højttalerens Bluetooth synlig/skjult fra HA (B276, 2026-10-29)

User 29/10: "kan du styre pairing mode på højttaleren? … gæsterne skal ikke
rode fysisk med højttaleren" + "it should be discoverable only in airbnb mode
when there is open plan presence". Hvornår: packages/hoejttaler_bt.yaml.

N3'ens Bluetooth (målt 29/10): Axioms USB-BT-dongle og Flirc-IR-modtageren er
væk (lsusb viser kun Pi'ens egen hub), så alle BT-tjenester fejlede ved boot.
Pi 3B'ens indbyggede BCM43438 på ttyAMA0 bruges i stedet, sat op af
`hciattach-onboard.service` PÅ højttaleren (installeret over SSH 29/10, ligger
i overlay'et og forsvinder ved en fabriks-nulstilling). Axioms
/usr/local/bin/bt-set-agent starter nu SKJULT (`discoverable off`; originalen
ligger som bt-set-agent.axiom). Chippen kan kun initialiseres én gang pr.
strøm-/genstart: stoppes hciattach, svarer den ikke igen før højttaleren
genstarter (målt 29/10, alle baudrates).

Ingen API på N3'en styrer BT → SSH. SSH er SLÅET FRA i drift og åbnes kun for
kaldet (socket.io `enableSSH`, samme som web-UI'ets /dev-side) og lukkes igen
bagefter. Login er Volumios fabriks-bruger; passwordet kan IKKE skiftes, fordi
Volumio selv kører `echo volumio | sudo -S` (mpd-plugin, pluginmanager). Det
står i secrets.yaml som `hoejttaler_ssh_password`. Værtsnøglen er låst i
hoejttaler_known_hosts.

  python3 hoejttaler_bt.py synlig   # nye telefoner kan finde "myair" og parre uden PIN
  python3 hoejttaler_bt.py skjul    # ingen nye parringer; parrede kan stadig forbinde
  python3 hoejttaler_bt.py ryd      # skjul + glem alle parrede telefoner (AirBnB-exit)
  python3 hoejttaler_bt.py status   # kun aflæs

Skriver én JSON-linje (ok, hci0, synlig, parbar, parrede, glemt, fejl).
Exit 0 = som ønsket, 1 = fejl. Kører i HA-containeren (shell_command, max
60 s) og fra SSH-add-on'et.
"""

import fcntl
import json
import os
import re
import shlex
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HER = Path(__file__).resolve().parent
sys.path.insert(0, str(HER))
import ha_secrets  # noqa: E402
import hoejttaler_spotify as hs  # noqa: E402

KNOWN_HOSTS = HER / "hoejttaler_known_hosts"
LAAS = "/tmp/hoejttaler_bt.lock"
HANDLINGER = ("synlig", "skjul", "ryd", "status")

# Kører som root på højttaleren (sudo -S, passwordet på stdin).
FAELLES = r"""
A=/org/bluez/hci0
P=org.freedesktop.DBus.Properties
g() { dbus-send --system --print-reply --dest=org.bluez $A $P.Get string:org.bluez.Adapter1 string:$1 2>/dev/null | awk '/boolean/{print $3}'; }
s() { dbus-send --system --print-reply --dest=org.bluez $A $P.Set string:org.bluez.Adapter1 string:$1 variant:boolean:$2 >/dev/null; }
"""
HANDLING = {
    # hci0 mangler (fx hciattach fejlede ved boot) → ét forsøg til, uden at vente
    # på chippens 30 s-timeout ud over shell_command's 60 s.
    "synlig": r"""
[ -e /sys/class/bluetooth/hci0 ] || systemctl start --no-block hciattach-onboard
for i in $(seq 12); do [ -n "$(g Powered)" ] && break; sleep 1; done
s Pairable true; s Discoverable true
""",
    "skjul": r"""
[ -e /sys/class/bluetooth/hci0 ] && s Discoverable false
""",
    "ryd": r"""
n=0
[ -e /sys/class/bluetooth/hci0 ] && s Discoverable false
for d in /var/lib/bluetooth/*/[0-9A-F][0-9A-F]:*; do
  [ -e "$d" ] || continue
  m=${d##*/}
  dbus-send --system --print-reply --dest=org.bluez $A org.bluez.Adapter1.RemoveDevice \
    objpath:$A/dev_$(echo $m | tr : _) >/dev/null 2>&1 || rm -rf "$d"
  n=$((n+1))
done
echo glemt=$n
""",
    "status": "",
}
AFLAES = r"""
echo hci0=$([ -e /sys/class/bluetooth/hci0 ] && echo true || echo false)
echo synlig=$(g Discoverable)
echo parbar=$(g Pairable)
echo parrede=$(ls -d /var/lib/bluetooth/*/[0-9A-F][0-9A-F]:* 2>/dev/null | wc -l)
"""


def ssh_aaben(on):
    hs.sio_emit(
        "callMethod",
        {
            "endpoint": "system_controller/system",
            "method": "enableSSH",
            "data": "true" if on else "false",
        },
        wait=1.0,
    )


def port_22(aaben, sek):
    slut = time.time() + sek
    while time.time() < slut:
        try:
            socket.create_connection((hs.HOST, 22), timeout=2).close()
            if aaben:
                return True
        except OSError:
            if not aaben:
                return True
        time.sleep(0.5)
    return False


def koer(script):
    pw = ha_secrets.get("hoejttaler_ssh_password")
    # HA-containerens /tmp er noexec (ssh: "exec(askpass): Permission denied" → login
    # afvist); .cache/ ligger på /config og er git-ignoreret. Hjælperen indeholder
    # ikke passwordet, den kalder dette script igen med "askpass".
    cache = HER.parent / ".cache"
    cache.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=cache) as d:
        ask = Path(d) / "askpass"
        mig = shlex.quote(str(Path(__file__).resolve()))
        ask.write_text(f"#!/bin/sh\nexec {shlex.quote(sys.executable)} {mig} askpass\n")
        ask.chmod(0o700)
        env = {
            **os.environ,
            "SSH_ASKPASS": str(ask),
            "SSH_ASKPASS_REQUIRE": "force",
            "DISPLAY": os.environ.get("DISPLAY", ":0"),
        }
        cmd = ["ssh", "-T"]
        for o in (
            f"UserKnownHostsFile={KNOWN_HOSTS}",
            "GlobalKnownHostsFile=/dev/null",
            "StrictHostKeyChecking=yes",
            "HostKeyAlgorithms=ecdsa-sha2-nistp256",
            "PubkeyAuthentication=no",
            "PreferredAuthentications=password",
            "NumberOfPasswordPrompts=1",
            "ConnectTimeout=8",
            "LogLevel=ERROR",
        ):
            cmd += ["-o", o]
        cmd += [f"volumio@{hs.HOST}", "sudo -S -p '' sh -c " + shlex.quote(script)]
        p = subprocess.run(
            cmd, input=pw + "\n", capture_output=True, text=True, timeout=30, env=env
        )
    if p.returncode == 255:
        raise RuntimeError(
            "SSH-login fejlede: " + (p.stderr.strip().splitlines() or ["?"])[-1][:60]
        )
    return p.stdout


def fortolk(tekst):
    out = {}
    for k, v in re.findall(r"^(\w+)=(.*)$", tekst, re.M):
        v = v.strip()
        out[k] = int(v) if v.isdigit() else {"true": True, "false": False}.get(v)
    return out


def main():
    arg = sys.argv[1:2]
    if arg == ["askpass"]:
        print(ha_secrets.get("hoejttaler_ssh_password"))
        return 0
    if not arg or arg[0] not in HANDLINGER:
        print("brug: hoejttaler_bt.py synlig|skjul|ryd|status", file=sys.stderr)
        return 2
    handling = arg[0]
    res = {"handling": handling}
    with open(LAAS, "w") as laas:
        fcntl.flock(laas, fcntl.LOCK_EX)
        try:
            ssh_aaben(True)
            if not port_22(True, 12):
                raise RuntimeError("SSH åbnede ikke")
            res.update(fortolk(koer(FAELLES + HANDLING[handling] + AFLAES)))
        except Exception as e:  # noqa: BLE001 — rapporteres i JSON
            res["fejl"] = str(e)[:80] or type(e).__name__
        finally:
            try:
                ssh_aaben(False)
                lukket = port_22(False, 8)
            except Exception:  # noqa: BLE001
                lukket = False
            if not lukket:
                res["ssh_aaben"] = True
                res.setdefault("fejl", "SSH står stadig åben på højttaleren")
    if "fejl" not in res and handling == "synlig" and not res.get("hci0"):
        res["fejl"] = "BT-chippen svarer ikke, genstart højttaleren"
    if "fejl" in res:
        res["ok"] = False
    elif handling == "synlig":
        res["ok"] = res.get("synlig") is True
    elif handling in ("skjul", "ryd"):
        res["ok"] = not res.get("hci0") or res.get("synlig") is False
    else:
        res["ok"] = True
    print(json.dumps(res, ensure_ascii=False))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
