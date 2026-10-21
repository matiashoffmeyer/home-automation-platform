---
paths:
  - "dashboards/**"
  - "www/**"
  - "scripts/lovelace_resources.py"
---

> *Danish. A path-scoped rule file: Claude Code loads it the first time a
> file matching `paths:` is read. See
> [docs/methodology.md](../../docs/methodology.md).*

# Dashboards og Lovelace

Path-scopet fra CLAUDE.md (Permanente fakta) — loades når du læser en fil
der matcher `paths:`. Samme genkendelses-lag: regel, signatur, entity-navn.
Den lange version (måledata, incidents): `docs/permanente_fakta.md`
(`grep -n "<nøgleord>"`). Ændrer virkeligheden sig, ret BEGGE lag.

- **Lovelace-`visibility` har INGEN `template`-betingelse**, og `attribute:`
  findes heller ikke. En ukendt condition-type afvises **tavst og lukket**.
  **Signatur:** et kort er væk uden nogen fejl. → læg tallet i sensorens state
  og brug `numeric_state`. **Et tile-feature ELLER service-kald uden entitetens
  feature-bit fejler lige så tavst** → tjek `supported_features` før copy-paste.
- **Lovelace kan IKKE rulle til et kort på samme side** → byg det som link til
  en `subview: true`-view + `back_path`; templated tekst kræver markdown-kortet,
  som ingen `tap_action` har.
- **`statistics-graph` tegner serier SIDE OM SIDE, ikke stablet** → en
  DELMÆNGDE ligner en konkurrent. Navnet må bære relationen (`👻 heraf uden
  radio`), og en ny serie skal ind i ALLE periode-varianter af kortet.

## Standing instruction: tekst på dashboards (flyttet fra CLAUDE.md 📊)

- **Tekst på dashboards (per 2026-09-29, user-spec: "kun hvad jeg har brug for
  at vide, ikke synlige noter til dig selv"):** synligt er KUN korte danske
  tile-navne uden emoji, én linje scope/brugs-instruks og live-status. Hvorfor,
  måledata, datoer, incidents, entity-/filnavne → YAML-kommentar over kortet.
  **Signatur: en markdown under en slider der forklarer hvorfor defaulten er
  som den er.** Indstillinger: ÉN sektion pr. emne; ny slider → den sektion der
  passer (🔍 Søg-fanen, `www/indstillinger-soeg.js`, finder den selv; efter en
  ændring af kortet: `python3 scripts/lovelace_resources.py`). **Støvsug, Mad,
  AirBnB, Tapo og Vandventil er FANER i Indstillinger (2026-09-30)** — kun Lys,
  Scener, Festlys, info-siderne og KONTROLPANELERNE Mad + Støvsug (kun knapper
  og status, i Lys-sidens stil) er egne dashboards; et nyt emne = ny fane.
