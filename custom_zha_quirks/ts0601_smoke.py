"""Tuya TS0601 røgalarm (_TZE284_mqaeyix5) — entré, over cykel-batterierne.

Parret 2026-07-28. IKKE understøttet upstream i zha-quirks (verificeret mod
2.1.1: tuya_smoke.py dækker _TZE200_aycxwiau/dq1mfjug/m9skfctm/rccxox8p/
vzekyi4c, _TZE284_rccxox8p/0zaf1cr8/n4ttsck2, _TZE204_vawy74yh/ntcy3xu1/
kgaxpvxr — ikke mqaeyix5). Uden quirk eksponerer ZHA kun en firmware-entity,
dvs. INGEN røg-sensor at automatisere på.

BEVIDST MINIMAL: kun DP 1 (røg). DP 1 er fælles for ALLE seks upstream
TS0601-røg-quirks, så det er den ene datapoint vi kan stole på uden at have
set enhedens egen trafik. `tuya_smoke` håndterer selv Tuya-inversionen
(værdi 0 == ALARM → IasZone.Alarm_1).

Batteri (DP 14/15) og "silence alarm" (DP 16) er UDELADT med vilje: de
varierer mellem varianter, og `tuya_switch` på DP 16 er en SKRIVE-sti der
kan kaste hvis enheden ikke har den. Vil vi have dem, skal vi først se de
faktiske DP'er i ZHA-debug-loggen når alarmen testes fysisk — så udvides
denne fil (mønster: se _TZE204_ntcy3xu1-blokken upstream).

NB: sensoren står `unknown` indtil enheden rapporterer første gang (Tuya-
røgalarmer sender kun ved ændring + sjælden heartbeat) → automations skal
trigge på `to: "on"`, ikke på `from: "off"`.
"""

from zhaquirks.tuya.builder import TuyaQuirkBuilder

(
    TuyaQuirkBuilder("_TZE284_mqaeyix5", "TS0601")
    .tuya_smoke(dp_id=1)
    .skip_configuration()
    .add_to_registry()
)
