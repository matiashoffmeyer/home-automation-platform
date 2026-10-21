# Bug-hunt-natten 2026-10-06 → 07 (handoff)

> *Written in Danish. English overview: [README](../README.md) ·
> [ARCHITECTURE](../ARCHITECTURE.md).*

User-ordre 22:10: "lav en ny bug hunt, fix bugs, endnu en bughunt, ingen spørgsmål,
jeg sover. Restart ok, bare sovelyset ikke tænder. Bliv ved til kl 05-06, tilføj
evt. ting til backlog." User står op 06:15. **Ingen push før 06:15; ingen HA-restart
efter 05:30; ingen lys-test om natten. Sove-loftet = light.spisestue_pendel.**

## Hvis sessionen døde (token-limit) — sådan fortsætter du
1. Læs denne fil (status nedenfor er altid den sidste committede).
2. En workflow der kørte, har sine agentsvar på disk:
   `<journal>` = én `{"type":"result",...}`-linje pr. færdig agent. Læs den og verificér
   fundene selv (kode + `hq.py` historik) før fix.
3. Fortsæt planen fra første ikke-afkrydsede runde. Formen: 2 finders + 1 skeptiker
   pr. finder, `model: sonnet`, maks 2 samtidige, ≤40 tool-kald, kun læsning.

## Status
| Runde | Område | Run-ID / journal | Status |
|---|---|---|---|
| 1 | dagens 10-06-commits + nat/morgen (godnat, sove-lys, restart-recovery, vækning) | wf_920877af-cc2 · `/root/.claude/projects/-homeassistant/714d65ec-2972-4b53-8749-621ba43482eb/subagents/workflows/wf_920877af-cc2/journal.jsonl` | færdig 22:30 — 4 fund |
| 2 | badeværelse + entré/hoveddør/people | wf_9a2d1c8f-419 · `…/subagents/workflows/wf_9a2d1c8f-419/journal.jsonl` | færdig 22:57 — 4 fund |
| 3 | AirBnB/house_modes + gardiner/sol | wf_f71afcc1-851 · `…/subagents/workflows/wf_f71afcc1-851/journal.jsonl` | færdig 23:21 — 4 fund |
| 4 | `state: "Normal"`-sweep (16 filer) + energi/elpris/cykel/robot | wf_c9486c79-c36 · `…/subagents/workflows/wf_c9486c79-c36/journal.jsonl` | kører (23:30) |
| 5 | energi/elpris/cykel/robot/roborock | – | planlagt |
| 6 | notifikationer + watchdogs | – | planlagt |
| 7 | activity_state/people/kids_home | – | planlagt |
| 8 | dance/scener/room_mode | – | planlagt |
| 9 | stemme/gestus/kamera | – | planlagt |
| 10 | soveværelse dybt | – | planlagt |

## Fund og rettelser (fyldes efter hver runde)

### Runde 1 (færdig 22:30)
- R1-1 mad påmind-guard død efter --detach (`automations/mad_planlaegning.yaml` ~140) — CONFIRMED, harmløs (låsen vent=False er den reelle vagt). → ryd død condition, behold 3 s-delay.
- R1-2 putning_sen_hjemkomst re-tjekker kun 4/7 gates efter ventetiden (`automations/putning_auto_detect.yaml` ~646) — PLAUSIBLE, egen ny kode. → spejl alle gates.
- R1-3 godnat_auto_clear (`packages/house_modes.yaml` ~2035) rydder godnat ved HA-start på genskabt stue-occupancy (06-09) → sove-loft kan tænde — PLAUSIBLE. → undersøg/fix.
- R1-4 bedroom_night_guard (`automations/bedroom_night_guard.yaml`) deler godnat-flag med gaten den skal sikre (08-14: greb ikke ind) — CONFIRMED (strukturel). → undersøg/fix.
- **Rettet 22:37 (`4069227`):** R1-1, R1-2, R1-3. R1-4 afvist ved egen verifikation (08-14 lå i guardens vækningsundtagelse; tids-signal ville blokere legitimt auto-lys før godnat).

**Generisk workflow-script (genbrug til runde 3+):** `/root/.claude/projects/-homeassistant/714d65ec-2972-4b53-8749-621ba43482eb/workflows/scripts/bughunt-generisk-wf_9a2d1c8f-419.js` — kald med `args = {fixed: "<rettet-liste>", clusters: [{key, prompt}, {key, prompt}]}`.

### Runde 2 (færdig 22:57)
- R2-1 bad: fugt_frisk wait_template (8 sluk-veje, timeout 600 s) falder igennem ved timeout; målte huller op til 26 min (`automations/presence_badevaerelse.yaml` ~718) — PLAUSIBLE. → undersøg design.
- R2-2 bad: wasp safety-clear `for:` uden restart-backstop (`packages/badevaerelse_wasp.yaml:284`) — PLAUSIBLE, max-on-vagten er 2. grænse. → BACKLOG.
- R2-3 people: 23-s GPS-flap på person.* = bekræftet afgang → åbner gulv-vinduet (`packages/people_estimate.yaml:954`) — PLAUSIBLE. → undersøg/fix debounce.
- R2-4 GPS-velkomst slukker før døren — REFUTED (design; døren tænder straks).
- **Rettet 23:05 (`49de91f`):** R2-1 (bad: timeout 30 min + continue_on_timeout false på alle 8), R2-3 (GPS-afgang 5-min debounce). R2-2 → BACKLOG B197.

### Runde 3 (færdig 23:21)
- R3-1 AirBnB-exit (airbnb_mode_resume) rydder ikke dance_mode/cirkus_active — CONFIRMED (kode; AirBnB ikke brugt i 120 d). → spejl entry-rydningen.
- R3-2 putning_auto_detect trigger A-D: `state: "Normal"` udelukker Home Vacation — CONFIRMED. → `in ['Normal','Home Vacation']` (+ natlys-bagkanten, samme feature #12). Resten af de 29 `state: "Normal"`-filer → egen sweep-runde.
- R3-3 Somrig sove NED stempler ikke manuel-ned → auto-åbner river gardinet op (10-04 09:15:14 → 09:25) — CONFIRMED. → gardin_mark_manual_down.
- R3-4 summer_defense held vs held_luk — REFUTED (undersøgt 10-04c).
- **Rettet 23:28 (`6428b2a`):** R3-1 (AirBnB-exit stopper fest/cirkus), R3-2 (7 putte-automationer kører i Home Vacation), R3-3 (Somrig sove-NED stempler manuel-ned).
