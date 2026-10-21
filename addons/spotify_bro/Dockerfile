ARG BUILD_FROM
FROM ${BUILD_FROM}
ARG BUILD_ARCH

# Debian, not Alpine: the go-librespot release binary is glibc-linked and
# needs libasound2 even with the pipe backend. flac is only used by format=flac.
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-aiohttp flac libasound2 ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

# 0.10.5 (16/10), not MA's 0.9.0: 0.10.x retries dropped connect-state
# pushes, tells Spotify the old session is inactive before a zeroconf
# re-login replaces it, and starts an external-volume session from the real
# volume - all three seen in the live test. Same API and event names (only
# playback_error added). Checksums are GitHub's published release digests.
ARG LIBRESPOT_VERSION=v0.10.5
RUN case "${BUILD_ARCH}" in \
        amd64) asset=go-librespot_linux_x86_64.tar.gz; sum=f08647217d1dced339375680d731bb5fc2410a9d693f2e1235303511c35a051c ;; \
        aarch64) asset=go-librespot_linux_arm64.tar.gz; sum=35274c1d3576090096d3459ecf76ee9c025258d19dc76f0bf724f95c525467e1 ;; \
        *) echo "unsupported arch ${BUILD_ARCH}"; exit 1 ;; \
    esac \
    && curl -fsSL -o /tmp/glr.tgz "https://github.com/devgianlu/go-librespot/releases/download/${LIBRESPOT_VERSION}/${asset}" \
    && echo "${sum}  /tmp/glr.tgz" | sha256sum -c - \
    && tar -xzf /tmp/glr.tgz -C /usr/local/bin go-librespot \
    && rm /tmp/glr.tgz \
    && test -x /usr/local/bin/go-librespot

COPY run.sh bro.py /
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
