# State Machine Visual

> *Written in Danish. English overview: [README](../README.md) ·
> [ARCHITECTURE](../ARCHITECTURE.md).*

Mermaid diagrams til at forstå hvordan modes interagerer. Render automatically i GitHub.

## Top-level house state

```mermaid
stateDiagram-v2
    [*] --> Active: Default
    Active --> Dormant: Entré-Styrbar BUND kort (armerer kun en evaluering)
    Active --> Dormant: Auto-detected absence
    Dormant --> Active: Hjemkomst (entré-Vallhorn / hoveddør)
    Dormant --> Active: Entré-Styrbar TOP kort
    Dormant --> Active: Mobile arrival
```

## House mode toggle (orthogonal til state)

```mermaid
stateDiagram-v2
    [*] --> Normal
    Normal --> AirBnB: Manual toggle (gæste-stay)
    AirBnB --> Normal: Manual toggle
    Normal --> HomeVacation: Manual toggle (ferie hjemme)
    HomeVacation --> Normal: Manual toggle
    note right of AirBnB: Disabler de fleste presence-automations
    note right of Normal: Standard adfærd
    note right of HomeVacation: Familie-logik som Normal, men ingen hverdags-rutiner (wake-ups)
```

## Activity state machine (computed)

```mermaid
stateDiagram-v2
    [*] --> idle
    idle --> sofa_relax: Stue presence
    idle --> dining: Spisestue presence
    idle --> bath_visit: Bad presence
    idle --> bedroom_only: Sove/børn presence

    sofa_relax --> cooking: + Spisestue
    dining --> cooking: + Stue
    cooking --> social_dining: 17-23 + 30 min
    cooking --> social_party: 4+ zones

    bedroom_only --> nightwalk: + Bad
    nightwalk --> bedroom_only: Bad clear

    sofa_relax --> idle: 20+ min empty
    dining --> idle: 20+ min empty
    cooking --> idle: 20+ min empty

    state "guest_mode_auto_set (after 30 min social_*)" as gms
    social_dining --> gms
    social_party --> gms
    cooking --> gms

    state "guest_mode_clear (after 15 min idle/bedroom)" as gmc
    idle --> gmc
    bedroom_only --> gmc
```

## Godnat state machine

```mermaid
stateDiagram-v2
    [*] --> day
    day --> godnat_pending: User starter godnat (script.godnat)
    godnat_pending --> godnat_active: Confirmed godnat (lights dimmed)
    godnat_active --> day: 06:00 auto-clear
    godnat_active --> day: User morning activity (Apollo)
    godnat_active --> day: Wakeup automation fires

    state "Sub-flags (independent toggles)" as subs
    godnat_active --> subs

    note right of subs
        godnat_voksne_active
        godnat_boern_active
        kalde_active
    end note

    subs --> day: 09:00 safety auto-clear (audit-runde 10)
```

## Mode flag interactions (priority order)

```mermaid
flowchart TD
    A[Trigger fires] --> B{house_state}
    B -->|Dormant| Z1[Skip — gated]
    B -->|Active| C{godnat_active?}
    C -->|on| D{Hold-alive mode?}
    D -->|cinema/cirkus/kalde on| Z2[Skip — protected]
    D -->|all off| E[Normal automation]
    C -->|off| E
    E --> F{godnat_pending?}
    F -->|on| Z3[Off-automations skip]
    F -->|off| G[Fire light/cover service]
```

## Sensor data flow

```mermaid
flowchart LR
    Apollo1[Apollo MSR-2 stue<br/>radar + lux] --> open_plan_lux
    Apollo2[Apollo MSR-2 sove<br/>radar + lux] --> open_plan_lux
    Apollo3[Apollo MSR-2 spisestue<br/>radar + lux] --> open_plan_lux
    open_plan_lux[sensor.open_plan_lux<br/>fallback chain]

    Apollo1 --> activity_state
    Apollo2 --> activity_state
    Apollo3 --> activity_state
    Apollo4[Apollo MSR-2 bad] --> activity_state
    Apollo5[Apollo MSR-2 boern] --> activity_state
    Vallhorn[Depot Vallhorn] --> activity_state
    Myggspray[Myggspray entré<br/>Matter/Thread] --> activity_state

    activity_state --> guest_mode_auto

    open_plan_lux --> presence_X[presence_X.yaml<br/>per-room conditions]
    activity_state --> presence_X

    Sun[sun.sun elev] --> auto_color_temp
    auto_color_temp[sensor.auto_color_temp_evening] --> presence_X
```

## Hardware → Software stack

```mermaid
flowchart TD
    HW1[ZBT-2 USB Zigbee dongle] --> ZHA[ZHA integration]
    ZHA --> ZigbeeDevices[5 RODRET + 5 Apollo Zigbee + Innr bulbs + Vallhorn]

    HW2[Sonoff ZBDongle-E<br/>flashed OpenThread RCP] --> OTBR[OpenThread Border Router addon]
    OTBR --> ThreadNetwork[ha-thread-4187 ch15]
    ThreadNetwork --> Matter[Matter integration<br/>+ Matter Server addon]
    Matter --> MatterDevices[3× Myggbett door + 1× Myggspray motion]

    HW3[NUC Intel BT] --> BTIntegration[Bluetooth integration]
    BTIntegration --> Matter

    HW4[Apollo MSR-2 ESPHome WiFi] --> WiFi[Home Wi-Fi]
    WiFi --> ESPHome[ESPHome integration]
```
