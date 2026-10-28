#!/usr/bin/env python3
"""Hvem skriver til NUC'ens disk? GB/døgn pr. cgroup over et måle-vindue (B273).

Docker-API'ets blkio dækker kun containerne; hostens journald, dockerd og
kernens ext4-journal står ingen steder. Scriptet starter derfor en kortlivet
container fra SSH-add-on'ets eget image med `--cgroupns=host` og læser
`wbytes` fra hver `io.stat` i hostens cgroup-træ — kun læsning, containeren
slettes igen (`--rm`). Målt 28/10: summen går op i sda's sektor-tæller.

  python3 scripts/nuc_skrivere.py [sekunder=120]

"kernel uden ejer" = roden minus system.slice (jbd2 + write-back hvis ejer-
cgroup er død, fx lige efter en HA-restart). Korte vinduer svinger meget
(recorder-checkpoints, restore_state hvert 15. min) — sammenlign kun vinduer
af samme længde og helst samme tid på døgnet.
"""

import subprocess
import sys
import time

SCAN = (
    "cd /sys/fs/cgroup; for f in $(find . -name io.stat); do "
    'awk -v p="$f" \'{for(i=2;i<=NF;i++) if($i ~ /^wbytes=/){split($i,a,"="); s+=a[2]}} '
    "END{print s+0, p}' $f; done"
)


def sh(*cmd):
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout


def cgroups(image):
    out = sh("docker", "run", "--rm", "--cgroupns=host", "--entrypoint", "sh", image, "-c", SCAN)
    return {
        p.removeprefix("./").removesuffix("/io.stat").removesuffix("io.stat") or "/": int(v)
        for v, p in (line.split(None, 1) for line in out.splitlines() if line.strip())
    }


def sda():
    with open("/sys/block/sda/stat") as f:
        return int(f.read().split()[6]) * 512


def main():
    secs = int(sys.argv[1]) if len(sys.argv) > 1 else 120
    image = sh("docker", "inspect", "app_a0d7b954_ssh", "--format", "{{.Config.Image}}").strip()
    names = dict(
        line.split(None, 1)
        for line in sh("docker", "ps", "--no-trunc", "--format", "{{.ID}} {{.Names}}").splitlines()
    )
    a, sa, ta = cgroups(image), sda(), time.time()
    time.sleep(secs)
    b, sb, tb = cgroups(image), sda(), time.time()
    rate = 86400 / (tb - ta) / 1e9

    def navn(path):
        leaf = path.rsplit("/", 1)[-1]
        if leaf.startswith("docker-") and leaf.endswith(".scope"):
            return names.get(leaf[7:-6], leaf[7:19])
        return leaf.removesuffix(".service")

    d = {k: b[k] - a.get(k, 0) for k in b}
    rows = [(v, navn(k)) for k, v in d.items() if k.startswith("system.slice/") and v > 0]
    rows.append((d.get("/", 0) - d.get("system.slice", 0), "kernel uden ejer (jbd2, døde cgroups)"))
    print(
        f"sda {(sb - sa) * rate:.2f} GB/døgn over {tb - ta:.0f} s (cgroup-sum {d.get('/', 0) * rate:.2f})"
    )
    for v, n in sorted(rows, reverse=True):
        if v * rate >= 0.01:
            print(f"{v * rate:7.2f} GB/døgn  {n}")


if __name__ == "__main__":
    main()
