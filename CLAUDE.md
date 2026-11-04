# CLAUDE.md — Standing Instructions

> **About this file.** The instruction set the AI coding agent (Claude
> Code) loads at the start of every session: recent lessons, permanent
> platform facts, standing rules and recurring failure classes, each kept to
> a one-line signature with a pointer to the long version (in Danish, the
> working language of the household).
> [docs/methodology.md](docs/methodology.md) describes the method in
> English. Links to operational logs (sprint log, backlog, feedback data)
> point to files that are not part of this repository.

Loaded in EVERY session; **every line is paid for in every call**. So this is a
*recognition layer*: rule, signature, pointer. History, data and incidents live in
docs/ (Danish — grep hints keep Danish keywords) and cost tokens only when read.

| To find out | Read (NOT auto-loaded) |
|---|---|
| What a failure looked like | [docs/fejlklasser.md](docs/fejlklasser.md) |
| Why it was built so | [docs/sprint_log.md](docs/sprint_log.md) — `grep`, never read it whole |
| Next task | [BACKLOG.md](BACKLOG.md) — only for triage questions |
| Where concept X lives | [docs/cross_cutting_map.md](docs/cross_cutting_map.md) |
| Entity name for X | `python3 scripts/hq.py find <words…>` (live, æøå-folded; `--offline` in the cloud) |
| Live state / history / who changed X | `hq.py state\|hist --stats\|flanks\|who X` — local time, ≤ 40 lines |
| Where entity X is used | `hq.py where X` — file:lines, live scan (~1 s), template-built refs separately |
| Who may write lamp X, at what rank | `docs/auto/ejerskab/<lamp>.md` (generated; the hook hands it to you when you touch the lamp) |
| Everything room X touches | `docs/auto/rooms/<room>.md` (generated, 100-400 lines) — cheaper than grepping 66 files |
| Validate / prove a refactor WITHOUT the NUC | `python3 scripts/ha_offline.py check\|equiv\|staging\|refs` — [docs/konsolidering.md](docs/konsolidering.md) |

---

## 🕐 Recent sprints — what the house learned last

One verdict per sprint, 3-5 lines, **max 3 notes** (`claude_rules.py check` counts);
roll the oldest out in the SAME commit. Full note: `grep -n "Sprint <date>"
docs/sprint_log.md`. A permanent lesson goes to "Permanent facts" or a failure class.

- **2026-10-26 — a witness for a sleeping partner protects no one once both
  adults have provably left.** The sleep ghost (06:39-09:24; g2_still = 100 does not
  damp energy 100, B269) blocked every fast dormant path; the prel guard set Active
  again. `binary_sensor.sove_efterslaeb_efter_afgang` (episode before the door +
  Parent B's anchor edge at the door) removes the witness; the latch's child ring is broken. B268.
- **2026-10-27 — a party is counted in zone MASS, not heads.** 15 guests showed 3:
  zones are capped at 8 (ceiling 6), and the extra floor resets at every door.
  `binary_sensor.people_fest` (min(45-, 15-min mean of occupied zones) ≥ 4.2; max
  3.71 without a party over 30 days) lifts the bid to 3.0 × mass, ceiling 30. Mass
  does NOT count 1-4 people (p50 1.5-1.8 for all) — the factor rests on one party. B271.
---

## 💡 Permanent facts (distilled from archived sprints)

Platform truths that still hold — rule, signature, entity name only. Long versions:
[docs/permanente_fakta.md](docs/permanente_fakta.md) (`grep -n "<keyword>"`, never
Read it whole). Reality changes → fix BOTH layers (here or `.claude/rules/<domain>.md`;
lint: `scripts/claude_rules.py check`).

**Home Assistant — house-wide** (authoring traps: `initial:`, slugify, `!include`,
`input_datetime`/`input_text`, `statistics`/`history_stats`, Jinja gotchas →
`.claude/rules/ha_yaml.md`, loaded on the first YAML read)
- **An HA restart kills every `to: X for: N` WAITING on an edge that already
  happened** (esp. off/cleanup paths) → time_pattern backstop measuring the time in a
  condition template. Two follow-on holes: an automation not yet listening gets NO
  triggers, and the `from: "off"` guard hides the restart edge from ON paths. Fix:
  `platform: homeassistant, event: start` + settle delay as an extra id on the
  EXISTING branch.
- **`template.reload` is NOT a free deploy** — every template entity passes
  `unavailable`, and `unavailable → off` fires off paths. **Signature:** an action in
  the same second as a reload. → explicit `from:` on `to:` triggers on template
  entities (**`scripts/b103_scan.py` blocks in pre-commit**; edge IS the evidence → its
  `ALLOWLIST` with a reason). **A `delay_on` sensor makes a REAL `off → on` exactly
  `delay_on` after the reload** → guard on the off phase's length; reload automations
  BEFORE templates. **Reload ONLY via `python3 scripts/ha_reload.py templates`**
  (restores darkened lights; `reload_guard.py` rejects the bare service, #30).
- **HA SEGFAULTS on shutdown (pychromecast thread, Python 3.14) → the final
  restore-state write NEVER happens**; only the 15-min dump survives. **Signature:
  slider/boolean changes from the last < 15 min before a restart are gone, without
  context, and `home-assistant.log.fault` has mtime = restart.** → restart ONLY with
  **`bash scripts/ha_restart.sh`** (saves first; `scripts/restart_guard.py` rejects a
  bare `ha core restart`).
- **`last_updated`/`last_changed` reset on HA restart** → NEVER a freshness measure;
  use a **written** stamp (#5). Apollo occupancy: `input_datetime.<room>_apollo_occ_since`
  (restart-safe, 1970 when off).
- **EVERY automatic bathroom off waits for `binary_sensor.badevaerelse_fugt_frisk`,
  then decides on `brusebad_hold`** (user-spec 1/10: "never turn off without a fresh
  humidity reading"). A new bathroom off path without the block is a regression (#21)
  — `grep -rn fugt_frisk`. Only the max-on watchdog is exempt on purpose.
- **Indoor humidity/temp: `sensor.inde_absolut_fugt` (g/m³) /
  `sensor.indoor_humidity_resilient` (%RH) / `sensor.indoor_temperature_resilient`
  (°C), never `timmerflotte_*` directly** — the kitchen TIMMERFLOTTE drops off Thread;
  the storage room's Broadlink is the backup (attribute `kilde`). `grep -n "TO fugt-instrumenter" docs/permanente_fakta.md`.

**Domain facts — path-scoped in `.claude/rules/`**, loaded when you read a file
matching their `paths:`. **Explaining behaviour in a domain WITHOUT reading its
files** (e.g. only via `hq.py`) → read the rule yourself first.

| Rule file | Covers |
|---|---|
| `lux_dagslys.md` | Apollo LTR390: LED and own lamps in the reading, ~20 lx step, clean samples, gate sources, deduction |
| `presence_radar.md` | Apollo/LD2410 + Valhorn: fields vs rooms, ghosts, gate layers, the sleep Apollo, blind channels (`ha_health.sh blind` BEFORE explaining presence), sleepy end devices, 🔥 ESPHome chip wear |
| `thread_matter.md` | Thread routers, partition split, BLE adapters, GRILLPLATS, phone commissioning, RCP hang |
| `lys_paerer.md` | bulb quirks (TRADFRI 2 %, RGBW, power_on_behavior, OTA), the living room's four lights, bulbs dropping off |
| `lys_effekter.md` | group calls wait for the slowest bulb, colour = 2 frames, the ZHA group, Matter reporting, transition traps |
| `gardiner_sol.md` | assumed RF positions, the hold anchor's two lists, sun penetration (the moss picture, 333°) |
| `energi.md` | delta-reported power plugs, the bike chargers, the Energi Data Service price |
| `stemme_gestus.md` | camera API dead (RTSP only), hand_recognition fingers, Speech-to-Phrase, the Android timer |
| `nemlig.md` | search is not ascii-folding, the product tree, multipack price |
| `roborock.md` | vacuum + mop is one state, cloud status lags, the robot IS the motion |
| `vejr.md` | DMI host and versions, REST sensors that freeze, met.no's cloud bias at night |
| `personer_telefon.md` | GPS proxies, iOS Always permission, zone.home, alarm sensors in UTC, button replies need network |
| `scripts_api.md` | shell_command token, POST /api/states entities, /api/template, recorder context fields, history end_time |
| `dashboards.md` | visibility conditions, no scroll-to-card, statistics-graph side by side, the text rule |
| `addons.md` | deploy from /addons/<slug>/, not the git copy — verify by version |
| `ha_yaml.md` | all automations/packages/script_pkg YAML: `initial:`, slugify, `!include`, template blocks, `input_datetime`/`input_text`, `statistics`/`history_stats`, `delay_on`/`delay_off`, Jinja gotchas |

**Radio — house-wide** (any YAML touching lights or Matter)

- **`light.spisestue_pendel` IS THE BEDROOM CEILING** (moved 06/2026, name kept; only
  member of `light.sovevaerelse_all`). Never in an open-plan call.
- **A Matter node that comes back reappears with its LAST known value** →
  `unavailable → on` is an echo. ON triggers need `from: "off"`.
- **CHIP Error 0x00000032 (Timeout) aborts the WHOLE automation script** →
  `continue_on_error: true` on Matter light calls, also via light groups
  (`ha_validate.py --check matter` blocks in pre-commit; blind to templated targets).

**📋 Cross-cutting concerns map:** [docs/cross_cutting_map.md](docs/cross_cutting_map.md)
— FIRST READ before changing cross-cutting logic.

---

## Other meta-docs

- **[AGENTS.md](AGENTS.md)** — fast-path navigation: file tree, "where do I find X", conventions, recipes
- **[system_design.md](system_design.md)** — verified Holy Grail spec (buttons, drift-back, off times,
  house modes, curtain defence) with the slider owning each number; fix it in the same commit as the behaviour
- **[docs/architecture.md](docs/architecture.md)** — Holy Grail philosophy, activity tree, mode-flag priority
- **[docs/README.md](docs/README.md)** · [automations/README.md](automations/README.md) · [packages/README.md](packages/README.md) — indexes

---

## Standing instructions

Long version — reasons, incidents, examples, recovery recipes:
[docs/standing_instructions.md](docs/standing_instructions.md) (`grep -n "<nøgleord>"`).
The rules below are binding as written. A user-spec changes → fix BOTH layers.

### 🔄 Check status BEFORE you code (user-spec 2026-07-29)

**First action in every code task**, before reading files:
`git fetch origin && git status && git rev-list --left-right --count origin/main...HEAD`.
Behind → `git merge --ff-only origin/main` BEFORE touching anything, and re-read
CLAUDE.md + relevant packages from the fresh tree. The checkout is routinely 30-200
commits behind; work on a stale base silently rolls back newer features.

### 💰 Token economy & cache (user-spec 2026-09-21)

Philosophy unchanged (**slow + thorough over fast**) — spend on diagnosis and verification.

- **Classify the task FIRST:** SIMPLE (one known slider/threshold) = `< 10 tool calls, NO full-file Read`. INVESTIGATION (bug hunt/new feature) = full log/history digging. The expensive anti-pattern is a full excavation for a text fix.
- **Context length IS the bill (measured 2026-11-03; `python3 scripts/token_audit.py sessions|context`; graphs on Statistik → Claude):** every call re-reads the whole conversation incl. your thinking (≈ 18 % of usage). The `autoCompactWindow: 200000` cap lives in **`.claude/settings.json`** (git; in `~/.claude` it vanished 29/10). `/clear` between unrelated tasks. Pause > 1 h = the WHOLE context is rewritten at double price → large context before a long physical test = ask the user for `/compact` first. Never re-read what you have; fetch only what is new.
- **NEVER save on:** log/history digging for a bug, calibration against real data, verification after deploy.
- **Anti-patterns:** re-Reading a file you just edited · dumping raw `/api/states` instead of filtering with python/grep.

### 🚦 Subagents — work yourself, delegate only broad sweeps (user-spec 2026-09-21, revised 2026-10-08)

Measured 8/10: subagents went 4 % → 33 % of usage. Each starts with 50-65k tokens
written to cache at double price BEFORE doing anything, and its findings are verified
here anyway.
1. **Work yourself:** lookups, few-file reads and code changes inline (`grep`/`hq.py`/targeted Read). Subagents only for genuinely broad sweeps (dozens of files, bug-hunt workflows), returning *only the conclusion*.
2. **Code is written by Opus** (user-spec 2026-10-07). Main session on Sonnet and code to commit → ask the user for `/model opus` rather than delegating (an Opus subagent starts cold and re-reads everything; 7/10: 3 Opus agents cost 4× the main session). User cannot answer now (🚀) → ONE Opus subagent. Sonnet (`model: "sonnet"`, never a version number) only for read-only triage such as bug-hunt finders; `subagent_type: "fork"` always runs on the main model.
3. **No parallel fleets (Pro plan quota):** max 1-2 subagents at a time — too many burn the quota mid-run, and all die WITHOUT reporting. Large reviews run SEQUENTIALLY. **Applies to the Workflow tool and "ultracode" too — nothing lifts it** (broken 10/10: Opus finders + a sceptic per finding, the quota died). `scripts/agent_guard.py` (PreToolUse) rejects workflows without `model:'sonnet'` on every agent(), with `pipeline()`/`while` or `parallel()` without `.slice(i, i + 2)`, and a 3rd concurrent Agent. Rejected = build it smaller, never circumvent.

### 🚀 Fix + commit + push FIRST — ask clarifying questions AFTER (user-spec 2026-07-27)

Asked for a fix: **change, commit and push FIRST**, then ask. Do NOT ask first and
wait, **unless the user explicitly writes that they are present and can answer now** —
blocking on a question they do not see (async/phone) loses the work. (1) Pick the most
likely, lowest-risk interpretation from the logs; (2) implement + commit + push +
deploy + notify; (3) THEN ask, clearly marked ("shipped X with default Y —
confirm/adjust:"). This **modifies** 🤔: stop-and-ask only when the user can answer, or
the change is genuinely irreversible/destructive.

### 📏 ALWAYS measure yourself — NEVER set a value from a sprint note (user-spec 2026-08-29)

**"Always measure it, never rely blindly on sprint notes — then we inherit errors and
they can grow."** Notes and code comments are *timestamped hypotheses*, not data. To
set, raise or lower a threshold, timing or offset: **pull the distribution of the
channel the gate actually reads** (percentiles + how many samples above/below) over 2-3
days BEFORE writing the number. Your numbers disagree with the note → the note is stale;
fix it in the same commit. **Signature:** a threshold that is a lone outlier among its
siblings on the SAME scale. **History/distributions: `python3 scripts/hq.py hist
<entity> --stats [--gate X]`** (samples + time-weighted, local time) — not ad hoc curl.

**Measure the right DISTRIBUTION, not just enough samples:** a negative set you label
yourself is POSED — operation delivers the whole continuum, so the gap you measure is
wider than the one you get. **Signature: the false positives cluster JUST below the
threshold instead of spreading.** Never set a gate from its own triggers alone — they
are only the ones that got through.

### 🔍 Solve tasks from actual behaviour + real-world data (user-spec 2026-07-23)

Examine **actual behaviour over the last 2-3 days**, not how the setup "should" behave.
(1) **Pull the history** of the entities involved (`hq.py hist|flanks|who`, the
ai_feedback JSONLs, `./scripts/ha_health.sh noisy`). (2) **Let real numbers drive
parameters**. (3) **Verify against reality at the end** (#6/#14): "live-tested" = real
device events + evidence in history, not synthetic events. The user keeps feeding
ground truth (ai_feedback trainers, corrections) — use it. Exceptions: trivial
syntax/docs, or behaviour the user explicitly dictates.

### 🤔 Unsure about DESIRED BEHAVIOUR → ask. Unsure about technique → look it up

**Behaviour questions (ASK, with concrete a/b/c options in prose):** "what should
happen if X times out?", "should Y fire in Dormant too?", "how bright = subjective".
**Tech questions (just do it):** syntax, entity_id, versions — look up/test. Unsure
which kind: ask anyway. But 🚀: if the user cannot answer now, ship the most likely
interpretation and ask afterwards.

### 📲 Notify the user of changes (user-spec 2026-06-27)

After **deployed changes**: one short bulleted push per work batch (not per file) —
what is live now + any manual step still missing. Skip only for pure research without
deploy. Channel: `notify/mobile_app_phone_a` via
`curl -X POST http://supervisor/core/api/services/notify/mobile_app_phone_a` with
`Authorization: Bearer $SUPERVISOR_TOKEN`.

**⚠️ EXCEPTION — AirBnB mode = SILENT (user-spec 2026-07-13):**
`input_select.house_mode` == `AirBnB` → NO push, not even the deploy summary (the phone
may be in the guest's hands). **Check the mode BEFORE you push.** Code/dashboards/
reloads are fine; only notifications are suppressed — say in your summary that the push
was skipped. **Three deliberate exceptions** MUST push in AirBnB (they reach the user
the second they flip the mode themselves): `packages/kamera_airbnb_vagt.yaml`
(user-spec 2026-09-11), the checkout date in `packages/airbnb_udtjekning.yaml`
(2026-10-28), the welcome-message reminder in `packages/airbnb_velkomst.yaml` (2026-10-29).

### 🧪 Test physically + measure when something new goes live (2026-05-03)

**Observable physical effect** (lights, curtains, sound, timing): deploy + verify HA is
really ready (state updated, not just "Command completed") → **measure the actual
behaviour** before declaring success (timestamp events via REST, read
`state_attr('light.X','hs_color')` after the action, brightness is 0-254 raw) → no match
with the design intent → iterate with measurements. **Do not stop at the first "seems
to work".** **HA's real throughput is ~5-10 light calls/sec** — loop designs assuming
>10/sec fail silently.

### ✋ Live tests and restarts need a yes via push FIRST (user-spec 2026-10-28)

**Anything the house can see or hear (lights, sound, curtains, robot) and every
restart** is asked for BEFORE: `python3 scripts/live_godkend.py spørg "<what, short
Danish>" [--genstart]` with `run_in_background` → push with Godkend / Afvis / Om 20 min
(exit 0 = yes, valid 15 min / restart 10; 1 = no; 2 = no answer = no; 3 = AirBnB → ask
in the chat). `scripts/live_guard.py` blocks the calls without a valid yes; `slut` when
done. Passive evidence in history needs nothing.
Details: `grep -n "Live-test og genstart" docs/standing_instructions.md`.

### 🎛️ Check existing sliders BEFORE you build new ones (2026-05-17)

Adjusting a parameter (timing, brightness, threshold, duration) → grep FIRST in
`packages/global_tuning.yaml`, `packages/constants.yaml` and the dashboards' Global
Tuning section. **A slider exists → tell the user before changing anything.** New
territory: slider + factor sensor + dashboard tile + snapshot export in ONE commit (the
snapshot IS the fresh-install default since P1 2026-10-04 — no new block in
init_user_preferences). Hardcoded magic numbers should preferably be tunable.

**Any button, not only parameters** (2026-09-19): grep X's FUNCTION before building —
the helper may be named differently from the room. **Signature: the user asks for a
button that EXISTS because it is on another page** → the task is placement + scope
text, not a new helper (a duplicate shares the state).

**Scope must be described (user-spec 2026-07-02):** a slider that does not hit all bulbs
— or not all in the room it names — gets ONE line under the tile ("Gælder ikke: …", cf.
the text rule under 📊). Changing a slider's scope → update ALL affected descriptions in
the same commit. Scope claims are verified in the code, not guessed (#1/#3).

**Values are snapshotted to git (2026-06-17):** sliders live in `.storage`, not git →
`python3 scripts/helpers_export.py` → commit **`config_snapshots/`** (both files —
pre-commit rejects a staged pair that does not match; hand-edited snapshot →
`--derive`); `helpers_restore.py [--apply]` restores. The export runs on an
**allowlist** (`DATETIME_CONFIG`/`SELECT_CONFIG` in the script) — a new config
`input_datetime`/`input_select` must be added there, or it is silently not snapshotted.

### 🚀 Deploy + multi-Claude sync — never a blind `reset --hard`

Claude has full access (SSH + REST) and does deploy, restart, state queries and service
calls **itself**; the user only uses HA's UI for the physical (pairing, add-ons, OAuth).
They also work from the phone, so `/config` may have local commits. **Safe sequence:**
commit locally → fetch → inspect `git log --oneline @{u}.. -5` → `pull --ff-only`
(fails on divergence = forces manual review) → `bash scripts/ha_restart.sh` (skip for
docs-only). Full procedure: [docs/commit_workflow.md](docs/commit_workflow.md).

**`git stash && git pull && git stash pop` is a TRAP on /config:** a `git stash` that
stashes nothing (clean tree) returns 0, and `pop` then pops a FOREIGN stash from an
earlier session. Check `git stash list` FIRST, or `git stash push -m "<name>"` and pop
only if your own entry was created.

**ALWAYS commit yourself — NEVER ask "shall I commit?"** (user-spec 2026-06-16). Skip
`ha core check`; use `python3 scripts/ha_offline.py check` (HA's own validator offline,
~13 s, also in pre-push). The 2026.4 bug was `KeyError: 'triggers'` in check_config —
fixed upstream in 2026.9.2. **After every deploy: `./scripts/ha_health.sh deploy`** —
catches automations that failed validation and are therefore completely silent (#22).

### 👁️ Monitoring — `./scripts/ha_health.sh`

The weekly health check. Subcommands: `deploy` (failed automations — after EVERY
deploy), `flags`, `flipflop`, `lights`, `noisy`, `zha`, `docs`, `backup`, `sys`,
`log [n]`, `blind`, `kamera`. No argument runs all.

**Git hooks are installed** (`.git/hooks/pre-commit` + `pre-push`, copies of
`scripts/*-hook.sh`). Missing (`ls .git/hooks/pre-*`) or the hook warns "ruff mangler"
→ **`bash scripts/dev_setup.sh`** (hooks + pinned ruff/yamllint/gitleaks in
`.cache/dev-venv`, which HA's backup skips). Pre-commit blocks on `ruff check`/`ruff
format --check` → run `.cache/dev-venv/bin/ruff format <file>` before committing.

**`docs/auto/*` is GENERATED and goes stale silently** — never edit by hand; run
`python3 scripts/gen_docs.py` and commit the result when you have added entities.

### 🔥 ESPHome chip wear — be paranoid with writes to Apollo MSR-2 (2026-05-19)

2 of 5 got chip faults from ~3600 unnecessary config writes: never the same value
again, only on user intent, value-compare before `number.set_value`, engineering
mode/BT never ON in operation. **Full rule + canary: `.claude/rules/presence_radar.md`**
(loaded when you touch the Apollo files).

### 🏡 EVERYTHING we build must work with AirBnB mode (user-spec 2026-07-28)

Every single change, not only those "about AirBnB":

1. **`house_mode` has THREE options** — `Normal`, `AirBnB`, `Home Vacation`. A
   `state: "Normal"` condition also excludes Home Vacation = almost always unintended.
   Family logic = `in ['Normal','Home Vacation']`; guest-only = `AirBnB`.
2. **Suppressors/enforcers are the most dangerous.** Always ask: *how does a guest get
   out of this state without knowing the system?* There MUST be an automatic exit.
3. **New flags:** cleared on AirBnB **entry** and **exit**? See the flag-clear and
   lockdown lists in `automations/airbnb_mode.yaml` (+ mirrors in
   `automations/light_power_recovery.yaml`). Reveals family patterns → add it to the
   privacy-purge globs (#16).
4. **AirBnB has its own night regime** (`packages/airbnb_natmode.yaml`) that sets the
   goodnight flags DIRECTLY, not via `script.godnat` → it does NOT clear cinema/scene flags.
5. **Never force family routines on a guest** — choose the neutral action: RELEASE a
   block rather than force a state.

### 📊 Keep the curated dashboards up to date

Hand-curated, so they **drift when the code changes** — update in the SAME sprint:

- **Dashboard text (user-spec 2026-09-29):** only short Danish tile names, one line of
  scope and live status — why/data go in a YAML comment. Full rule (Settings tabs,
  search, control panels): `.claude/rules/dashboards.md`.
- **New/dropped device** → `dashboards/status.yaml`, `dashboards/lights.yaml`,
  [docs/hardware_shopping.md](docs/hardware_shopping.md). Grep the new entity name in
  both dashboards — 0 hits = add it.
- **Automation that turns on/off/recolours a bulb or runs a curtain** →
  `dashboards/triggers.yaml` (user-spec 2026-07-03). House-wide = the top section ONCE;
  room-specific = the room card. Verify with `python3 scripts/triggers_scan.py`
  (ON/colour via scripts or templated entity_ids shows as DYNAMISK → curate manually, cf. #1).
- **Anything that only applies in AirBnB** (or an AirBnB gate in shared logic) → the 🏡
  AirBnB tab in `dashboards/settings.yaml` (user-spec 2026-07-08), same commit.
  `grep AirBnB` for all co-owners. NB the entity_id keeps the OLD slug on an alias rename.

### Other standing instructions

- **The people count falls ONLY after the front door** (user-spec 07-22, repeated 10-01
  and 10-21: "again and again … stick to that guess until the main door opens").
  `sensor.people_estimate` shows one HELD number (`input_number.people_gulv`): up when
  the bid has held, down only in the door window, on the door's empty verdict (Dormant ≤
  `people_afgang_dom_minutter` after the door → 0, 22/10) or on the user's own
  correction. No new way down (geofence, Dormant WITHOUT a door before it, decay, family
  growth) — too high is fixed at the SOURCE. Proof: **`./scripts/ha_health.sh people`**
  (checks the shown number, not the parts).
- **Check who is asleep — BOTH bedrooms — before clearing goodnight/setting Auto/calling
  scripts** (user-spec 11-02): bed counter + `sovevaerelse_dvale_vidne` (the sleep
  Apollo loses a sleeper), `kids_home` + its attributes (a latch with ~0 h stay lies).
  Someone asleep → `sove_sovende_beskyttes` must be on BEFORE the clear — NEVER set the
  sleep snooze manually (it blocks two-up → radio/curtain). `grep -n "Tjek hvem der sover" docs/standing_instructions.md`.
- **After a bug fix: put rooms the user took manually (Styrbar/app) back on Auto**
  (user-spec 11-02) — not for special light (party, mood, film, coloured). Fix the cause
  first, or Auto turns the light off again.
- **Button presses (Styrbar/RODRET/SOMRIG) are always respected — mis-presses too**
  (user-spec 11-01): no guard, goodnight lock or suppressor may override a press; only
  automation. New button in a bedroom → add it to the `bedroom_styrbar_intent_at`
  stamp. `grep -n "Knap-tryk respekteres" docs/standing_instructions.md`.
- **New problems** → [BACKLOG.md](BACKLOG.md) in the right category with the next free
  ID (`python3 scripts/backlog_ids.py --next`; never reused). **Solved** → "Done" with
  the date, or delete if trivial.
- **Permanent, useful fact** (hardware quirk, stable environment fact, repeated gotcha)
  → ONE short bullet in "Permanent facts" + the long one in `docs/permanente_fakta.md`.
  Criterion: would a future session waste time without it? Task-specific → memory or BACKLOG.
- **Lamps with an ownership register** (`ejerskab/<lamp>.yaml`; today the kitchen light
  chain): the rank IS the code → generated `sensor.<lamp>_ejer`. New writer/borrower =
  register + `python3 scripts/ejerskab.py gen` (pre-commit blocks otherwise). New lamp in
  the scheme = new register file, chosen by `ejerskab.py steder <entity>` — not per room.
- **`replace_all` on numeric patterns is dangerous:** `transition: 60` also matches the
  prefix of `transition: 600`. Broke HA boot 2026-04-29.
- **Hardware shopping list:** [docs/hardware_shopping.md](docs/hardware_shopping.md).

---

## 🧠 Failure classes — check BEFORE you declare anything done

Recurring patterns: cheap to avoid, expensive to discover. **Signature → method only.
Incident, data, reasoning: [docs/fejlklasser.md](docs/fejlklasser.md)** —
`grep -n "^20\." docs/fejlklasser.md`.

**Ownership, duplication and claims**

1. **"Single owner" designs have hidden co-owners.** → `grep -rn "<entity>"
   automations/ packages/ script_pkg/ rosters/` (a rosters/ hit → grep `rosters/<name>`
   for the consumers) before you claim — or build — that X is the only control. **Same
   burden of proof for the NEGATIVE claim** ("nothing guards X"): the house has more
   watchdogs than you remember (B147).
2. **The same rule coded in 2 places diverges.** → Grep the rule's key expression
   (entity + operator) and update every occurrence, or consolidate into one anchor.
   **Same trap in TIME: `mode: single` only excludes the script from ITSELF, so two
   scripts touching one lamp run at once — the one starting mid-way reads the other's
   intermediate state as "normal" and writes it back. Signature: several state rows on
   one entity within one second, while each source looks well-behaved in its own
   file.** → ONE `queued` channel for the action.
3. **Comment claims ≠ code.** A `time_pattern` backstop RE-ASSERTS its state, so
   "manual operation always wins" is false without a grace/stamp mechanism. → **Manual
   = `context.user_id is not none`, NEVER `parent_id is none`.** Button presses carry no
   user_id either → to count as manual, stamp them in the handler.
10. **Verify findings before you "fix"** — an unnecessary fix is diff risk too. → Read
    the actual consumer code.
16. **Entity rosters drift when devices are added** — the same list copy-pasted in many
    files; the diff is one line in the middle of a look-alike list. → Grep a roster
    fingerprint member and update ALL hits. **A list in several places lives in
    `rosters/<name>.yaml`** (`entity_id: !include ../rosters/<name>.yaml`) — fix it
    there; `roster_drift.py` shows the rest. In Jinja: `{% from 'rosters.jinja' import
    <name> %}` (generated: `python3 scripts/rosters.py jinja`).
21. **A kill switch that is not a `condition` on every way in is decoration** (backstop
    tick, restart recovery, manual script, sister automation). → `grep -rn
    "<feature>_enabled"` held against `grep -rn "<the action>"`.
26. **A HOUSE-WIDE gate on a ROOM-SCOPED state locks every room to something it has
    nothing to do with. Signature:** the feature works only partially — the working part
    is the one WITHOUT the gate. → room-scope the gate AND its neighbouring conditions (#12).
27. **A borrower's HANDBACK writes a snapshot from before the loan — as the LAST call,
    so an expired snapshot wins. Signature:** a light that turns OFF (not wrong colour)
    shortly after a temporary owner let go → no edge to fix. → ask the house again at
    handback, do not replay the snapshot. **The mirror image hits wider: a light that
    turns ON again ~40 s after an automation turned it off — the loan swallowed the
    decision and burned the victim's cooldown.** A blink/warning that `scene.create`s is
    a co-owner of EVERY decision in its window (#1).

**Triggers that never fire — or fire at the worst possible moment**

4. **Edge triggers lack re-arm.** → "What re-fires if the edge happens WHILE we are
   blocked?" **Worst variant: two automations share ONE edge, and one SETS the
   condition the other READS.** **Signature:** "only works if I also do Y", Y being
   ANOTHER trigger path to the same action. → The setter re-arms the reader itself
   (`automation.trigger` + `skip_condition: false`) — only if the target does not read
   `trigger.` (UndefinedError aborts the script).
15. **Disable/enable windows swallow events** — an automation turned OFF gets NO
    triggers. → A resume flow MUST re-evaluate the state the re-enabled logic maintains.
19. **A blocked automation fires in the SAME second the block lifts.** **Signature:** an
    action at the same time every day with no parameter varying. → For every long-term
    gate: does its exit time fit the ACTION? No → the action needs its own condition.
13. **Edge trigger + dedupe stamp = no re-push during a sustained episode.** → Dedupe on
    an edge needs a time_pattern backstop, gated to an ongoing episode (stamp age < N).
12. **Protection is added asymmetrically to sister automations.** → Giving one warning
    dedupe/grace/gate → review the siblings with the same physics.

**Sensors that lie — or measure something other than their name says**

9. **`unavailable` is neither on nor off** — is_state is silently false during a
   Thread/Zigbee flap. → Gate enforce logic on health sensors, not on a skewed state.
14. **An analogue sensor's `last_changed` CANNOT prove "sustained"** — it resets on
    EVERY report. → "Above the limit for 15 min" needs a `for:` trigger or
    history_stats, never a condition template.
20. **An accumulator over a LATCHING sensor measures time since the window started, not
    activity.** **Signature:** a gate tripping with the same fixed offset every day,
    whose time moves when you change the threshold. → Require **freshness**, not just `on`.
23. **A restart recovery must not prove its premise with the channel that was broken** —
    a sensor booting stuck `on` has `last_changed` = boot time, not an observation. →
    Require ANOTHER channel, re-check the gates AFTER the wait, and limit the action to
    the room the evidence came from.
24. **A template attribute with `now()` writes a DB row every minute — forever.**
    **Signature:** an entity at the top of `ha_health.sh noisy` with nearly all rows
    attribute changes. → Gate the attribute on the state where it means something and
    quantise it against the threshold it is compared with.
25. **An exit waiting for a radar to say ONE thing inherits the radar's lie the other
    way:** "off for N min" is erased by one blip, "empty" never comes under a still ghost
    (B290), "sees someone" never while it is blind (B280) — and a protection releasing on
    "empty" is an exit too. **Signature:** the watchdog does the primary path's work,
    exactly the backstop time too late (`./scripts/ha_health.sh backstop`) — or the state
    is never left. → ask every exit what it lands on when the radar lies; prove it with
    what the lie cannot fake: no MOTION since X, an anchor moved only by an edge that
    HOLDS (`sensor.last_sustained_presence`), or a written deadline.
28. **A high-water mark on a flickering signal stores the flicker's TOP, and a bonus
    conditioned on a radar's instantaneous state inherits its flicker. Signature:** a
    number jumping in step with one radar and hanging on the high value for exactly the
    decay time. → latch only what has HELD (`for:` + the same requirement on all re-arm
    paths), floor only what no stable source proves (people v4).
29. **A soak measured from the candidate's own edge counts time from BEFORE what
    disproved it — a bridge carries the candidate across a wake-up/clear. Signature:** an
    automation setting a flag a few min after the OPPOSITE path cleared it, on a backstop
    tick. → also count from the flag's latest change; `./scripts/ha_health.sh flipflop`.
30. **A rescale per VALUE change (bare trigger, `ny/gammel`) multiplies a reload
    flicker — the steps do not cancel out. Signature:** lights that are on sit below
    their own on-formula after a reload. → `for:` + `not_from/not_to`; B294.

**Time, tests and traces**

18. **The history/logbook API answers in UTC**; the house runs on Danish time (UTC+1
    winter, UTC+2 summer) → convert with `ZoneInfo('Europe/Copenhagen')` in your parser,
    never a fixed offset, never in your head.
8. **Midnight windows:** `today_at()` after 00:00 points to the NEXT window → shift 86400
   back when "tonight" means the current night.
5. **"Set live via API" steps get forgotten.** → New slider = **4** steps in the SAME
   session: **API set + settings tile + snapshot export + verify the live value at the
   end**. **API set seeds the HOUSE; the snapshot export seeds a FRESH install** (it
   derives `config_snapshots/fresh_install/`, read by init since P1 2026-10-04 — a slider
   missing from the snapshot sits at min after a reinstall; runtime counters belong in
   `RUNTIME_NUMBERS`). **Signature: a slider at its init default with an empty
   `context_user_id_bin`, ~30 s after a restart.**
6. **"Live-tested" with synthetic events proves nothing** — the physical button may send
   an old quirk form. → Test with REAL device events, or find history evidence that the
   real event form has been seen.
11. **API tests leave traces that look like user actions** — an API turn_off carries a
    user_id → manual-off trackers stamp it as the user's off. → Clear the stamps the test
    may have set; check that room_mode/last_press did not flip. **Worst variant: the
    trace is a SCENE, not your one call** — `scene.turn_on` emits internal
    `light.turn_on`s with the scene's context incl. user_id, so a snapshot RESTORE looks
    like N app adjustments at once. Restore scenes are allowlisted in
    `automations/manual_override.yaml`.
7. **Count trigger fires × API calls before deploy** (fires/day = 1440/interval × number
   of duplicate triggers). → Prefer state-change triggers + a /1h backstop.
22. **An automation in `unavailable` is not noise — it FAILED VALIDATION and is
    completely silent.** HA disables the WHOLE automation on the slightest template error
    in its `action:`, with no warning at commit, deploy or reload. →
    `./scripts/ha_health.sh deploy` after every deploy. (Real fault = `restored` missing;
    `restored: true` = harmless registry orphan, the house has ~74.)

**Jinja gotchas** (`variables:` becoming a truthy string, undefined script fields,
`trigger.` via `automation.trigger`, StrEnum, TupleWrapper, `repeat.index0` …) are in
`.claude/rules/ha_yaml.md`; full list with examples: `grep -n "Jinja-gotchas" docs/fejlklasser.md`.
