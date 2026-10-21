---
name: measure-threshold
description: Use before setting, raising or lowering any threshold, timing or offset (lux, seconds, %, W). Derives the number from the recorded distribution of the channel the gate actually reads, never from a note or a comment.
---

# Measure a threshold

A number in a sprint note or a code comment is a hypothesis with a timestamp.
This skill turns it into a measurement before it reaches the house.

## 1. Find the channel the gate reads

```sh
python3 scripts/hq.py where <entity>       # every file:line that uses it
```

Read the gate itself. The channel is the entity inside the condition or
template, which is often a filtered or resilient sensor rather than the device
with the friendly name. If a slider already holds the value, the slider is what
you change (`grep -n <name> packages/global_tuning.yaml packages/constants.yaml`).

## 2. Pull the distribution, not a handful of samples

```sh
python3 scripts/hq.py hist <entity> --stats --since 3d     # samples + time-weighted percentiles
python3 scripts/hq.py hist <entity> --gate <X> --since 3d  # time above/below X, and crossings
python3 scripts/hq.py flanks <entity> --since 3d           # the state changes with durations
```

Two to three days of real operation is the default window. Mind the bias
traps in `.claude/rules/` for the domain (the lux rules list which samples
are contaminated by the house's own lamps, for example).

## 3. Check the shape before you pick the number

- **A negative set you labelled yourself is posed.** Operation delivers the
  whole continuum, so the real gap is narrower than the one you measured.
  Signature of the mistake: false positives cluster *just under* the threshold.
- **Never calibrate a gate on its own trigger events.** They are, by
  definition, only the ones that got through.
- **Compare with the siblings on the same scale.** A threshold that is a lone
  outlier among its siblings is the signature of an inherited number.
- **Analogue `last_changed` cannot prove "sustained"** (failure class 14): use
  `--gate` or history_stats, not a single reading.

## 4. Write it down where it lives

- Change the slider (and snapshot it, see the `new-slider` skill), or build
  a slider if the value is a hard-coded magic number.
- If the note or comment that held the old number disagrees with your
  measurement, the note is outdated: correct it in the same commit.
- Put the evidence in the commit message or the YAML comment above the value:
  window, sample count, the percentiles you used and the margin you chose.

## Report

State the window, n, the relevant percentiles, how many samples fall on each
side of the new value, and why the margin is what it is.
