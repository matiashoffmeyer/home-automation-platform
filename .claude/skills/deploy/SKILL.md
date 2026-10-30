---
name: deploy
description: Use when a committed change has to go live on the house. Syncs with origin without overwriting other sessions' work, reloads or restarts the safe way, catches automations that failed validation silently, and notifies the household (never in guest mode).
---

# Deploy

The agent runs on the production host, so an edited file is already on disk.
Deploying means loading it into Home Assistant without losing state, and
proving that every automation came back.

## 1. Commit, then sync

```sh
git add <explicit files>              # never `git add -A`: feedback logs and dumps stay out
git commit                            # Danish message; the pre-commit hook lints and scans
git fetch origin
git log --oneline HEAD..@{u}          # someone else's commits? read them first
git pull --ff-only                    # fails loudly on divergence: inspect, never force
```

Never `git reset --hard` and never `git stash && pull && stash pop`: an empty
stash makes `pop` restore an unrelated stash from an earlier session.

## 2. Validate offline

```sh
python3 scripts/ha_offline.py check   # Home Assistant's own validator, ~13 s, also runs in pre-push
```

## 3. Load the change

- Reload only the domains you touched:
  `curl -s -X POST -H "Authorization: Bearer $SUPERVISOR_TOKEN" http://supervisor/core/api/services/<domain>/reload`.
- **Reload automations before templates.** A `template.reload` sends every
  template entity through `unavailable`, and `unavailable → off` fires
  switch-off paths. A `delay_on` sensor also makes a real `off → on` exactly
  `delay_on` after the reload.
- Restart only when a reload cannot load the change, and only with
  `bash scripts/ha_restart.sh`. It saves restore-state first, because Home
  Assistant segfaults during shutdown on this host. A plain `ha core restart`
  is blocked by the restart guard, and every restart first needs the
  household's yes: `python3 scripts/live_godkend.py spørg "<why>" --genstart`
  (run it in the background; exit 0 = approved for 10 min). The live guard
  blocks the restart without it.
- Skip this step for docs-only commits.

## 4. Prove it loaded

```sh
./scripts/ha_health.sh deploy         # automations that failed validation are completely silent
```

`unavailable` without `restored: true` is a real failure (failure class 22).
If the change has a physical effect (light, curtains, sound, timing), measure
the real behaviour: state after the action, `hs_color`, brightness 0-254. Do
not stop at "looks like it works". Triggering the effect yourself is a live
test and needs the household's yes first (`live_godkend.py spørg`); proof
that is already in history needs none.

## 5. Push and notify

```sh
git push origin main
python3 scripts/hq.py state input_select.house_mode
```

If `house_mode` is `AirBnB`, send nothing: the phone may be in a guest's
hands. Otherwise send ONE short push per batch of work (what is live now, and
any manual step left) via `notify/mobile_app_phone_a`. Say in the reply whether
the push was sent or skipped.
