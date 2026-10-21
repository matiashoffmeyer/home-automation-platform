#!/usr/bin/env python3
"""scene_overwrite.py — gem nuværende lys + gardiner som et scene-snapshot.

Kaldes af shell_command.scene_overwrite (packages/scene_overwrite.yaml), som
igen kaldes af script.scene_overwrite (dashboard "Overskriv"-knap).

  argv[1] = scene-navn (whitelist)
  argv[2] = base64(JSON) med live state pr. entity, bygget af script-Jinja:
            {"light.x": {"state": "on", "brightness": 51,
                         "color_mode": "color_temp", "color_temp_kelvin": 1953,
                         "hs_color": [..], "rgb_color": [..], "xy_color": [..],
                         "current_position": null}, ...}
  argv[3] = (valgfri) base64(JSON-liste) af open-plan-lysenes entity_id'er.
            Giver ud over snap_<name>.yaml en AFLEDT scene snap_<name>_openplan
            med KUN de lys der er i open-plan (ingen gardiner, ingen terrasse/
            depot/soveværelse). Den bruges af den automatiske scene-motor
            (script.scene_auto_apply), som kun må røre open-plan — den fulde
            snapshot bliver ved med at høre til dashboard-trykket.
            Køkkenkæden får sin EGEN afledte scene snap_<name>_kaede: motoren
            må kun male den mens køkkenet ikke er i brug, og skal kunne male
            den alene når køkkenet bliver ledigt midt i en session.

Hvorfor base64-payload i stedet for at scriptet selv læser API'et:
HA Core's shell_command-subproces har en SUPERVISOR_TOKEN, men supervisor-
proxyen afviser den (401) for /core/api — kun addons med homeassistant_api må
bruge den. Recorder-DB'en gemmer ikke brightness/farve pålideligt. Derfor
læser script-Jinja de live states (HA har dem natively, tokenfrit) og sender
dem hertil. Python = ren formatter + atomic writer, ingen netværk/deps.

Output: scene_snapshots/snap_<name>.yaml (JSON er gyldig YAML). Script-wrapperen
kører bagefter scene.reload så scene.snap_<name> bliver live uden HA-restart.
"""

import base64
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SNAP_DIR = os.path.normpath(os.path.join(HERE, "..", "scene_snapshots"))

VALID_SCENES = {
    "cinema",
    "zen",
    "cirkus",
    "party",
    "full_bright",
    "private",
    "blue",
    "happy",
    "sunset",
    "sofa_laesning",
    "spisestue_middag",
    "cyberpunk",
    "madlavning",
    "hverdagsaften",
    "winddown",
}

UNAVAIL = ("unavailable", "unknown", "none", "", None)


def light_entry(a):
    entry = {"state": "on"}
    if a.get("brightness") is not None:
        entry["brightness"] = int(a["brightness"])
    mode = a.get("color_mode")
    if mode == "color_temp" and a.get("color_temp_kelvin") is not None:
        entry["color_temp_kelvin"] = int(a["color_temp_kelvin"])
    elif mode == "hs" and a.get("hs_color") is not None:
        entry["hs_color"] = [round(x, 2) for x in a["hs_color"]]
    elif mode in ("rgb", "rgbw", "rgbww") and a.get("rgb_color") is not None:
        entry["rgb_color"] = [int(x) for x in a["rgb_color"]]
    elif mode == "xy" and a.get("xy_color") is not None:
        entry["xy_color"] = [round(x, 4) for x in a["xy_color"]]
    return entry


def build_entities(payload):
    entities = {}
    for eid, a in payload.items():
        state = a.get("state")
        if str(state).lower() in UNAVAIL:
            continue
        if eid.startswith("cover."):
            e = {"state": state}
            if a.get("current_position") is not None:
                e["current_position"] = int(a["current_position"])
            entities[eid] = e
        elif eid.startswith("light."):
            entities[eid] = light_entry(a) if state == "on" else {"state": "off"}
        else:
            entities[eid] = {"state": state}
    return entities


# Lys der har deres EGEN enforcer og derfor ikke må males sammen med resten af
# open-plan: køkkenkæden (packages/koekken_lyskaede.yaml) maler sig selv om
# flere gange hver aften. Den lånes separat (user-spec 2026-10-03: "med i Zen,
# men presence i køkkenet pauser Zen dér") via sin egen afledte scene.
AUTO_EXCLUDE = {"light.koekken_lyskaede"}
KAEDE = "light.koekken_lyskaede"


def openplan_subset(entities, openplan):
    """Kun lys der er i open-plan-rosteret — aldrig gardiner/andre domæner."""
    return {
        eid: e
        for eid, e in entities.items()
        if eid.startswith("light.") and eid in openplan and eid not in AUTO_EXCLUDE
    }


def write_scene(scene_id, entities):
    """Atomisk skrivning af scene_snapshots/<scene_id>.yaml (JSON er gyldig YAML)."""
    doc = [{"id": scene_id, "name": scene_id, "entities": entities}]
    os.makedirs(SNAP_DIR, exist_ok=True)
    path = os.path.join(SNAP_DIR, "%s.yaml" % scene_id)
    tmp = path + ".tmp"
    body = json.dumps(doc, indent=2, ensure_ascii=False)
    json.loads(body)  # validér før vi rører den rigtige fil
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(body + "\n")
    os.replace(tmp, path)
    return path


def main():
    if len(sys.argv) not in (3, 4) or sys.argv[1] not in VALID_SCENES:
        raise SystemExit(
            "brug: scene_overwrite.py <scene> <base64-json> [<base64-openplan-liste>]"
            "  (gyldige: %s)" % ", ".join(sorted(VALID_SCENES))
        )
    scene = sys.argv[1]
    try:
        payload = json.loads(base64.b64decode(sys.argv[2]).decode("utf-8"))
    except Exception as e:
        raise SystemExit("scene_overwrite: kunne ikke afkode payload: %s" % e) from None
    if not isinstance(payload, dict):
        raise SystemExit("scene_overwrite: payload er ikke et dict")
    openplan = None
    if len(sys.argv) == 4:
        try:
            openplan = set(json.loads(base64.b64decode(sys.argv[3]).decode("utf-8")))
        except Exception as e:
            raise SystemExit(
                "scene_overwrite: kunne ikke afkode open-plan-listen: %s" % e
            ) from None

    entities = build_entities(payload)
    if not entities:
        raise SystemExit(
            "scene_overwrite: 0 tilgængelige entities for '%s' — intet gemt "
            "(er lysene unavailable?)" % scene
        )

    path = write_scene("snap_%s" % scene, entities)
    print("scene_overwrite: gemte %d entities til %s" % (len(entities), path))

    # Afledt open-plan-scene til den automatiske motor. Findes der ingen open-
    # plan-lys i denne scene (private/winddown-sove-scener …), fjernes en gammel
    # afledt fil, så en forældet scene aldrig bliver liggende og snydes ind.
    if openplan is not None:
        derived_id = "snap_%s_openplan" % scene
        derived = openplan_subset(entities, openplan)
        derived_path = os.path.join(SNAP_DIR, "%s.yaml" % derived_id)
        if derived:
            print(
                "scene_overwrite: gemte %d open-plan-lys til %s"
                % (len(derived), write_scene(derived_id, derived))
            )
        elif os.path.exists(derived_path):
            os.remove(derived_path)
            print(
                "scene_overwrite: ingen open-plan-lys i '%s' — fjernede %s" % (scene, derived_path)
            )

        # Kæden alene (samme regel: ingen kæde i scenen → fjern en gammel fil).
        kaede_id = "snap_%s_kaede" % scene
        kaede_path = os.path.join(SNAP_DIR, "%s.yaml" % kaede_id)
        if KAEDE in entities and KAEDE in openplan:
            print(
                "scene_overwrite: gemte køkkenkæden til %s"
                % write_scene(kaede_id, {KAEDE: entities[KAEDE]})
            )
        elif os.path.exists(kaede_path):
            os.remove(kaede_path)
            print("scene_overwrite: ingen køkkenkæde i '%s' — fjernede %s" % (scene, kaede_path))


if __name__ == "__main__":
    main()
