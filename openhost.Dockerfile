# Dockerfile for running Sculptor as an OpenHost app, built from source.
#
# Unlike a released-binary image, this builds the exact code on this branch: it
# installs the backend with uv, regenerates the API client and builds the web
# UI, then runs the backend from source — serving the bundled UI itself, with no
# Electron shell. OpenHost builds with the repo root as the build context, from a
# clean git clone (so gitignored artifacts like node_modules/.venv/frontend dist
# are regenerated here, not copied in).
#
# All persistent state lands in the OpenHost app data dir so it survives
# rebuilds / "update and reload".

FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# libnss-wrapper lets the entrypoint present a passwd/group entry for the
# arbitrary runtime UID without making /etc/passwd writable (see entrypoint below).
# build-essential supplies a C compiler/linker (cc): Python deps with native
# extensions (e.g. typeid-python's Rust module) compile from sdist whenever no
# prebuilt wheel matches the interpreter, and uv/maturin's on-demand Rust install
# still needs a system C toolchain to link.
# nginx-light is the in-container front door (this dev branch): it owns port 5050
# and reverse-proxies /proxy/<port>/ to localhost dev servers for mobile live
# preview, everything else to the Sculptor backend (see openhost-nginx.conf).
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git curl ca-certificates xz-utils libnss-wrapper build-essential nginx-light && \
    rm -rf /var/lib/apt/lists/*

# Node.js 24 — for the frontend build and the API-client codegen. Matches the
# version the rest of the repo pins (24.17.0 via nvm / .nvmrc).
RUN curl -fsSL https://deb.nodesource.com/setup_24.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    rm -rf /var/lib/apt/lists/*

# GitHub CLI (gh) — used by the Add Repository remote-clone flow and signed in
# via the in-app auth flow. Installed from GitHub's official apt repo.
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        -o /usr/share/keyrings/githubcli-archive-keyring.gpg && \
    chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        > /etc/apt/sources.list.d/github-cli.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends gh && \
    rm -rf /var/lib/apt/lists/*

# pnpm via Corepack (ships with Node). The pinned version comes from the
# `packageManager` field in sculptor/frontend/package.json.
RUN corepack enable pnpm

# uv — Python package/venv manager; it provisions the right Python for the project.
RUN curl -fsSL https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"
# Copy into the venv instead of hardlinking the uv cache, so it stays
# self-contained when run later under a different (rootless) UID.
ENV UV_LINK_MODE=copy
# Install uv's managed Python under a world-readable path (default is
# /root/.local/share/uv/python, which the non-root runtime UID can't traverse).
# The venv's python symlinks here, so it must stay accessible at runtime.
ENV UV_PYTHON_INSTALL_DIR=/opt/uv-python

WORKDIR /app
COPY . /app

# Install the backend env first — the frontend's generate-api step shells out to
# `uv run` to emit the OpenAPI schema, so the backend env must already exist.
RUN cd /app/sculptor && uv sync

# Generate the `sculpt` CLI's OpenAPI client into tools/sculpt/sculpt/client.
# Without it, every `sculpt` command fails at import (ModuleNotFoundError: No
# module named 'sculpt.client'). Mirrors the `generate-sculpt-client` just recipe,
# run inline since `just` isn't in the image; needs the backend env (the uv sync
# above) to emit the OpenAPI schema.
RUN cd /app && \
    tmp_schema="$(mktemp)" && \
    uv run --project sculptor python sculptor/sculptor/scripts/generate_json_schema.py "$tmp_schema" && \
    uv run --project tools/sculpt openapi-python-client generate \
        --path "$tmp_schema" --output-path tools/sculpt/sculpt/client_tmp --overwrite && \
    rm -rf tools/sculpt/sculpt/client && \
    mv tools/sculpt/sculpt/client_tmp/sculptor_v1_api_client tools/sculpt/sculpt/client && \
    rm -rf tools/sculpt/sculpt/client_tmp "$tmp_schema"

# Regenerate the API client from the (just-built) backend, then build the web UI.
# NODE_OPTIONS raises V8's heap ceiling for the Vite build: the default (~2 GB)
# leaves the production build right at the limit, so it intermittently aborts
# with "JavaScript heap out of memory" (exit 134). 4 GB gives reliable headroom.
RUN cd /app/sculptor/frontend && \
    pnpm install --no-frozen-lockfile && \
    pnpm run generate-api && \
    NODE_OPTIONS=--max-old-space-size=4096 pnpm run build

# --- Runtime setup ---------------------------------------------------------

# Rename Ubuntu's stock 'ubuntu' user (UID 1000) to 'sculptor'. At runtime
# rootless podman assigns an arbitrary UID/GID; the entrypoint uses nss_wrapper
# to present a matching passwd/group entry, so /etc/passwd stays read-only (no
# `chmod 666`). /app is made world read/executable so the runtime UID can run the
# built venv and read the UI.
RUN usermod -l sculptor -d /home/sculptor -m ubuntu && \
    groupmod -n sculptor ubuntu && \
    mkdir -p /home/sculptor && chmod 777 /home/sculptor && \
    mkdir -p /data && chmod 777 /data && \
    chmod -R a+rX /app /opt/uv-python

ENV HOME=/home/sculptor
# The backend now sits BEHIND nginx, reachable only on loopback. nginx owns the
# public-facing port (5050, what openhost.toml declares) and proxies to here.
ENV SCULPTOR_BIND_HOST=127.0.0.1
# Backend port (internal). nginx listens on 5050 and forwards to 5051.
ENV SCULPTOR_API_PORT=5051
# Persist DB, workspaces, downloaded agent binaries, and user config into the
# OpenHost backed-up app data dir (the app is named "sculptor" in openhost.toml).
ENV SCULPTOR_FOLDER=/data/app_data/sculptor
# Persist Claude Code's OAuth credentials (written by the in-app sign-in flow).
ENV CLAUDE_CONFIG_DIR=/data/app_data/sculptor/claude
# Persist the GitHub CLI's auth token (written by the in-app gh sign-in flow) so
# it survives rebuilds / "update and reload" like the Claude credentials do.
ENV GH_CONFIG_DIR=/data/app_data/sculptor/gh

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
# the real /etc/passwd read-only. No binary download — we run from the source
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
# Start the backend (on loopback :5051) behind the nginx front (on :5050) via the
# run script: it resolves the app-data dir, ensures persistent dirs exist, launches
# the backend from the built venv (/app/.venv, the uv workspace root), and execs
# nginx. The backend still serves the bundled web UI it built above; nginx only
# adds the /proxy/<port>/ live-preview route on top. See openhost-run.sh.
CMD ["sh", "/app/openhost-run.sh"]
