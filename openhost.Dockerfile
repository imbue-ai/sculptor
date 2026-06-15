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

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git curl ca-certificates xz-utils && \
    rm -rf /var/lib/apt/lists/*

# Node.js 22 — for the frontend build and the API-client codegen.
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    rm -rf /var/lib/apt/lists/*

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

# Regenerate the API client from the (just-built) backend, then build the web UI.
RUN cd /app/sculptor/frontend && \
    npm install --force && \
    npm run generate-api && \
    npm run build

# --- Runtime setup ---------------------------------------------------------

# Rename Ubuntu's stock 'ubuntu' user (UID 1000) to 'sculptor'; the entrypoint
# remaps its UID to whatever rootless podman assigns at runtime. World-writable
# /etc/passwd lets that remap happen as a non-root user. /app is made world
# read/executable so the runtime UID can run the built venv and read the UI.
RUN usermod -l sculptor -d /home/sculptor -m ubuntu && \
    groupmod -n sculptor ubuntu && \
    mkdir -p /home/sculptor && chmod 777 /home/sculptor && \
    mkdir -p /data && chmod 777 /data && \
    chmod 666 /etc/passwd && \
    chmod -R a+rX /app /opt/uv-python

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

# A minimal git repo for Sculptor to open as a project on first run.
WORKDIR /workspace
RUN git -c user.email="sculptor@container" -c user.name="Sculptor" init && \
    git -c user.email="sculptor@container" -c user.name="Sculptor" commit --allow-empty -m "Initial commit" && \
    chmod -R 777 /workspace && \
    git config --system safe.directory '*'

# Minimal entrypoint: give the runtime UID a valid /etc/passwd entry (rootless
# podman assigns an arbitrary UID), then exec the command. No binary download —
# we run from the source built above. Written with printf to avoid heredoc
# portability concerns across build backends.
RUN printf '%s\n' \
    '#!/bin/sh' \
    'uid=$(id -u)' \
    'if ! getent passwd "$uid" >/dev/null 2>&1; then' \
    '  gid=$(id -g)' \
    '  tmp=$(mktemp /tmp/passwd.XXXXXX)' \
    '  sed "s/^sculptor:x:1000:1000:/sculptor:x:${uid}:${gid}:/" /etc/passwd > "$tmp"' \
    '  cat "$tmp" > /etc/passwd' \
    '  rm -f "$tmp"' \
    'fi' \
    'exec "$@"' \
    > /usr/local/bin/openhost-entrypoint.sh && \
    chmod +x /usr/local/bin/openhost-entrypoint.sh

USER sculptor
ENTRYPOINT ["/usr/local/bin/openhost-entrypoint.sh"]
# Ensure the persistent dirs exist, then run the backend from the built venv.
# The venv lives at the uv *workspace* root (/app/.venv), not /app/sculptor.
# No --no-serve-static: the backend serves the web UI built above (resolved via
# the 'sculptor' package's editable install at /app/sculptor/frontend/dist).
CMD ["sh", "-c", "mkdir -p \"$SCULPTOR_FOLDER\" \"$CLAUDE_CONFIG_DIR\" && exec /app/.venv/bin/python -m sculptor.cli.main --no-open-browser /workspace"]
