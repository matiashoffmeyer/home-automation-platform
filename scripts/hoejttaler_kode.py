#!/usr/bin/env python3
"""hoejttaler_kode.py — skift højttalerens SSH-kode uden at nogen ser den (B297, 2026-11-05)

User 5/11: "b297 skift bare højttaler koden, du har ssh adgang til den. intet jeg
skal gøre." Kontoen `volumio` kom med producentens offentligt kendte kode.

Volumio har den kode skrevet ind fire steder (målt 5/11): pluginmanager.js
(`sudo -S sh <plugin>/install.sh` og `uninstall.sh`) og mpd/index.js (`sudo -S
/bin/cp` af mpd-binæren, når SACD-ISO-valget skiftes; mpd er stoppet forinden, så et
afvist kald efterlader den stoppet). De fire får kodeløs sudo i
/etc/sudoers.d/zz_hus_b297. Det er ingen ny rettighed: fabriks-sudoers giver i
forvejen `volumio` kodeløs systemctl/mv/dd. Filen skal sortere EFTER `volumio-user`,
for sudo bruger den sidste regel der passer, og dér står `(ALL) ALL` med kode.

Rækkefølgen holder login åbent hele vejen:
  1. root-session med den gamle kode: installerer sudoers-filen (visudo-tjekket),
     prøver den, sætter den nye kode og venter på "ok" på stdin. Kommer det ikke
     inden VENT s, eller dør forbindelsen, sætter sessionen selv den gamle kode igen.
  2. NYT login med den nye kode + sudo → `id -u` = 0.
  3. ha_secrets.put (den gamle fil bliver secrets.yaml.prev), FØRST derefter "ok".
Værdierne går kun over stdin og askpass-hjælperen, aldrig i argv (hverken her eller
på højttaleren) og aldrig på skærmen.

  python3 hoejttaler_kode.py     # skift; skriver hvad der skete, aldrig koden

Bagefter: `python3 hoejttaler_bt.py status`. Fabriks-nulstilles højttaleren, har
den producentens kode igen (og en ny værtsnøgle), se B297.
Exit 0 = skiftet og gemt, 1 = ikke skiftet (højttaleren har den gamle), 2 = brug.
"""

from __future__ import annotations

import fcntl
import os
import queue
import shlex
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path

HER = Path(__file__).resolve().parent
sys.path.insert(0, str(HER))
import ha_secrets  # noqa: E402
import hoejttaler_bt as hb  # noqa: E402
import secret_set  # noqa: E402

KEY = "hoejttaler_ssh_password"
ENV = "HOEJTTALER_KODE"  # kun i miljøet til ssh'ens askpass-hjælper
LAENGDE = 32
VENT = 90  # s højttaleren venter på "ok", før den sætter den gamle kode igen
SUDOERS_FIL = "/etc/sudoers.d/zz_hus_b297"

# ASCII: sudo 1.8.19 skal kunne læse den.
SUDOERS = """\
# B297 (2026-11-05, /config/scripts/hoejttaler_kode.py): the volumio password was
# changed, but Volumio hardcodes the factory password in these calls
# (pluginmanager.js, mpd/index.js). No new right: volumio-user already grants
# passwordless systemctl/mv/dd. Must sort after volumio-user (last match wins).
volumio ALL=(ALL) NOPASSWD: /bin/cp -f /usr/bin/mpdsacd /usr/bin/mpd, \
/bin/cp -f /usr/bin/mpdorig /usr/bin/mpd, \
/bin/sh /data/plugins/*/install.sh, /bin/sh /data/plugins/*/uninstall.sh, \
/bin/sh /data/temp/*/install.sh
"""

# Kører som root på højttaleren (bash: `read -t`). stdin: gammel (til sudo), gammel,
# ny, og senere "ok". trap: en død forbindelse må ikke dræbe den, før den har sat
# den gamle kode igen.
ENHED = r"""trap '' PIPE HUP
IFS= read -r OLD; IFS= read -r NEW
[ ${#NEW} -ge 20 ] || { echo FEJL=ny_kode_mangler; exit 3; }
f=__FIL__; t=$(mktemp)
cat > "$t" <<'SUDOERS_SLUT'
__SUDOERS__
SUDOERS_SLUT
visudo -cqf "$t" && install -m 0440 -o root -g root "$t" "$f"; rm -f "$t"
[ -f "$f" ] && visudo -cq || { rm -f "$f"; echo FEJL=sudoers; exit 3; }
r=$(su -s /bin/sh volumio -c 'sudo -k; sudo -n /bin/sh /data/temp/zz_b297_findes_ikke/install.sh' </dev/null 2>&1)
case "$r" in *password*) rm -f "$f"; echo FEJL=sudoers_virker_ikke; exit 3;; esac
printf 'volumio:%s\n' "$NEW" | chpasswd || { echo FEJL=chpasswd; exit 3; }
echo SAT=ja
IFS= read -r -t __VENT__ SVAR
if [ "$SVAR" = ok ]; then echo SLUT=ny; exit 0; fi
printf 'volumio:%s\n' "$OLD" | chpasswd && echo SLUT=gammel || echo SLUT=FEJL_gammel
exit 1
"""


def enhed_script() -> str:
    return (
        ENHED.replace("__FIL__", SUDOERS_FIL)
        .replace("__SUDOERS__", SUDOERS.rstrip("\n"))
        .replace("__VENT__", str(VENT))
    )


def miljoe(d: str, kode: str) -> dict[str, str]:
    return {**hb.askpass_env(d, Path(__file__).resolve()), ENV: kode}


def vent_paa(linjer: queue.Queue, prefixes: tuple[str, ...], sek: float) -> str | None:
    """Første linje der starter med et af prefixes; None ved EOF eller timeout."""
    while True:
        try:
            linje = linjer.get(timeout=sek)
        except queue.Empty:
            return None
        if linje is None:
            return None
        if linje.startswith(prefixes):
            return linje


def login_virker(d: str, kode: str) -> bool:
    r = subprocess.run(
        hb.ssh_argv("sudo -S -p '' id -u"),
        input=kode + "\n",
        capture_output=True,
        text=True,
        timeout=30,
        env=miljoe(d, kode),
    )
    return r.returncode == 0 and r.stdout.strip() == "0"


def skift(gammel: str, ny: str, gem: Callable[[str], object]) -> tuple[bool, str]:
    """Sæt `ny` på højttaleren, bevis login med den, gem, bekræft. (ok, hvad der skete)"""
    with tempfile.TemporaryDirectory(dir=hb.cache_dir()) as d:
        p = subprocess.Popen(
            hb.ssh_argv("sudo -S -p '' bash -c " + shlex.quote(enhed_script())),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=miljoe(d, gammel),
        )
        linjer: queue.Queue = queue.Queue()

        def laes():
            for linje in p.stdout:
                linjer.put(linje.strip())
            linjer.put(None)

        threading.Thread(target=laes, daemon=True).start()
        svar = "nej"
        try:
            p.stdin.write(f"{gammel}\n{gammel}\n{ny}\n")
            p.stdin.flush()
            sat = vent_paa(linjer, ("SAT=", "FEJL="), 40)
            if sat != "SAT=ja":
                return False, f"højttaleren satte ikke koden ({sat or 'intet svar'})"
            if not login_virker(d, ny):
                return False, "login med den nye kode virkede ikke; den gamle sættes igen"
            try:
                gem(ny)
            except (OSError, ValueError) as e:  # put nævner nøglen, aldrig værdien
                return False, f"kunne ikke gemme ({e}); den gamle sættes igen"
            svar = "ok"
        finally:
            try:
                p.stdin.write(svar + "\n")
                p.stdin.close()
            except OSError:
                pass  # forbindelsen er død → højttaleren sætter selv den gamle
            slut = vent_paa(linjer, ("SLUT=",), 30)
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()  # lukker forbindelsen → højttaleren sætter den gamle igen
                p.wait(timeout=10)
        if slut == "SLUT=ny":
            return True, "ny kode sat, login + sudo prøvet med den, gemt"
        # Gemt, men bekræftelsen kom ikke tilbage: sessionen er slut, så højttaleren
        # fik enten "ok" eller satte selv den gamle igen. Spørg den i stedet for at gætte.
        time.sleep(3)
        if login_virker(d, ny):
            return True, "ny kode sat og gemt (bekræftelsen gik tabt; login med den virker)"
        if login_virker(d, gammel):
            gem(gammel)
            return False, "højttaleren satte den gamle igen; den er gemt igen"
        return False, (
            "UKENDT: hverken ny eller gammel kode logger ind; den nye er gemt, "
            "den gamle ligger i secrets.yaml.prev (B297)"
        )


def main(argv: list[str]) -> int:
    if argv == ["askpass"]:
        print(os.environ[ENV])
        return 0
    if argv:
        print("brug: hoejttaler_kode.py", file=sys.stderr)
        return 2
    gammel = ha_secrets.get(KEY)
    ny = secret_set.make("alnum", LAENGDE)
    with open(hb.LAAS, "w") as laas:
        fcntl.flock(laas, fcntl.LOCK_EX)
        try:
            hb.ssh_aaben(True)
            if not hb.port_22(True, 12):
                ok, hvad = False, "SSH åbnede ikke"
            else:
                ok, hvad = skift(gammel, ny, lambda v: ha_secrets.put(KEY, v))
        finally:
            hb.ssh_aaben(False)
            lukket = hb.port_22(False, 8)
    print(("SKIFTET: " if ok else "IKKE SKIFTET: ") + hvad)
    if not lukket:
        print("ADVARSEL: SSH står stadig åben på højttaleren")
    if ok:
        secret_set.logbook(f"{KEY}: ny tilfældig kode ({LAENGDE} tegn) sat på højttaleren")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
