#!/usr/bin/with-contenv bashio
# Trail Buddy add-on: start our own Tailscale node, publish the app with Funnel,
# then run the server. Home Assistant itself is not exposed: it stays behind the
# NUC's normal Tailscale node, as before.
#
# Two public addresses since 0.6.80 (2026-11-17):
#   https://<node>:10000  → :8080  the app (a new origin: no old service worker or
#                                  cache from v1-v115 can reach it)
#   https://<node>        → :8090  the old address: its pages move a phone's saved
#                                  data to the new one and open it there; API as before
# Home Assistant keeps http://local-trailbuddy:8080 (app + API) and :8081.
set -e

export TRIP_CODE="$(bashio::config 'trip_code')"
export APP_DIR=/app DATA_DIR=/data PORT=8080 LEGACY_PORT=8090
HOSTNAME_TS="$(bashio::config 'tailscale_hostname')"
AUTHKEY="$(bashio::config 'tailscale_authkey')"

if [ -z "${TRIP_CODE}" ]; then
  bashio::log.warning "trip_code is empty: group sharing is disabled"
fi

# Joined before (state in /data) → the key can be cleared from the options.
if [ -n "${AUTHKEY}" ] || [ -s /data/tailscale/tailscaled.state ]; then
  mkdir -p /data/tailscale /var/run/tailscale
  tailscaled --tun=userspace-networking --statedir=/data/tailscale \
             --socket=/var/run/tailscale/tailscaled.sock >/proc/1/fd/1 2>&1 &
  for _ in $(seq 1 30); do [ -S /var/run/tailscale/tailscaled.sock ] && break; sleep 1; done
  # The auth key is only needed the first time; state in /data keeps the node.
  if [ -n "${AUTHKEY}" ]; then
    tailscale up --authkey="${AUTHKEY}" --hostname="${HOSTNAME_TS}" --accept-dns=false || \
      tailscale up --hostname="${HOSTNAME_TS}" --accept-dns=false
  else
    tailscale up --hostname="${HOSTNAME_TS}" --accept-dns=false
  fi
  if bashio::config.true 'funnel'; then
    funnel_on() {
      tailscale serve reset >/dev/null 2>&1 || true   # drops every older mapping (8443 too)
      tailscale funnel --bg --https=10000 8080 && tailscale funnel --bg --https=443 8090
    }
    funnel_on || bashio::log.error "Funnel failed: enable HTTPS + the funnel node attribute for tag:trailbuddy in the Tailscale admin console"
    OLD="https://$(tailscale status --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')"
    PUBLIC="${OLD}:10000"
    bashio::log.info "Public address: ${PUBLIC} (old address ${OLD} moves phones there)"
    # Home Assistant asks the internal port for this (GET :8081/health), so the
    # tailnet name never has to be written into its config (B299).
    export PUBLIC_URL="${PUBLIC}"
    # Funnel watchdog (2026-11-05): after the 0.5.0 restart Funnel said "running"
    # but the relay dropped every outside TLS handshake for hours (phones on the
    # tailnet still worked, so nobody noticed); off + on fixed it. Every 30 min,
    # fetch our own public /api/health the way an outsider does; two misses in a
    # row → re-register Funnel. Home Assistant runs its own outside check and
    # pushes if this doesn't help (packages/trailbuddy_vagt.yaml).
    (
      ok() { curl -fsS -o /dev/null --max-time 20 "${PUBLIC}/api/health" && curl -fsS -o /dev/null --max-time 20 "${OLD}/api/health"; }
      sleep 300
      while true; do
        if ! ok && { sleep 60; ! ok; }; then
          echo "[funnel-watchdog] ${PUBLIC} unreachable from outside: re-registering Funnel"
          sleep 3
          funnel_on >/dev/null 2>&1 || echo "[funnel-watchdog] funnel on failed"
          sleep 30
          if ok; then echo "[funnel-watchdog] reachable again"; else echo "[funnel-watchdog] still unreachable"; fi
        fi
        sleep 1800
      done
    ) >/proc/1/fd/1 2>&1 &
  else
    tailscale serve reset >/dev/null 2>&1 || true
  fi
else
  bashio::log.warning "No tailscale_authkey: only reachable inside HA as http://local-trailbuddy:8080"
fi

exec python3 /trailbuddy_server.py
