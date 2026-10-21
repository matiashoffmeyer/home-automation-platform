# scene_snapshots/

> *Written in Danish. English overview: [README](../README.md) ·
> [ARCHITECTURE](../ARCHITECTURE.md).*

Persistent scene-overrides genereret af **script.scene_overwrite** (dashboard
"Overskriv"-knap, Scener-siden).

- Hver fil `snap_<scene>.yaml` er ét HA-scene (`scene.snap_<scene>`) med de
  lys + gardiner brugeren havde sat manuelt da de trykkede Overskriv.
- `scene: !include_dir_merge_list scene_snapshots/` i configuration.yaml
  loader dem. `scene.reload` (kørt af script.scene_overwrite) tager ændringer
  uden HA-restart.
- Hvis `scene.snap_<scene>` findes, anvender scene_toggle / script.scene_<scene>
  snapshottet i stedet for de hardcodede mood-værdier i
  `script_pkg/scenes.yaml`. Slet en `snap_*.yaml` for at falde tilbage til
  default-scenen.
- Filerne er JSON (gyldig YAML), skrevet af `scripts/scene_overwrite.py`.

Loader-noten: kun `*.yaml` indlæses som scene-config; denne README ignoreres.
- **`snap_<scene>_openplan.yaml` (2026-10-03):** hver Overskriv skriver også en
  AFLEDT scene med KUN open-plan-lysene (ingen gardiner, ingen terrasse/depot/
  soveværelse). Den bruges af den automatiske scene-motor
  (`script.scene_auto_apply`, `packages/sofa_zen_auto.yaml`), som aldrig må røre
  andet end open-plan. Roster = lysgruppen `light.stue_all` minus lys med egen enforcer (køkkenkæden, B183); stue-lysene i selve
  snapshottet = `light.stue_room`. En ny pære i de grupper kommer med af sig selv.
  Findes ingen open-plan-lys i scenen, fjernes en gammel afledt fil.
- Lys der ikke står i en snapshot får den automatiske motors standardværdier —
  tryk Overskriv igen for at fange en nyligt tilføjet pære.
