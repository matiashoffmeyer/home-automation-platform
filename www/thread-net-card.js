/*
 * Thread-net — custom Lovelace-kort (type: custom:thread-net-card)
 *
 * Tegner Thread-partitionen live som border-routeren ser den, på
 * plantegningen: hver enhed i sit rum (www/lejlighed-kort.js), links mellem
 * routerne (farve = det dårligste af link-kvalitet 3/2/1 og målt tab), børn
 * (sovende batteri-enheder) med en tynd streg til deres forælder, og
 * Matter-enheder der IKKE er i partitionen — en ø eller strømløse — med rød
 * stiplet ring på deres plads og i en rød række nederst.
 *
 * Data: sensor.thread_topologi (packages/thread_otbr_watchdog.yaml), fodret af
 * scripts/otbr_rcp_stats.py hvert 2. min via `ot-ctl meshdiag topology`.
 * En ø kan OTBR'en ikke se ind i (meshdiag krydser ikke partitioner) — kun at
 * den findes ("Different partition" i loggen = split_peer) og hvem der mangler.
 *
 * Registreret som Lovelace-ressource /local/thread-net-card.js?v=<hash>.
 * Kør `python3 scripts/lovelace_resources.py` efter HVER ændring af filen.
 *
 *   type: custom:thread-net-card
 *   entity: sensor.thread_topologi   # default
 *   orientering: auto                # auto | portraet | landskab (auto: landskab ≥ 760 px)
 */
const TNC_VERSION = "2.0.0";
const LANDSKAB_PX = 760;

function kort(navn) {
  return String(navn || "?")
    .replace(/Badevaerelse/g, "Bad")
    .replace(/Badeværelse/g, "Bad")
    .replace(/doer/g, "dør")
    .replace(/ Parasoll$/, "")
    .replace(/ Myggspray$/, " PIR")
    .replace(/^Timmerflotte$/, "Timmerflotte køkken")
    .replace(/^Ukendt$/, "?");
}

function esc(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

class ThreadNetCard extends HTMLElement {
  setConfig(config) {
    this._config = { entity: "sensor.thread_topologi", orientering: "auto", ...config };
    this._sig = null;
    this._s = undefined;
    this._paaKort = () => this._s !== undefined && this._render(this._s);
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
  }

  set hass(hass) {
    const s = hass.states[this._config.entity];
    const sig = s ? s.last_updated : "none";
    if (sig === this._sig) return;
    this._sig = sig;
    this._render(s);
  }

  connectedCallback() {
    window.addEventListener("lejlighed-kort", this._paaKort);
    if (!this._ro && window.ResizeObserver)
      this._ro = new ResizeObserver((e) => {
        this._bredde = e[0].contentRect.width;
        if (this._s !== undefined && this._orientering() !== this._orient) this._render(this._s);
      });
    if (this._ro) this._ro.observe(this);
  }

  disconnectedCallback() {
    window.removeEventListener("lejlighed-kort", this._paaKort);
    if (this._ro) this._ro.disconnect();
  }

  getCardSize() {
    return 12;
  }

  _orientering() {
    const o = this._config.orientering;
    if (o === "portraet" || o === "landskab") return o;
    return (this._bredde || 0) >= LANDSKAB_PX ? "landskab" : "portraet";
  }

  _render(s) {
    this._s = s;
    const root = this.shadowRoot;
    const L = window.lejlighedKort;
    const routere = (s && s.attributes.routere) || [];
    const udenFor = (s && s.attributes.uden_for) || [];
    const splitPeer = s && s.attributes.split_peer;
    const splitMin = (s && Number(s.attributes.split_minutter)) || 0;
    const style = `
      <style>
        :host { display: block; }
        ha-card { padding: 12px 12px 8px; }
        .top { display:flex; justify-content:space-between; align-items:baseline; gap:8px; flex-wrap:wrap; }
        .titel { font-size: 1.15em; font-weight: 500; color: var(--primary-text-color); }
        .meta { font-size: .85em; color: var(--secondary-text-color); }
        svg { width: 100%; height: auto; display:block; }
        .lbl { font: 10px var(--paper-font-body1_-_font-family, sans-serif); fill: var(--primary-text-color); }
        .lbl-s { font: 9px sans-serif; fill: var(--secondary-text-color); }
        .halo { stroke: var(--card-background-color, #fff); stroke-width: 3px; paint-order: stroke; }
        .ud { margin-top: 6px; display:flex; flex-wrap:wrap; gap:6px; align-items:center; }
        .ud .hd { font-size:.85em; color: var(--error-color, #db4437); font-weight:500; }
        .chip { font-size:.85em; padding:2px 8px; border-radius: 10px;
                border:1px dashed var(--error-color, #db4437); color: var(--primary-text-color); }
        .leg { margin-top: 6px; font-size:.8em; color: var(--secondary-text-color); display:flex; gap:12px; flex-wrap:wrap; }
        .leg i { display:inline-block; width:18px; height:3px; vertical-align:middle; margin-right:4px; border-radius:2px; }
        ${L ? L.CSS : ""}
      </style>`;
    if (!s || !routere.length || !L) {
      root.innerHTML = `${style}<ha-card><div class="titel">Thread-net</div>
        <div class="meta">${!L ? "Indlæser kortet." : "Venter på første måling."}</div></ha-card>`;
      return;
    }
    this._orient = this._orientering();
    const plan = L.plan(this._orient);
    const enheder = [];
    for (const r of routere) enheder.push({ id: `r:${r.mac}`, navn: r.navn });
    for (const r of routere) (r.born || []).forEach((b, i) => enheder.push({ id: `b:${r.mac}:${i}`, navn: b.navn }));
    udenFor.forEach((u, i) => enheder.push({ id: `u:${i}`, navn: u.navn }));
    const pos = plan.placer(enheder);
    const byId = {};
    for (const r of routere) byId[String(r.id)] = r;
    // [frame-fejl %, msg-fejl %] fra senderen. Msg-tab overlever alle
    // gensendinger; 15/10 stue 2 → entré: 90/26 = Matter død, bad 3 → bad 2:
    // 63/5 = virker men haltende.
    const tabNiveau = (f) => (!f ? 3 : f[1] >= 10 || f[0] >= 80 ? 1 : f[1] >= 2 || f[0] >= 40 ? 2 : 3);
    const farve = (q) => (q >= 3 ? "var(--success-color, #43a047)" : q === 2 ? "var(--warning-color, #ffa600)" : "var(--error-color, #db4437)");

    // Router-links: ét streg pr. par; kvalitet = den svageste retning. Kun
    // meldt fra én side = stiplet (envejs-hørt).
    const set = new Set();
    let kanter = "";
    for (const r of routere)
      for (const [id, q] of Object.entries(r.links || {})) {
        const o = byId[id];
        if (!o) continue;
        const key = [r.mac, o.mac].sort().join("-");
        if (set.has(key)) continue;
        set.add(key);
        const tilbage = (o.links || {})[String(r.id)];
        // Tab i hver senders retning trækker kvaliteten ned: et stærkt signal
        // hvor beskederne alligevel forsvinder er ikke en stærk forbindelse.
        const ud = (r.fejl || {})[String(o.id)], ind = (o.fejl || {})[String(r.id)];
        const kv = Math.min(tilbage ? Math.min(q, tilbage) : q, tabNiveau(ud), tabNiveau(ind));
        const tab = (f, fra, til) => (f ? `\n${fra} → ${til}: ${Math.round(f[1])} % tabt (${f[0]} % gensendt)` : "");
        const a = pos[`r:${r.mac}`], b = pos[`r:${o.mac}`];
        kanter += `<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" stroke="${farve(kv)}"
          stroke-width="${kv >= 3 ? 2.4 : kv === 2 ? 1.8 : 1.3}" stroke-opacity=".85"
          ${tilbage ? "" : 'stroke-dasharray="5 4"'}><title>${esc(kort(r.navn))} ↔ ${esc(kort(o.navn))}: signal ${q}/${tilbage || "–"}${esc(tab(ud, kort(r.navn), kort(o.navn)) + tab(ind, kort(o.navn), kort(r.navn)))}</title></line>`;
      }

    // Etiketter: routere først (de har førsteret på pladsen), så børn og øen.
    const punkter = [];

    // Børn: på deres egen plads, tynd streg til forælderen.
    let bornSvg = "";
    for (const r of routere) {
      const p = pos[`r:${r.mac}`];
      (r.born || []).forEach((b, i) => {
        const c = pos[`b:${r.mac}:${i}`];
        const syg = b.matter === false;
        const hop = b.hop > 0;
        const tip = `${kort(b.navn)} — barn af ${kort(r.navn)} (${b.rloc})` +
          (syg ? ", Matter svarer ikke" : "") +
          (hop ? `, skiftet forælder ${b.hop}× de sidste 4 min` : "");
        bornSvg += `<line x1="${p.x}" y1="${p.y}" x2="${c.x}" y2="${c.y}" stroke="${hop ? "var(--warning-color, #ffa600)" : "var(--secondary-text-color)"}"
            stroke-opacity="${hop ? 0.9 : 0.35}" stroke-width="${hop ? 1.2 : 0.8}" ${hop ? 'stroke-dasharray="3 3"' : ""}/>
          <circle cx="${c.x}" cy="${c.y}" r="4.5" fill="${syg ? "var(--error-color, #db4437)" : "var(--secondary-text-color)"}"><title>${esc(tip)}</title></circle>`;
        punkter.push({ x: c.x, y: c.y, r: 4.5, fs: 9, cls: "lbl-s", tekst: L.tekst(kort(b.navn), c.rum) + (hop ? " ⇄" : "") });
      });
    }

    let noder = "";
    const routerPunkter = [];
    for (const r of routere) {
      const p = pos[`r:${r.mac}`];
      const mig = r.navn === "Border-router";
      const fill = mig ? "var(--primary-color, #03a9f4)" : "var(--card-background-color, #fff)";
      // Tildelt router-ID der ikke svarer på meshdiag (og/eller Matter er
      // døv): halvdød — i nettets tabel, men ikke til at nå.
      const syg = r.svarer === false || r.matter === false;
      const ring = syg ? "var(--error-color, #db4437)" : r.leder ? "#f4b400" : mig ? "var(--primary-color, #03a9f4)" : "var(--primary-text-color)";
      const status = r.svarer === false ? ", svarer ikke" : r.matter === false ? ", Matter svarer ikke" : "";
      const rr = mig ? 10 : 8;
      noder += `<g><title>${esc(kort(r.navn))} — router ${r.id} (${r.rloc})${r.leder ? ", leder" : ""}${status}</title>
        <circle cx="${p.x}" cy="${p.y}" r="${rr}" fill="${fill}" stroke="${ring}" stroke-width="${r.leder || syg ? 2.5 : 1.8}"
          ${syg ? 'stroke-dasharray="3 2"' : ""}/>
        ${r.leder ? `<text x="${p.x}" y="${p.y + 3.5}" text-anchor="middle" font-size="10" fill="#f4b400">★</text>` : ""}</g>`;
      routerPunkter.push({ x: p.x, y: p.y, r: rr, fs: 10, cls: "lbl", tekst: L.tekst(kort(r.navn), p.rum) });
    }

    // Uden for partitionen: på deres plads med rød stiplet ring.
    udenFor.forEach((u, i) => {
      const c = pos[`u:${i}`];
      const rr = u.router ? 8 : 4.5;
      noder += `<circle cx="${c.x}" cy="${c.y}" r="${rr}" fill="var(--card-background-color, #fff)" stroke="var(--error-color, #db4437)"
          stroke-width="1.6" stroke-dasharray="3 2"><title>${esc(kort(u.navn))} — uden for nettet (${u.router ? "router" : "batteri-enhed"}${u.matter ? ", Matter svarer stadig" : ""})</title></circle>`;
      punkter.push({ x: c.x, y: c.y, r: rr, fs: 9, cls: "lbl-s", tekst: L.tekst(kort(u.navn), c.rum) });
    });

    const alle = [...routerPunkter, ...punkter];
    const etk = plan.etiketter(alle);
    const tekster = alle
      .map((p, i) => `<text class="${p.cls} halo" x="${etk[i].x}" y="${etk[i].y}" text-anchor="${etk[i].anchor}">${esc(p.tekst)}</text>`)
      .join("");

    const leder = routere.find((r) => r.leder);
    const opd = s.attributes.maalt ? s.attributes.maalt * 1000 : (s.last_reported || s.last_updated);
    const min = Math.max(0, Math.round((Date.now() - new Date(opd).getTime()) / 60000));
    const ud = udenFor.length
      ? `<div class="ud"><span class="hd">${splitPeer ? `Ø i ${splitMin} min — uden for nettet:` : "Uden for nettet:"}</span>
          ${udenFor.map((u) => `<span class="chip" title="${u.router ? "router" : "batteri-enhed"}${u.matter ? ", Matter svarer stadig" : ""}">${esc(kort(u.navn))}</span>`).join("")}</div>`
      : splitPeer
      ? `<div class="ud"><span class="hd">Fremmed partition hørt i ${splitMin} min</span></div>`
      : "";

    root.innerHTML = `${style}<ha-card>
      <div class="top"><span class="titel">Thread-net</span>
        <span class="meta">${routere.length} routere · leder ${esc(kort(leder ? leder.navn : "?"))} · ${min} min siden</span></div>
      <svg viewBox="${L.viewBox(plan.ramme, etk)}" role="img" aria-label="Thread-net">${plan.svg}${kanter}${bornSvg}${noder}${tekster}</svg>
      ${ud}
      <div class="leg"><span><i style="background:var(--success-color,#43a047)"></i>stærk</span>
        <span><i style="background:var(--warning-color,#ffa600)"></i>middel</span>
        <span><i style="background:var(--error-color,#db4437)"></i>svag / tab</span>
        <span>★ leder</span><span style="color:var(--error-color,#db4437)">◌ svarer ikke</span><span>⇄ hopper</span></div>
    </ha-card>`;
  }
}

customElements.define("thread-net-card", ThreadNetCard);
window.customCards = window.customCards || [];
window.customCards.push({ type: "thread-net-card", name: "Thread-net", description: "Live Thread-topologi på plantegningen" });
console.info(`thread-net-card ${TNC_VERSION}`);
