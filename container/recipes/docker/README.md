# Running the Sculptor Backend in a Docker Container

Run the Sculptor backend inside a Docker container while keeping the Electron desktop app on your local machine. Useful for isolation, reproducibility, or running on a different architecture.

## How It Works

The Electron app spawns a user-provided shell command (the "custom backend command"), reads the backend URL from its stdout, and connects to it. This recipe provides that command.

The launcher script (`run-backend.py`):
1. Starts a Docker container with port forwarding
2. Prints `http://localhost:8080` to stdout (for Electron to discover)
3. `exec`s into `docker run` so SIGTERM from Electron propagates cleanly

The backend binary is either **bind-mounted** from your host or **auto-downloaded** inside the container on first start.

## Prerequisites

- Docker Desktop installed and running
- Sculptor desktop app installed
- Python 3.10+ on your host (for the launcher script)

## Quick Start

### 1. Clone this gist

```bash
git clone <gist-url> sculptor-docker
cd sculptor-docker
```

### 2. Configure Sculptor

Open Sculptor > Settings > Experimental and set **Custom Backend Command** to:

```
/full/path/to/sculptor-docker/run-backend.py
```

Restart Sculptor. The launcher automatically builds the Docker image on first start (and rebuilds it when the Dockerfile changes). The container will auto-download the latest backend binary on first start.

## Configuration

All configuration is via environment variables. Set them in your shell profile or prefix them on the command line.

### Backend Binary Source

| Variable | Purpose | Default |
|---|---|---|
| `SCULPTOR_BINARIES_DIR` | Host directory containing `sculptor_backend/` and `sculpt/` subdirs (bind-mounted read-only) | Not set |
| `SCULPTOR_BACKEND_PATH` | Legacy: path to the `sculptor_backend` binary itself | Not set |
| `SCULPTOR_VERSION` | Version to auto-download if no binaries are provided (e.g., `0.17.0`) | `latest` |

If `SCULPTOR_BINARIES_DIR` or `SCULPTOR_BACKEND_PATH` is set, the directory is bind-mounted into the container at `/opt/sculptor`. Otherwise, the container downloads the specified version on first start.

### Container Settings

| Variable | Purpose | Default |
|---|---|---|
| `HOST_PORT` | Port on your local machine | `8080` |
| `CONTAINER_PORT` | Port inside the container | `5050` |
| `CONTAINER_NAME` | Docker container name | `sculptor-backend` |
| `HOST_DATA_VOLUME` | Named Docker volume for persistent state | `sculptor-data` |
| `CONTAINER_IMAGE` | Docker image to use | `sculptor-backend` |
| `CLAUDE_CONFIG_DIR` | Path to Claude Code config on host | `~/.claude` |

### Credentials

| Variable | Purpose |
|---|---|
| `SESSION_TOKEN` | Set automatically by Electron |
| `ANTHROPIC_API_KEY` | Forwarded to the container if set |

## File Overview

| File | Purpose |
|---|---|
| `Dockerfile` | Container image with git, Claude CLI, and runtime setup |
| `entrypoint.sh` | Remaps UID for `--user` support; downloads binaries if needed |
| `run-backend.py` | Builds the image, builds `docker run` arguments, prints URL, `exec`s Docker |
| `download-sculptor-backend.sh` | Downloads a Sculptor AppImage and extracts backend/sculpt binaries |

## How the Container Works

### User Identity

The container creates a `sculptor` user (UID 1000). When started with `--user UID:GID` (which the launcher does automatically), the entrypoint remaps the `sculptor` user's UID in `/etc/passwd` to match your host user. This means:
- `whoami` returns `sculptor` (not "I have no name!")
- Git, SSH, and other tools work normally
- Files created on mounted volumes are owned by your host user

### Git Configuration

- **`safe.directory=*`** is set via `git config --system` in the image (git ignores this setting from environment variables as a security measure)
- **`user.name`/`user.email`** are injected by the launcher via `GIT_CONFIG_*` environment variables, propagated from your host's global git config

### State Persistence

- `sculptor-data` Docker volume stores the database, workspace clones, and task sync data
- `~/.claude` is mounted from the host for Claude Code auth and config persistence

### Binary Auto-Download

When no binaries are bind-mounted, the entrypoint runs `download-sculptor-backend.sh` which:
1. Fetches the Sculptor AppImage from the release server
2. Extracts `sculptor_backend` and `sculpt` CLI binaries
3. Caches them in `/opt/sculptor` with a version marker (skips download on subsequent starts)

## Troubleshooting

### Connection refused
- Verify Docker is running: `docker ps`
- Check if another process is using port 8080: `lsof -i :8080`
- Try a different port: `HOST_PORT=9090 /path/to/run-backend.sh`

### "dubious ownership" git errors
- The image sets `safe.directory=*` via `git config --system`. If you're using a custom image, add `RUN git config --system safe.directory '*'` to your Dockerfile.

### Stale container
- The launcher removes stale containers automatically. If it doesn't: `docker rm -f sculptor-backend`

### Backend binary not found (auto-download)
- Check your architecture: only `x86_64` and `aarch64` Linux are supported
- Check network access to `imbue-sculptor-releases.s3.us-west-2.amazonaws.com`
- Pin a known version: `SCULPTOR_VERSION=0.17.0`

### Root-owned files
- The launcher passes `--user "$(id -u):$(id -g)"` automatically. If running manually, add this flag to your `docker run` command.

### Slow startup / timeout
- First start downloads binaries (~100MB) which may take a minute
- Increase the readiness timeout in Settings > Experimental (default: 60 seconds, try 120)
- Subsequent starts use cached binaries and are fast

### Claude Code auth lost between runs
- Ensure `~/.claude` exists on your host. The launcher mounts it automatically.
