/*
 * Lejlighedskort — fælles modul for thread-net-card.js og zigbee-net-card.js
 *
 * Sætter hver radio-enhed i det rum den sidder i, på plantegningen fra
 * Roborock-kortet (www/lejlighed-geometri.js, genereret af
 * scripts/lejlighed_kort.py). Rummet læses af enhedens navn (første ord der
 * er et rum); PLADS herunder er undtagelserne. Intet kendt rum → depotet
 * (user 23/10: "de er edge cases, smid dem alle i depotet").
 *
 * Inden for rummet: døre/kanter får et fast punkt, lofter midten, resten de
 * ledige ankre (spredt ud fra midten, ≥ 40 cm fra hinanden). Etiketterne
 * placeres grådigt der hvor de dækker mindst.
 *
 * Mangler plantegningen (www/lejlighed-geometri.js) tegnes en
 * skematisk bolig. Begge filer sender `lejlighed-kort` på window når de er
 * indlæst — kortene tegner sig selv igen.
 *
 * Registreret som Lovelace-ressource; kør `python3 scripts/lovelace_resources.py`
 * efter HVER ændring af filen.
 */
(() => {
  const VERSION = "1.0.0";
  const K = 0.06; // svg-enheder pr. mm (60 pr. meter)

  const fold = (s) =>
    String(s || "")
      .toLowerCase()
      .replace(/æ/g, "ae")
      .replace(/ø/g, "oe")
      .replace(/å/g, "aa")
      .replace(/é/g, "e")
      .replace(/[^a-z0-9]/g, "");

  // Rum-nøgle → de ord (foldet) der ER rummet i et navn. Et navneord der
  // STARTER med nøglen placerer enheden ("Badeværelse Spot 4" → bad).
  const ORD = {
    spisestue: ["spisestue"],
    boern: ["boern", "boernevaerelse"],
    bad: ["bad", "badevaerelse"],
    sove: ["sove", "sovevaerelse"],
    koekken: ["koekken"],
    entre: ["entre"],
    depot: ["depot"],
    terrasse: ["terrasse"],
    stue: ["stue"],
    tek: ["tek", "teknik"],
  };

  // Foldet fuldt navn → "rum" eller "rum:hint". Kun undtagelser fra ord-reglen.
  const PLADS = {
    borderrouter: "depot",
    zbt2: "depot",
    homeassistantconnectzbt2: "depot",
    spisestuependel: "sove:midt", // sove-loftet (flyttet 06/2026, navnet beholdt)
    threadrouterkoekken: "koekken",
    timmerflotte: "koekken",
    sovedoerparasoll: "sove:doer-entre",
    baddoerparasoll: "bad:doer-entre",
    hoveddoerparasoll: "entre:kant-o",
    terrassedoerparasoll: "stue:kant-v",
    // Kanttilfælde (23/10): navnet nævner et rum, men pladsen er uvis.
    koekkenspots: "depot",
    entrecykelladerplug: "depot",
    entreroegalarm: "depot",
    gardinsovevaerelse: "depot",
    gaesterodretopenplanlys: "depot",
  };

  function rumFor(navn) {
    const f = fold(navn);
    const p = PLADS[f];
    if (p) {
      const [rum, hint] = p.split(":");
      return { rum, hint: hint || null };
    }
    const hint = f.includes("loft") ? "midt" : null;
    for (const ord of String(navn || "").split(/[\s\-_/()]+/)) {
      const w = fold(ord);
      const rum = w && Object.keys(ORD).find((k) => w.startsWith(k));
      if (rum) return { rum, hint };
    }
    return { rum: "depot", hint };
  }

  // Etiket uden rummets ord (rummet står på kortet): "Bad Spot 3" → "Spot 3",
  // "Thread router køkken" → "Thread router", "Sovedør" → "Dør".
  function tekst(navn, rum) {
    const ord = (ORD[rum] || []);
    const er = (w) => ord.includes(fold(w));
    let d = String(navn || "?").split(" ");
    if (d.length > 1 && er(d[0])) d = d.slice(1);
    else if (d.length > 1 && er(d[d.length - 1])) d = d.slice(0, -1);
    else if (ord.some((o) => fold(d[0]) === `${o}doer`)) d = ["Dør", ...d.slice(1)];
    const s = d.join(" ");
    return s.charAt(0).toUpperCase() + s.slice(1);
  }

  const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
  const f1 = (v) => Math.round(v * 10) / 10;

  // Skematisk bolig når plantegningen mangler. Rektangler [x0, y0, x1, y1] i mm,
  // x = nord→syd, y = vest→øst som robottens kort.
  function skematisk() {
    const R = {
      spisestue: ["Spisestue", 0, 1500, 4000, 4500],
      boern: ["Børneværelse", 0, 4500, 4000, 8000],
      koekken: ["Køkken", 4000, 1500, 7000, 4500],
      tek: ["Tek", 4000, 4500, 5000, 6500],
      bad: ["Bad", 5000, 4500, 7000, 6500],
      depot: ["Depot", 4000, 6500, 7000, 8000],
      stue: ["Stue", 7000, 1500, 12000, 4500],
      entre: ["Entré", 7000, 4500, 9000, 8000],
      sove: ["Soveværelse", 9000, 4500, 12000, 8000],
      terrasse: ["Terrasse", 7500, 0, 11500, 1200],
    };
    const rum = {};
    for (const [k, [navn, x0, y0, x1, y1]] of Object.entries(R)) {
      const midt = [(x0 + x1) / 2, (y0 + y1) / 2];
      const gitter = [];
      for (let x = x0 + 400; x <= x1 - 400; x += 600)
        for (let y = y0 + 400; y <= y1 - 400; y += 600) gitter.push([x, y]);
      const ankre = [midt];
      while (gitter.length) {
        gitter.sort((a, b) => Math.min(...ankre.map((q) => dist(b, q))) - Math.min(...ankre.map((q) => dist(a, q))));
        ankre.push(gitter.shift());
      }
      rum[k] = {
        navn,
        omrids: [[[x0, y0], [x1, y0], [x1, y1], [x0, y1]]],
        midt,
        ankre,
        kant: { n: [x0 + 200, midt[1]], s: [x1 - 200, midt[1]], v: [midt[0], y0 + 200], o: [midt[0], y1 - 200] },
        hjoerne: { nv: [x0 + 50, y0 + 50], no: [x0 + 50, y1 - 50] },
        tegnet: k === "terrasse",
      };
    }
    return { kort: "skematisk", rum, doere: [] };
  }

  const tegnBredde = (s, fs) => String(s).length * fs * 0.56;
  const overlap = (a, b) =>
    Math.max(0, Math.min(a.x1, b.x1) - Math.max(a.x0, b.x0)) * Math.max(0, Math.min(a.y1, b.y1) - Math.max(a.y0, b.y0));
  const areal = (b) => (b.x1 - b.x0) * (b.y1 - b.y0);

  // orientering: "portraet" (nord op) eller "landskab" (robot-appens retning).
  function plan(orientering) {
    const g = window.lejlighedGeometri || skematisk();
    const land = orientering === "landskab";
    let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
    for (const r of Object.values(g.rum))
      for (const loop of r.omrids)
        for (const [x, y] of loop) {
          x0 = Math.min(x0, x); x1 = Math.max(x1, x);
          y0 = Math.min(y0, y); y1 = Math.max(y1, y);
        }
    const til = ([x, y]) => (land ? { x: (x - x0) * K, y: (y1 - y) * K } : { x: (y - y0) * K, y: (x - x0) * K });
    const ramme = { x0: 0, y0: 0, x1: (land ? x1 - x0 : y1 - y0) * K, y1: (land ? y1 - y0 : x1 - x0) * K };

    let svg = "";
    const navneBokse = {};
    for (const [k, r] of Object.entries(g.rum)) {
      const d = r.omrids
        .map((loop) => "M" + loop.map((p) => { const q = til(p); return `${f1(q.x)} ${f1(q.y)}`; }).join("L") + "Z")
        .join("");
      svg += `<path class="rum${r.tegnet ? " tegnet" : ""}" d="${d}" fill-rule="evenodd"/>`;
    }
    for (const [k, r] of Object.entries(g.rum)) {
      const h = til(land ? r.hjoerne.no : r.hjoerne.nv);
      const x = h.x + 3, y = h.y + 10;
      navneBokse[k] = { x0: x, y0: y - 8, x1: x + tegnBredde(r.navn, 9), y1: y + 2 };
      svg += `<text class="rum-navn" x="${f1(x)}" y="${f1(y)}">${r.navn}</text>`;
    }

    const spiral = (r, brugt) => {
      for (let i = 1; i < 400; i++) {
        const a = i * 2.39996, rr = 150 * Math.sqrt(i);
        const p = [r.midt[0] + Math.cos(a) * rr, r.midt[1] + Math.sin(a) * rr];
        if (brugt.every((q) => dist(p, q) >= 300)) return p;
      }
      return r.midt;
    };

    function fastPunkt(k, hint) {
      if (!hint || hint === "midt") return null;
      const r = g.rum[k];
      if (hint.startsWith("kant-")) return (r.kant || {})[hint.slice(5)] || null;
      if (hint.startsWith("doer-")) {
        const mod = hint.slice(5);
        const d = (g.doere || []).find((e) => (e.a === k && e.b === mod) || (e.a === mod && e.b === k));
        if (d) {
          // 20 cm ind i rummet, så prikken ikke står på væggen.
          const l = dist(r.midt, d.p) || 1;
          return [d.p[0] + ((r.midt[0] - d.p[0]) / l) * 200, d.p[1] + ((r.midt[1] - d.p[1]) / l) * 200];
        }
        const o = g.rum[mod];
        if (o) return r.ankre.slice().sort((a, b) => dist(a, o.midt) - dist(b, o.midt))[0];
      }
      return null;
    }

    // enheder: [{id, navn}] → {id: {x, y, rum}} i svg-enheder.
    function placer(enheder) {
      const pr = {};
      for (const e of enheder) {
        let { rum, hint } = rumFor(e.navn);
        if (!g.rum[rum]) { rum = g.rum.depot ? "depot" : Object.keys(g.rum)[0]; hint = null; }
        (pr[rum] = pr[rum] || []).push({ ...e, hint });
      }
      const ud = {};
      const sorter = (a, b) => String(a.navn).localeCompare(String(b.navn), "da") || String(a.id).localeCompare(String(b.id));
      for (const [k, liste] of Object.entries(pr)) {
        const r = g.rum[k];
        const brugt = [];
        const fri = (p) => brugt.every((q) => dist(p, q) >= 400);
        const saet = (e, p) => {
          brugt.push(p);
          const s = til(p);
          ud[e.id] = { x: f1(s.x), y: f1(s.y), rum: k };
        };
        // Ankre under rummets navn bruges ikke.
        const nb = navneBokse[k];
        const ankre = r.ankre.filter((p) => {
          const s = til(p);
          return !(s.x > nb.x0 - 6 && s.x < nb.x1 + 6 && s.y > nb.y0 - 6 && s.y < nb.y1 + 6);
        });
        const faste = liste.filter((e) => fastPunkt(k, e.hint)).sort(sorter);
        const midt = liste.filter((e) => !fastPunkt(k, e.hint) && e.hint === "midt").sort(sorter);
        const resten = liste.filter((e) => !fastPunkt(k, e.hint) && e.hint !== "midt").sort(sorter);
        for (const e of faste) saet(e, fastPunkt(k, e.hint));
        for (const e of midt) {
          const p = ankre.filter(fri).sort((a, b) => dist(a, r.midt) - dist(b, r.midt))[0];
          saet(e, p || spiral(r, brugt));
        }
        for (const e of resten) saet(e, ankre.find(fri) || spiral(r, brugt));
      }
      return ud;
    }

    // punkter: [{x, y, r, tekst, fs}] i prioriteret rækkefølge → [{x, y, anchor, boks}].
    // Grådig: den kandidat (højre, venstre, over, under, diagonaler) der
    // dækker mindst af prikker, andre etiketter, rum-navne og kanten.
    function etiketter(punkter) {
      const bokse = Object.values(navneBokse).map((b) => ({ ...b, w: 0.5 }));
      for (const p of punkter) bokse.push({ x0: p.x - p.r, y0: p.y - p.r, x1: p.x + p.r, y1: p.y + p.r, w: 1.5 });
      return punkter.map((p) => {
        const w = tegnBredde(p.tekst, p.fs), h = p.fs, g2 = 2.5, r = p.r, d = r * 0.72;
        const midtY = p.y + h * 0.29;
        const kand = [
          [p.x + r + g2, midtY, "start"],
          [p.x - r - g2, midtY, "end"],
          [p.x, p.y - r - g2 - h * 0.22, "middle"],
          [p.x, p.y + r + g2 + h * 0.8, "middle"],
          [p.x + d + 1, p.y - d - h * 0.22, "start"],
          [p.x - d - 1, p.y - d - h * 0.22, "end"],
          [p.x + d + 1, p.y + d + h * 0.8, "start"],
          [p.x - d - 1, p.y + d + h * 0.8, "end"],
          // Tæt rum: én linje længere ude.
          [p.x + r + g2, midtY - h * 1.05, "start"],
          [p.x - r - g2, midtY - h * 1.05, "end"],
          [p.x + r + g2, midtY + h * 1.05, "start"],
          [p.x - r - g2, midtY + h * 1.05, "end"],
          [p.x, p.y - r - g2 - h * 1.27, "middle"],
          [p.x, p.y + r + g2 + h * 1.85, "middle"],
        ];
        let bedst = null;
        kand.forEach(([tx, ty, anchor], i) => {
          const bx = anchor === "start" ? tx : anchor === "end" ? tx - w : tx - w / 2;
          const b = { x0: bx, x1: bx + w, y0: ty - h * 0.8, y1: ty + h * 0.22 };
          let s = i * 3 + (areal(b) - overlap(b, ramme)) * 0.6;
          for (const o of bokse) s += overlap(b, o) * o.w;
          if (!bedst || s < bedst.s) bedst = { s, x: f1(tx), y: f1(ty), anchor, boks: b };
        });
        bokse.push({ ...bedst.boks, w: 1 });
        return bedst;
      });
    }

    return { svg, ramme, til, placer, etiketter, kilde: g.kort };
  }

  // viewBox der rummer plantegningen og alle etiketter.
  function viewBox(ramme, etk, luft = 6) {
    let { x0, y0, x1, y1 } = ramme;
    for (const e of etk) {
      x0 = Math.min(x0, e.boks.x0); y0 = Math.min(y0, e.boks.y0);
      x1 = Math.max(x1, e.boks.x1); y1 = Math.max(y1, e.boks.y1);
    }
    return `${Math.floor(x0 - luft)} ${Math.floor(y0 - luft)} ${Math.ceil(x1 - x0 + 2 * luft)} ${Math.ceil(y1 - y0 + 2 * luft)}`;
  }

  const CSS = `
    .rum { fill: var(--primary-text-color); fill-opacity: .045; stroke: var(--primary-text-color);
           stroke-opacity: .28; stroke-width: 1; }
    .rum.tegnet { fill-opacity: .02; stroke-dasharray: 4 3; }
    .rum-navn { font: 9px sans-serif; fill: var(--secondary-text-color); fill-opacity: .75; }`;

  window.lejlighedKort = { VERSION, fold, rumFor, tekst, plan, viewBox, CSS };
  window.dispatchEvent(new Event("lejlighed-kort"));
  console.info(`lejlighed-kort ${VERSION}`);
})();
