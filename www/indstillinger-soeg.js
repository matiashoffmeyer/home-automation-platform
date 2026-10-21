/*
 * Indstillinger-søgning — custom Lovelace-kort (type: custom:indstillinger-soeg-card)
 *
 * Indekserer de dashboards der står i `dashboards:` ved at hente deres config
 * over websocket (lovelace/config), så søgningen ALDRIG kan drifte fra siderne:
 * flytter du en slider, finder søgningen den det nye sted. Resultaterne er de
 * ægte kort (tile/button), så man kan justere direkte i resultatlisten, og
 * overskriften over hver gruppe er et link til fanen hvor indstillingen bor.
 *
 * Registreret som Lovelace-ressource /local/indstillinger-soeg.js?v=<hash>.
 * Kør `python3 scripts/lovelace_resources.py` efter HVER ændring af filen —
 * ellers serverer app'en den gamle version fra sin cache. Ressourcen bor i
 * .storage (ikke git); samme script genopretter den efter en gendannelse.
 *
 * Søgningen: alle ord skal matche (navn, overskrift, fane, entity, tekst); æøå
 * foldes, så "koekken" finder "køkken". Et entity der står flere steder vises
 * én gang (bedste match).
 */
const VERSION = "1.1.0";

const DOMAIN_FEATURES = {
  input_number: [{ type: "numeric-input" }],
  number: [{ type: "numeric-input" }],
  input_select: [{ type: "select-options" }],
  select: [{ type: "select-options" }],
  input_boolean: [{ type: "toggle" }],
  switch: [{ type: "toggle" }],
};

const EXAMPLES = ["køkken", "sluk", "vækning", "gardin", "godnat", "bad", "notifikation", "elpris"];

function fold(s) {
  return String(s || "")
    .toLowerCase()
    .replace(/æ/g, "ae").replace(/ø/g, "oe").replace(/å/g, "aa")
    .normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .replace(/[_\-./:()"'`*→↳]/g, " ")
    .replace(/[^\p{L}\p{N}\s%°]/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function plainMarkdown(s) {
  return String(s || "")
    .replace(/\{%[\s\S]*?%\}/g, " ")
    .replace(/\{\{[\s\S]*?\}\}/g, " ")
    .replace(/\{#[\s\S]*?#\}/g, " ")
    .replace(/[#*_`>|\[\]]/g, " ")
    .replace(/\(\/[^)]*\)/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 400);
}

function navigate(path) {
  history.pushState(null, "", path);
  window.dispatchEvent(new CustomEvent("location-changed", { detail: { replace: false } }));
}

class IndstillingerSoegCard extends HTMLElement {
  setConfig(config) {
    this._config = {
      max_results: 40,
      placeholder: "Søg i indstillinger …",
      dashboards: [{ url_path: "indstillinger-dash", title: "Indstillinger" }],
      ...config,
    };
    this._query = this._query || "";
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._built) this._build();
    if (!this._indexPromise) this._indexPromise = this._loadIndex();
    for (const el of this._visible || []) el.hass = hass;
  }

  getCardSize() {
    return 2;
  }

  getGridOptions() {
    return { columns: "full", rows: "auto" };
  }

  // ---------------------------------------------------------------- UI
  _build() {
    this._built = true;
    const root = this.attachShadow({ mode: "open" });
    root.innerHTML = `
      <style>
        :host { display: block; }
        .box { position: relative; }
        ha-icon.mag { position: absolute; left: 14px; top: 50%; transform: translateY(-50%);
          color: var(--secondary-text-color); --mdc-icon-size: 22px; pointer-events: none; }
        input { box-sizing: border-box; width: 100%; font-size: 16px; line-height: 24px;
          padding: 14px 44px 14px 46px; border-radius: var(--ha-card-border-radius, 12px);
          border: 1px solid var(--divider-color); background: var(--card-background-color);
          color: var(--primary-text-color); outline: none; font-family: inherit; }
        input:focus { border-color: var(--primary-color); }
        button.clear { position: absolute; right: 6px; top: 50%; transform: translateY(-50%);
          border: none; background: none; color: var(--secondary-text-color); cursor: pointer;
          padding: 8px; display: none; }
        button.clear.show { display: block; }
        .hint { color: var(--secondary-text-color); padding: 12px 4px 0; font-size: 14px; }
        .chips { display: flex; flex-wrap: wrap; gap: 8px; padding-top: 10px; }
        .chip { border: 1px solid var(--divider-color); border-radius: 16px; padding: 6px 12px;
          cursor: pointer; font-size: 14px; color: var(--primary-text-color);
          background: var(--card-background-color); }
        .group { margin-top: 18px; }
        .crumb { display: flex; align-items: center; gap: 6px; font-size: 14px; font-weight: 500;
          color: var(--primary-color); cursor: pointer; padding: 0 4px 8px; }
        .crumb .rest { color: var(--secondary-text-color); font-weight: 400; }
        .grid { display: grid; gap: 8px; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); }
        .more { color: var(--secondary-text-color); font-size: 13px; padding: 6px 4px 0; cursor: pointer; }
      </style>
      <div class="box">
        <ha-icon class="mag" icon="mdi:magnify"></ha-icon>
        <input type="search" enterkeyhint="search" autocomplete="off" spellcheck="false">
        <button class="clear" title="Ryd"><ha-icon icon="mdi:close"></ha-icon></button>
      </div>
      <div class="out"></div>`;
    this._input = root.querySelector("input");
    this._out = root.querySelector(".out");
    this._clear = root.querySelector("button.clear");
    this._input.placeholder = this._config.placeholder;
    this._input.value = this._query;
    this._input.addEventListener("input", () => {
      clearTimeout(this._t);
      this._t = setTimeout(() => this._setQuery(this._input.value), 180);
    });
    this._clear.addEventListener("click", () => {
      this._input.value = "";
      this._setQuery("");
      this._input.focus();
    });
    this._render();
  }

  _setQuery(q) {
    this._query = q;
    this._render();
  }

  // ---------------------------------------------------------------- index
  async _loadIndex() {
    const items = [];
    for (const dash of this._config.dashboards) {
      let cfg;
      try {
        cfg = await this._hass.callWS({ type: "lovelace/config", url_path: dash.url_path });
      } catch (e) {
        continue;
      }
      (cfg.views || []).forEach((view, vi) => {
        const viewPath = `/${dash.url_path}/${view.path || vi}`;
        const ctx = { dash, view, viewPath, heading: "", sub: "" };
        const walk = (cards) => {
          for (const card of cards || []) this._indexCard(card, ctx, items);
        };
        for (const section of view.sections || []) {
          ctx.heading = "";
          ctx.sub = "";
          walk(section.cards);
        }
        ctx.heading = "";
        ctx.sub = "";
        walk(view.cards);
      });
    }
    this._items = items;
    this._render();
  }

  _indexCard(card, ctx, items) {
    if (!card || typeof card !== "object") return;
    const t = card.type;
    if (t === "heading") {
      if (card.heading_style === "subtitle") ctx.sub = card.heading || "";
      else {
        ctx.heading = card.heading || "";
        ctx.sub = "";
      }
      return;
    }
    if (t === "markdown") {
      const txt = plainMarkdown(card.content);
      const last = items[items.length - 1];
      if (txt && last && last.viewPath === ctx.viewPath && last.heading === ctx.heading) {
        last.desc = (last.desc + " " + txt).slice(0, 600);
      }
      return;
    }
    if (t === "vertical-stack" || t === "horizontal-stack" || t === "grid") {
      for (const c of card.cards || []) this._indexCard(c, ctx, items);
      return;
    }
    if (t === "conditional") {
      this._indexCard(card.card, ctx, items);
      return;
    }
    const base = {
      dash: ctx.dash.title,
      viewTitle: ctx.view.title || "",
      viewPath: ctx.viewPath,
      heading: ctx.heading,
      sub: ctx.sub,
      desc: "",
    };
    if ((t === "tile" || t === "entity") && typeof card.entity === "string") {
      const cfg = { ...card };
      delete cfg.visibility;
      delete cfg.grid_options;
      delete cfg.layout_options;
      if (t === "entity") {
        cfg.type = "tile";
        cfg.features = DOMAIN_FEATURES[card.entity.split(".")[0]];
        if (cfg.features) cfg.features_position = "bottom";
      }
      items.push({ ...base, key: `${ctx.viewPath}|${card.entity}`, entity: card.entity, name: card.name || "", cfg });
      return;
    }
    if (t === "entities" || t === "glance") {
      for (const row of card.entities || []) {
        const r = typeof row === "string" ? { entity: row } : row;
        if (!r || typeof r.entity !== "string") continue;
        const dom = r.entity.split(".")[0];
        const cfg = { type: "tile", entity: r.entity };
        if (r.name) cfg.name = r.name;
        if (r.icon) cfg.icon = r.icon;
        if (DOMAIN_FEATURES[dom]) {
          cfg.features = DOMAIN_FEATURES[dom];
          cfg.features_position = "bottom";
        }
        items.push({ ...base, key: `${ctx.viewPath}|${r.entity}`, entity: r.entity, name: r.name || "", cfg });
      }
      return;
    }
    if (t === "button" && card.tap_action && card.tap_action.action === "perform-action" && card.name) {
      const cfg = { ...card };
      delete cfg.visibility;
      delete cfg.grid_options;
      // Nøglen bærer sektionen: samme knap-navn i to sektioner ("Køkken" under både
      // Hurtig og Grundig støvsugning) er to forskellige handlinger, ikke en dublet.
      items.push({ ...base, key: `${ctx.viewPath}|${ctx.heading}|${ctx.sub}|btn|${card.name}`, entity: null, name: card.name, cfg });
    }
  }

  // ---------------------------------------------------------------- search
  _search(q) {
    const tokens = fold(q).split(" ").filter((x) => x.length > 0);
    if (!tokens.length || !this._items) return [];
    const states = this._hass.states;
    const hits = [];
    const seen = new Map();
    this._items.forEach((it, idx) => {
      if (it.entity && !states[it.entity]) return;
      const fn = it.entity ? (states[it.entity].attributes.friendly_name || "") : "";
      const nm = it.name || fn;
      const f = {
        // Også uden bindestreger, så "elpris" finder "El-pris" og "sovegardin" finder "Sove-gardin".
        name: `${fold(nm)} ${fold(nm.replace(/-/g, ""))}`,
        head: fold(`${it.heading} ${it.sub} ${`${it.heading} ${it.sub}`.replace(/-/g, "")}`),
        ent: fold(`${fn} ${it.entity || ""}`),
        rest: fold(`${it.viewTitle} ${it.dash} ${it.desc}`),
      };
      let score = 0;
      for (const tk of tokens) {
        let s = 0;
        if (f.name.includes(tk)) s = f.name.split(" ").some((w) => w.startsWith(tk)) ? 12 : 9;
        else if (f.head.includes(tk)) s = 6;
        else if (f.ent.includes(tk)) s = 4;
        else if (f.rest.includes(tk)) s = 1;
        if (!s) return;
        score += s;
      }
      const key = it.entity || it.key;
      const prev = seen.get(key);
      if (prev !== undefined) {
        if (hits[prev].score >= score) return;
        hits[prev] = null;
      }
      seen.set(key, hits.length);
      hits.push({ it, score, idx });
    });
    return hits.filter(Boolean).sort((a, b) => b.score - a.score || a.idx - b.idx);
  }

  // ---------------------------------------------------------------- render
  async _render() {
    if (!this._out) return;
    const q = (this._query || "").trim();
    this._clear.classList.toggle("show", q.length > 0);
    const out = this._out;
    const token = (this._renderToken = (this._renderToken || 0) + 1);
    this._visible = [];

    if (q.length < 2) {
      out.innerHTML = `<div class="hint">Skriv hvad du vil ændre — fx et rum, en lampe eller en funktion.</div>
        <div class="chips">${EXAMPLES.map((e) => `<span class="chip">${e}</span>`).join("")}</div>`;
      out.querySelectorAll(".chip").forEach((c) =>
        c.addEventListener("click", () => {
          this._input.value = c.textContent;
          this._setQuery(c.textContent);
        })
      );
      return;
    }
    if (!this._items) {
      out.innerHTML = `<div class="hint">Indlæser …</div>`;
      return;
    }
    const hits = this._search(q);
    const max = this._config.max_results;
    if (!hits.length) {
      out.innerHTML = `<div class="hint">Ingen indstillinger matcher „${q.replace(/</g, "&lt;")}“.</div>`;
      return;
    }
    const helpers = await window.loadCardHelpers();
    if (token !== this._renderToken) return;

    // Gruppér efter hvor indstillingen bor, i den rækkefølge de bedste hits kommer.
    const groups = new Map();
    for (const h of hits.slice(0, max)) {
      const g = `${h.it.viewPath}|${h.it.heading}|${h.it.sub}`;
      if (!groups.has(g)) groups.set(g, []);
      groups.get(g).push(h.it);
    }
    const frag = document.createDocumentFragment();
    const summary = document.createElement("div");
    summary.className = "hint";
    summary.textContent =
      hits.length > max ? `${hits.length} fund — viser de ${max} bedste. Skriv flere ord for at indsnævre.` : `${hits.length} fund`;
    frag.appendChild(summary);

    this._cache = this._cache || new Map();
    for (const [, list] of groups) {
      const it0 = list[0];
      const group = document.createElement("div");
      group.className = "group";
      const crumb = document.createElement("div");
      crumb.className = "crumb";
      const where = [it0.heading, it0.sub].filter(Boolean).join(" › ");
      crumb.innerHTML = `<ha-icon icon="mdi:arrow-right-circle-outline" style="--mdc-icon-size:18px"></ha-icon>
        <span></span><span class="rest"></span>`;
      crumb.children[1].textContent = `${it0.dash} › ${it0.viewTitle}`;
      crumb.children[2].textContent = where ? ` › ${where}` : "";
      crumb.addEventListener("click", () => navigate(it0.viewPath));
      group.appendChild(crumb);
      const grid = document.createElement("div");
      grid.className = "grid";
      for (const it of list) {
        let el = this._cache.get(it.key);
        if (!el) {
          el = helpers.createCardElement(it.cfg);
          this._cache.set(it.key, el);
        }
        el.hass = this._hass;
        this._visible.push(el);
        grid.appendChild(el);
      }
      group.appendChild(grid);
      frag.appendChild(group);
    }
    out.replaceChildren(frag);
  }
}

customElements.define("indstillinger-soeg-card", IndstillingerSoegCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "indstillinger-soeg-card",
  name: "Indstillinger-søgning",
  description: "Søg i husets indstillinger på tværs af dashboards",
});
console.info(`%c indstillinger-soeg ${VERSION} `, "background:#03a9f4;color:#fff;border-radius:3px");
