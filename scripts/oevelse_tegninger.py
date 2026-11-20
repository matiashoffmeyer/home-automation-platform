"""Stregtegninger til øvelser, hvor fotoet ikke viser øvelsen som beskrevet.

User 19/11: "billeder til øvelserne passer ikke altid til øvelserne som beskrevet.
hellere tegninger end forkert billede." Samme stil som de håndtegnede birddog/curlup/
aflastning: 300x200, mørk streg, rødt = det der bevæger sig/det der er pointen,
tekst øverst. Skriver <navn>_<n>.svg; `billede: egne/<navn>` i programmet.

  python3 scripts/oevelse_tegninger.py [ud-mappe] [navn ...]
  (default: www/oevelser/egne, alle). Helbred-kittet: deling/helbred_kit/www/oevelser/egne
"""

import sys
from pathlib import Path

OUT = (
    Path(sys.argv[1])
    if len(sys.argv) > 1
    else Path(__file__).resolve().parent.parent / "www/oevelser/egne"
)
KUN = set(sys.argv[2:])
BG, MAT, FLOOR, INK, RED, WOOD = "#f4f1ea", "#5b7bb5", "#9a9a9a", "#333", "#c0392b", "#8a6d3b"


def svg(cap, body, floor="mat", cap_x=150, size=16):
    f = {
        "mat": f'<rect x="20" y="170" width="260" height="8" rx="3" fill="{MAT}"/>',
        "gulv": f'<rect x="20" y="170" width="260" height="8" rx="3" fill="{FLOOR}"/>',
        None: "",
    }[floor]
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 200" width="300" height="200">'
        f'<rect width="300" height="200" fill="{BG}"/>{f}{body}'
        f'<text x="{cap_x}" y="30" font-family="sans-serif" font-size="{size}" text-anchor="middle" fill="{INK}">{cap}</text></svg>'
    )


def fig(*parts):
    """parts: ('h', x, y[, r]) head, or a path string, or (path, colour)."""
    out = []
    for p in parts:
        if isinstance(p, tuple) and p[0] == "h":
            r = p[3] if len(p) > 3 else 13
            out.append(f'<circle cx="{p[1]}" cy="{p[2]}" r="{r}" fill="{INK}"/>')
        elif isinstance(p, tuple):
            out.append(f'<path d="{p[0]}" stroke="{p[1]}"/>')
        else:
            out.append(f'<path d="{p}"/>')
    return f'<g stroke="{INK}" stroke-width="7" stroke-linecap="round" stroke-linejoin="round" fill="none">{"".join(out)}</g>'


def wood(d, w=6):
    return f'<g stroke="{WOOD}" stroke-width="{w}" fill="none" stroke-linecap="round"><path d="{d}"/></g>'


def kb(x, y, r=9):  # kettlebell: ball + handle
    return (
        f'<circle cx="{x}" cy="{y}" r="{r}" fill="{INK}"/>'
        f'<path d="M{x - 6} {y - r + 2} Q{x} {y - r - 9} {x + 6} {y - r + 2}" stroke="{INK}" stroke-width="3" fill="none"/>'
    )


def plate(x, y):  # barbell from the side
    return f'<circle cx="{x}" cy="{y}" r="15" fill="none" stroke="{INK}" stroke-width="5"/><circle cx="{x}" cy="{y}" r="3" fill="{INK}"/>'


D = {}
# Bench press, feet UP on the bench so the lower back lies flat.
bench = wood("M45 130 L250 130 M65 130 L65 170 M230 130 L230 170", 7)
D["baenkpres_0"] = svg(
    "Fødderne oppe på bænken, lænden flad",
    bench
    + fig(
        ("h", 66, 112),
        "M82 120 L170 120",
        ("M170 120 L200 86 L232 124", RED),
        "M95 120 L97 92 L96 66",
    )
    + plate(96, 58),
    floor=None,
)
D["baenkpres_1"] = svg(
    "Stangen ned mod brystet, pres op",
    bench
    + fig(
        ("h", 66, 112),
        "M82 120 L170 120",
        "M170 120 L200 86 L232 124",
        ("M95 120 L124 124 L118 100", RED),
    )
    + plate(118, 92),
    floor=None,
)

# Half-kneeling kettlebell press.
D["kbpres_0"] = svg(
    "Ét knæ i gulvet, ballen spændt",
    fig(
        ("h", 128, 72, 12),
        "M115 90 L115 134",
        ("M115 134 L113 166 L78 167", RED),
        "M115 134 L152 134 L154 167",
        "M115 92 L126 114 L132 98",
    )
    + kb(140, 99, 8),
)
D["kbpres_1"] = svg(
    "Pres lige op, ribbenene nede",
    fig(
        ("h", 128, 72, 12),
        "M115 90 L115 134",
        "M115 134 L113 166 L78 167",
        "M115 134 L152 134 L154 167",
        ("M113 92 L104 70 L100 50", RED),
    )
    + kb(92, 55, 8),
)

# Hang from a bar, legs heavy and a little in front.
bar = wood("M50 48 L250 48 M60 48 L60 190 M240 48 L240 190", 7)
D["haeng_0"] = svg(
    "Hæng løst, benene tunge lidt foran dig",
    bar
    + fig(
        "M140 50 L140 84",
        ("h", 153, 80, 12),
        "M140 84 L141 124",
        ("M141 124 L150 152 L150 182", RED),
    )
    + f'<rect x="20" y="190" width="260" height="6" rx="3" fill="{FLOOR}"/>',
    floor=None,
)

# Goblet squat down to a light touch on a box.
box = f'<rect x="66" y="134" width="40" height="36" fill="{WOOD}"/>'
D["gobletkasse_0"] = svg(
    "Vægten foran brystet, kassen bag dig",
    box
    + fig(("h", 126, 50, 12), "M130 168 L128 138 L125 108 L125 68", "M125 70 L133 92 L140 78")
    + kb(147, 80),
    floor="gulv",
)
D["gobletkasse_1"] = svg(
    "Ned til let berøring, ryggen lige",
    box
    + fig(
        ("h", 131, 76, 12),
        "M128 168 L132 138 L104 128",
        ("M104 128 L122 92", RED),
        "M122 94 L134 110 L142 96",
    )
    + kb(149, 98),
    floor="gulv",
)

# Suitcase carry: weight in ONE hand, walk upright (front view).
D["kuffert_0"] = svg(
    "Vægten i ÉN hånd, gå helt lodret",
    fig(
        ("h", 150, 50, 12),
        "M128 68 L172 68",
        "M150 68 L150 110",
        "M138 110 L162 110",
        "M140 110 L136 168",
        "M160 110 L164 168",
        "M128 68 L124 112",
        "M172 68 L176 114",
    )
    + kb(178, 128, 10)
    + f'<path d="M150 36 L150 168" stroke="{RED}" stroke-width="2" stroke-dasharray="5 5"/>',
    floor="gulv",
)


# Backpack curl: both hands on the top handle, elbows at the sides.
def pack(x, y):
    return f'<rect x="{x - 13}" y="{y}" width="26" height="32" rx="6" fill="{WOOD}"/><path d="M{x - 5} {y} L{x - 5} {y - 5} L{x + 5} {y - 5} L{x + 5} {y}" stroke="{WOOD}" stroke-width="3" fill="none"/>'


D["rygsaekcurl_0"] = svg(
    "Begge hænder i top-hanken",
    fig(("h", 140, 50, 12), "M140 168 L140 138 L140 108 L140 68", "M140 70 L142 96 L146 120")
    + pack(146, 125),
    floor="gulv",
)
D["rygsaekcurl_1"] = svg(
    "Albuerne ved siden, curl op",
    fig(
        ("h", 140, 50, 12),
        "M140 168 L140 138 L140 108 L140 68",
        "M140 70 L142 96",
        ("M142 96 L166 80", RED),
    )
    + pack(168, 85),
    floor="gulv",
)

# Push-ups on the knees.
D["armbknae_0"] = svg(
    "På knæ, lige linje fra knæ til hoved",
    fig(("h", 84, 106), ("M98 116 L190 164", RED), "M190 164 L236 166", "M100 117 L100 166"),
)
D["armbknae_1"] = svg(
    "Brystet ned mod måtten, pres op",
    fig(
        ("h", 82, 138), "M98 146 L190 164", "M190 164 L236 166", ("M100 147 L126 128 L104 166", RED)
    ),
)

# High plank with shoulder taps.
D["skulderklap_0"] = svg(
    "Høj planke på strakte arme", fig(("h", 82, 106), "M98 116 L238 166", "M100 117 L100 166")
)
D["skulderklap_1"] = svg(
    "Klap modsat skulder, hoften i ro",
    fig(
        ("h", 82, 106), "M98 116 L238 166", "M100 117 L100 166", ("M100 117 L128 150 L112 124", RED)
    ),
)

# Superman: lift a few centimetres, not more.
D["superman_0"] = svg(
    "På maven, armene frem", fig(("h", 62, 152), "M78 160 L170 160 L258 163", "M84 162 L26 163")
)
D["superman_1"] = svg(
    "Løft arme, bryst og ben et par cm",
    fig(("h", 64, 146), "M80 154 L170 160", ("M170 160 L258 152", RED), ("M86 156 L28 148", RED)),
)

# Mountain climbers: high plank, hip LOW.
D["mountain_0"] = svg(
    "Høj planke, hoften lav", fig(("h", 82, 106), "M98 116 L238 166", "M100 117 L100 166")
)
D["mountain_1"] = svg(
    "Skiftevis knæ op mod brystet, roligt",
    fig(
        ("h", 82, 106), "M98 116 L238 166", "M100 117 L100 166", ("M168 141 L132 146 L156 166", RED)
    ),
)

# Flutter kicks on the back.
D["flutter_0"] = svg(
    "På ryggen, hænderne under ballerne",
    fig(
        ("h", 54, 152),
        "M70 160 L150 160",
        "M80 161 L146 165",
        "M150 160 L262 146",
        ("M150 160 L262 156", RED),
    ),
)
D["flutter_1"] = svg(
    "Små skiftevise spark, lænden nede",
    fig(
        ("h", 54, 152),
        "M70 160 L150 160",
        "M80 161 L146 165",
        "M150 160 L262 156",
        ("M150 160 L262 142", RED),
    ),
)

# Side-lying leg raise.
D["sideben_0"] = svg(
    "På siden, kroppen lige",
    fig(
        ("h", 54, 140),
        "M60 162 L72 140",
        "M70 156 L160 158 L262 162",
        "M160 154 L262 154",
        "M88 150 L124 144",
    ),
)
D["sideben_1"] = svg(
    "Øverste ben skråt op, langsomt ned",
    fig(
        ("h", 54, 140),
        "M60 162 L72 140",
        "M70 156 L160 158 L262 162",
        ("M160 154 L248 112", RED),
        "M88 150 L124 144",
    ),
)

# Kit variant: bottom leg bent, top leg up and a little back.
D["sidebenbagud_0"] = svg(
    "På siden, nederste ben bøjet",
    fig(
        ("h", 54, 140),
        "M60 162 L72 140",
        "M70 156 L160 158 L210 140 L250 162",
        "M160 154 L262 154",
        "M88 150 L124 144",
    ),
)
D["sidebenbagud_1"] = svg(
    "Øverste ben skråt op og lidt bagud",
    fig(
        ("h", 54, 140),
        "M60 162 L72 140",
        "M70 156 L160 158 L210 140 L250 162",
        ("M160 154 L244 118", RED),
        "M88 150 L124 144",
    ),
)

# Calf raise with the forefoot on the edge of a step, hand on the railing.
step = f'<rect x="66" y="150" width="150" height="20" fill="{WOOD}"/>' + wood("M104 150 L104 52", 5)
D["taahaev_0"] = svg(
    "Hælen ned under trinet",
    step
    + fig(
        ("h", 69, 54, 11),
        ("M58 158 L84 150", RED),
        "M63 154 L64 124 L64 100 L66 68",
        "M66 70 L80 88 L100 82",
    ),
    floor="gulv",
    cap_x=195,
)
D["taahaev_1"] = svg(
    "Langsomt op på tæerne",
    step
    + fig(
        ("h", 73, 34, 11),
        ("M68 136 L84 150", RED),
        "M70 134 L68 104 L68 80 L70 48",
        "M70 50 L84 68 L100 62",
    ),
    floor="gulv",
    cap_x=195,
)

# Stair intervals (Parent B, user 19/11): briskly up, calmly down. Steps rise to the right.
trappe = (
    f'<path d="M60 170 L60 152 L100 152 L100 134 L140 134 L140 116 L180 116 '
    f'L180 98 L280 98 L280 170 Z" fill="{WOOD}"/>'
)
D["trappe_0"] = svg(
    "Op i rask tempo",
    trappe
    + fig(
        ("h", 116, 52, 11),
        "M84 152 L92 128 L100 104",
        ("M100 104 L124 110 L122 134", RED),
        "M100 104 L112 66",
        "M111 70 L126 86 L138 76",
        "M111 70 L98 88 L88 98",
    ),
    floor="gulv",
)
D["trappe_1"] = svg(
    "Gå roligt ned: det er pausen",
    trappe
    + fig(
        ("h", 98, 52, 11),
        "M100 104 L112 118 L120 134",
        ("M100 104 L88 128 L80 152", RED),
        "M100 104 L99 66",
        "M99 70 L94 88 L98 104",
    ),
    floor="gulv",
)

OUT.mkdir(parents=True, exist_ok=True)
n = 0
for k, v in D.items():
    if KUN and k.rsplit("_", 1)[0] not in KUN:
        continue
    (OUT / f"{k}.svg").write_text(v)
    n += 1
print(n, "tegninger →", OUT)
