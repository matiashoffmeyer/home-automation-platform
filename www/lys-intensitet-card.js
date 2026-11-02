/*
 * Lys pr. aktiv time — custom Lovelace-kort (type: custom:lys-intensitet-card)
 *
 * User 2026-11-01: "grafer for lys tændt per active hour for hver dag/uge osv.
 * så jeg kan læse hvor intensivt huset er med lys ved brug. for ellers kommer
 * det jo bare an på hvor meget vi er hjemme".
 *
 * Søjle = gennemsnitligt antal tændte pærer mens huset var aktivt — nogen
 * hjemme (house_state Active) og ikke godnat — = pære-timer pr. aktiv time,
 * for hver dag, uge eller måned. Kortet henter long-term statistics for to
 * sensorer (packages/lys_kpi.yaml) og dividerer:
 *   sensor.lys_paerer_taendt_aktiv  tændte pærer mens aktiv, ellers 0
 *   sensor.hus_aktiv_andel          1 mens aktiv, ellers 0
 * mean(A) / mean(B) over en periode = Σ(tændte × aktiv tid) / Σ aktiv tid.
 * statistics-graph kan ikke dividere to serier — derfor dette kort.
 * En periode med under en halv aktiv time vises ikke (tallet er støj).
 *
 * Registreret som Lovelace-ressource /local/lys-intensitet-card.js?v=<hash>.
 * Kør `python3 scripts/lovelace_resources.py` efter HVER ændring af filen.
 *
 *   type: custom:lys-intensitet-card
 *   periode: day        # day | week | month (startvalg; knapperne skifter)
 *   # dagslys-korrigeret kopi (kun aktive timer med solen nede):
 *   taeller: sensor.lys_paerer_taendt_aktiv_moerke
 *   naevner: sensor.hus_aktiv_moerke_andel
 *   titel: Lys pr. mørk aktiv time
 *   enhed: pr. mørk aktiv time
 */
const LIC_A = "sensor.lys_paerer_taendt_aktiv";
const LIC_B = "sensor.hus_aktiv_andel";
const LIC_ANTAL = { day: 30, week: 12, month: 12 };
const LIC_NAVN = { day: "Dag", week: "Uge", month: "Måned" };
const LIC_MDR = ["jan", "feb", "mar", "apr", "maj", "jun", "jul", "aug", "sep", "okt", "nov", "dec"];
const LIC_DAGE = ["søn", "man", "tir", "ons", "tor", "fre", "lør"];
const LIC_MIN_AKTIV_T = 0.5;
const LIC_OPDATER_MS = 15 * 60 * 1000;

function licUge(d) {
  const t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const dag = t.getUTCDay() || 7;
  t.setUTCDate(t.getUTCDate() + 4 - dag);
  const jan1 = new Date(Date.UTC(t.getUTCFullYear(), 0, 1));
  return Math.ceil(((t - jan1) / 86400000 + 1) / 7);
}

function licEtiket(ms, periode) {
  const d = new Date(ms);
  if (periode === "month") return LIC_MDR[d.getMonth()];
  if (periode === "week") return "u" + licUge(d);
  return String(d.getDate());
}

function licLang(ms, periode) {
  const d = new Date(ms);
  if (periode === "month") return LIC_MDR[d.getMonth()] + " " + d.getFullYear();
  if (periode === "week") return "uge " + licUge(d) + " (fra " + d.getDate() + ". " + LIC_MDR[d.getMonth()] + ")";
  return LIC_DAGE[d.getDay()] + " " + d.getDate() + ". " + LIC_MDR[d.getMonth()];
}

function licTal(x, dec = 1) {
  return x.toFixed(dec).replace(".", ",");
}

class LysIntensitetCard extends HTMLElement {
  setConfig(config) {
    this._config = { periode: "day", taeller: LIC_A, naevner: LIC_B, enhed: "pr. aktiv time", ...config };
    this._periode = LIC_ANTAL[this._config.periode] ? this._config.periode : "day";
    this._data = null;
    this._hentet = 0;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
  }

  set hass(hass) {
    this._hass = hass;
    if (Date.now() - this._hentet > LIC_OPDATER_MS) this._hent();
  }

  async _hent() {
    if (!this._hass) return;
    this._hentet = Date.now();
    const periode = this._periode;
    const nu = new Date();
    const start = new Date(nu);
    if (periode === "day") start.setDate(start.getDate() - (LIC_ANTAL.day - 1));
    if (periode === "week") start.setDate(start.getDate() - 7 * (LIC_ANTAL.week - 1) - ((start.getDay() + 6) % 7));
    if (periode === "month") { start.setDate(1); start.setMonth(start.getMonth() - (LIC_ANTAL.month - 1)); }
    start.setHours(0, 0, 0, 0);
    try {
      const r = await this._hass.callWS({
        type: "recorder/statistics_during_period",
        start_time: start.toISOString(),
        end_time: nu.toISOString(),
        statistic_ids: [this._config.taeller, this._config.naevner],
        period: periode,
        types: ["mean"],
      });
      if (periode !== this._periode) return;
      const b = new Map((r[this._config.naevner] || []).map((x) => [x.start, x]));
      // En igangværende periodes mean dækker kun de kompilerede timer (til
      // sidste hele time) — gang med dem, ikke med hele periodens længde.
      const sidsteTime = Math.floor(Date.now() / 3600000) * 3600000;
      this._data = (r[this._config.taeller] || []).map((a) => {
        const andel = b.get(a.start) ? b.get(a.start).mean : null;
        const varighed = Math.max(Math.min(a.end, sidsteTime) - a.start, 0);
        const timer = andel == null ? 0 : (andel * varighed) / 3600000;
        const ok = andel != null && a.mean != null && timer >= LIC_MIN_AKTIV_T;
        return { start: a.start, slut: a.end, timer, vaerdi: ok ? a.mean / andel : null };
      });
      this._fejl = null;
    } catch (e) {
      this._fejl = String((e && e.message) || e);
    }
    this._render();
  }

  _vaelg(p) {
    if (p === this._periode) return;
    this._periode = p;
    this._data = null;
    this._hentet = 0;
    this._render();
    this._hent();
  }

  _render() {
    const knapper = Object.keys(LIC_ANTAL)
      .map((p) => `<button data-p="${p}" class="${p === this._periode ? "valgt" : ""}">${LIC_NAVN[p]}</button>`)
      .join("");
    let krop;
    if (this._fejl) krop = `<div class="tom">Kunne ikke hente statistik: ${this._fejl}</div>`;
    else if (!this._data) krop = `<div class="tom">Henter…</div>`;
    else krop = this._graf(this._data);
    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; }
        ha-card { padding: 12px 16px 14px; }
        .top { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
        .titel { font-size: 16px; font-weight: 500; color: var(--primary-text-color); }
        .knapper { display: flex; gap: 4px; }
        button { font: inherit; font-size: 13px; padding: 4px 10px; border-radius: 14px; cursor: pointer;
          border: 1px solid var(--divider-color); background: none; color: var(--secondary-text-color); }
        button.valgt { background: var(--primary-color); border-color: var(--primary-color); color: var(--text-primary-color, #fff); }
        .tal { margin: 8px 0 4px; color: var(--secondary-text-color); font-size: 13px; }
        .tal b { color: var(--primary-text-color); font-size: 20px; font-weight: 500; }
        svg { width: 100%; height: auto; display: block; overflow: visible; }
        .bar { fill: var(--amber-color, #f2a93b); }
        .bar.nu { opacity: 0.55; }
        .akse { fill: var(--secondary-text-color); font-size: 10px; }
        .linje { stroke: var(--divider-color); stroke-width: 1; }
        .snit { stroke: var(--secondary-text-color); stroke-width: 1; stroke-dasharray: 3 3; }
        .tom { padding: 24px 0; text-align: center; color: var(--secondary-text-color); }
      </style>
      <ha-card>
        <div class="top"><div class="titel">${this._config.titel || "Lys pr. aktiv time"}</div><div class="knapper">${knapper}</div></div>
        ${krop}
      </ha-card>`;
    this.shadowRoot.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => this._vaelg(b.dataset.p)));
  }

  _graf(data) {
    const med = data.filter((d) => d.vaerdi != null);
    if (!med.length) return `<div class="tom">Ingen statistik endnu</div>`;
    const sumT = med.reduce((s, d) => s + d.timer, 0);
    const snit = med.reduce((s, d) => s + d.vaerdi * d.timer, 0) / sumT;
    const sidste = med[med.length - 1];
    const W = 600, H = 170, L = 26, B = 18, T = 6;
    const max = Math.max(...med.map((d) => d.vaerdi), 1);
    const loft = Math.ceil(max / 2) * 2;
    const bw = (W - L) / data.length;
    const y = (v) => T + (H - T - B) * (1 - v / loft);
    const hver = data.length > 15 ? 5 : 1;
    let s = "";
    for (let v = 0; v <= loft; v += loft / 2) {
      s += `<line class="linje" x1="${L}" x2="${W}" y1="${y(v)}" y2="${y(v)}"/>`;
      s += `<text class="akse" x="${L - 4}" y="${y(v) + 3}" text-anchor="end">${licTal(v, 0)}</text>`;
    }
    data.forEach((d, i) => {
      const x = L + i * bw;
      const nu = d.slut > Date.now();
      if (d.vaerdi != null) {
        s += `<rect class="bar${nu ? " nu" : ""}" x="${x + bw * 0.15}" y="${y(d.vaerdi)}" width="${bw * 0.7}" height="${Math.max(y(0) - y(d.vaerdi), 0.5)}" rx="1.5">`;
        s += `<title>${licLang(d.start, this._periode)}: ${licTal(d.vaerdi)} pærer ${this._config.enhed} · ${licTal(d.timer)} t${nu ? " (i gang)" : ""}</title></rect>`;
      }
      if ((data.length - 1 - i) % hver === 0)
        s += `<text class="akse" x="${x + bw / 2}" y="${H - 4}" text-anchor="middle">${licEtiket(d.start, this._periode)}</text>`;
    });
    s += `<line class="snit" x1="${L}" x2="${W}" y1="${y(snit)}" y2="${y(snit)}"/>`;
    const enhed = { day: "i dag", week: "denne uge", month: "denne måned" }[this._periode];
    const seneste = sidste.slut > Date.now() ? enhed : licLang(sidste.start, this._periode);
    return `
      <div class="tal"><b>${licTal(sidste.vaerdi)}</b> pærer ${this._config.enhed} ${seneste} · snit ${licTal(snit)} (stiplet)</div>
      <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${this._config.titel || "Lys pr. aktiv time"}">${s}</svg>`;
  }

  getCardSize() {
    return 4;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto" };
  }
}

customElements.define("lys-intensitet-card", LysIntensitetCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "lys-intensitet-card",
  name: "Lys pr. aktiv time",
  description: "Tændte pærer pr. aktiv time pr. dag, uge eller måned",
});
