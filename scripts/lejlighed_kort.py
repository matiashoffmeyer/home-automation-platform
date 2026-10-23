#!/usr/bin/env python3
"""Plantegningen under netværks-kortene — rummene fra Roborock-kortet.

Roborock-integrationen cacher robottens seneste kort i .storage/roborock/<entry>
(`homeMapContentBase64`). Billed-blokken har én byte pr. 5 cm-pixel, og en
rum-pixel bærer sit segment-nummer (`p & 7 == 7` → `p >> 3`). Scriptet:

  1. fylder hvert rum ud til dets bounding box (møbler, sengen og væggene
     ser robotten ikke som gulv) — en pixel går til det nærmeste rum,
  2. glatter i 10 cm-celler og sporer omridset; grænsen mellem to rum
     forenkles ÉN gang, så nabo-rummene deler præcis samme streg,
  3. finder et midtpunkt, ankre til enhederne, kant-punkter og døre
     (hvor to rums gulv-pixels rører hinanden direkte = en åben dør),

og skriver www/lejlighed-geometri.js (window.lejlighedGeometri, robottens mm).
Tegning og hvem-hænger-hvor står i www/lejlighed-kort.js.

  python3 scripts/lejlighed_kort.py            # skriv filen
  python3 scripts/lejlighed_kort.py --json     # kun print (tjek uden at skrive)

Kør igen når robotten har fået et nyt kort (rum delt eller flyttet i app'en),
og derefter `python3 scripts/lovelace_resources.py`.
"""

from __future__ import annotations

import argparse
import base64
import glob
import gzip
import hashlib
import json
import os
from collections import Counter, deque

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UD = os.path.join(ROOT, "www", "lejlighed-geometri.js")

MM = 50  # mm pr. pixel i robottens billede
C = 2  # pixels pr. celle → 10 cm
EPS = 0.75  # Douglas-Peucker i celler: retter 10 cm-trappetrin ud, holder hjørner

# Segment → (nøgle, navn). Numrene: packages/roborock_rum_scripts.yaml
# (roborock.get_maps) — deler user et rum i app'en, får det et nyt nummer.
SEGMENTER = {
    16: ("spisestue", "Spisestue"),
    17: ("boern", "Børneværelse"),
    18: ("bad", "Bad"),
    19: ("sove", "Soveværelse"),
    21: ("entre", "Entré"),
    22: ("depot", "Depot"),
    23: ("stue", "Stue"),
    24: ("tek", "Tek"),
    25: ("koekken", "Køkken"),
}
# Terrassen kører robotten aldrig på: et tegnet felt langs stuens vestvæg.
TERRASSE = 99
TERRASSE_BREDDE = 15  # celler
TERRASSE_LUFT = 2


def _i(b: bytes, a: int, n: int = 4) -> int:
    return int.from_bytes(b[a : a + n], "little")


def laes_kort(sti: str) -> tuple[int, int, int, int, bytes]:
    dev = next(iter(json.load(open(sti))["data"]["deviceInfo"].values()))
    raw = base64.b64decode(dev["homeMapContentBase64"]["0"])
    if raw[:2] != b"rr":
        raw = gzip.decompress(raw)
    pos = _i(raw, 2, 2)
    while pos < len(raw):
        hlen, typ, dlen = _i(raw, pos + 2, 2), _i(raw, pos, 2), _i(raw, pos + 4)
        if typ == 2:  # billedet
            top, left, h, w = (_i(raw, pos + hlen - k) for k in (16, 12, 8, 4))
            return left, top, w, h, raw[pos + hlen : pos + hlen + dlen]
        pos += hlen + dlen
    raise SystemExit("ingen billed-blok i Roborock-kortet")


def komponenter(lab: list[int], w: int, h: int, hvem) -> list[tuple[int, list[int]]]:
    """4-forbundne komponenter af ens label hvor hvem(label) er sand."""
    set_ = bytearray(w * h)
    ud = []
    for s in range(w * h):
        if set_[s] or not hvem(lab[s]):
            continue
        L, kø, del_ = lab[s], deque([s]), []
        set_[s] = 1
        while kø:
            i = kø.popleft()
            del_.append(i)
            x, y = i % w, i // w
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if 0 <= nx < w and 0 <= ny < h:
                    j = nx + ny * w
                    if not set_[j] and lab[j] == L:
                        set_[j] = 1
                        kø.append(j)
        ud.append((L, del_))
    return ud


def rum_pixels(w: int, h: int, data: bytes) -> list[int]:
    lab = [0] * (w * h)
    for i, p in enumerate(data):
        if p & 7 == 7 and p not in (0x07, 0xFF) and (p >> 3) in SEGMENTER:
            lab[i] = p >> 3
    # Løse øer (< 0,1 m²) er støj — de ville puste rummets box op.
    for _, del_ in komponenter(lab, w, h, bool):
        if len(del_) < 40:
            for i in del_:
                lab[i] = 0
    return lab


def fyld_bokse(lab: list[int], w: int, h: int) -> list[int]:
    """Hver pixel i et rums box går til det nærmeste rum hvis box den ligger i."""
    boks: dict[int, list[int]] = {}
    for i, L in enumerate(lab):
        if L:
            x, y = i % w, i // w
            b = boks.setdefault(L, [x, y, x, y])
            b[0], b[1], b[2], b[3] = min(b[0], x), min(b[1], y), max(b[2], x), max(b[3], y)
    bedst = [(1 << 30, 0)] * (w * h)
    for L, (x0, y0, x1, y1) in boks.items():
        dist = {}
        kø = deque()
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                if lab[x + y * w] == L:
                    dist[(x, y)] = 0
                    kø.append((x, y))
        while kø:
            x, y = kø.popleft()
            d = dist[(x, y)] + 1
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    n = (x + dx, y + dy)
                    if x0 <= n[0] <= x1 and y0 <= n[1] <= y1 and n not in dist:
                        dist[n] = d
                        kø.append(n)
        for (x, y), d in dist.items():
            i = x + y * w
            if (d, L) < bedst[i]:
                bedst[i] = (d, L)
    return [L for _, L in bedst]


def celler(fyld: list[int], w: int, h: int) -> tuple[list[int], int, int]:
    cw, ch = (w + C - 1) // C, (h + C - 1) // C
    g = [0] * (cw * ch)
    for cy in range(ch):
        for cx in range(cw):
            t = Counter(
                fyld[x + y * w]
                for x in range(cx * C, min(w, cx * C + C))
                for y in range(cy * C, min(h, cy * C + C))
            )
            g[cx + cy * cw] = max(t, key=lambda L: (t[L], L != 0, -L))
    # 3×3-flertal mod pixel-flimmer langs grænserne.
    ny = g[:]
    for cy in range(ch):
        for cx in range(cw):
            t = Counter(
                g[x + y * cw]
                for x in range(max(0, cx - 1), min(cw, cx + 2))
                for y in range(max(0, cy - 1), min(ch, cy + 2))
            )
            L, n = t.most_common(1)[0]
            if n >= 5:
                ny[cx + cy * cw] = L
    g = ny
    # Små stumper af et rum → nabo-flertallet; huller inde i ét rum → rummet.
    for _ in range(2):
        for L, del_ in komponenter(g, cw, ch, lambda v: True):
            s = set(del_)
            nab: Counter = Counter()
            kant = False
            for i in del_:
                x, y = i % cw, i // cw
                for nx, ny_ in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if not (0 <= nx < cw and 0 <= ny_ < ch):
                        kant = True
                    elif nx + ny_ * cw not in s:
                        nab[g[nx + ny_ * cw]] += 1
            if L and len(del_) < 20 and nab:
                ny_L = nab.most_common(1)[0][0]
            elif not L and not kant and nab and (len(nab) == 1 or len(del_) < 30):
                ny_L = max((k for k in nab if k), key=lambda k: nab[k], default=0)
            else:
                continue
            for i in del_:
                g[i] = ny_L
    return g, cw, ch


def tilfoej_terrasse(g: list[int], cw: int, ch: int, stue: int) -> None:
    cs = [(i % cw, i // cw) for i, L in enumerate(g) if L == stue]
    vest = min(y for _, y in cs)
    xs = [x for x, _ in cs]
    x0, x1 = min(xs) + 5, max(xs) - 5
    for y in range(max(0, vest - TERRASSE_LUFT - TERRASSE_BREDDE), vest - TERRASSE_LUFT):
        for x in range(x0, x1 + 1):
            if g[x + y * cw] == 0:
                g[x + y * cw] = TERRASSE


def dp(pts: list[tuple[int, int]], eps: float) -> list[tuple[int, int]]:
    """Douglas-Peucker med faste endepunkter."""
    if len(pts) < 3:
        return pts
    behold = [False] * len(pts)
    behold[0] = behold[-1] = True
    stak = [(0, len(pts) - 1)]
    while stak:
        a, b = stak.pop()
        (ax, ay), (bx, by) = pts[a], pts[b]
        dx, dy = bx - ax, by - ay
        n = (dx * dx + dy * dy) ** 0.5
        bedst, bi = -1.0, -1
        for i in range(a + 1, b):
            px, py = pts[i]
            d = (
                abs(dx * (ay - py) - dy * (ax - px)) / n
                if n
                else ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
            )
            if d > bedst:
                bedst, bi = d, i
        if bedst > eps:
            behold[bi] = True
            stak += [(a, bi), (bi, b)]
    return [p for p, k in zip(pts, behold) if k]


def omrids(g: list[int], cw: int, ch: int) -> dict[int, list[list[tuple[int, int]]]]:
    """Omrids pr. rum som løkker af gitter-hjørner. Grænsen mellem to labels
    deles op ved hjørner hvor ≥ 3 labels mødes og forenkles kun én gang."""

    def lab(x: int, y: int) -> int:
        return g[x + y * cw] if 0 <= x < cw and 0 <= y < ch else 0

    def fast(vx: int, vy: int) -> bool:
        r = (lab(vx - 1, vy - 1), lab(vx, vy - 1), lab(vx - 1, vy), lab(vx, vy))
        return len(set(r)) >= 3 or (r[0] == r[3] and r[1] == r[2] and r[0] != r[1])

    cache: dict[tuple, list[tuple[int, int]]] = {}
    ud: dict[int, list[list[tuple[int, int]]]] = {}
    for L in sorted(set(g) - {0}):
        ud_kant: dict[tuple[int, int], list[tuple[int, int]]] = {}
        for i, v in enumerate(g):
            if v != L:
                continue
            x, y = i % cw, i // cw
            if lab(x, y - 1) != L:
                ud_kant.setdefault((x + 1, y), []).append((x, y))
            if lab(x, y + 1) != L:
                ud_kant.setdefault((x, y + 1), []).append((x + 1, y + 1))
            if lab(x - 1, y) != L:
                ud_kant.setdefault((x, y), []).append((x, y + 1))
            if lab(x + 1, y) != L:
                ud_kant.setdefault((x + 1, y + 1), []).append((x + 1, y))
        loekker = []
        while ud_kant:
            start = min(ud_kant)
            # Mindste hjørne er aldrig en diagonal-kontakt → løkken ender i start.
            loop, v, d_ind = [], start, None
            while True:
                loop.append(v)
                valg = ud_kant[v]
                if len(valg) > 1 and d_ind:
                    # Diagonal-kontakt: drej til venstre, så rummet er 4-forbundet.
                    valg.sort(key=lambda n: d_ind[0] * (n[1] - v[1]) - d_ind[1] * (n[0] - v[0]))
                nxt = valg.pop(0)
                if not valg:
                    del ud_kant[v]
                d_ind = (nxt[0] - v[0], nxt[1] - v[1])
                v = nxt
                if v == start:
                    break
            loekker.append(loop)
        rum_ud = []
        for loop in loekker:
            idx = [i for i, v in enumerate(loop) if fast(*v)]
            if not idx:
                a = loop.index(min(loop))
                b = max(
                    range(len(loop)),
                    key=lambda i: (loop[i][0] - loop[a][0]) ** 2 + (loop[i][1] - loop[a][1]) ** 2,
                )
                idx = sorted({a, b})
            ny = []
            for k, a in enumerate(idx):
                b = idx[(k + 1) % len(idx)]
                stk = loop[a : b + 1] if b > a else loop[a:] + loop[: b + 1]
                vend = (stk[0], stk[1] if len(stk) > 1 else stk[0]) > (
                    stk[-1],
                    stk[-2] if len(stk) > 1 else stk[-1],
                )
                key = tuple(reversed(stk)) if vend else tuple(stk)
                if key not in cache:
                    cache[key] = dp(list(key), EPS)
                s = cache[key][::-1] if vend else cache[key]
                ny += s[:-1]
            rum_ud.append(ny)
        ud[L] = rum_ud
    return ud


def afstand_ind(g: list[int], cw: int, ch: int, L: int) -> dict[tuple[int, int], int]:
    """Skakbræt-afstand (celler) fra hver celle i rummet ud til dets kant."""
    d: dict[tuple[int, int], int] = {}
    kø: deque = deque()
    cs = {(i % cw, i // cw) for i, v in enumerate(g) if v == L}
    for x, y in cs:
        if any((x + dx, y + dy) not in cs for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
            d[(x, y)] = 0
            kø.append((x, y))
    while kø:
        x, y = kø.popleft()
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                n = (x + dx, y + dy)
                if n in cs and n not in d:
                    d[n] = d[(x, y)] + 1
                    kø.append(n)
    return d


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--json", action="store_true", help="print kun, skriv ikke")
    ap.add_argument("--cache", help="Roborock-cachefil (default: den første i .storage/roborock)")
    a = ap.parse_args()
    sti = a.cache or sorted(glob.glob(os.path.join(ROOT, ".storage", "roborock", "*")))[0]
    left, top, w, h, data = laes_kort(sti)

    lab = rum_pixels(w, h, data)
    g, cw, ch = celler(fyld_bokse(lab, w, h), w, h)
    stue = next(k for k, (n, _) in SEGMENTER.items() if n == "stue")
    tilfoej_terrasse(g, cw, ch, stue)

    def mm(vx: float, vy: float) -> list[int]:
        """Gitter-hjørne (celle-enheder) → robottens mm."""
        return [round((vx * C + left) * MM - MM / 2), round((vy * C + top) * MM - MM / 2)]

    def centrum(c: tuple[int, int]) -> list[int]:
        return mm(c[0] + 0.5, c[1] + 0.5)

    navne = {**SEGMENTER, TERRASSE: ("terrasse", "Terrasse")}
    rum = {}
    for L, loekker in omrids(g, cw, ch).items():
        key, navn = navne[L]
        d = afstand_ind(g, cw, ch, L)
        cs = list(d)
        mx = sum(x for x, _ in cs) / len(cs)
        my = sum(y for _, y in cs) / len(cs)
        midt = max(cs, key=lambda c: (min(d[c], 6), -((c[0] - mx) ** 2 + (c[1] - my) ** 2)))
        # Ankre: længst-væk-sampling fra midten, mindst 30 cm fra væggen.
        for margin in (3, 2, 1, 0):
            kand = [c for c in cs if d[c] >= margin]
            if kand:
                break
        ankre, bedst = [midt], {c: (c[0] - midt[0]) ** 2 + (c[1] - midt[1]) ** 2 for c in kand}
        while len(ankre) < 24 and bedst:
            c = max(bedst, key=lambda k: (bedst[k], k))
            if bedst[c] < 9:
                break
            ankre.append(c)
            for k in bedst:
                bedst[k] = min(bedst[k], (k[0] - c[0]) ** 2 + (k[1] - c[1]) ** 2)
        # Kant-punkter (n/s = robottens x min/max, v/o = y min/max), 20 cm inde.
        kant = {}
        for navn_k, akse, tegn in (("n", 0, -1), ("s", 0, 1), ("v", 1, -1), ("o", 1, 1)):
            yderst = max(c[akse] * tegn for c in cs)
            E = [c for c in cs if c[akse] * tegn >= yderst - 1]
            med = sorted(c[1 - akse] for c in E)[len(E) // 2]
            c = min(E, key=lambda k: abs(k[1 - akse] - med))
            ind = list(c)
            ind[akse] -= 2 * tegn
            kant[navn_k] = centrum(tuple(ind) if tuple(ind) in d else c)
        # Navne-hjørner: indvendig celle nærmest boksens nv/no-hjørne.
        x0, y0, y1 = min(x for x, _ in cs), min(y for _, y in cs), max(y for _, y in cs)
        hj = {
            k: centrum(min(cs, key=lambda c: (c[0] - x0) ** 2 + (c[1] - hy) ** 2))
            for k, hy in (("nv", y0), ("no", y1))
        }
        rum[key] = {
            "navn": navn,
            "omrids": [[mm(*v) for v in lp] for lp in loekker],
            "midt": centrum(midt),
            "ankre": [centrum(c) for c in ankre],
            "kant": kant,
            "hjoerne": hj,
            **({"tegnet": True} if L == TERRASSE else {}),
        }

    # Døre: hvor to rums gulv-pixels rører hinanden direkte (robotten har kørt
    # igennem); ellers midten af den fælles væg.
    par: dict[tuple[int, int], list] = {}
    for i, A in enumerate(lab):
        if not A:
            continue
        x, y = i % w, i // w
        for j, (nx, ny) in ((i + 1, (x + 1, y)), (i + w, (x, y + 1))):
            if nx < w and ny < h and lab[j] and lab[j] != A:
                k = (min(A, lab[j]), max(A, lab[j]))
                par.setdefault(k, []).append(((x + nx) / 2, (y + ny) / 2))
    vaeg: dict[tuple[int, int], list] = {}
    for i, A in enumerate(g):
        x, y = i % cw, i // cw
        for nx, ny in ((x + 1, y), (x, y + 1)):
            if nx < cw and ny < ch:
                B = g[nx + ny * cw]
                if A and B and A != B:
                    vaeg.setdefault((min(A, B), max(A, B)), []).append(
                        ((x + nx + 1) / 2, (y + ny + 1) / 2)
                    )
    doere = []
    for k in sorted(set(par) | set(vaeg)):
        if k[0] not in navne or k[1] not in navne:
            continue
        if len(par.get(k, [])) >= 4:
            p = par[k]
            sx = sum(q[0] for q in p) / len(p)
            sy = sum(q[1] for q in p) / len(p)
            pkt, aaben = [round((sx + left) * MM), round((sy + top) * MM)], True
        elif len(vaeg.get(k, [])) >= 3:
            p = vaeg[k]
            pkt, aaben = mm(sum(q[0] for q in p) / len(p), sum(q[1] for q in p) / len(p)), False
        else:
            continue
        doere.append({"a": navne[k[0]][0], "b": navne[k[1]][0], "p": pkt, "aaben": aaben})

    sha = hashlib.sha256(data).hexdigest()[:8]
    if a.json:
        print(json.dumps({"kort": sha, "rum": rum, "doere": doere}, ensure_ascii=False, indent=1))
        return
    linjer = [
        "// GENERERET af scripts/lejlighed_kort.py fra Roborock-kortet — rør ikke i hånden.",
        "// Rummene i robottens mm (x = nord→syd, y = vest→øst); tegnes af",
        "// www/lejlighed-kort.js. Boligens plantegning — en privat fil.",
        "window.lejlighedGeometri = {",
        f'  "kort": "{sha}",',
        '  "rum": {',
    ]
    linjer += [
        f'    "{k}": {json.dumps(v, ensure_ascii=False, separators=(",", ":"))},'
        for k, v in sorted(rum.items())
    ]
    linjer += ["  },", '  "doere": [']
    linjer += [f"    {json.dumps(d, ensure_ascii=False, separators=(',', ':'))}," for d in doere]
    linjer += ["  ],", "};", 'window.dispatchEvent(new Event("lejlighed-kort"));', ""]
    with open(UD, "w") as f:
        f.write("\n".join(linjer))
    print(f"skrev {os.path.relpath(UD, ROOT)}: {len(rum)} rum, {len(doere)} døre, kort {sha}")


if __name__ == "__main__":
    main()
