# Dockerfile for running Sculptor as an OpenHost app, built from source.
#
# Unlike a released-binary image, this builds the exact code on this branch: it
# installs the TypeScript backend (npm), bundles it with esbuild, regenerates the
# API client and builds the web UI, then runs the Node backend from the bundle —
# serving the bundled UI itself, with no Electron shell. OpenHost builds with the
# repo root as the build context, from a clean git clone (so gitignored artifacts
# like node_modules/frontend dist are regenerated here, not copied in).
#
# All persistent state lands in the OpenHost app data dir so it survives
# rebuilds / "update and reload".

FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# libnss-wrapper lets the entrypoint present a passwd/group entry for the
# arbitrary runtime UID without making /etc/passwd writable (see entrypoint below).
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git curl ca-certificates xz-utils libnss-wrapper python3 build-essential && \
    rm -rf /var/lib/apt/lists/*

# Node.js 24 — the runtime/ABI the backend's native addons (better-sqlite3,
# node-pty) are built against (matches the sidecar's pinned Node, Task 9.1), and
# the toolchain for the frontend build + API-client codegen. python3 +
# build-essential are present so node-gyp can compile the native addons.
RUN curl -fsSL https://deb.nodesource.com/setup_24.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

# Install the TypeScript backend deps (builds the native addons for linux-x64 /
# Node 24) and produce the esbuild bundle (dist/backend.cjs) + its drizzle
# migrations. The frontend's generate-api step (below) emits the OpenAPI schema
# from this backend, so it must be built first.
RUN cd /app/sculptor/backend && \
    npm ci && \
    npm run build

# Regenerate the API client from the (just-built) TS backend, then build the web
# UI. NODE_OPTIONS raises V8's heap ceiling for the Vite build: the default
# (~2 GB) leaves the production build right at the limit, so it intermittently
# aborts with "JavaScript heap out of memory" (exit 134). 4 GB gives headroom.
RUN cd /app/sculptor/frontend && \
    npm install --force && \
    npm run generate-api && \
    NODE_OPTIONS=--max-old-space-size=4096 npm run build

# --- Runtime setup ---------------------------------------------------------

# Rename Ubuntu's stock 'ubuntu' user (UID 1000) to 'sculptor'. At runtime
# rootless podman assigns an arbitrary UID/GID; the entrypoint uses nss_wrapper
# to present a matching passwd/group entry, so /etc/passwd stays read-only (no
# `chmod 666`). /app is made world read/executable so the runtime UID can run the
# bundle and read the UI.
RUN usermod -l sculptor -d /home/sculptor -m ubuntu && \
    groupmod -n sculptor ubuntu && \
    mkdir -p /home/sculptor && chmod 777 /home/sculptor && \
    mkdir -p /data && chmod 777 /data && \
    chmod -R a+rX /app

ENV HOME=/home/sculptor
# Serve on all interfaces so the OpenHost router can proxy to us.
ENV SCULPTOR_BIND_HOST=0.0.0.0
# Port the backend listens on. Keep in sync with `port` in openhost.toml.
ENV SCULPTOR_API_PORT=5050
# Persist DB, workspaces, downloaded agent binaries, and user config into the
# OpenHost backed-up app data dir (the app is named "sculptor" in openhost.toml).
ENV SCULPTOR_FOLDER=/data/app_data/sculptor
# Persist Claude Code's OAuth credentials (written by the in-app sign-in flow).
ENV CLAUDE_CONFIG_DIR=/data/app_data/sculptor/claude
# The backend serves the web UI built above + applies its schema migrations.
# These are resolved cwd-relative too, but set them explicitly so the launch
# command is independent of the working directory.
ENV SCULPTOR_STATIC_DIR=/app/sculptor/frontend/dist
ENV SCULPTOR_MIGRATIONS_DIR=/app/sculptor/backend/drizzle
ENV NODE_PATH=/app/sculptor/backend/node_modules

# A minimal git repo for Sculptor to open as a project on first run.
WORKDIR /workspace
RUN git -c user.email="sculptor@container" -c user.name="Sculptor" init && \
    git -c user.email="sculptor@container" -c user.name="Sculptor" commit --allow-empty -m "Initial commit" && \
    chmod -R 777 /workspace && \
    git config --system safe.directory '*'

# Minimal entrypoint: rootless podman assigns an arbitrary UID/GID with no
# matching /etc/passwd entry, which breaks anything that calls getpwuid (e.g.
# $HOME and username lookups). Rather than make /etc/passwd writable, use
# nss_wrapper: write passwd/group files to a writable tmp location with an entry
# for the runtime UID/GID and point the NSS layer at them via LD_PRELOAD, leaving
# the real /etc/passwd read-only. No binary download — we run from the bundle
# built above. The nss_wrapper lib path is resolved at build time and baked in.
# printf avoids heredoc portability concerns across build backends.
RUN NSS_WRAPPER_LIB="$(dpkg -L libnss-wrapper | grep -m1 '/libnss_wrapper\.so$')" && \
    : "${NSS_WRAPPER_LIB:?libnss_wrapper.so not found}" && \
    printf '%s\n' \
    '#!/bin/sh' \
    'uid=$(id -u)' \
    'if ! getent passwd "$uid" >/dev/null 2>&1; then' \
    '  gid=$(id -g)' \
    '  pw=$(mktemp /tmp/passwd.XXXXXX)' \
    '  gr=$(mktemp /tmp/group.XXXXXX)' \
    '  sed "s/^sculptor:x:1000:1000:/sculptor:x:${uid}:${gid}:/" /etc/passwd > "$pw"' \
    '  sed "s/^sculptor:x:1000:/sculptor:x:${gid}:/" /etc/group > "$gr"' \
    '  export NSS_WRAPPER_PASSWD="$pw" NSS_WRAPPER_GROUP="$gr"' \
    "  export LD_PRELOAD=$NSS_WRAPPER_LIB" \
    'fi' \
    'exec "$@"' \
    > /usr/local/bin/openhost-entrypoint.sh && \
    chmod +x /usr/local/bin/openhost-entrypoint.sh

USER sculptor
ENTRYPOINT ["/usr/local/bin/openhost-entrypoint.sh"]
# Ensure the persistent dirs exist, then run the Node backend bundle. The
# headless backend serves the web UI (SCULPTOR_STATIC_DIR) and applies its
# migrations; --no-open-browser is an accepted no-op (Task 9.2).
CMD ["sh", "-c", "mkdir -p \"$SCULPTOR_FOLDER\" \"$CLAUDE_CONFIG_DIR\" && exec node /app/sculptor/backend/dist/backend.cjs --no-open-browser"]
