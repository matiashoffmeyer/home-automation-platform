"""Generate adaptive_lighting.yaml v3 with burst-debounce + bug-fixes."""

ROOMS = [
    ("stue", "light.stue_loft", "binary_sensor.stue_apollo_occupancy"),
    ("spisestue", "light.spisestue_pendel", "binary_sensor.spisestue_apollo_occupancy"),
    ("sove", "light.sovevaerelse_loft", "binary_sensor.sovevaerelse_apollo_radar_still_target"),
    ("boern", "light.boernevaerelse_loft", "binary_sensor.boernevaerelse_apollo_occupancy"),
    ("bad", "light.badevaerelse_loft", "binary_sensor.badevaerelse_inde_occupancy"),
    ("depot", "light.depot_loft", "binary_sensor.depot_valhorn_occupancy"),
    ("entre", "light.entre_loft", "binary_sensor.entre_valhorn_occupancy"),
]

MODES = [
    ("morgen", "mdi:brightness-6"),
    ("dag", "mdi:brightness-7"),
    ("aften", "mdi:brightness-5"),
    ("nat", "mdi:brightness-2"),
]

DEFAULTS = {
    "stue": {"morgen": (60, 2700), "dag": (40, 2700), "aften": (40, 2400), "nat": (15, 2200)},
    "spisestue": {"morgen": (60, 2700), "dag": (40, 2700), "aften": (40, 2400), "nat": (15, 2200)},
    "sove": {"morgen": (40, 2400), "dag": (30, 2700), "aften": (25, 2200), "nat": (5, 2000)},
    "boern": {"morgen": (30, 2400), "dag": (15, 2700), "aften": (15, 2200), "nat": (3, 2000)},
    "bad": {"morgen": (70, 2700), "dag": (50, 2700), "aften": (40, 2400), "nat": (20, 2200)},
    "depot": {"morgen": (60, 2700), "dag": (40, 2700), "aften": (40, 2400), "nat": (15, 2200)},
    "entre": {"morgen": (60, 2700), "dag": (40, 2700), "aften": (40, 2400), "nat": (15, 2200)},
}

print("""# =============================================================================
# Adaptive Lighting v3 — selvjusterende belysning med burst-debounce
# =============================================================================
# Sprint 2026-05-23 v3 (rev af v2 efter user audit-request):
#   "vær grundig, gør det fejlfrit"
#
# KRITISKE V2→V3 CHANGES:
# 1. BURST-DEBOUNCE: Styrbar OP/NED klikkes ofte mange gange hurtigt
#    (push fra 30%→100% = 7 klikks). v2 lærte hver mellem-værdi som final
#    memory (= sidste klik vandt, men exception-protection blev bypassed
#    fordi hvert klik var <25% delta). v3: 60-sek burst-window. Baseline
#    fra start-of-burst, evaluate vs current EFTER 60s stabil. Cumulative
#    delta er det der måles mod threshold = "leder efter nøgler"-scenario
#    fanges som exception og skippes.
# 2. DELTA THRESHOLD: 25% → 50% (user-spec)
# 3. SOURCE captured AT burst start (not at evaluation) — 5-sec user-button
#    window virker ikke længere når debounce er 60s.
# 4. parent_id loop-check re-added som defense-in-depth (var fjernet i v2).
# 5. Memory readout sensors: defensive default hvis mode='unknown'.
# 6. Multi-target attribute check: brightness/ct begge skal være defined
#    før delta beregning (= ikke int(0) fallback der lyver om HUGE delta).
# 7. mode: parallel (max:16) på observer (var queued — race-prone med
#    8 rum × 4 modes burst evaluations).
# 8. init_defaults automation tilfojet (fresh boot resilience).
#
# ARKITEKTUR (uændret fra v2):
#   - 8 ceiling-lights covered
#   - 4 tids-modes (morgen/dag/aften/nat)
#   - LOCK pattern + parent_id check for loop-protection
#   - Whitelisted Styrbar IEEEs for learning source (room Styrbars only)
#
# LEARNING-FLOW v3:
#   t=0:   user starter burst (1. klik på Styrbar eller app slider)
#          → observer fyrer → detect burst_start (secs_since_last > 60)
#          → save baseline (= from_state attrs) i input_number helpers
#          → save source (app/button) i input_text helper
#          → stamp last_change_at = now
#          → wait 60s debounce
#   t=2,5,8: flere klikks → observer fyrer hver gang
#          → ikke burst_start (last <60s) → baseline + source uændret
#          → stamp last_change_at = now (continuously updates)
#          → wait 60s debounce (parallel runs)
#   t=66:  første run waits 60s done. Check: last_change_at == my trigger?
#          Hvis newer change kom (t=8 vs my t=0): SKIP (= newer run evaluerer)
#   t=68:  sidste run waits done. Check: last_change_at (t=8) == my (t=8)?
#          → True → evaluate. Compute delta from baseline → memory if OK.
# =============================================================================

# -----------------------------------------------------------------------------
# 1. HELPERS — input_number
# -----------------------------------------------------------------------------
input_number:
""")

# Mode sliders (per room × 4 modes × 2 attrs = 64)
for room, light, _trigger in ROOMS:
    print(f"  # === {room.upper()} ({light}) ===")
    for mode, icon in MODES:
        print(f"  adaptive_{room}_{mode}_brightness:")
        print(f'    name: "Adaptive {room.title()} {mode} brightness"')
        print(f"    icon: {icon}")
        print(
            '    min: 1\n    max: 100\n    step: 1\n    unit_of_measurement: "%"\n    mode: slider'
        )
        print(f"  adaptive_{room}_{mode}_ct:")
        print(f'    name: "Adaptive {room.title()} {mode} color temp"')
        print("    icon: mdi:thermometer")
        print(
            '    min: 2000\n    max: 6500\n    step: 50\n    unit_of_measurement: "K"\n    mode: slider'
        )
    # Per-room baseline helpers (debounce state)
    print(f"  adaptive_{room}_baseline_bri:")
    print(f'    name: "Adaptive {room.title()} burst-baseline brightness (raw 0-255)"')
    print("    icon: mdi:flag-outline")
    print("    min: 0\n    max: 255\n    step: 1\n    mode: box")
    print(f"  adaptive_{room}_baseline_ct:")
    print(f'    name: "Adaptive {room.title()} burst-baseline color temp"')
    print("    icon: mdi:flag-outline")
    print("    min: 1500\n    max: 7000\n    step: 1\n    mode: box")
    print()

# Global thresholds
print("""  # === SHARED THRESHOLDS ===
  adaptive_max_delta_brightness:
    name: "Adaptive: max brightness delta (%) før exception"
    icon: mdi:delta
    min: 5
    max: 90
    step: 1
    unit_of_measurement: "%"
    mode: slider
  adaptive_max_delta_ct:
    name: "Adaptive: max ct delta (K) før exception"
    icon: mdi:delta
    min: 100
    max: 3000
    step: 50
    unit_of_measurement: "K"
    mode: slider
  adaptive_burst_window_seconds:
    name: "Adaptive: burst-debounce window (sek)"
    icon: mdi:timer-sand
    min: 5
    max: 300
    step: 5
    unit_of_measurement: "s"
    mode: slider

# -----------------------------------------------------------------------------
# 2. HELPERS — input_boolean (LOCK per rum)
# -----------------------------------------------------------------------------
input_boolean:""")

for room, _, _ in ROOMS:
    print(f"  adaptive_lock_{room}:")
    print(f'    name: "Adaptive {room} auto-apply lock"')
    print("    icon: mdi:lock")

print("""
# -----------------------------------------------------------------------------
# 3. HELPERS — input_datetime (per-room last_change + per-room button stamp)
# -----------------------------------------------------------------------------
# V4 FIX #1: Per-room button stamp i stedet for shared. Eliminerer cross-
# room source-leak. Kun rum med dedikeret Styrbar har stamp (stue/boern/
# bad/sove). Andre 4 rum app-source only.
input_datetime:""")

STYRBAR_ROOMS = ["stue", "boern", "bad", "sove"]
for room in STYRBAR_ROOMS:
    print(f"  adaptive_{room}_last_button:")
    print(f'    name: "Adaptive {room.title()} sidste button-zha event"')
    print("    has_date: true\n    has_time: true\n    icon: mdi:gesture-tap")

for room, _, _ in ROOMS:
    print(f"  adaptive_{room}_last_change_at:")
    print(f'    name: "Adaptive {room} last state-change at"')
    print("    has_date: true\n    has_time: true\n    icon: mdi:clock-outline")

print("""
# -----------------------------------------------------------------------------
# 4. HELPERS — input_text (per-room burst source + burst-time mode)
# -----------------------------------------------------------------------------
# V4 FIX #4: Capture mode AT burst start (= input_text.adaptive_{room}_burst_
# mode). Evaluation 60s senere kan skydes over mode-grænse (16:58 dag →
# 17:58 aften). Bruger gemte mode så learning lander i RIGTIG memory.
input_text:""")

for room, _, _ in ROOMS:
    print(f"  adaptive_{room}_burst_source:")
    print(f'    name: "Adaptive {room} burst source"')
    print('    max: 16\n    icon: mdi:account-arrow-left\n    initial: "none"')
    print(f"  adaptive_{room}_burst_mode:")
    print(f'    name: "Adaptive {room} burst-time mode"')
    print('    max: 16\n    icon: mdi:clock-time-eight-outline\n    initial: "dag"')

# Template sensors
print("""
# -----------------------------------------------------------------------------
# 5. TEMPLATE SENSORS — current_mode + memory readouts (defensive defaults)
# -----------------------------------------------------------------------------
template:
  - sensor:
      - name: "Adaptive current mode"
        unique_id: adaptive_current_mode
        icon: mdi:clock-time-eight-outline
        state: >
          {% set h = now().hour %}
          {% if 6 <= h < 9 %}morgen
          {% elif 9 <= h < 17 %}dag
          {% elif 17 <= h < 22 %}aften
          {% else %}nat{% endif %}""")

for room, _, _ in ROOMS:
    print(f"""
      - name: "Adaptive {room} memory brightness"
        unique_id: adaptive_{room}_memory_brightness
        icon: mdi:brightness-percent
        unit_of_measurement: "%"
        state: >
          {{{{ ((states('sensor.adaptive_current_mode') in ['morgen','dag','aften','nat'])
              | iif(states('input_number.adaptive_{room}_' ~ states('sensor.adaptive_current_mode') ~ '_brightness') | int(50), 50)) }}}}
      - name: "Adaptive {room} memory ct"
        unique_id: adaptive_{room}_memory_ct
        icon: mdi:thermometer
        unit_of_measurement: "K"
        state: >
          {{{{ ((states('sensor.adaptive_current_mode') in ['morgen','dag','aften','nat'])
              | iif(states('input_number.adaptive_{room}_' ~ states('sensor.adaptive_current_mode') ~ '_ct') | int(2700), 2700)) }}}}""")

# Automations
print("""

# -----------------------------------------------------------------------------
# 6. AUTOMATIONS
# -----------------------------------------------------------------------------
automation:""")

# 8 motion-triggered apply
for room, light, trigger in ROOMS:
    extra = ""
    if room in ["sove", "boern"]:
        extra = '''
      - condition: state
        entity_id: binary_sensor.godnat_any_active
        state: "off"'''
    print(f"""
  - id: adaptive_apply_{room}
    alias: "Adaptive: {room} motion → apply memory"
    mode: single
    max_exceeded: silent
    trigger:
      - platform: state
        entity_id: {trigger}
        to: "on"
    condition:
      - condition: state
        entity_id: binary_sensor.presence_sensors_available
        state: "on"
      - condition: state
        entity_id: input_select.house_state
        state: "Active"
      - condition: template
        value_template: "{{{{ states('input_select.active_scene') == 'none' }}}}"
      - condition: state
        entity_id: input_boolean.cinema_active
        state: "off"
      - condition: state
        entity_id: input_boolean.cirkus_active
        state: "off"{extra}
    action:
      - service: input_boolean.turn_on
        target:
          entity_id: input_boolean.adaptive_lock_{room}
      - variables:
          mode: "{{{{ states('sensor.adaptive_current_mode') }}}}"
          bri_pct: "{{{{ states('input_number.adaptive_{room}_' ~ mode ~ '_brightness') | int(50) }}}}"
          ct_k: "{{{{ states('input_number.adaptive_{room}_' ~ mode ~ '_ct') | int(2700) }}}}"
      - service: light.turn_on
        continue_on_error: true
        target:
          entity_id: {light}
        data:
          brightness_pct: "{{{{ bri_pct }}}}"
          color_temp_kelvin: "{{{{ ct_k }}}}"
          transition: 0
      - delay:
          seconds: 5
      - service: input_boolean.turn_off
        target:
          entity_id: input_boolean.adaptive_lock_{room}""")

# V4 FIX #1: Per-room button stamp (IEEE→room mapping)
print("""
  - id: adaptive_user_button_stamp_per_room
    alias: "Adaptive: stamp user-button zha_event (per-room)"
    description: >
      V4 fix #1: per-room stamp eliminerer cross-room source-leak.
      IEEE → room mapping. Kun whitelistede Styrbars (stue/boern/bad/sove).
    mode: queued
    max: 10
    trigger:
      - platform: event
        event_type: zha_event
    variables:
      ieee_to_room:
        '7e:44:f6:62:8e:f4:b1:23': stue
        '66:19:44:cc:2c:41:57:fe': boern
        '06:0d:3a:e6:10:55:ae:30': bad
        'c3:db:c9:b4:05:ef:1d:63': sove
    condition:
      - condition: template
        value_template: "{{ trigger.event.data.device_ieee in ieee_to_room.keys() | list }}"
    action:
      - variables:
          room: "{{ ieee_to_room[trigger.event.data.device_ieee] }}"
      - service: input_datetime.set_datetime
        target:
          entity_id: "input_datetime.adaptive_{{ room }}_last_button"
        data:
          datetime: "{{ now().strftime('%Y-%m-%d %H:%M:%S') }}"

  # -------------------------------------------------------------------------
  # V4 FIX #3: Reset burst state når light → off (eller unavailable)
  # -------------------------------------------------------------------------
  # Stale burst-state kunne overleve hvis light gik off mid-burst (wall
  # switch, presence_off, etc.). Næste on-event ville se gammel baseline.
  # Reset clearer source så ny burst starter rent.
  - id: adaptive_reset_burst_on_off
    alias: "Adaptive: reset burst state når light → off"
    mode: parallel
    max: 8
    trigger:
      - platform: state
        entity_id:
          - light.stue_loft
          - light.spisestue_pendel
          - light.sovevaerelse_loft
          - light.boernevaerelse_loft
          - light.badevaerelse_loft
          - light.depot_loft
          - light.entre_loft
        to:
          - "off"
          - "unavailable"
    action:
      - variables:
          light_to_room:
            light.stue_loft: stue
            light.spisestue_pendel: spisestue
            light.sovevaerelse_loft: sove
            light.boernevaerelse_loft: boern
            light.badevaerelse_loft: bad
            light.depot_loft: depot
            light.entre_loft: entre
          room: "{{ light_to_room[trigger.entity_id] }}"
      - service: input_text.set_value
        target:
          entity_id: "input_text.adaptive_{{ room }}_burst_source"
        data:
          value: "none"

  # -------------------------------------------------------------------------
  # V4 FIX #6: LOCK auto-release safety net (60s timeout)
  # -------------------------------------------------------------------------
  # Hvis adaptive_apply hænger eller crasher før LOCK released, vil ingen
  # ny learning kunne ske for det rum. Safety net: LOCK on for 60s → forcer
  # off + logger warning.
  - id: adaptive_lock_safety_release
    alias: "Adaptive: LOCK safety release (60s timeout)"
    mode: parallel
    max: 8
    trigger:
      - platform: state
        entity_id:
          - input_boolean.adaptive_lock_stue
          - input_boolean.adaptive_lock_koekken
          - input_boolean.adaptive_lock_spisestue
          - input_boolean.adaptive_lock_sove
          - input_boolean.adaptive_lock_boern
          - input_boolean.adaptive_lock_bad
          - input_boolean.adaptive_lock_depot
          - input_boolean.adaptive_lock_entre
        to: "on"
        for:
          seconds: 60
    action:
      - service: input_boolean.turn_off
        target:
          entity_id: "{{ trigger.entity_id }}"
      - service: logbook.log
        data:
          name: "Adaptive LOCK safety"
          message: >
            {{ trigger.entity_id }} var stuck on i 60s — force-released.
            adaptive_apply hang eller crashede sandsynligvis.

  # ---------------------------------------------------------------------------
  # OBSERVER v3: burst-debounce + delta filter på cumulative change
  # ---------------------------------------------------------------------------
  - id: adaptive_observer_learn
    alias: "Adaptive: observer m. burst-debounce"
    condition:
      - condition: state
        entity_id: input_boolean.adaptive_learning_enabled
        state: "on"
    mode: parallel
    max: 32
    trigger:
      - platform: state
        entity_id:
          - light.stue_loft
          - light.spisestue_pendel
          - light.sovevaerelse_loft
          - light.boernevaerelse_loft
          - light.badevaerelse_loft
          - light.depot_loft
          - light.entre_loft
    action:
      - variables:
          light_to_room:
            light.stue_loft: stue
            light.spisestue_pendel: spisestue
            light.sovevaerelse_loft: sove
            light.boernevaerelse_loft: boern
            light.badevaerelse_loft: bad
            light.depot_loft: depot
            light.entre_loft: entre
          room: "{{ light_to_room[trigger.entity_id] }}"
          # V5 FIX (2026-06-11): render skalar-felter direkte — hele
          # context/attributes-objekter degraderer til strenge i HA templates
          # (ColorMode-enums/Context-repr kan ikke literal_eval'es).
          ctx_parent_id: "{{ trigger.to_state.context.parent_id }}"
          ctx_user_id: "{{ trigger.to_state.context.user_id }}"
          my_trigger_ts: "{{ trigger.to_state.last_updated }}"
          lock_state: "{{ states('input_boolean.adaptive_lock_' ~ room) }}"
          from_bri: "{{ trigger.from_state.attributes.get('brightness') }}"
          from_ct: "{{ trigger.from_state.attributes.get('color_temp_kelvin') }}"
          to_bri: "{{ trigger.to_state.attributes.get('brightness') }}"
          to_ct: "{{ trigger.to_state.attributes.get('color_temp_kelvin') }}"
      # GATE 1: LOCK off (= ikke auto-apply self-loop)
      - condition: template
        value_template: "{{ lock_state == 'off' }}"
      # GATE 2: parent_id check (defense-in-depth — skip if change came from
      # adaptive auto-apply automation via context chain)
      - condition: template
        value_template: >
          {% set auto = states.automation['adaptive_' ~ room ~ '_motion_apply_memory'] %}
          {% if auto is none %}true
          {% else %}{{ ctx_parent_id is none or ctx_parent_id != auto.context.id }}
          {% endif %}
      # GATE 3: State on→on + attrs defined begge sider (= ikke transition/unavail)
      - condition: template
        value_template: >
          {{ trigger.from_state.state == 'on'
             and trigger.to_state.state == 'on'
             and from_bri is not none and to_bri is not none
             and from_ct is not none and to_ct is not none }}
      # GATE 4: Mikro-flicker filter — V4 FIX #9: konsistent <1% bri threshold
      # V4.1 FIX #16: defensive | int(0) (HA variables kan rendere som string)
      - condition: template
        value_template: >
          {% set fb = from_bri | int(0) %}
          {% set tb = to_bri | int(0) %}
          {% set fc = from_ct | int(0) %}
          {% set tc = to_ct | int(0) %}
          {% set d_bri_pct = ((tb - fb) | abs / 2.55) | round(2) %}
          {% set d_ct = (tc - fc) | abs %}
          {{ d_bri_pct > 1 or d_ct > 50 }}
      # GATE 4b PUTNING (2026-06-12, user-spec): boern lærer IKKE i putning-
      # kontekst — putning-dims er scenarie-signaler, ikke præference-
      # korrektioner, og må ikke forurene boern-memory.
      - condition: template
        value_template: >-
          {{ room != 'boern'
             or not (is_state('binary_sensor.putning_vindue_aktivt', 'on')
                     or is_state('input_boolean.puttelys_descent_active', 'on')
                     or is_state('input_boolean.godnat_boern_active', 'on')) }}
      # GATE 5: SOURCE — V4 FIX #1+#8: per-room button stamp + 10s tolerance
      # (var shared + 5s). Per-room: kun stamp matching THIS room's Styrbar.
      # 10s window dækker Zigbee mesh delay.
      - variables:
          is_app: "{{ ctx_user_id is not none }}"
          has_room_button: "{{ room in ['stue', 'boern', 'bad', 'sove'] }}"
          last_btn: >
            {% if has_room_button %}
              {{ states('input_datetime.adaptive_' ~ room ~ '_last_button') }}
            {% else %}none{% endif %}
          btn_secs_ago: >
            {% if last_btn in ['none', 'unknown', 'unavailable', ''] %}9999
            {% else %}
              {% set btn_ts = as_timestamp(last_btn) %}
              {% set my_ts = as_timestamp(my_trigger_ts) %}
              {{ (my_ts - btn_ts) | abs }}
            {% endif %}
          is_recent_button: "{{ has_room_button and (btn_secs_ago | float(9999)) < 10 }}"
          source: >
            {% if is_app %}app
            {% elif is_recent_button %}button
            {% else %}none{% endif %}
      - condition: template
        value_template: "{{ source != 'none' }}"
      # BURST DETECTION: er dette burst-start eller fortsættelse?
      - variables:
          last_change_secs_ago: >
            {% set t = states('input_datetime.adaptive_' ~ room ~ '_last_change_at') %}
            {% if t in ['unknown', 'unavailable', ''] %}9999
            {% else %}{{ (now() - as_datetime(t)).total_seconds() }}
            {% endif %}
          burst_window: "{{ states('input_number.adaptive_burst_window_seconds') | float(60) }}"
          is_burst_start: "{{ (last_change_secs_ago | float(9999)) > burst_window }}"
      # IF burst start: save baseline + source + MODE (V4 FIX #4)
      - if:
          - condition: template
            value_template: "{{ is_burst_start }}"
        then:
          - service: input_number.set_value
            target:
              entity_id: "input_number.adaptive_{{ room }}_baseline_bri"
            data:
              value: "{{ from_bri }}"
          - service: input_number.set_value
            target:
              entity_id: "input_number.adaptive_{{ room }}_baseline_ct"
            data:
              value: "{{ from_ct }}"
          - service: input_text.set_value
            target:
              entity_id: "input_text.adaptive_{{ room }}_burst_source"
            data:
              value: "{{ source }}"
          # V4 FIX #4: capture mode AT burst start (= save mode i input_text)
          # så evaluation 60s+ senere lander i RIGTIG memory selv hvis vi
          # er skydet over mode-grænse (16:58 dag → 17:58 aften eval).
          - service: input_text.set_value
            target:
              entity_id: "input_text.adaptive_{{ room }}_burst_mode"
            data:
              value: "{{ states('sensor.adaptive_current_mode') }}"
      # ALWAYS stamp last_change_at (rolls forward for hver event i burst)
      - service: input_datetime.set_datetime
        target:
          entity_id: "input_datetime.adaptive_{{ room }}_last_change_at"
        data:
          datetime: "{{ now().strftime('%Y-%m-%d %H:%M:%S') }}"
      # WAIT for burst window (debounce). Hvis flere events kommer ind, hver
      # restarter sin egen run (mode: parallel) med sin egen delay. Den
      # NYESTE run vil "vinde" via stamp-check nedenfor.
      - delay:
          seconds: "{{ states('input_number.adaptive_burst_window_seconds') | int(60) }}"
      # POST-DELAY: er dette stadig den nyeste trigger for dette rum?
      - condition: template
        value_template: >
          {% set last = states('input_datetime.adaptive_' ~ room ~ '_last_change_at') %}
          {% set last_ts = as_timestamp(last) if last not in ['unknown','unavailable',''] else 0 %}
          {% set my_ts = as_timestamp(my_trigger_ts) %}
          {{ (last_ts - my_ts) | abs < 1 }}
      # EVALUATE: compute delta fra baseline til NU (post-burst stable state)
      # V4 FIX #4: brug GEMTE burst_mode (= mode AT burst start), ikke current
      - variables:
          mode: "{{ states('input_text.adaptive_' ~ room ~ '_burst_mode') }}"
          current_light: >
            {% set rl = {'stue': 'stue_loft', 'spisestue': 'spisestue_pendel',
                         'sove': 'sovevaerelse_loft', 'boern': 'boernevaerelse_loft',
                         'bad': 'badevaerelse_loft', 'depot': 'depot_loft', 'entre': 'entre_loft'} %}
            light.{{ rl[room] }}
          current_state: "{{ states(current_light) }}"
          current_bri: "{{ state_attr(current_light, 'brightness') }}"
          current_ct: "{{ state_attr(current_light, 'color_temp_kelvin') }}"
          baseline_bri: "{{ states('input_number.adaptive_' ~ room ~ '_baseline_bri') | int(0) }}"
          baseline_ct: "{{ states('input_number.adaptive_' ~ room ~ '_baseline_ct') | int(2700) }}"
          burst_source: "{{ states('input_text.adaptive_' ~ room ~ '_burst_source') }}"
      # Defensive: skip hvis mode ikke er valid (helper-corruption guard)
      - condition: template
        value_template: "{{ mode in ['morgen', 'dag', 'aften', 'nat'] }}"
      # POST-DELAY validation: lyset må STADIG være on + have attrs
      - condition: template
        value_template: >
          {{ current_state == 'on' and current_bri is not none and current_ct is not none }}
      # Compute cumulative delta (baseline → current) — V4.1 FIX #16 defensive int
      - variables:
          cb: "{{ current_bri | int(0) }}"
          cc: "{{ current_ct | int(0) }}"
          bb: "{{ baseline_bri | int(0) }}"
          bc: "{{ baseline_ct | int(0) }}"
          current_bri_pct: "{{ (cb | float / 2.55) | round(0) | int }}"
          cum_bri_delta_pct: "{{ (((cb | float) - (bb | float)) | abs / 2.55) | round(1) }}"
          cum_ct_delta_k: "{{ ((cc | float) - (bc | float)) | abs }}"
          max_bri_delta: "{{ states('input_number.adaptive_max_delta_brightness') | float(50) }}"
          max_ct_delta: "{{ states('input_number.adaptive_max_delta_ct') | float(800) }}"
          is_exception: >
            {{ cum_bri_delta_pct | float > max_bri_delta or cum_ct_delta_k | float > max_ct_delta }}
      # SOURCE check #2: burst_source skal være valid (= sat ved burst start)
      - condition: template
        value_template: "{{ burst_source in ['app', 'button'] }}"
      # EXCEPTION FILTER
      - choose:
          - conditions:
              - condition: template
                value_template: "{{ is_exception }}"
            sequence:
              - service: logbook.log
                data:
                  name: "Adaptive: exception (skip)"
                  message: >
                    {{ room }}/{{ mode }} source={{ burst_source }}:
                    cum bri Δ={{ cum_bri_delta_pct }}% (max {{ max_bri_delta }}),
                    ct Δ={{ cum_ct_delta_k }}K (max {{ max_ct_delta }}).
                    Burst over threshold = exception, memory uændret → Manual + 3h hold.
              # HYBRID 2026-06-12 (user-spec): within-bounds button-justeringer
              # bliver i Auto (styrbar_brightness_step sender set_manual=false).
              # Over-bounds = brugeren vil noget HELT andet end auto → NU sættes
              # Manual + 3h drift-back hold her (eneste sted for button-source).
              # stamp_press har selv putning-guard for boernevaerelse.
              - if:
                  - condition: template
                    value_template: "{{ burst_source == 'button' }}"
                then:
                  # Open-plan (koekken/spisestue) mapper til 'stue' — de har
                  # ingen egne styrbar_last_press_/room_mode_-helpers.
                  - service: script.styrbar_stamp_press
                    data:
                      room: >-
                        {{ {'stue': 'stue', 'koekken': 'stue', 'spisestue': 'stue',
                            'sove': 'sovevaerelse', 'boern': 'boernevaerelse',
                            'bad': 'badevaerelse', 'entre': 'entre',
                            'depot': 'depot'}.get(room, 'stue') }}
              # Reset burst source så næste burst starter fresh
              - service: input_text.set_value
                target:
                  entity_id: "input_text.adaptive_{{ room }}_burst_source"
                data:
                  value: "none"
              - stop: "Exception"
      # LEARN: save current values til memory for current mode
      - service: input_number.set_value
        target:
          entity_id: "input_number.adaptive_{{ room }}_{{ mode }}_brightness"
        data:
          value: "{{ current_bri_pct }}"
      - service: input_number.set_value
        target:
          entity_id: "input_number.adaptive_{{ room }}_{{ mode }}_ct"
        data:
          value: "{{ current_ct }}"
      - service: logbook.log
        data:
          name: "Adaptive: learned"
          message: >
            {{ room }}/{{ mode }} source={{ burst_source }}:
            baseline bri {{ baseline_bri }} → {{ current_bri }} ({{ current_bri_pct }}%, Δ={{ cum_bri_delta_pct }}%),
            ct {{ baseline_ct }}K → {{ current_ct }}K (Δ={{ cum_ct_delta_k }}K). Memory opdateret.
      # Reset burst source efter successful learn
      - service: input_text.set_value
        target:
          entity_id: "input_text.adaptive_{{ room }}_burst_source"
        data:
          value: "none"
""")


# Case 2 handler: light off→on sustained ≥2 min via user-source → learn
print("""
  # ---------------------------------------------------------------------------
  # OBSERVER CASE 2: manual ON sustained ≥ 2 min → learn
  # ---------------------------------------------------------------------------
  # User-spec: lys er slukket, motion detected men adaptive_apply skipper
  # (fx active_scene, godnat, lux). User tænder manuelt og lader stå tændt
  # i 2+ min → klart "vil have lys her" signal → lær current values.
  #
  # Skelnes fra Case 1 (= burst i already-on light). For: 2min på trigger
  # garanterer stabilitet. Source-detect ved fire-tid bruger trigger.to_state
  # (= det originale on-event, ikke fire-time).
  - id: adaptive_observer_manual_on_sustained
    alias: "Adaptive: manual ON sustained ≥ 2 min → learn"
    condition:
      - condition: state
        entity_id: input_boolean.adaptive_learning_enabled
        state: "on"
    mode: parallel
    max: 8
    trigger:
      - platform: state
        entity_id:
          - light.stue_loft
          - light.spisestue_pendel
          - light.sovevaerelse_loft
          - light.boernevaerelse_loft
          - light.badevaerelse_loft
          - light.depot_loft
          - light.entre_loft
        from: 'off'
        to: 'on'
        for:
          minutes: 2
    action:
      - variables:
          light_to_room:
            light.stue_loft: stue
            light.spisestue_pendel: spisestue
            light.sovevaerelse_loft: sove
            light.boernevaerelse_loft: boern
            light.badevaerelse_loft: bad
            light.depot_loft: depot
            light.entre_loft: entre
          room: "{{ light_to_room[trigger.entity_id] }}"
          ctx_parent_id: "{{ trigger.to_state.context.parent_id }}"
          ctx_user_id: "{{ trigger.to_state.context.user_id }}"
          on_event_time: "{{ trigger.to_state.last_changed }}"
          lock_state: "{{ states('input_boolean.adaptive_lock_' ~ room) }}"
      # GATE 1: LOCK off (= ikke adaptive_apply der trigged on-event)
      - condition: template
        value_template: "{{ lock_state == 'off' }}"
      # GATE 2: parent_id check
      - condition: template
        value_template: >
          {% set auto = states.automation['adaptive_' ~ room ~ '_motion_apply_memory'] %}
          {% if auto is none %}true
          {% else %}{{ ctx_parent_id is none or ctx_parent_id != auto.context.id }}
          {% endif %}
      # GATE 3: light STADIG on med valid attrs (kunne være gået off mellem trigger og fire)
      - condition: template
        value_template: >
          {% set light_entity = 'light.' ~ {'stue':'stue_loft','spisestue':'spisestue_pendel','sove':'sovevaerelse_loft','boern':'boernevaerelse_loft','bad':'badevaerelse_loft','depot':'depot_loft','entre':'entre_loft'}[room] %}
          {{ states(light_entity) == 'on'
             and state_attr(light_entity, 'brightness') is not none
             and state_attr(light_entity, 'color_temp_kelvin') is not none }}
      # GATE 4: SOURCE check — V4 FIX #1 per-room stamp + V4 FIX #8 10s window
      - variables:
          is_app: "{{ ctx_user_id is not none }}"
          has_room_button: "{{ room in ['stue', 'boern', 'bad', 'sove'] }}"
          last_btn: >
            {% if has_room_button %}
              {{ states('input_datetime.adaptive_' ~ room ~ '_last_button') }}
            {% else %}none{% endif %}
          btn_match: >
            {% if last_btn in ['none', 'unknown', 'unavailable', ''] %}false
            {% else %}
              {% set btn_ts = as_timestamp(last_btn) %}
              {% set on_ts = as_timestamp(on_event_time) %}
              {{ (btn_ts - on_ts) | abs < 10 }}
            {% endif %}
          source: "{{ 'app' if is_app else ('button' if btn_match else 'none') }}"
      - condition: template
        value_template: "{{ source != 'none' }}"
      # PUTNING-GATE (2026-06-12, user-spec): samme som observer GATE 4b —
      # boern lærer ikke i putning-kontekst (scenarie-lys, ikke præference).
      - condition: template
        value_template: >-
          {{ room != 'boern'
             or not (is_state('binary_sensor.putning_vindue_aktivt', 'on')
                     or is_state('input_boolean.puttelys_descent_active', 'on')
                     or is_state('input_boolean.godnat_boern_active', 'on')) }}
      # LEARN: save current brightness + ct til memory for current mode
      - variables:
          mode: "{{ states('sensor.adaptive_current_mode') }}"
          light_entity: >
            light.{{ {'stue':'stue_loft','spisestue':'spisestue_pendel','sove':'sovevaerelse_loft','boern':'boernevaerelse_loft','bad':'badevaerelse_loft','depot':'depot_loft','entre':'entre_loft'}[room] }}
          current_bri: "{{ state_attr(light_entity, 'brightness') }}"
          current_ct: "{{ state_attr(light_entity, 'color_temp_kelvin') }}"
          # V5.1 defensive int (samme V4.1 FIX #16 rationale som observer)
          current_bri_pct: "{{ ((current_bri | int(0)) / 2.55) | round(0) | int }}"
      - service: input_number.set_value
        target:
          entity_id: "input_number.adaptive_{{ room }}_{{ mode }}_brightness"
        data:
          value: "{{ current_bri_pct }}"
      - service: input_number.set_value
        target:
          entity_id: "input_number.adaptive_{{ room }}_{{ mode }}_ct"
        data:
          value: "{{ current_ct }}"
      - service: logbook.log
        data:
          name: "Adaptive: learned (manual ON sustained 2min)"
          message: >
            {{ room }}/{{ mode }} source={{ source }}: light tændt 2+ min uden
            adaptive_apply. Memory opdateret: bri={{ current_bri_pct }}%, ct={{ current_ct }}K.
""")

# Init defaults
print("""
  # ---------------------------------------------------------------------------
  # INIT DEFAULTS — sætter sensible values ved fresh boot / nye helpers
  # ---------------------------------------------------------------------------
  - id: adaptive_init_defaults
    alias: "Adaptive: init defaults ved fresh boot + reset burst state"
    mode: single
    trigger:
      - platform: homeassistant
        event: start
    action:
      - delay:
          seconds: 30
      # V4 FIX #2: reset burst state for ALLE rum ved HA start.
      # input_text holder string value gennem restart — kunne være 'app' fra
      # før crash. Reset til 'none' så ny burst starter rent. last_change_at
      # behøver ikke reset (gammel timestamp = burst-window udløbet = burst_start).
      - service: input_text.set_value
        target:
          entity_id:
            - input_text.adaptive_stue_burst_source
            - input_text.adaptive_koekken_burst_source
            - input_text.adaptive_spisestue_burst_source
            - input_text.adaptive_sove_burst_source
            - input_text.adaptive_boern_burst_source
            - input_text.adaptive_bad_burst_source
            - input_text.adaptive_depot_burst_source
            - input_text.adaptive_entre_burst_source
        data:
          value: none
      # V4.1 FIX #2: reset last_change_at til far-past (= 2000-01-01) så
      # første event efter HA start altid betragtes som burst_start. Uden
      # dette ville last_change_at = current midnight kunne være < burst_window
      # tidligt på dagen → første event mistolkes som mid-burst → mister learn.
      - service: input_datetime.set_datetime
        target:
          entity_id:
            - input_datetime.adaptive_stue_last_change_at
            - input_datetime.adaptive_koekken_last_change_at
            - input_datetime.adaptive_spisestue_last_change_at
            - input_datetime.adaptive_sove_last_change_at
            - input_datetime.adaptive_boern_last_change_at
            - input_datetime.adaptive_bad_last_change_at
            - input_datetime.adaptive_depot_last_change_at
            - input_datetime.adaptive_entre_last_change_at
        data:
          datetime: '2000-01-01 00:00:00'
""")

# Defaults inline
for room, _, _ in ROOMS:
    rd = DEFAULTS[room]
    for mode, _ in MODES:
        bri, ct = rd[mode]
        print(f"""      - if:
          - condition: template
            value_template: >
              {{{{ states('input_number.adaptive_{room}_{mode}_brightness') | float(1) <= 1 }}}}
        then:
          - service: input_number.set_value
            data:
              entity_id: input_number.adaptive_{room}_{mode}_brightness
              value: {bri}
          - service: input_number.set_value
            data:
              entity_id: input_number.adaptive_{room}_{mode}_ct
              value: {ct}""")

# Init threshold defaults
print("""      - if:
          - condition: template
            value_template: "{{ states('input_number.adaptive_max_delta_brightness') | float(5) <= 5 }}"
        then:
          - service: input_number.set_value
            data:
              entity_id: input_number.adaptive_max_delta_brightness
              value: 50
      - if:
          - condition: template
            value_template: "{{ states('input_number.adaptive_max_delta_ct') | float(100) <= 100 }}"
        then:
          - service: input_number.set_value
            data:
              entity_id: input_number.adaptive_max_delta_ct
              value: 800
      - if:
          - condition: template
            value_template: "{{ states('input_number.adaptive_burst_window_seconds') | float(5) <= 5 }}"
        then:
          - service: input_number.set_value
            data:
              entity_id: input_number.adaptive_burst_window_seconds
              value: 60""")
