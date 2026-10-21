#!/usr/bin/env python3
"""hq.py: one command-line tool for live Home Assistant data. Compact TSV output, never raw JSON.

  hq.py state  <glob|entity...> [--attr a,b|all]   state, last_changed, age
  hq.py hist   <entity> [--since 3d] [--stats|--rows] [--gate X] [--attr NAME]
  hq.py flanks <entity> [--since 3d] [--to S] [--from S] [--min-prev 30s]
  hq.py who    <entity> [--since 1d] [--attr-changes]   who or what changed it
  hq.py auto   <automation_id|glob>                 state, last_triggered, file:line
  hq.py find   <text...>                            entity, state, room, repository refs
  hq.py where  <entity|glob>                        file:lines in the repository (offline)
  hq.py tmpl   '<jinja>'                            render through /api/template

The traps it closes (failure classes in docs/fejlklasser.md): times are always
local (Europe/Copenhagen, DST-safe; the history API answers in UTC, #18);
``/api/history`` always gets an ``end_time`` and is fetched one day at a time
(otherwise it is silently truncated to one day); ``who`` reads the recorder
through ``context_user_id_bin`` and full context equality, never context id
prefixes. Output is capped at 40 lines by default (``--all`` for the rest), and
``hist`` switches to ``--stats`` by itself above 200 rows.

Access: ``HA_TOKEN`` (environment or ``.env``, on a workstation), then
``SUPERVISOR_TOKEN`` (the host's SSH add-on), then ``ha_api_token`` from
``secrets.yaml``. ``who`` needs the recorder database: on the host it is read
directly (read-only); from a workstation the script runs itself over ``ssh ha``
and falls back to the logbook. ``where`` runs offline against the repository,
so it also works in the cloud.
Tests: python3 -m unittest discover -s scripts/tests -p "test_hq*.py"
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import shlex
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta, timezone

import ha_secrets

CAP = 40  # default-loft på output-linjer
AUTO_STATS = 200  # hist: flere rækker end dette → --stats
DB_PATH = os.environ.get("HQ_DB", "/config/home-assistant_v2.db")
AUTH_PATH = os.environ.get("HQ_AUTH", "/config/.storage/auth")
NONNUM = {"unknown", "unavailable", "", "None", "none"}

try:
    _HERE = os.path.dirname(os.path.abspath(__file__))
    REPO = os.environ.get("HQ_REPO") or os.path.dirname(_HERE)
except NameError:  # kørt som `python3 -` (who over ssh)
    _HERE, REPO = None, os.environ.get("HQ_REPO", "/config")
if not os.path.isdir(os.path.join(REPO, "packages")) and os.path.isdir("/config/packages"):
    REPO = "/config"


class HQError(Exception):
    pass


# ---------------------------------------------------------------- tid ------
# zoneinfo når tz-data findes (NUC'en); ellers EU-reglen (PC'en har ingen
# tzdata): sommertid fra sidste søndag i marts 01:00 UTC til sidste søndag i
# oktober 01:00 UTC. Danmark har fulgt den siden 1996.
try:
    from zoneinfo import ZoneInfo

    LOCAL = ZoneInfo("Europe/Copenhagen")
except Exception:  # noqa: BLE001 — ZoneInfoNotFoundError/ImportError
    LOCAL = None


def _last_sunday_0100utc(year, month):
    d = datetime(year, month, 31, 1, 0, tzinfo=UTC)
    return d - timedelta(days=(d.weekday() + 1) % 7)


def eu_offset(dt_utc):
    start, end = _last_sunday_0100utc(dt_utc.year, 3), _last_sunday_0100utc(dt_utc.year, 10)
    return timedelta(hours=2 if start <= dt_utc < end else 1)


def to_local(dt_utc, use_zoneinfo=True):
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=UTC)
    if LOCAL is not None and use_zoneinfo:
        return dt_utc.astimezone(LOCAL)
    dt_utc = dt_utc.astimezone(UTC)
    return dt_utc.astimezone(timezone(eu_offset(dt_utc)))


def from_local(naive, use_zoneinfo=True):
    """Naiv lokal tid → UTC. Tvetydig (25/10 02:30) = sommertid som zoneinfo's
    fold=0; ikke-eksisterende (29/3 02:30) = vintertid."""
    if LOCAL is not None and use_zoneinfo:
        return naive.replace(tzinfo=LOCAL).astimezone(UTC)
    for hours in (2, 1):
        cand = (naive - timedelta(hours=hours)).replace(tzinfo=UTC)
        if eu_offset(cand) == timedelta(hours=hours):
            return cand
    return (naive - timedelta(hours=1)).replace(tzinfo=UTC)


def local_candidates(naive, use_zoneinfo=True):
    """Alle UTC-øjeblikke en lokal vægur-tid betyder: 2 i den gentagne time
    (25/10 02:30), 1 normalt, og for en tid der ikke findes (29/3 02:30) den
    samme fortolkning som from_local."""
    out = []
    if LOCAL is not None and use_zoneinfo:
        for fold in (0, 1):
            u = naive.replace(tzinfo=LOCAL, fold=fold).astimezone(UTC)
            if to_local(u).replace(tzinfo=None) == naive and u not in out:
                out.append(u)
    else:
        for hours in (2, 1):
            cand = (naive - timedelta(hours=hours)).replace(tzinfo=UTC)
            if eu_offset(cand) == timedelta(hours=hours):
                out.append(cand)
    return sorted(out) or [from_local(naive, use_zoneinfo)]


def now_utc():
    return datetime.now(UTC)


def parse_ts(s):
    """HA-ISO-streng → aware UTC datetime."""
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).astimezone(UTC)


_REL = re.compile(r"^(\d+(?:\.\d+)?)\s*([smhtdw])$")
_UNIT = {"s": 1, "m": 60, "h": 3600, "t": 3600, "d": 86400, "w": 7 * 86400}


def parse_dur(s):
    m = _REL.match(s.strip().lower())
    if not m:
        raise HQError(f"ukendt varighed '{s}' (fx 30s, 5m, 2h, 3d)")
    return timedelta(seconds=float(m.group(1)) * _UNIT[m.group(2)])


def parse_when(s, ref=None):
    """'3d'/'12h' (før nu), 'now', 'today', 'HH:MM' (seneste), eller lokal
    'YYYY-MM-DD[ HH:MM[:SS]]'. Returnerer aware UTC."""
    ref = ref or now_utc()
    s = s.strip()
    if s.lower() == "now":
        return ref
    if _REL.match(s.lower()):
        return ref - parse_dur(s)
    loc = to_local(ref)
    if s.lower() == "today":
        return from_local(datetime(loc.year, loc.month, loc.day))
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", s)
    if m:
        hh, mm = int(m.group(1)), int(m.group(2))
        if hh > 23 or mm > 59:
            raise HQError(f"ukendt klokkeslæt '{s}'")
        # Seneste forekomst ≤ ref, regnet i LOKAL kalender (24 t tilbage i UTC
        # rammer en time forkert på DST-dagene).
        for day in (loc.date(), loc.date() - timedelta(days=1)):
            hits = [
                t
                for t in local_candidates(datetime(day.year, day.month, day.day, hh, mm))
                if t <= ref
            ]
            if hits:
                return max(hits)
        raise HQError(f"kunne ikke placere '{s}'")
    try:
        naive = datetime.fromisoformat(s.replace(" ", "T"))
    except ValueError as e:
        raise HQError(f"ukendt tid '{s}' (fx 3d, 12h, 18:00, 2026-10-04 18:00)") from e
    if naive.tzinfo:
        return naive.astimezone(UTC)
    return from_local(naive)


def fmt_t(dt_utc, with_date=True):
    """Lokal tid. I den gentagne time ved vintertid (25/10 02:00-03:00 findes
    to gange) får tiden offset på, ellers kan to rækker ikke skelnes."""
    loc = to_local(dt_utc)
    txt = loc.strftime("%m-%d %H:%M:%S" if with_date else "%H:%M:%S")
    if any(to_local(dt_utc + timedelta(hours=h)).hour == loc.hour for h in (-1, 1)):
        txt += f"+{int(loc.utcoffset().total_seconds() // 3600):02d}"
    return txt


def fmt_dur(sec):
    sec = int(round(max(sec, 0)))
    if sec < 60:
        return f"{sec}s"
    if sec < 3600:
        return f"{sec // 60}m{sec % 60:02d}s"
    if sec < 86400:
        return f"{sec // 3600}h{sec % 3600 // 60:02d}m"
    return f"{sec // 86400}d{sec % 86400 // 3600:02d}h"


def fnum(x):
    if x is None:
        return "-"
    x = float(x)
    if x.is_integer():
        return str(int(x))
    a = abs(x)
    d = 0 if a >= 100 else 1 if a >= 10 else 2 if a >= 1 else 3
    s = f"{x:.{d}f}"
    return s.rstrip("0").rstrip(".") if "." in s else s  # 110 må ikke blive 11


def chunks(start, end, step=timedelta(days=1)):
    """[start, end) i bidder af højst ét døgn — /api/history trunkerer ellers."""
    out, t = [], start
    while t < end:
        out.append((t, min(t + step, end)))
        t += step
    return out


# ---------------------------------------------------------------- output ---
def emit(lines, show_all=False, cap=CAP, tail=False, what="rækker"):
    """Skriv linjer; over loftet: hoved (lister) eller hale (tidsserier)."""
    lines = list(lines)
    if show_all or len(lines) <= cap:
        print("\n".join(lines))
        return
    skjult = len(lines) - cap
    if tail:
        print(f"# … {skjult} ældre {what} skjult (--all, eller snævrere --since)")
        print("\n".join(lines[-cap:]))
    else:
        print("\n".join(lines[:cap]))
        print(f"# … +{skjult} {what} mere (--all)")


# ---------------------------------------------------------------- HA REST --
def _read_kv(path, key, sep="="):
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith(key + sep):
                    return line.split(sep, 1)[1].strip().strip("\"'")
    except OSError:
        pass
    return None


def resolve_access():
    """(base_url, token) — samme rækkefølge som helpers_export/ha_validate."""
    env_file = os.path.join(REPO, ".env")
    url = (
        os.environ.get("HA_URL")
        or _read_kv(env_file, "HA_URL")
        or "http://homeassistant.local:8123"
    )
    tok = (
        os.environ.get("HA_TOKEN")
        or _read_kv(env_file, "HA_TOKEN")
        or _read_kv("/config/.env", "HA_TOKEN")
    )
    if tok:
        return url.rstrip("/"), tok
    if os.environ.get("SUPERVISOR_TOKEN"):
        return "http://supervisor/core", os.environ["SUPERVISOR_TOKEN"]
    tok = ha_secrets.get(ha_secrets.HA_API_TOKEN, required=False)
    if tok:
        return "http://127.0.0.1:8123", tok
    raise HQError(
        "ingen HA-adgang (HA_TOKEN i .env / SUPERVISOR_TOKEN) — "
        "offline virker kun `where` og `find --offline`"
    )


class HA:
    def __init__(self, base=None, token=None):
        if base is None:
            base, token = resolve_access()
        self.base, self.token = base, token
        self._states = None

    def req(self, path, params=None, body=None, raw=False):
        url = self.base + "/api" + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = json.dumps(body).encode() if body is not None else None
        r = urllib.request.Request(
            url,
            data=data,
            headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(r, timeout=30) as resp:
                txt = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            raise HQError(
                f"HTTP {e.code} på {path}: {e.read().decode('utf-8', 'replace')[:200]}"
            ) from e
        except (urllib.error.URLError, OSError) as e:
            raise HQError(f"HA ikke nåbar ({self.base}): {e}") from e
        return txt if raw else json.loads(txt)

    def states(self):
        if self._states is None:
            self._states = self.req("/states")
        return self._states

    def template(self, tpl):
        return self.req("/template", body={"template": tpl}, raw=True)

    def history(self, entity, start, end, attr=None):
        """Rækker [(ts_utc, value)] i [start, end), chunket pr. døgn, med
        end_time i HVERT kald. Første række = tilstanden ved start (klemt)."""
        rows, seen = [], False
        for a, b in chunks(start, end):
            params = {"filter_entity_id": entity, "end_time": b.isoformat()}
            if attr:
                params["significant_changes_only"] = "0"
            else:
                params.update(minimal_response="", no_attributes="")
            data = self.req("/history/period/" + urllib.parse.quote(a.isoformat()), params)
            for r in data[0] if data else []:
                ts = parse_ts(r.get("last_updated") if attr else r["last_changed"])
                val = (r.get("attributes") or {}).get(attr) if attr else r["state"]
                seen = seen or not attr or attr in (r.get("attributes") or {})
                rows.append((max(ts, a), val))
        if attr and rows and not seen:
            raise HQError(
                f"attributten '{attr}' findes ikke i recorderens historik for {entity} — recorderen "
                f"gemmer den ikke (fx lys-attributter, sun-azimut). Kun live: hq.py state {entity} --attr {attr}"
            )
        return collapse(rows)

    def logbook(self, entity, start, end):
        out = []
        for a, b in chunks(start, end):
            out += self.req(
                "/logbook/" + urllib.parse.quote(a.isoformat()),
                {"entity": entity, "end_time": b.isoformat()},
            )
        return out


def collapse(rows):
    """Sortér og fjern gentagelser (chunk-grænsernes start-rækker)."""
    out = []
    for ts, val in sorted(rows, key=lambda r: r[0]):
        if out and out[-1][1] == val:
            continue
        out.append((ts, val))
    return out


def segments(rows, end):
    """[(start, slut, værdi)] — hver værdi holder til næste række / end."""
    return [(t, rows[i + 1][0] if i + 1 < len(rows) else end, v) for i, (t, v) in enumerate(rows)]


def as_num(v):
    if v is None or isinstance(v, bool):
        return None
    try:
        x = float(v)
    except TypeError, ValueError:
        return None
    return x if x == x and abs(x) != float("inf") else None


def pct(sorted_vals, q):
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def tw_pct(pairs, q):
    """Tids-vægtet percentil over [(værdi, sekunder)]."""
    pairs = sorted(p for p in pairs if p[1] > 0)
    total = sum(d for _, d in pairs)
    if not total:
        return None
    acc = 0.0
    for v, d in pairs:
        acc += d
        if acc >= q * total:
            return v
    return pairs[-1][0]


def stats_lines(rows, end, gate=None):
    segs = segments(rows, end)
    total = sum((b - a).total_seconds() for a, b, _ in segs) or 1
    nums = [(as_num(v), (b - a).total_seconds(), v) for a, b, v in segs]
    numeric = [x for x in nums if x[0] is not None]
    other = [x for x in nums if x[0] is None]
    lines = []
    if numeric and sum(x[1] for x in numeric) >= sum(x[1] for x in other):  # efter TID, ikke antal
        vals = sorted(x[0] for x in numeric)
        lines.append(
            "samples\t"
            + "  ".join(
                f"{k} {fnum(v)}"
                for k, v in (
                    ("n", len(vals)),
                    ("min", vals[0]),
                    ("p5", pct(vals, 0.05)),
                    ("p50", pct(vals, 0.5)),
                    ("p95", pct(vals, 0.95)),
                    ("max", vals[-1]),
                )
            )
        )
        tw = [(x[0], x[1]) for x in numeric]
        lines.append(
            "tid-vægtet\t"
            + "  ".join(
                f"{k} {fnum(tw_pct(tw, q))}"
                for k, q in (
                    ("p5", 0.05),
                    ("p25", 0.25),
                    ("p50", 0.5),
                    ("p75", 0.75),
                    ("p95", 0.95),
                )
            )
        )
        if gate is not None:
            over = sum(d for v, d, _ in numeric if v > gate)
            under = sum(d for v, d, _ in numeric if v <= gate)
            ups = sum(
                1 for i in range(1, len(numeric)) if numeric[i - 1][0] <= gate < numeric[i][0]
            )
            lines.append(
                f"gate {gate:g}\tover {fmt_dur(over)} ({over / total:.0%})  "
                f"≤ {fmt_dur(under)} ({under / total:.0%})  krydsninger op: {ups}"
            )
        if other:
            agg = {}
            for _, d, v in other:
                c = agg.setdefault(str(v), [0, 0.0])
                c[0] += 1
                c[1] += d
            lines.append(
                "ikke-tal\t"
                + "  ".join(
                    f"{k} {fmt_dur(d)} ({d / total:.1%}, {n}×)" for k, (n, d) in sorted(agg.items())
                )
            )
        return lines
    agg = {}
    for _, d, v in nums:
        agg.setdefault(str(v), []).append(d)
    if gate is not None:
        lines.append("# --gate ignoreret: entity'en er mest ikke-tal i vinduet")
    lines.append("state\tn\ttid\tandel\tp50-varighed\tmax")
    for k, ds in sorted(agg.items(), key=lambda kv: -sum(kv[1])):
        s = sorted(ds)
        lines.append(
            f"{k}\t{len(s)}\t{fmt_dur(sum(s))}\t{sum(s) / total:.1%}\t{fmt_dur(pct(s, 0.5))}\t{fmt_dur(s[-1])}"
        )
    return lines


# ---------------------------------------------------------------- kommandoer
def _match_states(ha, pats):
    st = ha.states()
    ids = {s["entity_id"]: s for s in st}
    out = []
    for p in pats:
        if p in ids:
            hits = [p]
        elif any(c in p for c in "*?["):
            hits = sorted(e for e in ids if fnmatch.fnmatch(e, p))
        else:
            hits = sorted(e for e in ids if p.lower() in e)
        out += [ids[h] for h in hits if ids[h] not in out]
    return out


def _attr_str(attrs, want):
    keys = sorted(attrs) if want == ["all"] else want
    parts = []
    for k in keys:
        if k in attrs:
            v = attrs[k]
            v = json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else str(v)
            parts.append(f"{k}={v[:60]}")
    return "; ".join(parts)


def cmd_state(a, ha):
    now = now_utc()
    rows = _match_states(ha, a.entities)
    if not rows:
        raise HQError("ingen entities matcher " + " ".join(a.entities))
    want = [w.strip() for w in a.attr.split(",")] if a.attr else None
    lines = ["# entity\tstate\tlast_changed\talder" + ("\tattrs" if want else "")]
    for s in rows:
        unit = (s.get("attributes") or {}).get("unit_of_measurement")
        lc = parse_ts(s["last_changed"])
        line = f"{s['entity_id']}\t{s['state']}{' ' + unit if unit else ''}\t{fmt_t(lc)}\t{fmt_dur((now - lc).total_seconds())}"
        if want:
            line += "\t" + _attr_str(s.get("attributes") or {}, want)
        lines.append(line)
    emit(lines, a.all, what="entities")


def _window(a, default):
    """Relative tider (3d, 12h) regnes altid fra NU — også med --until."""
    end = parse_when(a.until) if a.until else now_utc()
    start = parse_when(a.since or default)
    if start >= end:
        raise HQError("--since ligger efter --until")
    return start, end


def cmd_hist(a, ha):
    start, end = _window(a, "3d")
    rows = ha.history(a.entity, start, end, attr=a.attr)
    if not rows:
        raise HQError(f"ingen historik for {a.entity} i vinduet (findes entity'en? `hq.py find`)")
    head = (
        f"# {a.entity}{'[' + a.attr + ']' if a.attr else ''}  {fmt_t(start)} → {fmt_t(end)} "
        f"({fmt_dur((end - start).total_seconds())}, lokal tid)  {len(rows) - 1} skift"
    )
    if a.gate is not None or a.stats or (len(rows) > AUTO_STATS and not a.rows):
        print(
            head + ("" if a.stats or a.gate is not None else "  [auto --stats; --rows for rækker]")
        )
        emit(stats_lines(rows, end, a.gate), a.all, what="states")
        return
    print(head + "  (tid\tstate\tvarighed)")
    emit(
        [f"{fmt_t(t)}\t{v}\t{fmt_dur((b - t).total_seconds())}" for t, b, v in segments(rows, end)],
        a.all,
        tail=True,
    )


def cmd_flanks(a, ha):
    start, end = _window(a, "3d")
    rows = ha.history(a.entity, start, end)
    segs = segments(rows, end)
    out, durs = [], {}
    for i in range(1, len(segs)):
        p, c = segs[i - 1], segs[i]
        prev_d = (p[1] - p[0]).total_seconds()
        clipped = i - 1 == 0  # forrige state startede før vinduet
        if a.to and str(c[2]) != a.to:
            continue
        if a.from_ and str(p[2]) != a.from_:
            continue
        if a.min_prev and prev_d < a.min_prev.total_seconds() and not clipped:
            continue  # en klippet varighed er kun en NEDRE grænse — den beholdes
        if not clipped:
            durs.setdefault(str(p[2]), []).append(prev_d)
        out.append(
            f"{fmt_t(c[0])}\t{p[2]}→{c[2]}\t{'≥' if clipped else ''}{fmt_dur(prev_d)} i {p[2]}"
        )
    print(
        f"# {a.entity}  {fmt_t(start)} → {fmt_t(end)}  {len(out)} flanker  (tid\tskift\tvarighed i forrige)"
    )
    emit(out, a.all, tail=True, what="flanker")
    if durs and sum(as_num(k) is not None for k in durs) > len(durs) / 2 and not a.all:
        print("# (numerisk entity — varighed pr. værdi giver ikke mening; brug hist --stats)")
        return
    keys = sorted(durs, key=lambda k: -len(durs[k]))
    for k in keys if a.all else keys[:8]:
        s = sorted(durs[k])
        print(
            f"# varighed i {k}: n={len(s)}  p50 {fmt_dur(pct(s, 0.5))}  p95 {fmt_dur(pct(s, 0.95))}  max {fmt_dur(s[-1])}"
        )
    if len(keys) > 8 and not a.all:
        print(f"# … +{len(keys) - 8} states mere (--all)")


# --- who: recorder-DB ------------------------------------------------------
# HA genbruger en kalders context på en entity i kun 5 s (Entity
# CONTEXT_RECENT_TIME_SECONDS). En langsom pære der melder efter 5,4 s får en
# frisk context og ligner et fysisk tryk — derfor kigges der efter et kald på
# entity'en (eller en gruppe den er med i) i vinduet før.
CALL_LOOKBACK_S = 15


def _users():
    """{user-id-hex: 'user:Navn' | 'api:Navn'} — system-genererede brugere
    (Supervisor, add-ons, cron-scripts med SUPERVISOR_TOKEN) er IKKE et
    fingertryk (#3)."""
    try:
        with open(AUTH_PATH, encoding="utf-8") as f:
            return {
                u["id"].lower(): ("api:" if u.get("system_generated") else "user:") + u["name"]
                for u in json.load(f)["data"]["users"]
            }
    except OSError, KeyError, ValueError:
        return {}


def _user_label(users, uid):
    lab = users.get(uid.hex()) or uid.hex()[:8]
    return lab if lab.startswith(("user:", "api:")) else "user:" + lab


def who_db(conn, entity, start, end, attr_changes=False, users=None):
    """[(ts_utc, fra, til, hvem, detalje)] — ren funktion over en
    recorder-forbindelse (testbar med en in-memory DB)."""
    users = users if users is not None else _users()
    row = conn.execute(
        "SELECT metadata_id FROM states_meta WHERE entity_id=?", (entity,)
    ).fetchone()
    if not row:
        raise HQError(f"{entity} findes ikke i recorderen (excluded? stavefejl? `hq.py find`)")
    mid = row[0]
    s0, s1 = start.timestamp(), end.timestamp()
    prev = conn.execute(
        "SELECT state FROM states WHERE metadata_id=? AND last_updated_ts<? "
        "ORDER BY last_updated_ts DESC LIMIT 1",
        (mid, s0),
    ).fetchone()
    prev = prev[0] if prev else "?"
    rows = conn.execute(
        "SELECT state, last_updated_ts, last_changed_ts, context_id_bin, context_user_id_bin, "
        "context_parent_id_bin, old_state_id FROM states WHERE metadata_id=? AND last_updated_ts>=? "
        "AND last_updated_ts<? ORDER BY last_updated_ts",
        (mid, s0, s1),
    ).fetchall()
    out = []
    for state, lu, lc, ctx, uid, par, old_sid in rows:
        changed = lc is None or lc == lu
        if not changed and not attr_changes:
            prev = state
            continue
        if changed and state == prev:
            who, det = "genskrevet", "samme state skrevet igen (restart/reload/genopstået)"
        else:
            who, det = _attribute(conn, mid, lu, ctx, uid, par, users)
            if who == "device" and old_sid is None:
                who, det = "genstart", "første række efter HA-start/reload (old_state_id tom)"
            elif who == "device":
                who, det = _recent_call(conn, entity, lu, users) or (who, det)
        out.append(
            (
                datetime.fromtimestamp(lu, UTC),
                prev if changed else state,
                state if changed else "(attr)",
                who,
                det,
            )
        )
        prev = state
    return out


def _events_in(conn, ctx):
    """[(event_type, data, time_fired_ts)] i præcis denne context."""
    if not ctx:
        return []
    out = []
    for et, data, t in conn.execute(
        "SELECT et.event_type, ed.shared_data, e.time_fired_ts FROM events e JOIN event_types et "
        "USING(event_type_id) LEFT JOIN event_data ed USING(data_id) WHERE e.context_id_bin=? "
        "ORDER BY e.time_fired_ts",
        (ctx,),
    ):
        try:
            out.append((et, json.loads(data) if data else {}, t))
        except ValueError:
            out.append((et, {}, t))
    return out


def _state_with_ctx(conn, ctx, before_ts=None, not_mid=None):
    q = (
        "SELECT m.entity_id, s.state, s.last_updated_ts FROM states s JOIN states_meta m USING(metadata_id) "
        "WHERE s.context_id_bin=?"
    )
    args = [ctx]
    if not_mid is not None:
        q += " AND s.metadata_id!=?"
        args.append(not_mid)
    if before_ts is not None:
        q += " AND s.last_updated_ts<?"
        args.append(before_ts)
    return conn.execute(q + " ORDER BY s.last_updated_ts LIMIT 1", args).fetchone()


def _attribute(conn, mid, lu, ctx, uid, par, users):
    """(hvem, detalje). hvem = automation.x / script.x / user:Navn / api:Navn /
    device / fulgte:<entity> / barn:<entity>. Kun FULD context-lighed
    (CLAUDE.md: afkortede context-id'er matcher altid falsk)."""
    evs = _events_in(conn, ctx)
    autos = [d for et, d, _ in evs if et == "automation_triggered"]
    scripts = []  # kun scripts startet FØR skiftet, inderste (seneste) først
    for et, d, t in sorted(evs, key=lambda e: -(e[2] or 0)):
        if (
            et == "script_started"
            and (t or 0) <= lu
            and d.get("entity_id")
            and d["entity_id"] not in scripts
        ):
            scripts.append(d["entity_id"])
    via = ("via " + ",".join(scripts)) if scripts else ""
    if uid:
        svc = next(
            (f"{d.get('domain')}.{d.get('service')}" for et, d, _ in evs if et == "call_service"),
            "",
        )
        return _user_label(users, uid), " ".join(x for x in (svc, via) if x)
    if autos:
        a = autos[0]
        src = a.get("source") or ""
        if not src and par:
            p = _state_with_ctx(conn, par)
            src = f"{p[0]}→{p[1]}" if p else ""
        return a.get("entity_id") or "automation.?", " ".join(
            x for x in (via, f"← {src}" if src else "") if x
        )
    if scripts:
        return scripts[0], ("via " + ",".join(scripts[1:])) if scripts[1:] else ""
    lead = _state_with_ctx(conn, ctx, before_ts=lu, not_mid=mid) if ctx else None
    if lead:
        return f"fulgte:{lead[0]}", f"samme context; {lead[0]}→{lead[1]} kom først"
    if par:
        p = _state_with_ctx(conn, par)
        if p:
            return f"barn:{p[0]}", f"forælder-context = {p[0]}→{p[1]}"
        pe = _events_in(conn, par)
        return (
            (f"barn:{pe[0][0]}", "forælder-context = event")
            if pe
            else ("barn:?", "forælder ukendt (purget?)")
        )
    return "device", "intet context-ophav (fysisk/integration)"


def _members(conn, group_entity, before_ts):
    """Medlemmerne af en gruppe-entity som de stod i dens seneste attributter
    før before_ts (tom liste hvis den ikke er en gruppe)."""
    r = conn.execute(
        "SELECT sa.shared_attrs FROM states s JOIN states_meta m USING(metadata_id) "
        "LEFT JOIN state_attributes sa USING(attributes_id) WHERE m.entity_id=? AND s.last_updated_ts<=? "
        "ORDER BY s.last_updated_ts DESC LIMIT 1",
        (group_entity, before_ts),
    ).fetchone()
    try:
        ids = json.loads(r[0]).get("entity_id") if r and r[0] else None
    except ValueError:
        ids = None
    return ids if isinstance(ids, list) else []


def _recent_call(conn, entity, lu, users):
    """Et call_service på entity'en (direkte eller via en gruppe) inden for
    CALL_LOOKBACK_S før skiftet → ('≈<hvem>', detalje) eller None."""
    rows = conn.execute(
        "SELECT e.time_fired_ts, ed.shared_data, e.context_id_bin, e.context_user_id_bin, "
        "e.context_parent_id_bin FROM events e JOIN event_types et USING(event_type_id) "
        "LEFT JOIN event_data ed USING(data_id) WHERE et.event_type='call_service' "
        "AND e.time_fired_ts BETWEEN ? AND ? ORDER BY e.time_fired_ts DESC",
        (lu - CALL_LOOKBACK_S, lu),
    ).fetchall()
    for t, data, ctx, uid, par in rows:
        try:
            d = json.loads(data) if data else {}
        except ValueError:
            continue
        tgt = (d.get("service_data") or {}).get("entity_id") or []
        tgt = [tgt] if isinstance(tgt, str) else tgt
        if not isinstance(tgt, list):
            continue
        via = (
            entity
            if entity in tgt
            else next((g for g in tgt if entity in _members(conn, g, t)), None)
        )
        if not via:
            continue
        who, det = _attribute(conn, -1, t, ctx, uid, par, users)
        if who == "device":
            continue
        svc = f"{d.get('domain')}.{d.get('service')}"
        return (
            "≈" + who,
            f"{svc} på {via} {lu - t:.1f}s før (HA-context udløber efter 5 s)"
            + (f"; {det}" if det else ""),
        )
    return None


def _ssh_target():
    if os.environ.get("HQ_SSH"):
        return shlex.split(os.environ["HQ_SSH"])
    try:
        with open(os.path.expanduser("~/.ssh/config"), encoding="utf-8") as f:
            if re.search(r"(?mi)^\s*Host\s+(.*\s)?ha(\s|$)", f.read()):
                return ["ha"]
    except OSError:
        pass
    env_file = os.path.join(REPO, ".env")
    host = _read_kv(env_file, "HA_HOST") or "homeassistant.local"
    user = _read_kv(env_file, "HA_USER") or "root"
    port = _read_kv(env_file, "HA_PORT") or "22"
    return ["-p", port, "-i", os.path.expanduser("~/.ssh/ha_key"), f"{user}@{host}"]


def _who_remote(argv):
    if _HERE is None:
        raise HQError("recorder-DB ikke fundet på denne maskine")
    with open(os.path.abspath(__file__), "rb") as f:
        src = f.read()
    remote = "python3 - " + " ".join(shlex.quote(x) for x in argv + ["--on-nuc"])
    cmd = ["ssh", "-4", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8"] + _ssh_target() + [remote]
    try:
        p = subprocess.run(cmd, input=src, capture_output=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise HQError(f"ssh fejlede: {e}") from e
    if p.returncode == 255:
        raise HQError("ssh fejlede: " + p.stderr.decode("utf-8", "replace").strip()[-200:])
    sys.stdout.write(p.stdout.decode("utf-8", "replace"))
    sys.stderr.write(p.stderr.decode("utf-8", "replace"))
    return p.returncode


def _who_print(a, rows, start, end, src):
    print(
        f"# {a.entity}  {fmt_t(start)} → {fmt_t(end)}  {len(rows)} skift  [{src}]  (tid	skift	hvem	detalje)"
    )
    emit(
        [f"{fmt_t(t)}	{f}→{to}	{who}	{det}".rstrip() for t, f, to, who, det in rows],
        a.all,
        tail=True,
        what="skift",
    )
    if rows:
        tally = {}
        for r in rows:
            tally[r[3]] = tally.get(r[3], 0) + 1
        print(
            "# fordeling: "
            + "  ".join(f"{k} ×{n}" for k, n in sorted(tally.items(), key=lambda kv: -kv[1])[:8])
        )


def cmd_who(a, ha_factory, argv):
    start, end = _window(a, "1d")
    if os.path.exists(DB_PATH):
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=15)
        _who_print(a, who_db(conn, a.entity, start, end, a.attr_changes), start, end, "recorder")
        return 0
    if not a.on_nuc and not a.logbook:
        try:
            return _who_remote(argv)
        except HQError as e:
            print(f"# ssh-vej fejlede ({e}) → logbog-fallback (grovere)", file=sys.stderr)
    return _who_logbook(a, ha_factory(), start, end)


def _who_logbook(a, ha, start, end):
    persons = {
        (s.get("attributes") or {}).get("user_id"): s["attributes"].get("friendly_name")
        for s in ha.states()
        if s["entity_id"].startswith("person.")
    }
    rows, prev = [], "?"
    for e in ha.logbook(a.entity, start, end):
        if "state" not in e:
            continue
        t = parse_ts(e["when"])
        # Automation FØR bruger: logbogen hænger triggerens user-id på
        # automationens rækker, så en bruger-test først ville skjule den (#3).
        if e.get("context_event_type") == "automation_triggered":
            who = e.get("context_entity_id", "automation.?")
            det = f"← {e['context_message']}" if e.get("context_message") else ""
        elif e.get("context_event_type") == "script_started":
            who, det = e.get("context_entity_id", "script.?"), ""
        elif e.get("context_user_id"):
            who = "user:" + (persons.get(e["context_user_id"]) or e["context_user_id"][:8])
            det = f"{e.get('context_domain', '')}.{e.get('context_service', '')}".strip(".")
        elif e.get("context_entity_id"):
            who, det = "fulgte:" + e["context_entity_id"], str(e.get("context_state", ""))
        else:
            who, det = ("genskrevet", "") if e["state"] == prev else ("device", "")
        rows.append((t, prev, e["state"], who, det))
        prev = e["state"]
    _who_print(a, rows, start, end, "logbog")
    return 0


# --- auto / find / where / tmpl -----------------------------------------
def _yaml_files(subdirs=("automations", "packages", "script_pkg")):
    for sd in subdirs:
        root = os.path.join(REPO, sd)
        for dp, dns, fns in os.walk(root):
            dns[:] = [d for d in dns if not d.startswith(".")]
            for fn in sorted(fns):
                if fn.endswith((".yaml", ".yml")):
                    yield os.path.join(dp, fn)


def _rel(p):
    return os.path.relpath(p, REPO).replace("\\", "/")


def find_automation_lines(ids):
    """{automation-id: 'fil:linje'} — mindste indrykning vinder (trigger-id'er
    står dybere end automationens eget `- id:`)."""
    want, best = set(ids), {}
    pat = re.compile(r"^(\s*)-?\s*id:\s*['\"]?([^'\"\s#]+)['\"]?\s*(#.*)?$")
    for p in _yaml_files():
        with open(p, encoding="utf-8", errors="replace") as f:
            for n, line in enumerate(f, 1):
                m = pat.match(line)
                if m and m.group(2) in want:
                    ind = len(m.group(1))
                    if m.group(2) not in best or ind < best[m.group(2)][0]:
                        best[m.group(2)] = (ind, f"{_rel(p)}:{n}")
    return {k: v[1] for k, v in best.items()}


def find_script_lines(objs):
    """{script-objekt: 'fil:linje'} — script_pkg/ har scripts som top-nøgler
    (!include_dir_merge_named), packages/ har dem under en `script:`-blok."""
    want, out = set(objs), {}
    for p in _yaml_files(("script_pkg", "packages")):
        top = _rel(p).startswith("script_pkg/")
        key = re.compile(r"^" + ("" if top else "  ") + r"([a-z0-9_]+):\s*(#.*)?$")
        in_script = top
        with open(p, encoding="utf-8", errors="replace") as f:
            for n, line in enumerate(f, 1):
                if not top:
                    m0 = re.match(r"^([A-Za-z_]\w*):", line)
                    if m0:
                        in_script = m0.group(1) == "script"
                        continue
                m = key.match(line) if in_script else None
                if m and m.group(1) in want and m.group(1) not in out:
                    out[m.group(1)] = f"{_rel(p)}:{n}"
    return out


def cmd_auto(a, ha):
    now = now_utc()
    pat = a.pattern
    hits = []
    for s in ha.states():
        e = s["entity_id"]
        if not e.startswith(("automation.", "script.")):
            continue
        at = s.get("attributes") or {}
        keys = [
            e,
            e.split(".", 1)[1],
            str(at.get("id", "")),
            str(at.get("friendly_name", "")).lower(),
        ]
        if any(fnmatch.fnmatch(k, pat) or fnmatch.fnmatch(k, pat.lower()) for k in keys) or (
            not any(c in pat for c in "*?[") and any(pat.lower() in k for k in keys)
        ):
            hits.append(s)
    if not hits:
        raise HQError(f"ingen automation/script matcher '{pat}'")
    hits.sort(key=lambda s: s["entity_id"])
    alines = find_automation_lines(
        [str(s["attributes"].get("id")) for s in hits if s["entity_id"].startswith("automation.")]
    )
    slines = find_script_lines(
        [s["entity_id"].split(".", 1)[1] for s in hits if s["entity_id"].startswith("script.")]
    )
    lines = ["# entity\tstate\tlast_triggered\tmode\tkører\tfil:linje\tnavn"]
    for s in hits:
        at = s.get("attributes") or {}
        lt = at.get("last_triggered")
        ltxt = (
            f"{fmt_t(parse_ts(lt))} ({fmt_dur((now - parse_ts(lt)).total_seconds())} siden)"
            if lt
            else "aldrig"
        )
        loc = (
            alines.get(str(at.get("id")))
            if s["entity_id"].startswith("automation.")
            else slines.get(s["entity_id"].split(".", 1)[1])
        ) or "?"
        lines.append(
            f"{s['entity_id']}\t{s['state']}\t{ltxt}\t{at.get('mode', '?')}\t{at.get('current', 0)}\t{loc}\t"
            f"{at.get('friendly_name', '')}"
        )
    emit(lines, a.all, what="automations")


def fold(s):
    """æ/ø/å-foldning til ÉN form for både søgeord og id'er: huset staver ø
    som 'oe' i id'er (koekken) men HA-slugify giver 'o' — begge → 'o'."""
    s = s.lower()
    for k, v in (
        ("æ", "ae"),
        ("ø", "o"),
        ("å", "a"),
        ("é", "e"),
        ("ü", "u"),
        ("ö", "o"),
        ("ä", "a"),
    ):
        s = s.replace(k, v)
    return s.replace("oe", "o").replace("aa", "a")


_scan_cache = None


def repo_refs():
    """{entity: [(fil, linje)]} — YAML via gen_docs (samme regler som
    docs/auto, inkl. roster-!include) + scripts/*.py og www/*.js."""
    global _scan_cache
    if _scan_cache is not None:
        return _scan_cache
    refs = {}
    sys.path.insert(0, os.path.join(REPO, "scripts"))
    try:
        import gen_docs

        for ent, locs in gen_docs.scan_codebase()["refs"].items():
            refs[ent] = [(f.replace("\\", "/"), n) for f, n in locs]
        domains = gen_docs.ENTITY_DOMAINS
    except Exception as e:  # noqa: BLE001
        print(f"# gen_docs-scan fejlede ({e}) — kun py/js", file=sys.stderr)
        domains = {
            "sensor",
            "binary_sensor",
            "light",
            "switch",
            "input_boolean",
            "automation",
            "script",
        }
    pat = re.compile(
        r"(?<![A-Za-z0-9_.])(" + "|".join(sorted(domains)) + r")\.([a-z0-9_]+)(?![a-z0-9_])"
    )
    known = set(refs)
    snap = os.path.join(REPO, "config_snapshots", "entity_ids.txt")
    if os.path.exists(snap):
        with open(snap, encoding="utf-8") as f:
            known |= {x.strip() for x in f if x.strip()}
    # Kode: kun et id i en streng ELLER et kendt id — ellers er datetime.now()
    # og time.sleep() "entities". Hele kommentar-linjer springes over.
    for sub, exts in (
        ("scripts", (".py", ".sh", ".ps1")),
        ("www", (".js",)),
        ("addons", (".py", ".sh", ".js")),
    ):
        for dp, dns, fns in os.walk(os.path.join(REPO, sub)):
            dns[:] = [d for d in dns if not d.startswith((".", "__")) and d != "tests"]
            for fn in fns:
                if fn.endswith(exts) and fn != "hq.py":
                    p = os.path.join(dp, fn)
                    with open(p, encoding="utf-8", errors="replace") as f:
                        for n, line in enumerate(f, 1):
                            if line.lstrip().startswith(("#", "//")):
                                continue
                            for m in pat.finditer(line):
                                ent = m.group(0)
                                quoted = m.start() > 0 and line[m.start() - 1] in "'\"`"
                                if not m.group(2).endswith("_") and (ent in known or quoted):
                                    refs.setdefault(ent, []).append((_rel(p), n))
    _scan_cache = refs
    return refs


def dynamic_refs(entity, limit=10):
    """Linjer hvor entity'en kan være bygget af en template:
    `light.koekken_{{ x }}` / `'sensor.stue_' ~ rum`. Præfikset skal være
    ≥ 3 tegn efter domænet, ellers matcher alt."""
    dom, obj = entity.split(".", 1)
    pat = re.compile(
        r"(?<![a-z0-9_])" + re.escape(dom) + r"\.([a-z0-9_]{3,})(?=\{\{|\{%|['\"]\s*~|\s*~)"
    )
    out = []
    for p in _yaml_files(("automations", "packages", "script_pkg", "dashboards", "rosters")):
        with open(p, encoding="utf-8", errors="replace") as f:
            for n, line in enumerate(f, 1):
                for m in pat.finditer(line.split("#", 1)[0] if "{#" not in line else line):
                    if obj.startswith(m.group(1)) and obj != m.group(1):
                        out.append(f"{_rel(p)}:{n}\t{dom}.{m.group(1)}…")
                        break
        if len(out) >= limit:
            break
    return out


def _group_lines(locs):
    by = {}
    for f, n in locs:
        by.setdefault(f, []).append(n)
    lines = []
    for f in sorted(by, key=lambda k: (-len(by[k]), k)):
        ns = sorted(set(by[f]))
        lines.append(
            f"{f}\t{','.join(map(str, ns)) if len(ns) <= 12 else f'{len(ns)} refs, l.{ns[0]}-{ns[-1]}'}"
        )
    return lines


def cmd_where(a, _ha=None):
    refs = repo_refs()
    pat = a.entity
    if any(c in pat for c in "*?["):
        hits = sorted(e for e in refs if fnmatch.fnmatch(e, pat))
        if not hits:
            raise HQError(f"ingen refererede entities matcher {pat}")
        emit(
            [f"{e}\t{len(refs[e])} refs\t{len({f for f, _ in refs[e]})} filer" for e in hits],
            a.all,
            what="entities",
        )
        return
    locs = refs.get(pat, [])
    files = {f for f, _ in locs}
    print(
        f"# {pat}: {len(locs)} refs i {len(files)} filer (YAML uden kommentarer + strenge i scripts/ www/ addons/)"
    )
    if locs:
        emit(_group_lines(locs), a.all, what="filer")
    if "." in pat:
        dyn = dynamic_refs(pat)
        if dyn:
            print("# mulige template-byggede referencer (præfiks-match, verificér):")
            print("\n".join(dyn))


def cmd_find(a, ha_factory):
    words = [fold(w) for w in a.text]
    refs = repo_refs()
    try:
        if a.offline:
            raise HQError("offline")
        ha = ha_factory()
        st = ha.states()
        live = True
    except HQError as e:
        if not a.offline:
            print(
                f"# {e} → offline-søgning (config_snapshots/entity_ids.txt + repo)", file=sys.stderr
            )
        snap = os.path.join(REPO, "config_snapshots", "entity_ids.txt")
        ids = set(refs)
        if os.path.exists(snap):
            with open(snap, encoding="utf-8") as f:
                ids |= {x.strip() for x in f if x.strip()}
        st = [{"entity_id": e, "state": "?", "attributes": {}} for e in sorted(ids)]
        live = False
    hits = []
    for s in st:
        hay = fold(s["entity_id"] + " " + str((s.get("attributes") or {}).get("friendly_name", "")))
        if all(w in hay for w in words):
            hits.append(s)
    if not hits:
        raise HQError("intet match for " + " ".join(a.text))
    hits.sort(key=lambda s: (-len(refs.get(s["entity_id"], [])), s["entity_id"]))
    shown = hits if a.all else hits[:CAP]
    areas = {}
    if live and shown:
        tpl = (
            "{% for e in "
            + json.dumps([s["entity_id"] for s in shown])
            + " %}{{ e }}|{{ area_name(e) or '-' }}\n{% endfor %}"
        )
        try:
            for line in ha.template(tpl).splitlines():
                if "|" in line:
                    e, ar = line.split("|", 1)
                    areas[e.strip()] = ar.strip()
        except HQError:
            pass
    lines = ["# entity\tstate\trum\trepo-refs\tnavn"]
    for s in shown:
        e = s["entity_id"]
        nm = (s.get("attributes") or {}).get("friendly_name", "")
        lines.append(f"{e}\t{s['state']}\t{areas.get(e, '-')}\t{len(refs.get(e, []))}\t{nm}")
    print("\n".join(lines))
    if len(hits) > len(shown):
        print(f"# … +{len(hits) - len(shown)} entities mere (--all, eller flere søgeord)")


def cmd_tmpl(a, ha):
    print(ha.template(a.template))


# ---------------------------------------------------------------- main -----
def build_parser():
    ap = argparse.ArgumentParser(
        prog="hq.py",
        description=__doc__.split("\n\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p, window=None):
        p.add_argument("--all", action="store_true", help="intet 40-linjers loft")
        if window:
            p.add_argument(
                "--since",
                help=f"start: 3d, 12h, 18:00, 2026-10-04 18:00 (lokal) — default {window}",
            )
            p.add_argument("--until", help="slut (default nu)")
        return p

    p = common(sub.add_parser("state", help="state + last_changed + alder"))
    p.add_argument("entities", nargs="+")
    p.add_argument("--attr", help="kommasepareret attribut-liste eller 'all'")

    p = common(sub.add_parser("hist", help="historik: rækker eller fordeling"), "3d")
    p.add_argument("entity")
    p.add_argument("--stats", action="store_true", help="fordeling i stedet for rækker")
    p.add_argument("--rows", action="store_true", help="rækker selv over 200")
    p.add_argument("--gate", type=float, help="tid over/under X + krydsninger")
    p.add_argument("--attr", help="historik for en attribut i stedet for state")

    p = common(sub.add_parser("flanks", help="kun skift, med varighed i forrige state"), "3d")
    p.add_argument("entity")
    p.add_argument("--to")
    p.add_argument("--from", dest="from_")
    p.add_argument("--min-prev", type=parse_dur, help="kun skift hvor forrige state varede ≥ X")

    p = common(sub.add_parser("who", help="hvem/hvad skiftede entity'en (recorder)"), "1d")
    p.add_argument("entity")
    p.add_argument("--attr-changes", action="store_true", help="medtag attribut-opdateringer")
    p.add_argument("--logbook", action="store_true", help="spring ssh over, brug logbogen")
    p.add_argument("--on-nuc", action="store_true", help=argparse.SUPPRESS)

    p = common(sub.add_parser("auto", help="automation/script: state, last_triggered, fil:linje"))
    p.add_argument("pattern")

    p = common(sub.add_parser("find", help="find entity på navn/id (æ/ø/å-foldet)"))
    p.add_argument("text", nargs="+")
    p.add_argument("--offline", action="store_true")

    p = common(sub.add_parser("where", help="fil:linjer i repoet for en entity (offline)"))
    p.add_argument("entity")

    p = sub.add_parser("tmpl", help="render en template via /api/template")
    p.add_argument("template")
    return ap


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError, ValueError:
        pass
    a = build_parser().parse_args(argv)
    try:
        if a.cmd == "who":
            return cmd_who(a, HA, argv) or 0
        if a.cmd == "where":
            cmd_where(a)
        elif a.cmd == "find":
            cmd_find(a, HA)
        else:
            {
                "state": cmd_state,
                "hist": cmd_hist,
                "flanks": cmd_flanks,
                "auto": cmd_auto,
                "tmpl": cmd_tmpl,
            }[a.cmd](a, HA())
    except HQError as e:
        print(f"hq: {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
