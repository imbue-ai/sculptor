# Dockerfile for running the Sculptor backend as an OpenHost app.
#
# This is the headless, browser-less counterpart to
# container/recipes/docker/Dockerfile: it serves the bundled web UI itself
# (no Electron shell) and persists all state into the OpenHost app data dir.
#
# OpenHost builds this with the repo root as the build context, so the COPY
# lines below reference the existing recipe scripts at their real paths.
#
# The backend binary is auto-downloaded from the release server on first start
# (see download-sculptor-backend.sh). Pin a version by setting SCULPTOR_VERSION;
# the default is the latest release.

FROM ubuntu:24.04

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git \
        curl \
        ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Install Claude CLI (Claude Code) to a system-wide path so it is accessible
# when running as a non-root user via --user.
RUN export HOME=/tmp && \
    curl -fsSL https://claude.ai/install.sh | bash && \
    mv /tmp/.local/bin/claude /usr/local/bin/claude

# Ubuntu 24.04 ships with an 'ubuntu' user (UID 1000, GID 1000). Rename it
# to 'sculptor' and set up its home directory so the container feels like a
# normal Linux environment.
RUN usermod -l sculptor -d /home/sculptor -m ubuntu && \
    groupmod -n sculptor ubuntu && \
    mkdir -p /home/sculptor && chown sculptor:sculptor /home/sculptor

# Writable data and home directories. chmod 777 because the runtime UID (from
# rootless podman / --user) won't match the image UID (1000). Standard practice
# for containers that support arbitrary UIDs.
RUN mkdir -p /data && chmod 777 /data && \
    chmod 777 /home/sculptor

# /opt/sculptor holds the backend and sculpt CLI binaries, populated at runtime
# by the download script. Make it writable so the download can land there.
RUN mkdir -p /opt/sculptor && chmod 777 /opt/sculptor

# Make /etc/passwd world-writable so the entrypoint can remap the sculptor
# user's UID when started with an arbitrary UID/GID at runtime (rootless podman).
RUN chmod 666 /etc/passwd

ENV HOME=/home/sculptor

# Expose the backend on all interfaces so the OpenHost router can proxy to it.
ENV SCULPTOR_BIND_HOST=0.0.0.0
# Port the backend listens on. Keep in sync with `port` in openhost.toml.
ENV SCULPTOR_API_PORT=5050

# Persist all Sculptor state (database, workspaces, downloaded agent binaries,
# user config) into the OpenHost persistent, backed-up app data dir. The app is
# named "sculptor" in openhost.toml, so OpenHost mounts it at this path.
ENV SCULPTOR_FOLDER=/data/app_data/sculptor
# Persist Claude Code's OAuth credentials (written by the in-app authenticate
# flow, which runs `claude auth login`) so you don't re-authenticate on rebuild.
ENV CLAUDE_CONFIG_DIR=/data/app_data/sculptor/claude

# Add both binary directories to PATH so sculptor_backend and sculpt are
# available as commands without full paths.
ENV PATH="/opt/sculptor/sculptor_backend:/opt/sculptor/sculpt:${PATH}"

WORKDIR /workspace

# Initialize a minimal git repo so Sculptor has a project to open on first run.
RUN git -c user.email="sculptor@container" -c user.name="Sculptor" \
    init && \
    git -c user.email="sculptor@container" -c user.name="Sculptor" \
    commit --allow-empty -m "Initial commit" && \
    chmod -R 777 /workspace

# Git safe.directory must live in a config file — git ignores safe.directory
# from env vars and -c flags as a security measure. Write it to the system
# config so it applies regardless of which UID ends up running.
RUN git config --system safe.directory '*'

# Reuse the existing container recipe scripts (COPY paths are relative to the
# repo-root build context).
COPY container/recipes/docker/download-sculptor-backend.sh /usr/local/bin/download-sculptor-backend.sh
RUN chmod +x /usr/local/bin/download-sculptor-backend.sh

# Entrypoint: remaps the sculptor UID/GID at runtime, then downloads the backend
# binary if it isn't already present, then execs the command.
COPY container/recipes/docker/entrypoint.sh /usr/local/bin/container-entrypoint.sh
RUN chmod +x /usr/local/bin/container-entrypoint.sh

USER sculptor
ENTRYPOINT ["/usr/local/bin/container-entrypoint.sh"]
# Ensure the persistent state + Claude config dirs exist (they live on the
# runtime-mounted volume), then launch the backend. No --no-serve-static: the
# backend serves the bundled web UI itself since there is no Electron shell.
CMD ["sh", "-c", "mkdir -p \"$SCULPTOR_FOLDER\" \"$CLAUDE_CONFIG_DIR\" && exec sculptor_backend --no-open-browser"]
