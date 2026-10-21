/*
 * Thread-net — custom Lovelace-kort (type: custom:thread-net-card)
 *
 * Tegner Thread-partitionen live som border-routeren ser den: routere, links
 * mellem dem (farve = det dårligste af link-kvalitet 3/2/1 og målt tab), børn
 * (sovende batteri-enheder) ved deres forælder, og Matter-enheder der IKKE er
 * i partitionen — en ø eller strømløse — i en rød række nederst.
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
 */
const TNC_VERSION = "1.2.0";
const W = 640;
const H = 420;

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

// Deterministisk 0..1 af en streng (startpositioner uden Math.random).
function hash01(s) {
  let h = 2166136261;
  for (const c of String(s)) h = Math.imul(h ^ c.charCodeAt(0), 16777619);
  return ((h >>> 0) % 10000) / 10000;
}

class ThreadNetCard extends HTMLElement {
  setConfig(config) {
    this._config = { entity: "sensor.thread_topologi", ...config };
    this._pos = {};
    this._sig = null;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
  }

  set hass(hass) {
    const s = hass.states[this._config.entity];
    const sig = s ? s.last_updated : "none";
    if (sig === this._sig) return;
    this._sig = sig;
    this._render(s);
  }

  getCardSize() {
    return 8;
  }

  _layout(routere) {
    const ids = routere.map((r) => r.mac);
    const mig = routere.find((r) => r.br && r.navn === "Border-router") || routere[0];
    const pos = {};
    for (const r of routere) {
      const p = this._pos[r.mac];
      if (p) pos[r.mac] = { ...p };
      else {
        const a = hash01(r.mac) * Math.PI * 2;
        pos[r.mac] = { x: W / 2 + Math.cos(a) * 170, y: H / 2 + Math.sin(a) * 130 };
      }
    }
    if (!this._pos[mig.mac]) pos[mig.mac] = { x: W / 2, y: H / 2 };
    const byId = {};
    for (const r of routere) byId[String(r.id)] = r.mac;
    const kanter = [];
    for (const r of routere)
      for (const [id, q] of Object.entries(r.links || {}))
        if (byId[id]) kanter.push([r.mac, byId[id], q]);
    const iter = Object.keys(this._pos).length ? 60 : 300;
    for (let it = 0; it < iter; it++) {
      const f = {};
      for (const a of ids) f[a] = { x: 0, y: 0 };
      for (let i = 0; i < ids.length; i++)
        for (let j = i + 1; j < ids.length; j++) {
          const a = pos[ids[i]], b = pos[ids[j]];
          let dx = a.x - b.x, dy = a.y - b.y;
          const d2 = Math.max(dx * dx + dy * dy, 100);
          const k = 22000 / d2;
          const d = Math.sqrt(d2);
          f[ids[i]].x += (dx / d) * k; f[ids[i]].y += (dy / d) * k;
          f[ids[j]].x -= (dx / d) * k; f[ids[j]].y -= (dy / d) * k;
        }
      for (const [m1, m2, q] of kanter) {
        const a = pos[m1], b = pos[m2];
        const dx = b.x - a.x, dy = b.y - a.y;
        const d = Math.max(Math.sqrt(dx * dx + dy * dy), 1);
        const L = q >= 3 ? 150 : q === 2 ? 190 : 230;
        const k = (d - L) * 0.02;
        f[m1].x += (dx / d) * k; f[m1].y += (dy / d) * k;
        f[m2].x -= (dx / d) * k; f[m2].y -= (dy / d) * k;
      }
      for (const m of ids) {
        const p = pos[m];
        p.x += Math.max(-8, Math.min(8, f[m].x));
        p.y += Math.max(-8, Math.min(8, f[m].y));
        p.x = Math.max(70, Math.min(W - 70, p.x));
        p.y = Math.max(45, Math.min(H - 45, p.y));
      }
    }
    // Centrér tegningen (bbox) så den ikke klumper i ét hjørne.
    const xs = ids.map((m) => pos[m].x), ys = ids.map((m) => pos[m].y);
    const dx = W / 2 - (Math.min(...xs) + Math.max(...xs)) / 2;
    const dy = H / 2 - (Math.min(...ys) + Math.max(...ys)) / 2;
    for (const m of ids) { pos[m].x += dx; pos[m].y += dy; }
    this._pos = pos;
    return pos;
  }

  _render(s) {
    const root = this.shadowRoot;
    const routere = (s && s.attributes.routere) || [];
    const udenFor = (s && s.attributes.uden_for) || [];
    const splitPeer = s && s.attributes.split_peer;
    const splitMin = (s && Number(s.attributes.split_minutter)) || 0;
    const style = `
      <style>
        ha-card { padding: 12px 12px 8px; }
        .top { display:flex; justify-content:space-between; align-items:baseline; gap:8px; flex-wrap:wrap; }
        .titel { font-size: 1.15em; font-weight: 500; color: var(--primary-text-color); }
        .meta { font-size: .85em; color: var(--secondary-text-color); }
        svg { width: 100%; height: auto; display:block; }
        .lbl { font: 11px var(--paper-font-body1_-_font-family, sans-serif); fill: var(--primary-text-color); }
        .lbl-s { font: 9.5px sans-serif; fill: var(--secondary-text-color); }
        .halo { stroke: var(--card-background-color, #fff); stroke-width: 3px; paint-order: stroke; }
        .ud { margin-top: 6px; display:flex; flex-wrap:wrap; gap:6px; align-items:center; }
        .ud .hd { font-size:.85em; color: var(--error-color, #db4437); font-weight:500; }
        .chip { font-size:.85em; padding:2px 8px; border-radius: 10px;
                border:1px dashed var(--error-color, #db4437); color: var(--primary-text-color); }
        .leg { margin-top: 6px; font-size:.8em; color: var(--secondary-text-color); display:flex; gap:12px; flex-wrap:wrap; }
        .leg i { display:inline-block; width:18px; height:3px; vertical-align:middle; margin-right:4px; border-radius:2px; }
      </style>`;
    if (!s || !routere.length) {
      root.innerHTML = `${style}<ha-card><div class="titel">Thread-net</div>
        <div class="meta">Venter på første måling.</div></ha-card>`;
      return;
    }
    const pos = this._layout(routere);
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
        const a = pos[r.mac], b = pos[o.mac];
        kanter += `<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" stroke="${farve(kv)}"
          stroke-width="${kv >= 3 ? 3 : kv === 2 ? 2.2 : 1.6}" stroke-opacity=".85"
          ${tilbage ? "" : 'stroke-dasharray="5 4"'}><title>${esc(kort(r.navn))} ↔ ${esc(kort(o.navn))}: signal ${q}/${tilbage || "–"}${esc(tab(ud, kort(r.navn), kort(o.navn)) + tab(ind, kort(o.navn), kort(r.navn)))}</title></line>`;
      }

    // Børn: vifte udad fra midten, væk fra forælderen.
    let born = "";
    for (const r of routere) {
      const n = (r.born || []).length;
      if (!n) continue;
      const p = pos[r.mac];
      const base = Math.atan2(p.y - H / 2, p.x - W / 2 || 0.01);
      const spred = Math.min(Math.PI * 1.2, 0.55 * n);
      (r.born || []).forEach((b, i) => {
        const a = n === 1 ? base : base - spred / 2 + (spred * i) / (n - 1);
        const R = 46;
        const x = p.x + Math.cos(a) * R, y = p.y + Math.sin(a) * R;
        const tx = p.x + Math.cos(a) * (R + 9), ty = p.y + Math.sin(a) * (R + 9);
        const anchor = Math.cos(a) > 0.3 ? "start" : Math.cos(a) < -0.3 ? "end" : "middle";
        const syg = b.matter === false;
        const hop = b.hop > 0;
        const tip = `${kort(b.navn)} — barn af ${kort(r.navn)} (${b.rloc})` +
          (syg ? ", Matter svarer ikke" : "") +
          (hop ? `, skiftet forælder ${b.hop}× de sidste 4 min` : "");
        born += `<line x1="${p.x}" y1="${p.y}" x2="${x}" y2="${y}" stroke="${hop ? "var(--warning-color, #ffa600)" : "var(--secondary-text-color)"}"
            stroke-opacity="${hop ? 0.9 : 0.45}" stroke-width="1" ${hop ? 'stroke-dasharray="3 3"' : ""}/>
          <circle cx="${x}" cy="${y}" r="5" fill="${syg ? "var(--error-color, #db4437)" : "var(--secondary-text-color)"}"><title>${esc(tip)}</title></circle>
          <text class="lbl-s halo" x="${tx}" y="${ty + 3}" text-anchor="${anchor}">${esc(kort(b.navn))}${hop ? " ⇄" : ""}</text>`;
      });
    }

    let noder = "";
    for (const r of routere) {
      const p = pos[r.mac];
      const mig = r.navn === "Border-router";
      const fill = mig ? "var(--primary-color, #03a9f4)" : "var(--card-background-color, #fff)";
      // Tildelt router-ID der ikke svarer på meshdiag (og/eller Matter er
      // døv): halvdød — i nettets tabel, men ikke til at nå.
      const syg = r.svarer === false || r.matter === false;
      const ring = syg ? "var(--error-color, #db4437)" : r.leder ? "#f4b400" : mig ? "var(--primary-color, #03a9f4)" : "var(--primary-text-color)";
      const status = r.svarer === false ? ", svarer ikke" : r.matter === false ? ", Matter svarer ikke" : "";
      noder += `<g><title>${esc(kort(r.navn))} — router ${r.id} (${r.rloc})${r.leder ? ", leder" : ""}${status}</title>
        <circle cx="${p.x}" cy="${p.y}" r="${mig ? 17 : 13}" fill="${fill}" stroke="${ring}" stroke-width="${r.leder || syg ? 3 : 2}"
          ${syg ? 'stroke-dasharray="4 3"' : ""}/>
        ${r.leder ? `<text x="${p.x}" y="${p.y + 4}" text-anchor="middle" font-size="12" fill="#f4b400">★</text>` : ""}
        <text class="lbl halo" x="${p.x}" y="${p.y - (mig ? 23 : 19)}" text-anchor="middle">${esc(kort(r.navn))}</text></g>`;
    }

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
      <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Thread-net">${kanter}${born}${noder}</svg>
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
window.customCards.push({ type: "thread-net-card", name: "Thread-net", description: "Live Thread-topologi" });
console.info(`thread-net-card ${TNC_VERSION}`);
