"""Øvelsesbilleder: `billede:`-feltet i program.yaml → URL'er under /local.

  billede: Dead_Bug                  → alle frames i www/oevelser/Dead_Bug/
  billede: Dead_Bug/0                → kun frame 0

Filer der ikke findes udelades tavst (kortet viser så bare intet billede).
Fotos: free-exercise-db (github.com/yuhonas/free-exercise-db), The Unlicense.
"""

from __future__ import annotations

import os
from pathlib import Path

WWW = Path(os.environ.get("OEVELSE_WWW", "/config/www/oevelser"))
URL = "/local/oevelser"


def billeder(spec) -> list[str]:
    if not spec:
        return []
    spec = str(spec).strip("/")
    if spec.startswith("egne/"):
        navn = spec.split("/", 1)[1]
        filer = sorted((WWW / "egne").glob(f"{navn}_*.svg"))
        return [f"{URL}/egne/{f.name}" for f in filer]
    mappe, _, frame = spec.partition("/")
    if frame:
        filer = [WWW / mappe / f"{frame}.jpg"]
    else:
        filer = sorted((WWW / mappe).glob("*.jpg"))
    return [f"{URL}/{mappe}/{f.name}" for f in filer if f.exists()]
