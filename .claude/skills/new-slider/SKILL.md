---
name: new-slider
description: Use when a parameter should become tunable, or before building any new helper or button. Checks for an existing one first, then does all four steps a new input_number needs in one session (YAML, live value, settings tile with scope, snapshot) and verifies the live value.
---

# Add a slider

Sliders live in `.storage`, not in git. A slider that misses one of the four
steps below either stands at its minimum after a fresh install or shows a
value nobody chose. Signature: a slider at its init default with an empty
`context_user_id_bin` about 30 s after a restart (failure class 5).

## 0. Does it exist already?

```sh
grep -n -i "<keyword>" packages/global_tuning.yaml packages/constants.yaml dashboards/settings.yaml
python3 scripts/hq.py find <words…>
```

Grep the *function*, not only the room name: the helper may be named after
something else. If it exists, tell the user before changing anything; the task
is then placement or scope text, not a new helper (a duplicate shares no state).

## 1. YAML

Add the `input_number` next to its siblings, with a comment that says what
was measured to choose the default (use the `measure-threshold` skill). No
`initial:`, because it overrides the restored value on every restart (see
`.claude/rules/ha_yaml.md`). Replace the magic number in the consumer with
the slider.

## 2. Live value

Reload the domain and set the value through the API, so the house runs on the
chosen number now rather than on the minimum:

```sh
curl -s -X POST -H "Authorization: Bearer $SUPERVISOR_TOKEN" \
  http://supervisor/core/api/services/input_number/reload
curl -s -X POST -H "Authorization: Bearer $SUPERVISOR_TOKEN" -H "Content-Type: application/json" \
  -d '{"entity_id":"input_number.<name>","value":<v>}' \
  http://supervisor/core/api/services/input_number/set_value
```

## 3. Settings tile with scope

Add a tile on the matching tab in `dashboards/settings.yaml`: a short Danish
name and, if the slider does not reach every lamp it seems to, ONE line
"Gælder ikke: …". The scope claim must be verified in the code (`grep` the
consumers), not guessed. No explanatory notes on the dashboard; the why goes in
the YAML comment (`.claude/rules/dashboards.md`).

## 4. Snapshot

```sh
python3 scripts/helpers_export.py      # writes config_snapshots/ (it takes no flags)
```

Commit both files under `config_snapshots/`. The derived
`fresh_install/` file is what a fresh install seeds from. A counter the house
writes itself belongs in `RUNTIME_NUMBERS` in that script instead; a new
configuration `input_datetime` or `input_select` must be added to
`DATETIME_CONFIG`/`SELECT_CONFIG`, or it is silently left out.

## 5. Verify

```sh
python3 scripts/hq.py state input_number.<name>
```

The live value must equal the snapshot value. Then run the `deploy` skill.
