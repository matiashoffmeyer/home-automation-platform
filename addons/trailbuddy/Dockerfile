ARG BUILD_FROM
FROM ${BUILD_FROM}

# python3 runs the server (stdlib only); tailscale gives this add-on its own
# tailnet node + Funnel, in userspace networking (no TUN device, no host network).
RUN apk add --no-cache python3 tailscale ca-certificates

# app/ and trailbuddy_server.py are copied in by sync_app.sh from golden-repo.
COPY app/ /app/
COPY trailbuddy_server.py run.sh /
RUN chmod a+x /run.sh && test -f /app/index.html

CMD [ "/run.sh" ]
