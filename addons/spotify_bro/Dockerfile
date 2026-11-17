ARG BUILD_FROM
# golang:1.25-bookworm (index digest 15/11) - same Debian as the runtime, so
# the dynamically linked libflac/libmpg123/libasound/libvorbis match.
FROM golang:1.25-bookworm@sha256:3b4a11519ad929d1e1d261a12cff056f0c85b735253d7d861346b9c6f8b36437 AS glr
ARG LIBRESPOT_COMMIT=9085364713233bb3b1a9effe72284c658209a5ed
ARG LIBRESPOT_SRC_SHA256=66a1dfcb67e9a50444590f641aad10967174546aa3cbc55b6fe5575f9b0b284d
RUN apt-get update \
    && apt-get install -y --no-install-recommends libflac-dev libmpg123-dev libasound2-dev libogg-dev libvorbis-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*
ENV GOTOOLCHAIN=local CGO_ENABLED=1
RUN curl -fsSL -o /tmp/src.tgz "https://github.com/devgianlu/go-librespot/archive/${LIBRESPOT_COMMIT}.tar.gz" \
    && echo "${LIBRESPOT_SRC_SHA256}  /tmp/src.tgz" | sha256sum -c - \
    && mkdir /src && tar -xzf /tmp/src.tgz -C /src --strip-components=1 \
    && cd /src \
    && go build -trimpath -ldflags "-s -w -X github.com/devgianlu/go-librespot.version=v0.10.5-${LIBRESPOT_COMMIT}" -o /go-librespot ./cmd/daemon \
    && test -x /go-librespot

FROM ${BUILD_FROM}
ARG BUILD_ARCH

# Debian, not Alpine: the go-librespot binary is glibc-linked and
# needs libasound2, libflac, libmpg123, libvorbis(enc) even with the pipe backend. The
# flac CLI is only used by format=flac.
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-aiohttp flac libasound2 libflac12 libmpg123-0 libogg0 libvorbis0a libvorbisenc2 ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

# go-librespot is BUILT from commit 9085364 (8/11), 10 commits after v0.10.5,
# because the fix for upstream #434 is merged but not yet released: v0.10.5
# pushes a connect state with playback_id set and no track while a new
# context loads, and Spotify for Android (9.1.x) crashes on it - "the app
# closes when I pick a new song" (15/11). Back to a release binary when one
# newer than v0.10.5 ships (check its notes for "drop the playback id").
# Source tarball and the golang build image are pinned by sha256; the build
# runs with GOTOOLCHAIN=local so no other toolchain is fetched.
# 0.10.x itself (not MA's 0.9.0): retries dropped connect-state pushes, tells
# Spotify the old session is inactive before a zeroconf re-login, starts an
# external-volume session from the real volume - all seen in the live test.
COPY --from=glr /go-librespot /usr/local/bin/go-librespot
RUN test -x /usr/local/bin/go-librespot

COPY run.sh bro.py /
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
