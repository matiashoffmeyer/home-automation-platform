#!/usr/bin/env python3
"""One Home Assistant-compatible slugify for every repository script (standard library only).

The same rule used to exist in three places, and the copies disagreed (failure
class #2, inside the tooling itself): one scanner turned "å" into "aa" where
Home Assistant writes "a"; two other tools each had a hand-written table; and
one validator treated ``sensor.<unique_id>`` as defined, although the entity id
is derived from ``name:``, which hid exactly the slug errors it should have
caught.

Home Assistant's own function is ``homeassistant.util.slugify``, which calls
python-slugify (``separator="_"``) on top of text-unidecode. This module
reproduces it for every character the house uses, and ``--verify`` proves that
against the real function over every ``name:`` and ``alias:`` in the
repository (this needs Home Assistant's venv:
``python3 scripts/ha_offline.py slugcheck``).

Use from other scripts::

  sys.path.insert(0, os.path.dirname(__file__)); from ha_slug import slugify
"""

from __future__ import annotations

import re
import unicodedata

# Tegn hvor NFKD-dekomposition IKKE giver det unidecode giver. Kun det huset
# faktisk skriver i navne — udvid her (og kør --verify), ikke i kalderen.
_TRANSLIT = {
    "æ": "ae",
    "Æ": "AE",
    "ø": "o",
    "Ø": "O",
    "å": "a",
    "Å": "A",
    "ß": "ss",
    "ð": "d",
    "þ": "th",
    "đ": "d",
    "ł": "l",
    "œ": "oe",
    "–": "-",
    "—": "-",
    "×": "x",
    "°": "deg",
    "²": "2",
    "³": "3",
    "½": "1/2",
    # Pile og sammenligninger er SEPARATORER hos unidecode ("→" = "->"), ikke
    # tomme: "top→bund" bliver top_bund, ikke topbund (målt mod HA 2026.9.2).
    "→": "->",
    "←": "<-",
    "↔": "<->",
    "⇒": "=>",
    "≥": ">=",
    "≤": "<=",
    "≠": "!=",
    "≈": "~",
    "·": "*",
    "…": "...",
    # Græsk (Σ pære-timer → s_paere_timer)
    "Σ": "S",
    "σ": "s",
    "Δ": "D",
    "δ": "d",
    "μ": "m",
    "µ": "m",
    "π": "p",
    "λ": "l",
    "α": "a",
    "β": "b",
    "γ": "g",
    "Ω": "O",
    "ω": "o",
}
_QUOTE = re.compile(r"[']+")
_NUM_COMMA = re.compile(r"(?<=\d),(?=\d)")
_DISALLOWED = re.compile(r"[^-a-zA-Z0-9]+")
_DUP_DASH = re.compile(r"-{2,}")


def slugify(text: str | None) -> str:
    """HA's slugify (homeassistant.util.slugify) for repoets navne."""
    if text is None or text == "":
        return ""
    t = _QUOTE.sub("-", str(text))
    t = "".join(_TRANSLIT.get(c, c) for c in t)
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.encode("ascii", "ignore").decode("ascii")  # emoji m.m. forsvinder
    t = t.lower()
    t = _NUM_COMMA.sub("", t)
    t = _DISALLOWED.sub("-", t)
    t = _DUP_DASH.sub("-", t).strip("-")
    slug = t.replace("-", "_")
    return slug or "unknown"


if __name__ == "__main__":
    import sys

    for arg in sys.argv[1:]:
        print(slugify(arg))
