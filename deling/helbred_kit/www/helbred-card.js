/*
 * helbred-card — custom Lovelace-kort (type: custom:helbred-card)
 *
 * Viser og logger et trænings-/vægt-program. Kortet rummer INGEN data: alt
 * indhold (øvelser, tal, tekster) kommer fra sensorernes attributter, og hver
 * handling sendes som base64-JSON til script.helbred_cmd, der validerer og
 * gemmer. Sensorerne genlæses af scriptet → kortet tegner om på last_updated.
 *
 *   type: custom:helbred-card
 *   visning: idag | traening | kost | statistik | spoergsmaal
 *
 * Registreres som Lovelace-ressource /local/helbred-card.js (JavaScript-modul).
 * Efter en ændring af filen: hæv ?v=… på ressourcen, eller ryd browserens cache.
 */
const HBC_VERSION = "1.4.0";
const HBC_SENSOR = {
  idag: "sensor.helbred_idag",
  traening: "sensor.helbred_idag",
  kost: "sensor.helbred_kost",
  statistik: "sensor.helbred_statistik",
  spoergsmaal: "sensor.helbred_historik",
};
const HBC_NIVEAU = { "-2": "#c62828", "-1": "#ef6c00", 0: "#607d8b", 1: "#2e7d32", 2: "#1b5e20" };

function hbcEsc(s) {
  return String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}
function hbcTal(x) {
  if (x === null || x === undefined || x === "") return "";
  const r = Math.round(Number(x) * 100) / 100;
  return String(r).replace(".", ",");
}
function hbcDato(s) {
  const d = new Date(s);
  return `${d.getDate()}/${d.getMonth() + 1}`;
}

class HelbredCard extends HTMLElement {
  setConfig(config) {
    this._config = { visning: "idag", ...config };
    this._entity = HBC_SENSOR[this._config.visning] || HBC_SENSOR.idag;
    this._script = "helbred_cmd";
    this._sig = null;
    this._val = {}; // øvelse-id → {antal, kg} justeret med +/−, indtil logget
    this._kladde = {}; // felt-nøgle → tekst der er ved at blive skrevet
    this._aaben = {}; // øvelse-id → "sådan gør du" er foldet ud
    this._vent = {}; // nøgle → sendt, venter på sensoren
    this._sted = null;
    this._alle = false;
    this._kostdag = null; // kost: hverdag | weekend (default efter ugedag)
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
  }

  set hass(hass) {
    this._hass = hass;
    const s = hass.states[this._entity];
    const sig = s ? s.last_updated : "none";
    if (sig !== this._sig) {
      this._sig = sig;
      this._vent = {};
      this._render();
    }
  }

  getCardSize() {
    return 8;
  }

  _send(obj, ventNoegle) {
    const bytes = new TextEncoder().encode(JSON.stringify(obj));
    let bin = "";
    bytes.forEach((b) => (bin += String.fromCharCode(b)));
    if (ventNoegle) this._vent[ventNoegle] = true;
    this._render();
    this._hass.callService("script", this._script, { b64: btoa(bin) });
  }

  _a() {
    const s = this._hass && this._hass.states[this._entity];
    return s ? { state: s.state, ...s.attributes } : null;
  }

  _render() {
    const a = this._a();
    let html;
    if (!a) html = `<div class="tom">Sensoren mangler (${hbcEsc(this._entity)}).</div>`;
    else if (a.state === "unknown" || a.state === "unavailable") html = `<div class="tom">Henter …</div>`;
    else html = this[`_${this._config.visning}`] ? this[`_${this._config.visning}`](a) : "";
    const fokus = this.shadowRoot.activeElement && this.shadowRoot.activeElement.dataset.k;
    this.shadowRoot.innerHTML = `<style>${HBC_CSS}</style><ha-card><div class="wrap">${html}</div></ha-card>`;
    this._bind();
    if (fokus) {
      const el = this.shadowRoot.querySelector(`[data-k="${fokus}"]`);
      if (el) {
        el.focus();
        if (el.setSelectionRange && el.type === "text") el.setSelectionRange(el.value.length, el.value.length);
      }
    }
  }

  _bind() {
    const r = this.shadowRoot;
    r.querySelectorAll("[data-k]").forEach((el) => {
      el.addEventListener("input", () => (this._kladde[el.dataset.k] = el.value));
    });
    r.querySelectorAll("[data-act]").forEach((el) => {
      el.addEventListener("click", (e) => {
        e.stopPropagation();
        this._klik(el.dataset.act, el.dataset);
      });
    });
  }

  _num(k) {
    const v = String(this._kladde[k] ?? "").replace(",", ".").trim();
    return v === "" || isNaN(Number(v)) ? null : Number(v);
  }

  _klik(act, d) {
    const a = this._a();
    if (act === "vaegt") {
      const kg = this._num("vaegt");
      if (kg === null || kg < 40 || kg > 250) return this._fejl("Skriv vægten i kg, fx 96,4");
      delete this._kladde.vaegt;
      this._send({ op: "vaegt", kg }, "vaegt");
    } else if (act === "step") {
      const x = this._post(a, d.id);
      if (!x) return;
      const v = this._v(x);
      if (d.felt === "saet") v.saet = Math.min(10, Math.max(1, Number(v.saet) + Number(d.dir)));
      else if (d.felt === "kg") v.kg = Math.max(0, Math.round((Number(v.kg || 0) + Number(d.dir) * (x.kg_trin || 1)) * 100) / 100);
      else v.antal = Math.max(0, Math.round((Number(v.antal) + Number(d.dir) * (x.trin || 1)) * 100) / 100);
      this._val[x.id] = v;
      this._render();
    } else if (act === "done") {
      const x = this._post(a, d.id);
      if (!x) return;
      const v = this._v(x);
      delete this._val[x.id];
      this._send({ op: "oevelse", id: x.id, antal: v.antal, kg: x.har_kg ? v.kg : null, saet: v.saet, session: x.session }, "o_" + x.id);
    } else if (act === "fortryd") {
      this._send({ op: "fortryd", id: d.id }, "o_" + d.id);
    } else if (act === "info") {
      this._aaben[d.id] = !this._aaben[d.id];
      this._render();
    } else if (act === "sted") {
      this._sted = d.sted;
      this._render();
    } else if (act === "spist") {
      this._send({ op: "maaltid", dag: d.dag, id: d.id, andel: Number(d.v) }, "k_" + d.dag + "_" + d.id);
    } else if (act === "kostdag") {
      this._kostdag = d.dag;
      this._render();
    } else if (act === "alle") {
      this._alle = !this._alle;
      this._render();
    } else if (act === "vaelg") {
      this._kladde[d.felt] = d.v;
      this._render();
    } else if (act === "smerte") {
      this._send({ op: "smerte", score: Number(d.v) }, "smerte");
    } else if (act === "svar") {
      const t = String(this._kladde["q_" + d.id] ?? "").trim();
      if (!t) return this._fejl("Skriv eller vælg et svar først");
      delete this._kladde["q_" + d.id];
      this._send({ op: "svar", id: d.id, tekst: t }, "q_" + d.id);
    } else if (act === "maal") {
      const cm = this._num("m_" + d.id);
      if (cm === null || cm < 10 || cm > 200) return this._fejl("Skriv målet i cm");
      delete this._kladde["m_" + d.id];
      this._send({ op: "maal", id: d.id, cm }, "m_" + d.id);
    }
  }

  _fejl(t) {
    this.dispatchEvent(new CustomEvent("hass-notification", { detail: { message: t }, bubbles: true, composed: true }));
  }

  _post(a, id) {
    return [...(a.daglig || []), ...(a.hoved || []), ...(a.alternativ || []), ...(a.andre || [])].find((x) => x.id === id);
  }

  _v(x) {
    const v = this._val[x.id];
    return {
      antal: v && v.antal !== undefined ? v.antal : x.antal,
      kg: v && v.kg !== undefined ? v.kg : x.kg,
      saet: v && v.saet !== undefined ? v.saet : x.saet,
    };
  }

  // Farvet hoved med titel og HVORFOR. Teksterne står i data-filerne.
  _hero(titel, hvorfor, ekstra = "", klasse = "") {
    return `<div class="hero ${klasse}">
      <div class="herotitel">${titel}</div>
      ${hvorfor ? `<div class="herohv">${hbcEsc(hvorfor)}</div>` : ""}${ekstra}</div>`;
  }
  // Dagens fremdrift: ét samlet tal for de øvelser der hører til dagens sted.
  _fremdrift(liste, alternativ = []) {
    let l = liste;
    if (alternativ.length && alternativ.filter((x) => x.gjort).length > liste.filter((x) => x.gjort).length) l = alternativ;
    if (!l.length) return "";
    const n = l.filter((x) => x.gjort).length;
    const pct = (100 * n) / l.length;
    return `<div class="fremdrift ${n === l.length ? "fuld" : ""}">
      <div class="row"><b>${n === l.length ? "✅ Alt klaret i dag" : "I dag"}</b><span class="pill">${n}/${l.length} klaret</span></div>
      <div class="bar"><div style="width:${pct}%"></div></div></div>`;
  }

  _hvorfor(t) {
    return t ? `<div class="hvf"><span class="hvfi">💡</span><span>${hbcEsc(t)}</span></div>` : "";
  }

  // ---------------------------------------------------------------- I dag --
  _bannere(a) {
    return (a.bannere || []).map((b) => `<div class="banner">${hbcEsc(b)}</div>`).join("");
  }

  _idag(a) {
    const sted = a.sted;
    const liste = [...a.daglig, ...a.hoved].filter((x) => x.steder.includes(sted) && !x.hvile);
    const klaret = liste.filter((x) => x.gjort).length;
    const v = a.vaegt || {};
    const k = this._kladde;
    const sn = a.smerte_navn || "Knæ";
    const ss = a.smerte_sidst;
    return `
      ${this._bannere(a)}
      <h3>Vægt</h3>
      <div class="row">
        <input data-k="vaegt" type="text" inputmode="decimal" placeholder="kg" value="${hbcEsc(k.vaegt ?? "")}">
        <button class="pri" data-act="vaegt">${this._vent.vaegt ? "Gemmer …" : v.i_dag ? "Ret dagens" : "Gem vægt"}</button>
        <span class="dim">${v.sidst ? `Sidst: <b>${hbcTal(v.sidst)} kg</b> (${hbcDato(v.sidst_dato)})` : "Ingen vejninger endnu"}</span>
      </div>
      <div class="dim lille">Vej dig om morgenen efter toilettet, før mad og kaffe. Mad og væske flytter vægten 1-2 kg i løbet af en dag, så kun morgenvægten kan sammenlignes fra uge til uge.</div>

      <h3>Dagens program · ${hbcEsc(a.ugedag)}</h3>
      ${this._hero(
        `${hbcEsc(a.session.navn)} <span class="pill">${klaret}/${liste.length} klaret</span>`,
        a.session.hvorfor,
        `<div class="bar"><div style="width:${liste.length ? (100 * klaret) / liste.length : 0}%"></div></div>
         <div class="lille">${liste.map((x) => `${x.gjort ? "✅" : "▫️"} ${hbcEsc(x.navn.split(" (")[0])}`).join(" · ")}</div>`
      )}

      <h3>Ugens ${hbcEsc(sn.toLowerCase())} (0 = ingen gener, 10 = værst tænkelige)</h3>
      <div class="dim lille">Tallet styrer programmet: stiger det, bliver næste uge automatisk skånsom, så du ikke træner dig ind i et tilbagefald.</div>
      <div class="chips">${[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((n) => `<button class="chip tal" data-act="smerte" data-v="${n}">${n}</button>`).join("")}</div>
      <div class="dim lille">${this._vent.smerte ? "Gemmer …" : ss ? `Sidst: <b>${ss.score}</b> (${hbcDato(ss.dato)}). Du bliver spurgt hver søndag.` : "Du bliver spurgt hver søndag — eller svar her."}</div>`;
  }

  // -------------------------------------------------------------- Træning --
  _raekke(x) {
    const v = this._v(x);
    const vent = this._vent["o_" + x.id];
    const step = (felt, val, enhed) => `
      <div class="step">
        <button data-act="step" data-id="${x.id}" data-felt="${felt}" data-dir="-1">−</button>
        <span class="val">${hbcTal(val)}<small>${hbcEsc(enhed)}</small></span>
        <button data-act="step" data-id="${x.id}" data-felt="${felt}" data-dir="1">+</button>
      </div>`;
    const g = x.gjort;
    const b = x.billeder || [];
    const aaben = this._aaben[x.id];
    return `
      <div class="ov ${g ? "gjort" : ""} ${x.hvile ? "hvile" : ""} ${aaben ? "aaben" : ""}">
        <div class="ovtop" data-act="info" data-id="${x.id}">
          ${b.length && !aaben ? `<img class="thumb" loading="lazy" src="${hbcEsc(b[0])}" alt="">` : ""}
          <div class="ovtekst">
            <div class="navn">${g ? "✅ " : ""}${hbcEsc(x.navn)}</div>
            <div class="dim lille">${x.sidst ? "sidst " + hbcEsc(x.sidst) : "første gang"}</div>
          </div>
          <span class="chev">${aaben ? "▴" : "▾"}</span>
        </div>
        ${x.hvorfor && !g && !aaben ? `<div class="hvf kort" data-act="info" data-id="${x.id}"><span class="hvfi">💡</span><span>${hbcEsc(x.hvorfor)}</span></div>` : ""}
        ${x.hvile ? `<div class="advarsel">⏳ ${hbcEsc(x.hvile)}</div>` : ""}
        ${aaben && b.length ? `<div class="frames">${b.map((u) => `<img loading="lazy" src="${hbcEsc(u)}" alt="">`).join("")}</div>` : ""}
        ${aaben && x.hvorfor ? `<div class="boks hv"><div class="bokst">Hvorfor</div>${hbcEsc(x.hvorfor)}</div>` : ""}
        ${aaben && x.hvordan ? `<div class="boks"><div class="bokst">Sådan gør du</div>${hbcEsc(x.hvordan)}</div>` : ""}
        ${
          g
            ? `<div class="row"><span>Logget: <b>${g.saet || x.saet} × ${hbcTal(g.antal)} ${hbcEsc(x.enhed)}${g.kg ? ` · ${hbcTal(g.kg)} kg` : ""}</b></span>
               <button class="sek" data-act="fortryd" data-id="${x.id}">${vent ? "…" : "Fortryd"}</button></div>`
            : `<div class="row ctl">
                ${x.saet_valg ? step("saet", v.saet, "sæt") : `<span class="saet">${x.saet} ×</span>`}
                ${step("antal", v.antal, x.enhed)}
                ${x.har_kg ? step("kg", v.kg || 0, "kg") : ""}
                <button class="pri" data-act="done" data-id="${x.id}">${vent ? "Gemmer …" : "Done"}</button>
              </div>`
        }
      </div>`;
  }

  _traening(a) {
    const sted = this._sted || a.sted;
    const f = (l) => l.filter((x) => x.steder.includes(sted));
    const hoved = f(a.hoved || []);
    return `
      ${this._bannere(a)}
      <div class="row">
        <div class="seg">
          ${(a.steder || [{ id: "fitness", navn: "Fitness" }, { id: "hjemme", navn: "Hjemme" }]).map((s) => `<button class="${s.id === sted ? "on" : ""}" data-act="sted" data-sted="${hbcEsc(s.id)}">${hbcEsc(s.navn)}</button>`).join("")}
        </div>
        <span class="dim lille">Tryk på en øvelse for hvorfor og hvordan.</span>
      </div>
      ${this._fremdrift([...(a.daglig || []), ...hoved].filter((x) => x.steder.includes(sted) && !x.hvile))}
      ${this._hero(hbcEsc(a.daglig_navn || "Hver dag"), a.daglig_hvorfor, "", "blid")}
      ${f(a.daglig || []).map((x) => this._raekke(x)).join("")}
      ${this._hero(hbcEsc(a.session.navn), a.session.hvorfor)}
      ${hoved.length ? hoved.map((x) => this._raekke(x)).join("") : `<div class="dim">Ingen tunge øvelser i dag — musklerne vokser mens du hviler.</div>`}
      <h3 class="klik" data-act="alle">${this._alle ? "▾" : "▸"} Alle andre øvelser (${(a.andre || []).length})</h3>
      ${this._alle ? (a.andre || []).map((x) => this._raekke(x)).join("") : ""}`;
  }

  // ----------------------------------------------------------------- Kost --
  _kost(a) {
    const dage = a.dage || [];
    const weekend = [0, 6].includes(new Date().getDay());
    const valgt = this._kostdag || (weekend ? "weekend" : "hverdag");
    const dag = dage.find((x) => x.id === valgt) || dage[0];
    // Sensoren genlæses kun hver time: efter midnat er gårsdagens "spist" ikke dagens.
    const nu = new Date();
    const iDagIso = `${nu.getFullYear()}-${String(nu.getMonth() + 1).padStart(2, "0")}-${String(nu.getDate()).padStart(2, "0")}`;
    const frisk = a.dato === iDagIso;
    const iDag = frisk && a.i_dag ? a.i_dag : { kcal: 0, protein: 0, antal: 0 };
    const maaltid = (m) => {
      const s = frisk ? Number(m.spist || 0) : 0;
      const vk = "k_" + dag.id + "_" + m.id;
      const vent = this._vent[vk];
      const knap = (v, tekst) =>
        `<button class="${s === v ? "pri" : "sek"}" data-act="spist" data-dag="${dag.id}" data-id="${hbcEsc(m.id)}" data-v="${s === v ? 0 : v}">${vent ? "…" : s === v ? "✓ " + tekst : tekst}</button>`;
      return `
      <div class="mrk ${s ? "spist" : ""}">
        <div class="mtid">${hbcEsc(m.tid)}</div>
        <div class="mkrop">
          <div>${hbcEsc(m.hvad)}</div>
          <div class="pills"><span class="pill">${m.kcal} kcal</span><span class="pill">${m.protein} g protein</span></div>
          ${this._hvorfor(m.hvorfor)}
          <div class="row hoejre">${knap(0.5, "Halvt")}${knap(1, "Spist")}</div>
        </div>
      </div>`;
    };
    const pct = Math.min(100, Math.round((100 * iDag.kcal) / Number(a.state || 1)));
    const iDagHtml = `<div class="raad"><div class="navn">I dag: ${iDag.kcal} af ${hbcEsc(a.state)} kcal · ${iDag.protein} af ${hbcEsc(a.protein)} g protein</div>
      <div class="bar"><div style="width:${pct}%"></div></div>
      <div class="lille dim">Tryk Spist eller Halvt under hvert måltid. Tryk igen for at fortryde.</div></div>`;
    return `
      ${this._hero(
        `${a.state} kcal · ${hbcEsc(a.protein)} g protein om dagen`,
        a.hvorfor_maal,
        a.justering ? `<div class="lille herofod">${hbcEsc(a.justering)}</div>` : ""
      )}
      ${a.ekstra ? `<div class="banner">${hbcEsc(a.ekstra)}</div>` : ""}
      ${iDagHtml}
      ${
        dag
          ? `<div class="row">
        <div class="seg">${dage.map((x) => `<button class="${x.id === dag.id ? "on" : ""}" data-act="kostdag" data-dag="${x.id}">${hbcEsc(x.titel.split(" ")[0])}</button>`).join("")}</div>
        <span class="dim lille">ca. ${dag.kcal} kcal · ${dag.protein} g protein</span></div>
      <div class="tidslinje">${dag.maaltider.map(maaltid).join("")}</div>`
          : ""
      }
      ${(a.afsnit || [])
        .map(
          (af) => `<h3><ha-icon icon="${hbcEsc(af.ikon)}"></ha-icon> ${hbcEsc(af.titel)}</h3>
        ${af.raad.map((r) => `<div class="raad"><div class="navn">${hbcEsc(r.goer)}</div>${this._hvorfor(r.hvorfor)}</div>`).join("")}`
        )
        .join("")}`;
  }

  // ------------------------------------------------------------ Statistik --
  _graf(serier, o = {}) {
    const W = 340, H = o.h || 170, L = 34, R = 8, T = 8, B = 20;
    const alle = serier.flatMap((s) => s.pts);
    if (!alle.length) return `<div class="dim">Ingen data endnu.</div>`;
    const xs = alle.map((p) => p[0]);
    let x0 = Math.min(...xs), x1 = Math.max(...xs);
    if (x1 - x0 < 86400000 * 7) x1 = x0 + 86400000 * 7;
    const ys = alle.map((p) => p[1]).concat(o.ymed || []);
    let y0 = o.ymin !== undefined ? o.ymin : Math.floor(Math.min(...ys) - 0.5);
    let y1 = o.ymax !== undefined ? o.ymax : Math.ceil(Math.max(...ys) + 0.5);
    if (y1 <= y0) y1 = y0 + 1;
    const X = (x) => L + ((x - x0) / (x1 - x0)) * (W - L - R);
    const Y = (y) => T + (1 - (y - y0) / (y1 - y0)) * (H - T - B);
    let g = "";
    const trin = o.ytrin || Math.max(1, Math.round((y1 - y0) / 5));
    for (let y = Math.ceil(y0 / trin) * trin; y <= y1; y += trin)
      g += `<line x1="${L}" x2="${W - R}" y1="${Y(y)}" y2="${Y(y)}" class="grid"/><text x="${L - 4}" y="${Y(y) + 3}" class="akse" text-anchor="end">${y}</text>`;
    (o.linjer || []).forEach(([y, tekst]) => {
      if (y < y0 || y > y1) return;
      g += `<line x1="${L}" x2="${W - R}" y1="${Y(y)}" y2="${Y(y)}" class="maal"/><text x="${W - R}" y="${Y(y) - 3}" class="akse maalt" text-anchor="end">${hbcEsc(tekst)}</text>`;
    });
    [x0, (x0 + x1) / 2, x1].forEach((x, i) => {
      g += `<text x="${X(x)}" y="${H - 5}" class="akse" text-anchor="${["start", "middle", "end"][i]}">${hbcDato(x)}</text>`;
    });
    serier.forEach((s) => {
      if (!s.pts.length) return;
      const d = s.pts.map((p, i) => `${i ? "L" : "M"}${X(p[0]).toFixed(1)},${Y(p[1]).toFixed(1)}`).join("");
      g += `<path d="${d}" fill="none" stroke="${s.farve}" stroke-width="${s.tyk || 2}" ${s.streg ? 'stroke-dasharray="5 4"' : ""}/>`;
      if (s.prik) g += s.pts.map((p) => `<circle cx="${X(p[0]).toFixed(1)}" cy="${Y(p[1]).toFixed(1)}" r="3" fill="${s.farve}"/>`).join("");
    });
    return `<svg viewBox="0 0 ${W} ${H}" class="graf">${g}</svg>`;
  }

  _statistik(a) {
    const v = a.vurdering || {};
    const t = (s) => new Date(s).getTime();
    const vaegt = (a.vaegt || []).map((p) => [t(p[0]), Number(p[1])]);
    const forv = (a.forventet || []).map((p) => [t(p[0]), Number(p[1])]);
    const smerte = (a.smerte || []).map((p) => [t(p[0]), Number(p[1])]);
    const mp = a.milepaele || [];
    const sidste = vaegt.length ? vaegt[vaegt.length - 1][1] : null;
    const naeste = mp.find((m) => sidste === null || sidste > m); // vægttab: milepæle i faldende orden
    const tabel = (hoved, raekker) =>
      raekker.length
        ? `<table><tr>${hoved.map((h) => `<th>${h}</th>`).join("")}</tr>${raekker.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("")}</table>`
        : `<div class="dim">Ingen data endnu.</div>`;
    return `
      <div class="vurd" style="border-color:${HBC_NIVEAU[v.niveau] || "#607d8b"}">
        <div class="lille dim">Ugens vurdering${a.foreloebig ? " (foreløbig)" : v.dato ? " · " + hbcDato(v.dato) : ""}</div>
        <div class="vlabel" style="color:${HBC_NIVEAU[v.niveau] || "#607d8b"}">${hbcEsc(v.label || "")}</div>
        <div>${hbcEsc(v.tekst || "")}</div>
        ${(v.dele || []).map((d) => `<div class="lille"><span class="prik" style="background:${d.niveau === null ? "#bbb" : HBC_NIVEAU[d.niveau]}"></span><b>${hbcEsc(d.navn)}:</b> ${hbcEsc(d.tekst)}</div>`).join("")}
        <div class="lille dim">Opdateres hver søndag aften.</div>
      </div>

      <h3>Vægt</h3>
      <div class="row">
        <span class="stor">${sidste !== null ? hbcTal(sidste) + " kg" : "–"}</span>
        <span class="dim">${a.basis ? `start ${hbcTal(a.basis)} kg · ${sidste !== null ? (sidste - a.basis >= 0 ? "+" : "") + hbcTal(Math.round((sidste - a.basis) * 10) / 10) + " kg" : ""}` : ""}
          ${a.trend !== null && a.trend !== undefined ? ` · trend ${a.trend >= 0 ? "+" : ""}${hbcTal(a.trend)} kg/uge` : ""}</span>
      </div>
      ${naeste && sidste !== null ? `<div class="dim lille">${hbcTal(Math.round((sidste - naeste) * 10) / 10)} kg ned til ${naeste} kg.</div>` : ""}
      ${this._graf(
        [
          { pts: forv, farve: "var(--secondary-text-color)", streg: true, tyk: 1.5 },
          { pts: vaegt, farve: "var(--primary-color)", prik: true },
        ],
        { linjer: mp.map((m) => [m, m + " kg"]), ymed: sidste !== null && naeste ? [naeste - 0.5] : [] }
      )}
      <div class="dim lille">Stiplet: forventet (${hbcEsc(a.forventet_tekst || "")}). Vægten svinger 1-2 kg fra dag til dag — se på trenden, ikke på den enkelte vejning.</div>

      <h3>${hbcEsc(a.smerte_navn || "Knæ")} (ugens score, lavere er bedre)</h3>
      ${this._graf([{ pts: smerte, farve: "#ef6c00", prik: true }], { ymin: 0, ymax: 10, ytrin: 2, h: 130 })}

      <h3>Træning pr. uge</h3>
      ${tabel(["Uge", "Styrke", "Kondition", "Basis", "Langtur"], (a.uger || []).map((u) => [u.uge, `${u.styrke}/${a.styrke_pr_uge || 3}`, u.kondition, `${u.daglig}/7`, u.km ? hbcTal(u.km) + " km" : "–"]))}

      <h3>Styrke — første mod seneste</h3>
      ${tabel(["Øvelse", "Første", "Seneste", ""], (a.loeft || []).map((l) => [hbcEsc(l.navn.split(" (")[0]), hbcEsc(l.foerste), hbcEsc(l.sidste), `<b class="${l.pct > 0 ? "op" : ""}">${l.pct > 0 ? "+" : ""}${l.pct} %</b>`]))}

      <h3>Kropsmål (cm)</h3>
      ${tabel(["Mål", "Første", "Seneste", ""], (a.maal || []).map((m) => [hbcEsc(m.navn), hbcTal(m.foerste), hbcTal(m.sidste), `<b>${m.diff > 0 ? "+" : ""}${hbcTal(m.diff)}</b>`]))}`;
  }

  // ----------------------------------------------------------- Spørgsmål --
  _spoergsmaal(a) {
    const k = this._kladde;
    const sp = (a.spoergsmaal || []).slice(0, 4);
    const q = (x) => {
      const n = "q_" + x.id;
      let felt;
      if (x.type === "valg")
        felt = `<div class="chips">${(x.valg || []).map((v) => `<button class="chip ${k[n] === v ? "on" : ""}" data-act="vaelg" data-felt="${n}" data-v="${hbcEsc(v)}">${hbcEsc(v)}</button>`).join("")}</div>`;
      else
        felt = `<input class="bred" data-k="${n}" type="text" ${x.type === "tal" ? 'inputmode="decimal"' : ""} placeholder="Dit svar" value="${hbcEsc(k[n] ?? "")}">`;
      return `<div class="ov"><div class="navn">${hbcEsc(x.tekst)}</div>${felt}
        <div class="row hoejre"><button class="pri" data-act="svar" data-id="${x.id}">${this._vent[n] ? "Gemmer …" : "Gem svar"}</button></div></div>`;
    };
    return `
      <h3>Spørgsmål til dig ${a.spoergsmaal && a.spoergsmaal.length ? `(${a.spoergsmaal.length} tilbage)` : ""}</h3>
      ${sp.length ? sp.map(q).join("") : `<div class="dim">Alt er besvaret. Tak — svarene bruges til at justere programmet.</div>`}
      <h3>Kropsmål (cm) — hver 4. uge, om morgenen, afslappet</h3>
      ${(a.maalinger || [])
        .map(
          (m) => `<div class="row maalrk">
            <span class="bred">${hbcEsc(m.navn)}<br><span class="dim lille">${m.sidst ? `sidst ${hbcTal(m.sidst)} cm (${hbcDato(m.dato)})` : "ikke målt endnu"}</span></span>
            <input data-k="m_${m.id}" type="text" inputmode="decimal" placeholder="cm" value="${hbcEsc(k["m_" + m.id] ?? "")}">
            <button class="pri" data-act="maal" data-id="${m.id}">${this._vent["m_" + m.id] ? "…" : "Gem"}</button>
          </div>`
        )
        .join("")}`;
  }
}

const HBC_CSS = `
  .wrap { padding: 12px 14px 16px; font-size: 15px; line-height: 1.4; }
  h3 { margin: 18px 0 6px; font-size: 15px; font-weight: 600; color: var(--primary-text-color); }
  h3:first-child { margin-top: 2px; }
  h3.klik { cursor: pointer; color: var(--primary-color); }
  .tom { padding: 24px; text-align: center; color: var(--secondary-text-color); }
  .dim { color: var(--secondary-text-color); }
  .lille { font-size: 13px; }
  .stor { font-size: 28px; font-weight: 700; }
  .row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin: 4px 0; }
  .row.hoejre { justify-content: flex-end; }
  .bred { flex: 1 1 140px; min-width: 0; }
  .banner { background: color-mix(in srgb, var(--warning-color, #ff9800) 16%, transparent); border-left: 4px solid var(--warning-color, #ff9800);
    padding: 8px 10px; border-radius: 6px; margin-bottom: 8px; }
  input { font: inherit; padding: 9px 10px; border-radius: 8px; border: 1px solid var(--divider-color); width: 84px;
    background: var(--card-background-color); color: var(--primary-text-color); box-sizing: border-box; }
  input.bred { width: auto; }
  button { font: inherit; border: 0; border-radius: 8px; padding: 9px 14px; cursor: pointer; background: var(--secondary-background-color); color: var(--primary-text-color); }
  button.pri { background: var(--primary-color); color: var(--text-primary-color, #fff); font-weight: 600; }
  button.sek { padding: 6px 10px; font-size: 13px; }
  .pill { background: var(--secondary-background-color); border-radius: 12px; padding: 2px 10px; font-size: 13px; }
  .bar { height: 8px; border-radius: 4px; background: var(--secondary-background-color); overflow: hidden; margin: 6px 0; }
  .bar div { height: 100%; background: var(--success-color, #43a047); }
  .lbl { margin: 10px 0 4px; font-size: 13px; color: var(--secondary-text-color); }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; }
  .chip { padding: 7px 11px; font-size: 13px; border-radius: 16px; }
  .chip.tal { min-width: 38px; }
  .chip.on { background: var(--primary-color); color: var(--text-primary-color, #fff); }
  .seg { display: inline-flex; border-radius: 8px; overflow: hidden; border: 1px solid var(--divider-color); }
  .seg button { border-radius: 0; padding: 7px 14px; background: transparent; }
  .seg button.on { background: var(--primary-color); color: var(--text-primary-color, #fff); }
  .ov { border: 1px solid var(--divider-color); border-left: 4px solid var(--primary-color); border-radius: 12px; padding: 10px 12px; margin: 10px 0;
    background: var(--card-background-color); box-shadow: 0 1px 3px rgba(0,0,0,0.12); }
  .ov.aaben { box-shadow: 0 3px 10px rgba(0,0,0,0.22); }
  .ov.gjort { border-left-color: var(--success-color, #43a047); }
  .ov.gjort { background: color-mix(in srgb, var(--success-color, #43a047) 10%, transparent); }
  .ov.hvile { opacity: 0.75; }
  .thumb { width: 64px; height: 48px; object-fit: cover; border-radius: 8px; align-self: center; flex: 0 0 auto; background: #fff; }
  .frames { display: flex; gap: 6px; margin: 6px 0; }
  .frames img { flex: 1 1 0; min-width: 0; max-width: 50%; height: auto; border-radius: 6px; background: #fff; }
  .ovtop { display: flex; gap: 12px; align-items: center; cursor: pointer; }
  .ovtekst { flex: 1 1 auto; min-width: 0; }
  .chev { color: var(--secondary-text-color); font-size: 14px; }
  .navn { font-weight: 600; }
  .hvf { display: flex; gap: 8px; margin: 8px 0 2px; font-size: 13.5px; line-height: 1.45; color: var(--primary-text-color); }
  .hvf .hvfi { flex: 0 0 auto; }
  .hvf.kort span:last-child { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; cursor: pointer; opacity: 0.85; }
  .boks { margin: 8px 0; padding: 9px 11px; border-radius: 10px; background: var(--secondary-background-color); font-size: 14px; }
  .boks.hv { background: color-mix(in srgb, var(--primary-color) 13%, transparent); }
  .bokst { font-size: 11.5px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; color: var(--primary-color); margin-bottom: 3px; }
  .hero { margin: 16px 0 8px; padding: 13px 15px; border-radius: 14px;
    background: linear-gradient(135deg, color-mix(in srgb, var(--primary-color) 30%, transparent), color-mix(in srgb, var(--primary-color) 7%, transparent)); }
  .hero:first-child { margin-top: 2px; }
  .hero.blid { background: linear-gradient(135deg, color-mix(in srgb, var(--success-color, #43a047) 24%, transparent), color-mix(in srgb, var(--success-color, #43a047) 5%, transparent)); }
  .herotitel { font-size: 17px; font-weight: 700; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .herohv { margin-top: 5px; font-size: 14px; line-height: 1.45; opacity: 0.92; }
  .herofod { margin-top: 6px; opacity: 0.75; }
  .hero .bar { background: rgba(127,127,127,0.25); }
  .fremdrift { margin: 6px 0 10px; }
  .fremdrift .bar { height: 10px; border-radius: 5px; }
  .fremdrift.fuld .pill { background: color-mix(in srgb, var(--success-color, #43a047) 30%, transparent); }
  .tidslinje { margin: 6px 0 4px; border-left: 2px solid var(--divider-color); margin-left: 6px; }
  .mrk { position: relative; padding: 4px 0 12px 16px; }
  .mrk::before { content: ""; position: absolute; left: -7px; top: 8px; width: 12px; height: 12px; border-radius: 50%; background: var(--primary-color); }
  .mtid { font-weight: 700; color: var(--primary-color); font-size: 14px; }
  .pills { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 5px; }
  .raad { border-radius: 12px; padding: 10px 12px; margin: 8px 0; background: var(--secondary-background-color); }
  .raad .hvf { opacity: 0.9; }
  h3 ha-icon { --mdc-icon-size: 18px; color: var(--primary-color); vertical-align: -3px; }
  .advarsel { color: var(--warning-color, #ef6c00); font-size: 13px; margin: 4px 0; }
  .ctl { margin-top: 8px; }
  .ctl .pri { margin-left: auto; }
  .saet { font-weight: 600; }
  .step { display: inline-flex; align-items: center; border: 1px solid var(--divider-color); border-radius: 8px; overflow: hidden; }
  .step button { border-radius: 0; padding: 8px 13px; font-size: 18px; line-height: 1; }
  .step .val { min-width: 54px; text-align: center; font-weight: 700; padding: 0 4px; }
  .step small { font-weight: 400; margin-left: 3px; color: var(--secondary-text-color); }
  .vurd { border-left: 6px solid; padding: 8px 12px; border-radius: 8px; background: var(--secondary-background-color); }
  .vlabel { font-size: 22px; font-weight: 700; margin: 2px 0 4px; }
  .prik { display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 6px; }
  .graf { width: 100%; height: auto; display: block; margin: 6px 0; }
  .grid { stroke: var(--divider-color); stroke-width: 0.5; }
  .maal { stroke: var(--success-color, #43a047); stroke-width: 1; stroke-dasharray: 2 3; }
  .akse { font-size: 9px; fill: var(--secondary-text-color); }
  .maalt { fill: var(--success-color, #43a047); }
  table { width: 100%; border-collapse: collapse; font-size: 13px; margin: 4px 0 8px; }
  th { text-align: left; color: var(--secondary-text-color); font-weight: 500; }
  th, td { padding: 4px 6px 4px 0; border-bottom: 1px solid var(--divider-color); }
  .op { color: var(--success-color, #2e7d32); }
  .maalrk input { width: 72px; }
  .mrk.spist .mtid::after { content: " ✓"; color: var(--success-color, #43a047); }
  .mrk .row.hoejre { gap: 6px; margin-top: 6px; }
  .bar { height: 8px; border-radius: 4px; background: var(--divider-color); overflow: hidden; margin: 6px 0; }
  .bar > div { height: 100%; background: var(--success-color, #43a047); }
`;

if (!customElements.get("helbred-card")) {
  customElements.define("helbred-card", HelbredCard);
  window.customCards = window.customCards || [];
  window.customCards.push({ type: "helbred-card", name: "Helbred", description: "Trænings- og vægtlog" });
  console.info(`%c HELBRED-CARD %c ${HBC_VERSION} `, "background:#2e7d32;color:#fff", "background:#ddd;color:#000");
}
