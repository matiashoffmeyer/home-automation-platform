#!/usr/bin/env python3
"""Remote reset of the Sonoff Thread RCP (EFR32) without a physical re-plug.

Background
----------
The OpenThread Border Router add-on periodically dies because the RCP firmware
on the Sonoff ZBDongle (ttyUSB0) wedges: otbr-agent's Spinel handshake times out
(`migrate_otbr_settings.py` -> get_adapter_hardware_addr -> TimeoutError) and the
add-on container exits. A plain add-on restart does NOT fix a wedged RCP. Until
2026-06-29 the only known cure was unplugging the stick.

This script delivers that cure remotely. The Sonoff's CP210x USB-UART bridge has
its DTR/RTS lines wired to the EFR32's reset/bootloader pins (the same circuit
universal-silabs-flasher uses). Pulsing RTS asserts the EFR32 nRESET line, so the
radio cold-boots its firmware. Proven working: after the pulse the RCP reported
`Reset info: 0x301 (PIN)` and re-attached on the SAME Thread network (PAN 0x4187),
so NO Matter re-pairing is needed (the RCP holds no network credentials; the
dataset lives in the OTBR add-on + .storage/thread.datasets).

We do NOT and cannot cut USB VBUS from software (sysfs is read-only in the SSH
add-on; no uhubctl). The DTR/RTS pin reset is the working substitute.

Usage
-----
  python3 otbr_rcp_reset.py            # pulse-only: just reset the RCP (default)
  python3 otbr_rcp_reset.py --full     # orchestrated recovery (needs SUPERVISOR_TOKEN)

--full does the safe full sequence: disable our Thread watchdog -> stop the OTBR
add-on (free the port) -> pulse -> start the add-on -> verify matter_spots_ok ->
re-enable the watchdog. Run --full from the SSH add-on (it has SUPERVISOR_TOKEN).

The watchdog automation calls the default pulse-only mode via shell_command;
HA itself stops/starts the add-on around it (HA core has no SUPERVISOR_TOKEN).

SAFETY: the script refuses to touch anything that is not the Sonoff Thread stick
(VID:PID 10c4:ea60, by-id name contains "Itead_Sonoff"). The ZBT-2 Zigbee
coordinator is a different device (ttyACM0) and is never matched.
"""

import glob
import os
import sys
import time

SONOFF_VID = "10c4"
SONOFF_PID = "ea60"
ADDON = "core_openthread_border_router"


def find_thread_tty():
    """Return /dev/ttyUSBx for the Sonoff Thread stick, or None. Refuses other devices."""
    for link in glob.glob("/dev/serial/by-id/*Itead*Sonoff*if00-port0"):
        dev = os.path.realpath(link)
        if _verify_vid_pid(dev):
            return dev
    return None


def _verify_vid_pid(dev):
    """Walk sysfs up from the tty to the USB device and confirm VID:PID == Sonoff."""
    name = os.path.basename(dev)
    node = os.path.realpath(f"/sys/class/tty/{name}/device")
    for _ in range(6):
        vid = os.path.join(node, "idVendor")
        pid = os.path.join(node, "idProduct")
        if os.path.exists(vid) and os.path.exists(pid):
            with open(vid) as f:
                v = f.read().strip()
            with open(pid) as f:
                p = f.read().strip()
            return v == SONOFF_VID and p == SONOFF_PID
        node = os.path.dirname(node)
    return False


def pulse_reset(dev):
    """Assert the EFR32 nRESET via the CP210x RTS line, then release so it runs firmware."""
    import fcntl
    import struct
    import termios

    DTR = termios.TIOCM_DTR
    RTS = termios.TIOCM_RTS
    fd = os.open(dev, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    try:

        def get():
            return struct.unpack("I", fcntl.ioctl(fd, termios.TIOCMGET, struct.pack("I", 0)))[0]

        def setb(bits):
            fcntl.ioctl(fd, termios.TIOCMSET, struct.pack("I", bits))

        start = get()
        # deassert both -> assert RTS (nRESET low), DTR low (boot=run) -> release RTS (run)
        setb(start & ~DTR & ~RTS)
        time.sleep(0.1)
        setb((start & ~DTR) | RTS)
        time.sleep(0.2)
        setb(start & ~DTR & ~RTS)
        time.sleep(0.2)
        setb(start)
    finally:
        os.close(fd)


# ---- --full orchestration (supervisor API; only where SUPERVISOR_TOKEN exists) ----


def _sup():
    import urllib.request

    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        sys.exit("--full needs SUPERVISOR_TOKEN (run from the SSH add-on).")

    def call(method, path, body=None):
        data = body.encode() if body else None
        req = urllib.request.Request(
            f"http://supervisor{path}",
            data=data,
            method=method,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode()

    return call


def full_recovery(dev):
    import json

    call = _sup()
    print("disable thread watchdog")
    call(
        "POST",
        "/core/api/services/input_boolean/turn_off",
        '{"entity_id":"input_boolean.thread_watchdog_enabled"}',
    )
    print("stop OTBR add-on")
    call("POST", f"/addons/{ADDON}/stop")
    time.sleep(3)
    print(f"pulse-reset {dev}")
    pulse_reset(dev)
    time.sleep(4)
    print("start OTBR add-on")
    call("POST", f"/addons/{ADDON}/start")
    print("wait for Thread to re-attach...")
    ok = False
    for _ in range(18):  # ~90s
        time.sleep(5)
        st = json.loads(call("GET", "/core/api/states/binary_sensor.badevaerelse_matter_spots_ok"))
        if st.get("state") == "on":
            ok = True
            break
    print("re-enable thread watchdog")
    call(
        "POST",
        "/core/api/services/input_boolean/turn_on",
        '{"entity_id":"input_boolean.thread_watchdog_enabled"}',
    )
    print(
        "RESULT: matter_spots_ok =",
        "on (recovered)"
        if ok
        else "STILL OFF (likely real hardware/power issue -> physical re-plug)",
    )
    return ok


def main():
    dev = find_thread_tty()
    if not dev:
        sys.exit("Sonoff Thread stick not found (by-id Itead/Sonoff, VID:PID 10c4:ea60). Aborting.")
    if "--full" in sys.argv:
        ok = full_recovery(dev)
        sys.exit(0 if ok else 1)
    print(f"pulse-reset {dev}")
    pulse_reset(dev)
    print("done (RCP reset pulse delivered)")


if __name__ == "__main__":
    main()
