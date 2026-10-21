#!/usr/bin/env python3
# Somfy RTS RF-capture via Broadlink RM4 Pro @ fixed 433.42 MHz.
# HA's native learn auto-sweeper finder ALDRIG Somfy (433.42 vs 433.92).
# Brug: python3 scripts/somfy_capture.py <label> [window_seconds]
import base64
import sys
import time

import broadlink

label = sys.argv[1] if len(sys.argv) > 1 else "kode"
window = int(sys.argv[2]) if len(sys.argv) > 2 else 30
dev = broadlink.hello("192.0.2.87")
dev.auth()
dev.find_rf_packet(frequency=433.42)
print(
    f'>>> ARMED for "{label}" — TRYK NU paa fjernbetjeningen (hold knappen). Vindue: {window}s',
    flush=True,
)
t0 = time.time()
pkt = None
while time.time() - t0 < window:
    try:
        pkt = dev.check_data()
    except Exception:
        pkt = None
    if pkt:
        break
    time.sleep(0.4)
if pkt:
    print("CAPTURED " + label + " b64:" + base64.b64encode(pkt).decode())
else:
    print("TIMEOUT — ingen RF fanget for " + label + " (proev igen, hold knappen laengere)")
