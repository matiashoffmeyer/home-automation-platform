/*
 * Folketing-liste — custom Lovelace-kort (type: custom:folketing-liste-card)
 *
 * Alle levende forslag fra sensor.folketing (attribut `alle`, bygget af
 * status_doc() i scripts/folketing.py): ubesvarede først i kø-rækkefølge, så
 * de besvarede. Hver række har tre små knapper — dit svar er fremhævet, et
 * tryk på en anden ÆNDRER svaret (seneste svar pr. sag vinder i
 * ai_feedback/folketing_feedback.jsonl). Kalder script.folketing_svar med
 * sag-id'et, samme vej ind som pushen (fejlklasse #2).
 *
 * Mærket: "Ny" = Folketinget har ikke stemt endnu, "Stemt <dato>" = afstemt.
 * Fanen Stemt samler dem (de ligger ellers sidst i køen, 11-04: 39 af 107
 * ubesvarede, alle under 68 "Ny"). ⟳ starter en scan uden push
 * (shell_command.folketing_opdater); sensoren genlæser selv bagefter.
 * Resultat og partier vises først når DU har svaret (user-spec 1a).
 *
 * Registreret som Lovelace-ressource /local/folketing-liste-card.js?v=<hash>.
 * Kør `python3 scripts/lovelace_resources.py` efter HVER ændring af filen.
 *
 *   type: custom:folketing-liste-card
 *   entity: sensor.folketing   # default
 *   visning: vaegt             # Vægtning-fanen (2026-11-05): kun For/Imod-svar
 *                              # (Neutral tæller ikke i enighed → intet at vægte),
 *                              # knapperne er Vigtig/Normal/Uvigtig →
 *                              # script.folketing_vaegt (attribut `w`, udeladt
 *                              # = Normal). Vægten tæller i enighed-procenten.
 */
const FLC_VERSION = "1.2.1";
const FLC_SVAR = [
  ["FOR", "👍", "For"],
  ["IMOD", "👎", "Imod"],
  ["NEUTRAL", "🤷", "Neutral"],
];

const FLC_VAEGT = [
  ["VIGTIG", "Vigtig"],
  ["NORMAL", "Normal"],
  ["UVIGTIG", "Uvigtig"],
];
const FLC_SVAR_IKON = { FOR: "👍", IMOD: "👎", NEUTRAL: "🤷" };

function flcEsc(s) {
  return String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

class FolketingListeCard extends HTMLElement {
  setConfig(config) {
    this._config = { entity: "sensor.folketing", ...config };
    this._sig = null;
    this._vent = {}; // sag-id → svar trykket, indtil sensoren har det
    this._ventW = {}; // sag-id → vægt trykket, indtil sensoren har den
    this._vaegt = config.visning === "vaegt";
    this._filter = this._filter || (this._vaegt ? "alle" : "ubesvarede");
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
  }

  set hass(hass) {
    this._hass = hass;
    const s = hass.states[this._config.entity];
    const sig = s ? s.last_updated : "none";
    if (sig === this._sig) return;
    this._sig = sig;
    // Sensoren har svaret → det optimistiske tryk er ikke længere nødvendigt.
    const alle = (s && s.attributes.alle) || [];
    for (const r of alle) {
      if (this._vent[r.id] && this._vent[r.id] === r.s) delete this._vent[r.id];
      if (this._ventW[r.id] && this._ventW[r.id] === (r.w || "NORMAL")) delete this._ventW[r.id];
    }
    this._render();
  }

  getCardSize() {
    return 10;
  }

  _svar(id, svar) {
    this._vent[id] = svar;
    this._render();
    this._hass.callService("script", "folketing_svar", { svar, sag: id, kilde: "side" });
  }

  _saetVaegt(id, vaegt) {
    this._ventW[id] = vaegt;
    this._render();
    this._hass.callService("script", "folketing_vaegt", { vaegt, sag: id });
  }

  _render() {
    if (this._vaegt) return this._renderVaegt();
    const s = this._hass && this._hass.states[this._config.entity];
    const alle = (s && s.attributes.alle) || [];
    const mit = (r) => this._vent[r.id] || r.s || "";
    const ub = alle.filter((r) => !r.s);
    const be = alle.filter((r) => r.s);
    const stemt = alle.filter((r) => r.st);
    const vis = { besvarede: be, stemt, alle }[this._filter] || ub;
    const sidst = s && s.attributes.sidst_scannet;
    if (this._henter && sidst !== this._henter) this._henter = null;
    const kl = sidst ? new Date(sidst).toLocaleString("da-DK", { timeZone: "Europe/Copenhagen", day: "numeric", month: "numeric", hour: "2-digit", minute: "2-digit" }) : "–";

    const fane = (k, navn, n) =>
      `<button class="fane${this._filter === k ? " valgt" : ""}" data-fane="${k}">${navn} <span class="n">${n}</span></button>`;

    const raekke = (r) => {
      const m = mit(r);
      let res = "";
      if (r.s && r.st && r.v !== undefined && r.v !== null) {
        res = `<div class="res">${r.v ? "Vedtaget" : "Forkastet"} · For: ${flcEsc((r.f || []).join(", ") || "–")} · Imod: ${flcEsc((r.i || []).join(", ") || "–")}</div>`;
      }
      const knapper = FLC_SVAR.map(
        ([k, ikon, navn]) =>
          `<button class="svar${m === k ? " valgt " + k.toLowerCase() : ""}" data-id="${flcEsc(r.id)}" data-svar="${k}" title="${navn}">${ikon}</button>`
      ).join("");
      const nr = r.u ? `<a href="${flcEsc(r.u)}" target="_blank" rel="noopener">${flcEsc(r.n)}</a>` : flcEsc(r.n);
      return `<div class="r">
        <div class="tekst">
          <div class="top"><span class="nr">${nr}</span><span class="maerke ${r.st ? "stemt" : "ny"}">${r.st ? "Stemt" + (r.d ? " " + flcEsc(r.d.slice(8, 10).replace(/^0/, "") + "/" + r.d.slice(5, 7).replace(/^0/, "")) : "") : "Ny"}</span></div>
          <div class="kort">${flcEsc(r.k)}</div>${res}
        </div>
        <div class="knapper">${knapper}</div>
      </div>`;
    };

    this.shadowRoot.innerHTML = `
      ${this._css()}
      <ha-card>
        <div class="opd"><span>Afstemninger hentet ${flcEsc(kl)}</span><button class="opdater"${this._henter ? " disabled" : ""}>${this._henter ? "Henter …" : "⟳ Opdater"}</button></div>
        <div class="faner">${fane("ubesvarede", "Ubesvarede", ub.length)}${fane("besvarede", "Besvarede", be.length)}${fane("stemt", "Stemt", stemt.length)}${fane("alle", "Alle", alle.length)}</div>
        ${vis.length ? vis.map(raekke).join("") : `<div class="tom">Ingen forslag her.</div>`}
      </ha-card>`;

    this.shadowRoot.querySelectorAll(".fane").forEach((b) =>
      b.addEventListener("click", () => {
        this._filter = b.dataset.fane;
        this._render();
      })
    );
    const opd = this.shadowRoot.querySelector(".opdater");
    if (opd)
      opd.addEventListener("click", () => {
        this._henter = sidst || "ingen";
        this._render();
        this._hass.callService("shell_command", "folketing_opdater", {});
        // Scanningen tager typisk 10-60 s; giver den op efter 3 min.
        setTimeout(() => {
          if (this._henter) {
            this._henter = null;
            this._render();
          }
        }, 180000);
      });
    this.shadowRoot.querySelectorAll(".svar").forEach((b) =>
      b.addEventListener("click", () => this._svar(b.dataset.id, b.dataset.svar))
    );
  }
}

// Vægtning-fanen: kun For/Imod-svar (user-spec 2026-11-05: "ikke ting jeg har
// svaret ved ikke til"); dit svar som ikon, knapperne vægter det.
FolketingListeCard.prototype._renderVaegt = function () {
  const s = this._hass && this._hass.states[this._config.entity];
  const be = ((s && s.attributes.alle) || []).filter((r) => r.s === "FOR" || r.s === "IMOD");
  const w = (r) => this._ventW[r.id] || r.w || "NORMAL";
  const vig = be.filter((r) => w(r) === "VIGTIG");
  const uvig = be.filter((r) => w(r) === "UVIGTIG");
  const vis = { vigtige: vig, uvigtige: uvig }[this._filter] || be;
  const fane = (k, navn, n) =>
    `<button class="fane${this._filter === k ? " valgt" : ""}" data-fane="${k}">${navn} <span class="n">${n}</span></button>`;
  const raekke = (r) => {
    const m = w(r);
    const knapper = FLC_VAEGT.map(
      ([k, navn]) => `<button class="vgt${m === k ? " valgt " + k.toLowerCase() : ""}" data-id="${flcEsc(r.id)}" data-vaegt="${k}">${navn}</button>`
    ).join("");
    const nr = r.u ? `<a href="${flcEsc(r.u)}" target="_blank" rel="noopener">${flcEsc(r.n)}</a>` : flcEsc(r.n);
    return `<div class="r">
      <div class="tekst">
        <div class="top"><span class="nr">${nr}</span><span>${FLC_SVAR_IKON[r.s] || ""}</span><span class="maerke ${r.st ? "stemt" : "ny"}">${r.st ? "Stemt" : "Ny"}</span></div>
        <div class="kort">${flcEsc(r.k)}</div>
      </div>
      <div class="knapper">${knapper}</div>
    </div>`;
  };
  this.shadowRoot.innerHTML = `
    ${this._css()}
    <ha-card>
      <div class="faner">${fane("alle", "Besvarede", be.length)}${fane("vigtige", "Vigtige", vig.length)}${fane("uvigtige", "Uvigtige", uvig.length)}</div>
      ${vis.length ? vis.map(raekke).join("") : `<div class="tom">Ingen forslag her.</div>`}
    </ha-card>`;
  this.shadowRoot.querySelectorAll(".fane").forEach((b) =>
    b.addEventListener("click", () => {
      this._filter = b.dataset.fane;
      this._render();
    })
  );
  this.shadowRoot.querySelectorAll(".vgt").forEach((b) =>
    b.addEventListener("click", () => this._saetVaegt(b.dataset.id, b.dataset.vaegt))
  );
};

FolketingListeCard.prototype._css = function () {
  return `<style>
        ha-card { padding: 12px 12px 4px; }
        .faner { display: flex; gap: 4px; margin-bottom: 8px; }
        .opd { display: flex; align-items: center; justify-content: space-between; font-size: .85em;
               color: var(--secondary-text-color); margin-bottom: 8px; }
        .opd button { border: 1px solid var(--divider-color); background: none; color: var(--primary-text-color);
                      border-radius: 16px; padding: 4px 12px; font: inherit; cursor: pointer; }
        .opd button[disabled] { opacity: .5; }
        .fane { flex: 1; border: 1px solid var(--divider-color); background: none; color: var(--primary-text-color);
                border-radius: 16px; padding: 6px 2px; font: inherit; font-size: .85em; cursor: pointer; }
        .fane.valgt { background: var(--primary-color); color: var(--text-primary-color, #fff); border-color: var(--primary-color); }
        .n { opacity: .7; font-size: .85em; }
        .r { display: flex; gap: 8px; align-items: center; padding: 8px 0; border-top: 1px solid var(--divider-color); }
        .tekst { flex: 1; min-width: 0; }
        .top { display: flex; gap: 6px; align-items: center; font-size: .85em; color: var(--secondary-text-color); }
        .nr a { color: inherit; }
        .maerke { border-radius: 8px; padding: 0 6px; font-size: .8em; }
        .maerke.ny { background: rgba(33,150,243,.18); color: var(--info-color, #2196f3); }
        .maerke.stemt { background: rgba(76,175,80,.18); color: var(--success-color, #4caf50); }
        .kort { line-height: 1.3; }
        .res { font-size: .8em; color: var(--secondary-text-color); margin-top: 2px; }
        .knapper { display: flex; gap: 4px; flex-shrink: 0; }
        .svar { width: 34px; height: 34px; border-radius: 50%; border: 1px solid var(--divider-color);
                background: none; font-size: 16px; cursor: pointer; opacity: .45; padding: 0; }
        .svar.valgt { opacity: 1; border-width: 2px; }
        .svar.for { border-color: var(--success-color, #4caf50); background: rgba(76,175,80,.15); }
        .svar.imod { border-color: var(--error-color, #f44336); background: rgba(244,67,54,.15); }
        .svar.neutral { border-color: var(--secondary-text-color); background: rgba(128,128,128,.15); }
        .tom { padding: 12px 0; color: var(--secondary-text-color); }
        .vgt { border: 1px solid var(--divider-color); background: none; color: var(--primary-text-color);
               border-radius: 14px; padding: 5px 8px; font: inherit; font-size: .8em; cursor: pointer; opacity: .5; }
        .vgt.valgt { opacity: 1; border-width: 2px; }
        .vgt.vigtig { border-color: var(--warning-color, #ff9800); background: rgba(255,152,0,.18); }
        .vgt.normal { border-color: var(--secondary-text-color); background: rgba(128,128,128,.15); }
        .vgt.uvigtig { border-color: var(--divider-color); background: rgba(128,128,128,.08); }
      </style>`;
};

customElements.define("folketing-liste-card", FolketingListeCard);
window.customCards = window.customCards || [];
window.customCards.push({ type: "folketing-liste-card", name: "Folketing-liste", description: `Alle forslag med svar-knapper (v${FLC_VERSION})` });
