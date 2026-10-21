# Commit-workflow — altid commit, aldrig overskriv PC/NUC-arbejde

> *Written in Danish. English overview: [README](../README.md) ·
> [ARCHITECTURE](../ARCHITECTURE.md).*

**Standing rule (per 2026-06-16, user-spec):** Claude SKAL altid committe arbejde
selv — spørg ALDRIG "skal jeg committe?". Men commit på en måde der garanteret
**ikke overskriver** commits lavet fra en anden maskine (PC-Claude, NUC-Claude
eller telefon-Claude der arbejder mod samme `origin/main`).

Se også: [remote_workflow.md](remote_workflow.md) (deploy) og CLAUDE.md-sektionen
"⚠️ Multi-Claude sync".

## Hvorfor (incident-baggrund)

Sprint 2026-05-18: phone-Claude lavede en commit på NUC'en, og PC-Claude wipede
den bagefter med `git reset --hard origin/main`. Lektie: flere Claude-instanser
deler ét remote — blind reset/force kan smide en anden maskines arbejde væk.

## Den sikre commit-sekvens

Kør ALTID denne rækkefølge. Den committer lokalt arbejde og fletter remote
ind med `--ff-only`, så den **fejler højlydt** ved divergens i stedet for at
overskrive noget.

```bash
# 1. Stage + commit lokalt arbejde FØRST (så intet er i fare under fetch)
git add <eksplicitte filer>          # ikke "git add -A" blindt — se nedenfor
git commit -m "<besked>"

# 2. Hent remote og se om der ligger fremmed arbejde
git fetch origin

# 3a. Hvis IKKE bagud (HEAD..@{u} tom) → bare push
git push origin main

# 3b. Hvis bagud → flet remote ind med --ff-only / rebase, så push
git pull --rebase origin main        # vores commit lægges oven på remote
git push origin main
```

### Regler

1. **Commit lokalt FØR `fetch`/`pull`.** Uncommitted ændringer kan gå tabt ved
   en merge/rebase; et commit er sikkert.
2. **Aldrig `git reset --hard origin/main`** for at "rydde op" før push — det
   sletter lokale commits. Brug `git pull --rebase` i stedet.
3. **Aldrig `git push --force` / `--force-with-lease`** mod `main` uden at
   brugeren eksplicit beder om det.
4. **`--ff-only` / `--rebase` failer ved divergens** = ønsket adfærd. Stop og
   inspicér (`git log --oneline HEAD..@{u}`) i stedet for at tvinge.
5. **Stage eksplicitte filer**, ikke `git add -A`, så debris (state-dumps,
   `.bak`, secrets) ikke ryger med. Debris hører hjemme i `.gitignore`.
6. **Vi kører ofte PÅ NUC'en** (`/config` er symlink til `/homeassistant`) →
   redigerede filer er allerede live. Commit = versionsstyring; `bash
   scripts/ha_restart.sh` (eller reload) loader ændringerne. Se remote_workflow.md.

## Hurtig divergens-tjek

```bash
git fetch origin -q
git log --oneline @{u}..HEAD   # commits VI har, remote ikke har (vil pushes)
git log --oneline HEAD..@{u}   # commits REMOTE har, vi ikke har (skal flettes ind)
```

Tom output begge veje = i sync, push trygt.
