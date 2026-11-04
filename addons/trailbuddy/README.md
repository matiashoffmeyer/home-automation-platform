# Trail Buddy add-on

Publishes the Trail Buddy hiking app from the NUC on its **own** public HTTPS
address (`https://trail.<tailnet>.ts.net`) using Tailscale Funnel. The four
hikers open the link: no VPN, no Tailscale app, no Home Assistant account.

Only this add-on is public. It runs its own small Tailscale node in userspace
mode and funnels only its port 8080. Home Assistant is **not** exposed and keeps
its current posture (no Nabu Casa, no Funnel/Serve on the NUC's node). The
add-on has no host ports; HA reads it on the Docker network as
`http://local-trailbuddy:8080`.

## What it serves

- The app: offline topo map, route stats, POIs, day plan, weather tab.
- `/api/weather`, `/api/briefing`: the trip forecast (Open-Meteo), refreshed every 2 h.
- `/api/group/<trip_code>`: each hiker's latest position and progress. The trip
  code is required, and without it nobody's position is visible.
- `/api/om`, `/api/proxy`: Open-Meteo / Google Sheets / Overpass for the app.

## Install

1. Copy this folder to `/addons/trailbuddy/` on the NUC, then run
   `./sync_app.sh` there. It pulls the app from golden-repo `main` into `app/`.
2. Supervisor: reload the add-on store, install **Trail Buddy** (local add-on).
3. Options:
   - `trip_code`: a word you share with the group, e.g. 2–3 random words.
   - `tailscale_authkey`: see below. Only needed for the first start.
   - `tailscale_hostname`: `trail` (gives `https://trail.<tailnet>.ts.net`).
4. Start it. The log prints the public address.

Updating the app later: run `./sync_app.sh` again, bump `version` in `config.yaml`,
then rebuild/update the add-on. Your rules say to deploy from `/addons/<slug>/`
and verify on `version`.

## Tailscale admin console (one time, about 5 minutes)

1. **DNS:** MagicDNS on, and **HTTPS Certificates: Enable**.
2. **Access controls** (policy file). Add a tag that may use Funnel:
   ```jsonc
   "tagOwners": { "tag:trailbuddy": ["autogroup:admin"] },
   "nodeAttrs": [ { "target": ["tag:trailbuddy"], "attr": ["funnel"] } ],
   ```
   And make sure the public node **cannot reach your other devices**. If your
   policy still has the default allow-all rule, change its source from `*` to
   members only (tagged nodes are not members):
   ```jsonc
   // ACL style
   { "action": "accept", "src": ["autogroup:member"], "dst": ["*:*"] }
   // or grants style
   { "src": ["autogroup:member"], "dst": ["*"], "ip": ["*"] }
   ```
3. **Settings → Keys → Generate auth key:** not reusable, not ephemeral,
   **pre-approved**, **tags: `tag:trailbuddy`**. Paste it into the add-on's
   `tailscale_authkey` option. Tagged nodes don't expire, so the key is only
   used once.

## Security notes

- The add-on container is internet-facing through Funnel. It holds only the
  route, POIs, forecasts and the group's positions, and no HA token.
- `/api/proxy` only fetches from Google Sheets, googleusercontent and Overpass.
- Request bodies are capped at 64 KB; group entries keep a fixed set of fields.
- Turn the `funnel` option off (or stop the add-on) after the trip.
