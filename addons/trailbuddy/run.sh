#!/usr/bin/with-contenv bashio
# Trail Buddy add-on: start our own Tailscale node, publish ONLY port 8080 of
# this container with Funnel, then run the server. Home Assistant itself is not
# exposed: it stays behind the NUC's normal Tailscale node, as before.
set -e

export TRIP_CODE="$(bashio::config 'trip_code')"
export APP_DIR=/app DATA_DIR=/data PORT=8080
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
    tailscale funnel --bg 8080 || bashio::log.error "Funnel failed: enable HTTPS + the funnel node attribute for tag:trailbuddy in the Tailscale admin console"
    bashio::log.info "Public address: https://$(tailscale status --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')"
  else
    tailscale funnel --bg off >/dev/null 2>&1 || true
  fi
else
  bashio::log.warning "No tailscale_authkey: only reachable inside HA as http://local-trailbuddy:8080"
fi

exec python3 /trailbuddy_server.py
