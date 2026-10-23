/*
 * Zigbee-net — custom Lovelace-kort (type: custom:zigbee-net-card)
 *
 * Søster til thread-net-card.js: tegner ZHA-nettet live på plantegningen —
 * hver enhed i sit rum (www/lejlighed-kort.js): koordinator og routere, links
 * mellem dem farvet efter signalstyrke (LQI fra begge siders nabo-tabel; den
 * svageste retning vinder), batteri-enheder med en tynd streg til deres
 * forælder og deres RSSI i dBm, og enheder der er utilgængelige i en rød
 * række nederst (< 1 uge: også med rød stiplet ring på deres plads).
 *
 * Data: henter selv `zha/devices` over HA's websocket (kræver admin) hvert
 * 5. min. Nabo-tabellerne er fra ZHA's seneste topologi-skan (zigpy, hver 4. t)
 * — "Skan nu" beder ZHA om et nyt (svarer først når det er færdigt, > 2 min). RSSI/LQI pr.
 * enhed er fra seneste modtagne pakke (sidste hop ind til koordinatoren).
 *
 * Farvegrænser (målt 15/10 på ZBT-2: LQI 152 ≈ −62 dBm, 108 ≈ −73, 72 ≈ −82):
 * stærk ≥ 150 / ≥ −63 dBm, middel ≥ 80 / ≥ −80 dBm, ellers svag. Nabo-links
 * med LQI 0 er forældede tabel-rækker og tegnes ikke.
 *
 * Nettet er tæt (hver router hører 10-19 andre) → som standard tegnes kun hver
 * routers 3 stærkeste links; "alle links" i bunden viser resten.
 *
 * Registreret som Lovelace-ressource /local/zigbee-net-card.js?v=<hash>.
 * Kør `python3 scripts/lovelace_resources.py` efter HVER ændring af filen.
 *
 *   type: custom:zigbee-net-card
 *   orientering: auto   # auto | portraet | landskab (auto: landskab ≥ 760 px)
 */
const ZNC_VERSION = "2.0.0";
const ZLANDSKAB_PX = 760;
const TOP_K = 3;
const HENT_MS = 5 * 60 * 1000;
const GAMMEL_MS = 7 * 24 * 3600 * 1000; // ikke hørt i en uge = pensioneret, ikke et udfald

function zkort(navn) {
  return String(navn || "?")
    .replace(/^Spisestue Pendel$/, "Loft (pendel)")
    .replace(/Badev(æ|ae)relse/g, "Bad")
    .replace(/Børnev(æ|ae)relse|^Boern/g, "Børn")
    .replace(/Sovev(æ|ae)relse/g, "Sove")
    .replace(/^Entre\b/, "Entré")
    .replace(/\bEntre$/, "entré")
    .replace(/ \(open-plan lys\)$/, "")
    .replace(/^(Home Assistant Connect )?ZBT-2$/, "Koordinator");
}

function zesc(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

const lqiNiveau = (l) => (l >= 150 ? 3 : l >= 80 ? 2 : 1);
const rssiNiveau = (r) => (r == null ? 0 : r >= -63 ? 3 : r >= -80 ? 2 : 1);
const zfarve = (n) =>
  n >= 3 ? "var(--success-color, #43a047)"
  : n === 2 ? "var(--warning-color, #ffa600)"
  : n === 1 ? "var(--error-color, #db4437)"
  : "var(--secondary-text-color)";

class ZigbeeNetCard extends HTMLElement {
  setConfig(config) {
    this._config = { orientering: "auto", ...config };
    this._paaKort = () => this._data && this._render();
    this._data = null;
    this._sig = null;
    this._fejl = null;
    this._alle = false;
    this._skan = null;
    this._hentet = 0;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._hentet && !this._henter) this._hent();
  }

  connectedCallback() {
    this._timer = setInterval(() => this._hent(), HENT_MS);
    if (this._hass && Date.now() - this._hentet > HENT_MS) this._hent();
    window.addEventListener("lejlighed-kort", this._paaKort);
    if (!this._ro && window.ResizeObserver)
      this._ro = new ResizeObserver((e) => {
        this._bredde = e[0].contentRect.width;
        if (this._data && this._orientering() !== this._orient) this._render();
      });
    if (this._ro) this._ro.observe(this);
  }

  disconnectedCallback() {
    clearInterval(this._timer);
    window.removeEventListener("lejlighed-kort", this._paaKort);
    if (this._ro) this._ro.disconnect();
  }

  getCardSize() {
    return 12;
  }

  _orientering() {
    const o = this._config.orientering;
    if (o === "portraet" || o === "landskab") return o;
    return (this._bredde || 0) >= ZLANDSKAB_PX ? "landskab" : "portraet";
  }

  async _hent() {
    if (!this._hass || this._henter) return;
    this._henter = true;
    try {
      const devs = await this._hass.callWS({ type: "zha/devices" });
      this._hentet = Date.now();
      this._fejl = null;
      // Gentegn kun når nettet faktisk har ændret sig (positioner bevares).
      const sig = JSON.stringify(devs.map((d) => [d.ieee, d.available, d.lqi, d.rssi, (d.neighbors || []).map((n) => [n.ieee, n.lqi, n.relationship])]));
      this._data = devs;
      if (sig !== this._sig) {
        this._sig = sig;
        this._render();
      } else this._opdaterMeta();
    } catch (e) {
      this._fejl = (e && e.message) || String(e);
      this._render();
    } finally {
      this._henter = false;
    }
  }

  async _skanNu() {
    if (this._skan) return;
    this._skan = "skanner…";
    this._opdaterMeta();
    // Svaret kommer først når hele skannet er færdigt (målt > 2 min).
    try {
      await this._hass.callWS({ type: "zha/topology/update" });
      this._skan = null;
      await this._hent();
      this._opdaterMeta();
    } catch (e) {
      this._skan = null;
      this._fejl = `Skan fejlede: ${(e && e.message) || e}`;
      this._render();
    }
  }

  _navn(d) {
    if (d.user_given_name) return d.user_given_name;
    const reg = this._hass.devices && this._hass.devices[d.device_reg_id];
    if (reg && reg.name_by_user) return reg.name_by_user;
    // Unavngivne enheder: brug den entitet der ER enheden (lys/kontakt/gardin…).
    const pref = ["light", "switch", "cover", "binary_sensor", "climate", "fan", "lock"];
    const ents = (d.entities || []).map((e) => e.entity_id);
    for (const dom of pref) {
      const e = ents.find((x) => x.startsWith(dom + "."));
      const st = e && this._hass.states[e];
      if (st && st.attributes.friendly_name) return st.attributes.friendly_name;
    }
    return d.model || d.ieee;
  }

  // Routere + koordinator, kanter (svageste retning, LQI 0 ignoreret),
  // børn pr. forælder, utilgængelige.
  _model() {
    const devs = this._data || [];
    const by = {};
    for (const d of devs) by[d.ieee] = d;
    const erRouter = (d) => d.device_type === "Coordinator" || d.device_type === "Router";
    const routere = devs.filter((d) => d.available && erRouter(d));
    const rset = new Set(routere.map((d) => d.ieee));
    const lqi = {}; // "a|b" → a's LQI for b
    for (const d of routere)
      for (const n of d.neighbors || []) {
        const l = Number(n.lqi) || 0;
        if (l > 0 && rset.has(n.ieee)) lqi[`${d.ieee}|${n.ieee}`] = l;
      }
    const par = {};
    for (const key of Object.keys(lqi)) {
      const [a, b] = key.split("|");
      const k = a < b ? `${a}|${b}` : `${b}|${a}`;
      if (par[k]) continue;
      const [x, y] = k.split("|");
      const xy = lqi[`${x}|${y}`], yx = lqi[`${y}|${x}`];
      par[k] = { a: x, b: y, xy, yx, v: Math.min(xy || 999, yx || 999), envejs: !(xy && yx) };
    }
    const alleKanter = Object.values(par);
    const valgt = new Set();
    for (const r of routere)
      alleKanter
        .filter((e) => e.a === r.ieee || e.b === r.ieee)
        .sort((p, q) => q.v - p.v)
        .slice(0, TOP_K)
        .forEach((e) => valgt.add(e));
    const stærkeste = [...valgt];
    // Forælder: tilgængelig router der har enheden som "Child"; flere (forældet
    // række i en gammel forælders tabel) → højeste LQI.
    const born = {};
    for (const d of devs) {
      if (!d.available || erRouter(d)) continue;
      let best = null;
      for (const r of routere)
        for (const n of r.neighbors || [])
          if (n.ieee === d.ieee && n.relationship === "Child") {
            const l = Number(n.lqi) || 0;
            if (!best || l > best.l) best = { r: r.ieee, l };
          }
      const far = best ? best.r : (routere.find((r) => r.device_type === "Coordinator") || {}).ieee;
      if (!far) continue;
      (born[far] = born[far] || []).push({ d, l: best ? best.l : null, ukendt: !best });
    }
    const ude = devs.filter((d) => !d.available);
    return { routere, stærkeste, alleKanter, born, ude };
  }

  _metaTekst() {
    const min = this._hentet ? Math.max(0, Math.round((Date.now() - this._hentet) / 60000)) : null;
    return min == null ? "" : `${min} min siden`;
  }

  _opdaterMeta() {
    const el = this.shadowRoot && this.shadowRoot.querySelector(".tid");
    if (el) el.textContent = this._metaTekst();
    const b = this.shadowRoot && this.shadowRoot.querySelector(".skan");
    if (b) b.textContent = this._skan || "Skan nu";
  }

  _render() {
    const root = this.shadowRoot;
    const L = window.lejlighedKort;
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
        .chip.gl { border-color: var(--divider-color, #ccc); color: var(--secondary-text-color); }
        .leg { margin-top: 6px; font-size:.8em; color: var(--secondary-text-color); display:flex; gap:12px; flex-wrap:wrap; align-items:center; }
        .leg i { display:inline-block; width:18px; height:3px; vertical-align:middle; margin-right:4px; border-radius:2px; }
        .knap { cursor:pointer; color: var(--primary-color); user-select:none; }
        ${L ? L.CSS : ""}
      </style>`;
    if (this._fejl && !this._data) {
      root.innerHTML = `${style}<ha-card><div class="titel">Zigbee-net</div>
        <div class="meta">Kan ikke hente ZHA-data: ${zesc(this._fejl)}</div></ha-card>`;
      return;
    }
    const { routere, stærkeste, alleKanter, born, ude } = this._model();
    const kanter = this._alle ? alleKanter : stærkeste;
    if (!routere.length || !L) {
      root.innerHTML = `${style}<ha-card><div class="titel">Zigbee-net</div>
        <div class="meta">${!L ? "Indlæser kortet." : "Venter på ZHA."}</div></ha-card>`;
      return;
    }
    const byIeee = {};
    for (const r of routere) byIeee[r.ieee] = r;
    const navn = (d) => zkort(this._navn(d));
    // Utilgængelig < 1 uge = et udfald (rød chip + ring på pladsen). Længere =
    // pensioneret/i skabet → kun én grå samle-chip, ellers står huset med 10+
    // røde chips for evigt.
    const sidst = (d) => (d.last_seen ? new Date(d.last_seen).getTime() : 0);
    const nyligt = ude.filter((d) => Date.now() - sidst(d) < GAMMEL_MS);
    const gamle = ude.filter((d) => Date.now() - sidst(d) >= GAMMEL_MS);

    this._orient = this._orientering();
    const plan = L.plan(this._orient);
    const enheder = [...routere, ...Object.values(born).flat().map((c) => c.d), ...nyligt].map((d) => ({ id: d.ieee, navn: this._navn(d) }));
    const pos = plan.placer(enheder);

    let svgK = "";
    for (const e of kanter) {
      const a = pos[e.a], b = pos[e.b];
      const n = lqiNiveau(e.v);
      const A = navn(byIeee[e.a]), B = navn(byIeee[e.b]);
      const tip = `${A} ↔ ${B}\n${A} hører ${B}: ${e.xy ? `LQI ${e.xy}` : "–"}\n${B} hører ${A}: ${e.yx ? `LQI ${e.yx}` : "–"}`;
      svgK += `<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" stroke="${zfarve(n)}"
        stroke-width="${n >= 3 ? 2.4 : n === 2 ? 1.8 : 1.2}" stroke-opacity="${this._alle ? 0.5 : 0.85}"
        ${e.envejs ? 'stroke-dasharray="5 4"' : ""}><title>${zesc(tip)}</title></line>`;
    }

    // Etiketter: routere først (førsteret på pladsen), så børn og de udfaldne.
    const rPunkter = [], punkter = [];
    const tal = (d) => (d.rssi != null ? ` ${d.rssi}` : "");

    // Børn: på deres egen plads, tynd streg til forælderen.
    let svgB = "";
    for (const r of routere) {
      const p = pos[r.ieee];
      for (const c of born[r.ieee] || []) {
        const d = c.d, q = pos[d.ieee];
        const rn = rssiNiveau(d.rssi);
        const tip = `${navn(d)} — barn af ${navn(r)}` +
          (c.ukendt ? " (forælder ukendt — ikke i nogen nabo-tabel)" : `, forælderen hører den med LQI ${c.l}`) +
          (d.rssi != null ? `\nSeneste pakke: ${d.rssi} dBm, LQI ${d.lqi}` : "") +
          (d.last_seen ? `\nSidst hørt ${new Date(d.last_seen).toLocaleString("da-DK")}` : "");
        svgB += `<line x1="${p.x}" y1="${p.y}" x2="${q.x}" y2="${q.y}" stroke="var(--secondary-text-color)"
            stroke-opacity=".35" stroke-width=".8" ${c.ukendt ? 'stroke-dasharray="3 3"' : ""}/>
          <circle cx="${q.x}" cy="${q.y}" r="4.5" fill="${zfarve(rn)}"><title>${zesc(tip)}</title></circle>`;
        punkter.push({ x: q.x, y: q.y, r: 4.5, fs: 9, cls: "lbl-s", tekst: L.tekst(navn(d), q.rum) + tal(d) });
      }
    }

    let svgN = "";
    for (const r of routere) {
      const p = pos[r.ieee];
      const koord = r.device_type === "Coordinator";
      const fill = koord ? "var(--primary-color, #03a9f4)" : "var(--card-background-color, #fff)";
      const rn = koord ? 0 : rssiNiveau(r.rssi);
      const ring = koord ? "var(--primary-color, #03a9f4)" : "var(--primary-text-color)";
      const antal = alleKanter.filter((e) => e.a === r.ieee || e.b === r.ieee).length;
      const tip = `${navn(r)}${koord ? " — koordinator" : " — router"}\nHører ${antal} routere` +
        (!koord && r.rssi != null ? `\nSeneste pakke ind: ${r.rssi} dBm, LQI ${r.lqi} (sidste hop)` : "") +
        (r.last_seen && !koord ? `\nSidst hørt ${new Date(r.last_seen).toLocaleString("da-DK")}` : "");
      const rr = koord ? 10 : 8;
      svgN += `<g><title>${zesc(tip)}</title>
        <circle cx="${p.x}" cy="${p.y}" r="${rr}" fill="${fill}" stroke="${ring}" stroke-width="1.8"/>
        ${!koord && r.rssi != null ? `<circle cx="${p.x}" cy="${p.y}" r="3.5" fill="${zfarve(rn)}"/>` : ""}</g>`;
      rPunkter.push({ x: p.x, y: p.y, r: rr, fs: 10, cls: "lbl", tekst: L.tekst(navn(r), p.rum) + (koord ? "" : tal(r)) });
    }

    for (const d of nyligt) {
      const q = pos[d.ieee];
      const rr = d.device_type === "Router" ? 8 : 4.5;
      svgN += `<circle cx="${q.x}" cy="${q.y}" r="${rr}" fill="var(--card-background-color, #fff)" stroke="var(--error-color, #db4437)"
          stroke-width="1.6" stroke-dasharray="3 2"><title>${zesc(navn(d))} — utilgængelig${d.last_seen ? `, sidst hørt ${new Date(d.last_seen).toLocaleString("da-DK")}` : ""}</title></circle>`;
      punkter.push({ x: q.x, y: q.y, r: rr, fs: 9, cls: "lbl-s", tekst: L.tekst(navn(d), q.rum) });
    }

    const alle = [...rPunkter, ...punkter];
    const etk = plan.etiketter(alle);
    const tekster = alle
      .map((p, i) => `<text class="${p.cls} halo" x="${etk[i].x}" y="${etk[i].y}" text-anchor="${etk[i].anchor}">${zesc(p.tekst)}</text>`)
      .join("");

    const antalBorn = Object.values(born).reduce((s, l) => s + l.length, 0);
    const dato = (d) => (d.last_seen ? new Date(d.last_seen).toLocaleString("da-DK", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "aldrig");
    const udRk = ude.length
      ? `<div class="ud">${nyligt.length ? `<span class="hd">Utilgængelige:</span>
          ${nyligt.map((d) => `<span class="chip" title="${d.device_type === "Router" ? "router" : "batteri-enhed"}, sidst hørt ${zesc(dato(d))}">${zesc(navn(d))}</span>`).join("")}` : ""}
          ${gamle.length ? `<span class="chip gl" title="${zesc(gamle.map((d) => `${navn(d)} (${dato(d)})`).join("\n"))}">${gamle.length} ikke hørt i over en uge</span>` : ""}</div>`
      : "";
    const fejl = this._fejl ? `<div class="meta" style="color:var(--error-color,#db4437)">${zesc(this._fejl)}</div>` : "";

    root.innerHTML = `${style}<ha-card>
      <div class="top"><span class="titel">Zigbee-net</span>
        <span class="meta">${routere.length - 1} routere · ${antalBorn} enheder · <span class="tid">${this._metaTekst()}</span></span></div>
      <svg viewBox="${L.viewBox(plan.ramme, etk)}" role="img" aria-label="Zigbee-net">${plan.svg}${svgK}${svgB}${svgN}${tekster}</svg>
      ${udRk}${fejl}
      <div class="leg"><span><i style="background:var(--success-color,#43a047)"></i>stærk</span>
        <span><i style="background:var(--warning-color,#ffa600)"></i>middel</span>
        <span><i style="background:var(--error-color,#db4437)"></i>svag</span>
        <span>tal = dBm</span>
        <span class="knap alle">${this._alle ? "kun 3 stærkeste links" : `alle links (${alleKanter.length})`}</span>
        <span class="knap skan">${this._skan || "Skan nu"}</span></div>
    </ha-card>`;
    root.querySelector(".alle").addEventListener("click", () => {
      this._alle = !this._alle;
      this._render();
    });
    root.querySelector(".skan").addEventListener("click", () => this._skanNu());
  }
}

customElements.define("zigbee-net-card", ZigbeeNetCard);
window.customCards = window.customCards || [];
window.customCards.push({ type: "zigbee-net-card", name: "Zigbee-net", description: "Live Zigbee-topologi med signalstyrke på plantegningen" });
console.info(`zigbee-net-card ${ZNC_VERSION}`);
