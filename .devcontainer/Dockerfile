# Offload sandbox image for running tests on Modal.
# With checkpointing enabled, this image is cached via git notes and only
# rebuilt when build_inputs (Dockerfile, pyproject.toml, etc.) change.
# This Dockerfile only stages the system tools and the source tree; the
# heavy dependency install runs as offload's `sandbox_init_cmd`, which
# invokes `scripts/finalize-base-image.sh` against the COPYed source.
# The resulting image is snapshotted as the checkpoint base. Subsequent
# runs apply a thin diff plus `post_patch_cmd` on top.

FROM ubuntu:24.04

RUN apt-get update && apt-get install -y --no-install-recommends \
        git curl ca-certificates build-essential pkg-config libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install just
RUN curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to /usr/local/bin

# Node via nvm (needed for frontend unit tests and integration test frontend build)
ENV NODE_VERSION="20.13.1"
RUN curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash && \
    bash -c "source /root/.nvm/nvm.sh && nvm install $NODE_VERSION"

# offload >= 0.9.1 invokes `offload apply-diff` inside the sandbox to apply
# thin-diff patches (replacing the previous `git apply --3way`), so the
# binary must be on PATH here. Install via rustup minimal, then strip the
# toolchain to keep the cached image small.
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
        | sh -s -- -y --default-toolchain stable --profile minimal \
    && . "$HOME/.cargo/env" \
    && cargo install offload@0.9.5 \
    && mv /root/.cargo/bin/offload /usr/local/bin/offload \
    && rustup self uninstall -y \
    && rm -rf /root/.cargo /root/.rustup

# Critical for Modal snapshots — without this, some files vanish after snapshot restore.
ENV UV_LINK_MODE=copy
ENV NVM_DIR="/root/.nvm"

WORKDIR /app

# Copy source. Dependency install happens in sandbox_init_cmd
# (scripts/finalize-base-image.sh) so the heavy work lives in a real
# bash file rather than a Dockerfile RUN string.
COPY . /app
