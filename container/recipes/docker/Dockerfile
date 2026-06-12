# Dockerfile for running the Sculptor backend in a container.
#
# This image provides the runtime environment (git, Claude CLI).
# The Sculptor backend binary itself is either:
#   - Bind-mounted from the host at runtime (via SCULPTOR_BINARIES_DIR), or
#   - Downloaded inside the container on first start (via SCULPTOR_VERSION)
#
# Build (from this directory):
#   docker build -t sculptor-backend .

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

# Writable data and home directories. These use chmod 777 because the runtime
# UID (from --user) won't match the image UID (1000). This is standard
# practice for containers that support arbitrary UIDs.
RUN mkdir -p /data && chmod 777 /data && \
    chmod 777 /home/sculptor

# /opt/sculptor holds the backend and sculpt CLI binaries. It may be:
#   - Bind-mounted read-only from the host, or
#   - Populated at runtime by the download script
# Make it writable so the download script can write to it when not bind-mounted.
RUN mkdir -p /opt/sculptor && chmod 777 /opt/sculptor

# Make /etc/passwd world-writable so the entrypoint can remap the sculptor
# user's UID when --user is passed with an arbitrary GID at runtime.
RUN chmod 666 /etc/passwd

ENV HOME=/home/sculptor

# Default bind address for container mode
ENV SCULPTOR_BIND_HOST=0.0.0.0

# Add both binary directories to PATH so sculptor_backend and sculpt are
# available as commands without full paths.
ENV PATH="/opt/sculptor/sculptor_backend:/opt/sculptor/sculpt:${PATH}"

WORKDIR /workspace

# Initialize a minimal git repo so Sculptor has a project to open.
RUN git -c user.email="sculptor@container" -c user.name="Sculptor" \
    init && \
    git -c user.email="sculptor@container" -c user.name="Sculptor" \
    commit --allow-empty -m "Initial commit" && \
    chmod -R 777 /workspace

# Git safe.directory must be in a config file — git ignores safe.directory
# from env vars (GIT_CONFIG_*) and -c flags as a security measure.
# Write to the system config so it applies regardless of which user runs.
RUN git config --system safe.directory '*'

# Copy the download script so the container can self-provision binaries
COPY download-sculptor-backend.sh /usr/local/bin/download-sculptor-backend.sh
RUN chmod +x /usr/local/bin/download-sculptor-backend.sh

# Entrypoint wrapper: remaps the sculptor user's UID/GID when --user is
# passed at runtime, downloads binaries if needed, then execs the command.
COPY entrypoint.sh /usr/local/bin/container-entrypoint.sh
RUN chmod +x /usr/local/bin/container-entrypoint.sh

USER sculptor
ENTRYPOINT ["/usr/local/bin/container-entrypoint.sh"]
CMD ["sculptor_backend", "--no-open-browser"]
