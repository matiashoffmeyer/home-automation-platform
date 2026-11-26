# Trail Buddy add-on

Publishes the Trail Buddy hiking app from the NUC on its **own** public HTTPS
address (`https://trail.<tailnet>.ts.net:10000`) using Tailscale Funnel. The four
hikers open the link: no VPN, no Tailscale app, no Home Assistant account.

The old address (`https://trail.<tailnet>.ts.net`, until 0.6.79) now only moves
phones: its pages hand the phone's saved routes/settings/track to the new address
and open it there, and its service worker removes the old app's worker and caches
(they kept serving old versions, 2026-11-16). Its API still answers.

Only this add-on is public. It runs its own small Tailscale node in userspace
mode and funnels only its ports 8080 (the app, :10000) and 8090 (the old address, :443). Home Assistant is **not** exposed and keeps
its current posture (no Nabu Casa, no Funnel/Serve on the NUC's node). The
add-on has no host ports; HA reads it on the Docker network as
`http://local-trailbuddy:8080`.

## What it serves

- The app: offline topo map, route stats, POIs, day plan, weather tab.
- `/api/weather`, `/api/briefing`: the trip forecast (Open-Meteo), refreshed every 2 h.
  They hold the camp coordinates, so they need the trip code too
  (`?code=<trip_code>` or header `X-Trip-Code`).
- `/api/group/<trip_code>`: each hiker's latest position and progress. The trip
  code is required, and without it nobody's position is visible.
- `/api/camps/<trip_code>`: where the group actually camps each night (moved in the app), kept per route.
- `/api/days/<trip_code>`: the day log (broke camp, made camp, 🚕 skipped), kept per route.
- `/api/hiking/<trip_code>`: shared settings, each route's trip (name, first day, nights) and each
  walked trip's record (its logged days time the trips not walked yet).
- `/api/archive/<trip_code>`: earlier data kept on the server; `{"restore": stamp}` brings it back.
- `/api/routes/<trip_code>`: the route library (every GPX kept on the server); `{"delete": id}`
  takes one out (moved to `routes/deleted/`, not the group's route).
- `/api/trails/<trip_code>` (POST, the app's Overpass queries): the paths, tracks and roads
  (dirt roads drawn as tracks, since 0.6.97; cycleways and pedestrian streets since 0.6.98) for "Satellite + trails". The server fetches them itself and keeps asking while the public
  Overpass servers are busy (up to 6 h), keeps the newest 12 trips' in `trails/`, and the
  phone asks again until it answers `ready` (2026-11-19: Overpass was at capacity for hours).
- `/api/snap/<trip_code>` (POST `{a, b}`, the route editor since 0.6.138): one leg a → b over
  hiking trails (BRouter `hiking-mountain` on brouter.de; ≤ 60 km straight, 600 legs an hour,
  kept per leg) → `{pts: [[lat, lon, ele]], m: {path, track, street, road}}`. `/api/trails` with
  `kind: "edit"` fetches the editor's map cells (0.1°), kept apart from the trips' trails.
- `/api/elevate/<trip_code>` (POST `{pts}`, ≤ 2000): Copernicus GLO-30 heights for the edited
  stretches (`dem.py`, range reads from AWS's open bucket, no key).
- `/api/closures/<trip_code>` (0.6.147): closed trails and tunnels on a route (`closures.py`).
  POST `{pts}` (every 25 m, as `/api/hammock`) checks OpenStreetMap's closure tags and, with a
  `mapy_api_key`, Mapy.com's closures (routing API, ~4 credits per 25 points; kept 3 days);
  ask again with `{key}` until `ready`. The group's own list: GET, POST `{add, by}` / `{remove}`;
  the route editor's legs go around what is on it (BRouter nogos). Mapy's closed stretches
  join the list by themselves. Never copy Mapy's data into OpenStreetMap.
- `/api/hammock/<trip_code>` (v2 in 0.6.148): tree cover and distances to people along a route
  (POST `{pts}` every 25 m, then `{key}` until `ready`), and `detours`: woods up to 1 km off
  where the trail has no trees, with the path there by BRouter, so no night is treeless.
- `/api/om`, `/api/proxy`: Open-Meteo / Google Sheets / Overpass for the app.

## Install

1. Copy this folder to `/addons/trailbuddy/` on the NUC, then run
   `./sync_app.sh` there. It pulls the app from golden-repo `main` into `app/`.
2. Supervisor: reload the add-on store, install **Trail Buddy** (local add-on).
3. Options:
   - `trip_code`: a word you share with the group, e.g. 2–3 random words.
   - `tailscale_authkey`: see below. Only needed for the first start.
   - `tailscale_hostname`: `trail` (gives `https://trail.<tailnet>.ts.net`).
   - `mapy_api_key` (optional): a Mapy.com API key for the closure check (developer.mapy.com,
     free tier 250 000 credits a month). Without it only OpenStreetMap's tags are checked.
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
- Trip code: constant-time compare; after 20 wrong codes in 10 min every code
  gets 429 until the window clears. Use 2–3 random words, not a name.
- `/api/proxy` only fetches from Google Sheets, googleusercontent and Overpass,
  follows redirects only to those hosts, answers only as JSON/CSV/text (never
  HTML) in a sandbox, and the proxies are rate-limited (60/min).
- Every page gets a strict Content-Security-Policy, `nosniff`, `X-Frame-Options:
  DENY` and no referrer; no folder listings; the trip code is masked in the log.
- Request bodies are capped at 64 KB; group entries keep a fixed set of fields
  (numbers must be finite, text ≤ 80 chars, ≤ 20 members); camps take day 1–30
  and a valid lat/lon only.
- After the first start you can clear `tailscale_authkey`; the node keeps its
  identity in `/data`.
- Turn the `funnel` option off (or stop the add-on) after the trip.
