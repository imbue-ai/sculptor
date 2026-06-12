# Dockerfile for building the sculptor_backend and sculpt CLI PyInstaller
# binaries targeting Linux.
#
# Build (from repo root):
#   docker build --platform linux/arm64 -f container/build-backend-linux.dockerfile -t sculptor-backend-builder .
#
# Extract the binaries:
#   docker create --name sb-extract sculptor-backend-builder
#   docker cp sb-extract:/output ./sculptor_binaries_linux_arm64
#   docker rm sb-extract
#
# Output layout:
#   sculptor_binaries_linux_arm64/
#     sculptor_backend/sculptor_backend   (+ _internal/)
#     sculpt/sculpt                       (+ _internal/)

FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        binutils \
        git \
        curl \
        ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

WORKDIR /build

# Copy the root workspace config and lockfile
COPY pyproject.toml uv.lock ./

# Copy workspace members
COPY imbue_core/ imbue_core/
COPY tools/ tools/
COPY sculptor/pyproject.toml sculptor/pyproject.toml
COPY sculptor/sculptor/ sculptor/sculptor/
COPY sculptor/builder/ sculptor/builder/

# Create placeholder directories expected by PyInstaller --add-data.
# The containerized backend runs with --no-serve-static so frontend-dist
# doesn't need real content.
RUN mkdir -p sculptor/frontend-dist && \
    echo '{}' > sculptor/frontend-dist/placeholder.json

# Copy the real plugin/container assets
COPY sculptor/sculptor-plugin/ sculptor/sculptor-plugin/
COPY sculptor/sculptor-workflow/ sculptor/sculptor-workflow/
COPY sculptor/sculptor-experimental/ sculptor/sculptor-experimental/

# Build the backend sidecar
WORKDIR /build/sculptor
RUN bash builder/build-sidecar.sh

# Build the sculpt CLI
WORKDIR /build/tools/sculpt
RUN bash /build/sculptor/builder/build-sculpt.sh

# Collect both binaries into a single output directory matching the layout
# expected by the container launcher (sculptor_backend/ and sculpt/ subdirs).
RUN mkdir -p /output && \
    cp -a /build/sculptor/dist/sculptor_backend /output/sculptor_backend && \
    cp -a /build/sculptor/dist/sculpt /output/sculpt
