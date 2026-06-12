# check=skip=SecretsUsedInArgOrEnv
# Dev Dockerfile for running the Sculptor backend in a container.
#
# This image provides the runtime environment (Python, git, uv).
# The source code is bind-mounted at /app at runtime — no rebuild needed
# when code changes.
#
# Build:
#   docker build -f container/container-backend-dev.dockerfile -t sculptor-backend-dev .
#
# Run:
#   docker run --rm -it \
#     --user "$(id -u):$(id -g)" \
#     -p 8080:8080 \
#     -v "$(pwd)":/app \
#     -e SCULPTOR_BIND_HOST=0.0.0.0 \
#     -e SCULPTOR_API_PORT=8080 \
#     sculptor-backend-dev

FROM python:3.12-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git \
        curl \
        ca-certificates \
        gcc \
        python3-dev \
        libc6-dev && \
    rm -rf /var/lib/apt/lists/*

# Install uv (fast Python package manager) to a system-wide path so it is
# accessible when running as a non-root user via --user.
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    mv /root/.local/bin/uv /usr/local/bin/uv && \
    mv /root/.local/bin/uvx /usr/local/bin/uvx 2>/dev/null || true

# Install Node.js (needed for Claude CLI) and Claude CLI globally
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/* && \
    npm install -g @anthropic-ai/claude-code

# Create a real user so the container feels like a normal Linux environment.
# The entrypoint handles UID remapping when --user is passed at runtime.
RUN groupadd -g 1000 sculptor && \
    useradd -u 1000 -g sculptor -m -d /home/sculptor -s /bin/bash sculptor

# Writable data and home directories. These use chmod 777 because the runtime
# UID (from --user) won't match the image UID (1000). This is standard
# practice for containers that support arbitrary UIDs.
RUN mkdir -p /data && chmod 777 /data && \
    chmod 777 /home/sculptor

# Make /etc/passwd world-writable so the entrypoint can remap the sculptor
# user's UID when --user is passed with an arbitrary GID at runtime.
RUN chmod 666 /etc/passwd

ENV HOME=/home/sculptor

ENV SCULPTOR_BIND_HOST=0.0.0.0
ENV SCULPTOR_API_PORT=8080

# Use a container-local venv so we don't clobber the host's .venv
ENV UV_PROJECT_ENVIRONMENT=/opt/sculptor-venv

# Venv directory owned by sculptor
RUN mkdir -p /opt/sculptor-venv && chmod 777 /opt/sculptor-venv

WORKDIR /app

# Create a sample project so there's something to open immediately.
RUN mkdir -p /workspace/sample-project && \
    echo 'print("Hello from Sculptor container!")' > /workspace/sample-project/main.py && \
    echo '# Sample Project\n\nA simple project for testing Sculptor in a container.' > /workspace/sample-project/README.md && \
    cd /workspace/sample-project && git init && \
    git add -A && \
    git -c user.email="dev@sculptor.dev" -c user.name="Sculptor Dev" \
    commit -m "Initial commit" && \
    chmod -R 777 /workspace

# Git safe.directory must be in a config file — git ignores safe.directory
# from env vars (GIT_CONFIG_*) and -c flags as a security measure.
# Write to the system config so it applies regardless of which user runs.
RUN git config --system safe.directory '*'

# Entrypoint wrapper: remaps the sculptor user's UID/GID when --user is
# passed at runtime, so files have proper ownership everywhere.
COPY container/recipes/docker/entrypoint.sh /usr/local/bin/container-entrypoint.sh
RUN chmod +x /usr/local/bin/container-entrypoint.sh

USER sculptor
ENTRYPOINT ["/usr/local/bin/container-entrypoint.sh"]

# Default command: run the backend from the mounted source, auto-opening the sample project
CMD ["sh", "-c", "cd sculptor && uv run python -m sculptor.cli.main --no-open-browser --no-serve-static /workspace/sample-project"]
