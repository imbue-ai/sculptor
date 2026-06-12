#!/usr/bin/env python3
"""Launch the Sculptor backend inside a Docker container.

This script is intended to be used as the "Custom Backend Command" in
Sculptor's Settings > Experimental. Electron sets SESSION_TOKEN before
invoking this script.

Usage:
  Production (bind-mount binaries):
    1. Build the container image:
         docker build -f container/container-backend-dockerfile -t sculptor-backend .
    2. Set SCULPTOR_BINARIES_DIR to a directory containing sculptor_backend/ and sculpt/ subdirs:
         SCULPTOR_BINARIES_DIR=/path/to/binaries container/run-backend-in-container.sh
       Or use the legacy SCULPTOR_BACKEND_PATH (single binary):
         SCULPTOR_BACKEND_PATH=/path/to/sculptor_backend/sculptor_backend container/run-backend-in-container.sh

  Production (auto-download):
    1. Build the container image (same as above)
    2. Run without setting binaries — the container downloads them on first start:
         container/run-backend-in-container.sh
       Or pin a version:
         SCULPTOR_VERSION=0.17.0 container/run-backend-in-container.sh

  Dev mode (source mount):
    1. Build the dev container image:
         docker build -f container/container-backend-dev.dockerfile -t sculptor-backend-dev .
    2. Run with --dev flag:
         SCULPTOR_CUSTOM_BACKEND_CMD="container/run-backend-in-container.sh --dev" just frontend
       Or with the Vite dev server:
         container/run-backend-in-container.sh --dev
         SCULPTOR_CUSTOM_BACKEND_URL=http://localhost:8080 just frontend
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# -- Container paths (fixed inside the container) --
CONTAINER_DATA_PATH = "/data"
CONTAINER_SOURCE_PATH = "/app"
CONTAINER_BINARY_PATH = "/opt/sculptor"
CONTAINER_HOME = "/home/sculptor"


@dataclass
class ContainerConfig:
    """Configuration for running the Sculptor backend container."""

    dev_mode: bool
    host_port: str = "8080"
    container_port: str = "5050"
    container_name: str = "sculptor-backend"
    host_data_volume: str = "sculptor-data"
    container_image: str | None = None
    claude_config_dir: str = ""
    sculptor_source_dir: str | None = None
    sculptor_binaries_dir: str | None = None
    sculptor_version: str | None = None
    extra_env_keys: list[str] = field(default_factory=list)

    def resolved_image(self) -> str:
        if self.container_image:
            return self.container_image
        return "sculptor-backend-dev" if self.dev_mode else "sculptor-backend"


def parse_args() -> ContainerConfig:
    """Parse CLI arguments and environment overrides into a ContainerConfig."""
    parser = argparse.ArgumentParser(description="Run Sculptor backend in a container")
    parser.add_argument("--dev", action="store_true", help="Run in dev mode (mount source)")
    args = parser.parse_args()

    default_claude_dir = str(Path.home() / ".claude")

    # SCULPTOR_BINARIES_DIR: directory containing sculptor_backend/ and sculpt/ subdirs.
    # SCULPTOR_BACKEND_PATH: legacy — path to the sculptor_backend binary itself.
    #   If set, we derive the binaries dir by going up two levels (binary is at
    #   <dir>/sculptor_backend/sculptor_backend).
    binaries_dir = os.environ.get("SCULPTOR_BINARIES_DIR")
    if not binaries_dir:
        backend_path = os.environ.get("SCULPTOR_BACKEND_PATH")
        if backend_path:
            # Legacy: SCULPTOR_BACKEND_PATH=/foo/sculptor_backend/sculptor_backend
            # -> binaries_dir=/foo (parent of parent)
            binaries_dir = str(Path(backend_path).parent.parent)

    config = ContainerConfig(
        dev_mode=args.dev,
        host_port=os.environ.get("HOST_PORT", "8080"),
        container_port=os.environ.get("CONTAINER_PORT", "5050"),
        container_name=os.environ.get("CONTAINER_NAME", "sculptor-backend"),
        host_data_volume=os.environ.get("HOST_DATA_VOLUME", "sculptor-data"),
        container_image=os.environ.get("CONTAINER_IMAGE"),
        claude_config_dir=os.environ.get("CLAUDE_CONFIG_DIR", default_claude_dir),
        sculptor_source_dir=os.environ.get("SCULPTOR_SOURCE_DIR"),
        sculptor_binaries_dir=binaries_dir,
        sculptor_version=os.environ.get("SCULPTOR_VERSION"),
    )

    env_keys_raw = os.environ.get("_DEBUGSCULPTOR_ENV_KEYS", "")
    if env_keys_raw:
        config.extra_env_keys = [k.strip() for k in env_keys_raw.split(",") if k.strip()]

    return config


def _log(message: str) -> None:
    """Log to stderr so Electron can capture diagnostics."""
    print(f"[run-backend-in-container] {message}", file=sys.stderr)


def build_docker_args(config: ContainerConfig) -> list[str]:
    """Build the full list of arguments for `docker run`."""
    uid = os.getuid()
    gid = os.getgid()

    docker_args: list[str] = [
        "run",
        "--rm",
        "--name",
        config.container_name,
        "-p",
        f"{config.host_port}:{config.container_port}",
        "--user",
        f"{uid}:{gid}",
        "-e",
        "SCULPTOR_BIND_HOST=0.0.0.0",
        "-e",
        f"SCULPTOR_API_PORT={config.container_port}",
    ]

    # Data volume
    docker_args += [
        "-v",
        f"{config.host_data_volume}:{CONTAINER_DATA_PATH}",
        "-e",
        f"TASK_SYNC_DIR={CONTAINER_DATA_PATH}/task_sync",
        "-e",
        f"WORKSPACE_SYNC_DIR={CONTAINER_DATA_PATH}/workspace_sync",
    ]

    # Claude config mount (if directory exists on host)
    claude_dir = Path(config.claude_config_dir)
    if claude_dir.is_dir():
        docker_args += [
            "-v",
            f"{claude_dir}:{CONTAINER_HOME}/.claude",
        ]

    # Git config env vars
    docker_args += build_git_config_args()

    # Debug env vars
    docker_args += build_debug_env_args(config)

    # Passthrough env vars
    session_token = os.environ.get("SESSION_TOKEN", "")
    if session_token:
        docker_args += ["-e", f"SESSION_TOKEN={session_token}"]

    anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if anthropic_api_key:
        docker_args += ["-e", f"ANTHROPIC_API_KEY={anthropic_api_key}"]

    # Extra env vars from _DEBUGSCULPTOR_ENV_KEYS
    for key in config.extra_env_keys:
        value = os.environ.get(key, "")
        if value:
            docker_args += ["-e", f"{key}={value}"]

    # Mode-specific args
    if config.dev_mode:
        source_dir = config.sculptor_source_dir
        if not source_dir:
            # Auto-detect: this script lives in container/recipes/docker/, go up three levels
            source_dir = str(Path(__file__).resolve().parent.parent.parent.parent)

        docker_args += [
            "-v",
            f"{source_dir}:{CONTAINER_SOURCE_PATH}",
            config.resolved_image(),
        ]
    else:
        # Production mode
        docker_args += ["-e", f"SCULPTOR_FOLDER={CONTAINER_DATA_PATH}/sculptor"]

        binaries_dir = config.sculptor_binaries_dir
        if binaries_dir:
            # Bind-mount the binaries directory (contains sculptor_backend/ and sculpt/ subdirs)
            binaries_path = Path(binaries_dir)
            backend_binary = binaries_path / "sculptor_backend" / "sculptor_backend"
            if not backend_binary.is_file():
                _log(f"Error: sculptor_backend binary not found at {backend_binary}")
                _log("Expected layout: <dir>/sculptor_backend/sculptor_backend")
                _log("                 <dir>/sculpt/sculpt")
                sys.exit(1)

            _log(f"Mounting binaries from {binaries_dir}")
            docker_args += [
                "-v",
                f"{binaries_dir}:{CONTAINER_BINARY_PATH}:ro",
                config.resolved_image(),
            ]
        else:
            # No local binaries — the container will download them on first start.
            # Pass SCULPTOR_VERSION so the entrypoint knows what to fetch.
            version = config.sculptor_version or "latest"
            _log(f"No binaries dir provided; container will download version={version}")
            docker_args += ["-e", f"SCULPTOR_VERSION={version}"]
            docker_args.append(config.resolved_image())

    return docker_args


def build_git_config_args() -> list[str]:
    """Build Docker args to inject git config via GIT_CONFIG_* env vars.

    Note: safe.directory is set in the Dockerfile via `git config --system`
    because git ignores safe.directory from env vars as a security measure.
    """
    git_user_name = _get_host_git_config("user.name", "Sculptor User")
    git_user_email = _get_host_git_config("user.email", "sculptor@container")

    return [
        "-e",
        "GIT_CONFIG_COUNT=2",
        "-e",
        "GIT_CONFIG_KEY_0=user.name",
        "-e",
        f"GIT_CONFIG_VALUE_0={git_user_name}",
        "-e",
        "GIT_CONFIG_KEY_1=user.email",
        "-e",
        f"GIT_CONFIG_VALUE_1={git_user_email}",
    ]


def _get_host_git_config(key: str, default: str) -> str:
    """Read a git config value from the host, returning default on failure."""
    try:
        result = subprocess.run(
            ["git", "config", "--global", key],
            capture_output=True,
            text=True,
            timeout=5,
        )
        value = result.stdout.strip()
        if value:
            return value
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    return default


def build_debug_env_args(config: ContainerConfig) -> list[str]:
    """Build Docker args for _DEBUGSCULPTOR_* diagnostic env vars."""
    git_user_name = _get_host_git_config("user.name", "Sculptor User")
    git_user_email = _get_host_git_config("user.email", "sculptor@container")

    debug_vars = {
        "_DEBUGSCULPTOR_HOST_DATA_VOLUME": config.host_data_volume,
        "_DEBUGSCULPTOR_HOST_SOURCE_DIR": config.sculptor_source_dir or "",
        "_DEBUGSCULPTOR_HOST_PORT": config.host_port,
        "_DEBUGSCULPTOR_CONTAINER_IMAGE": config.resolved_image(),
        "_DEBUGSCULPTOR_CONTAINER_DATA_VOLUME_PATH": CONTAINER_DATA_PATH,
        "_DEBUGSCULPTOR_DEV_MODE": str(config.dev_mode).lower(),
        "_DEBUGSCULPTOR_HOST_GIT_USER_NAME": git_user_name,
        "_DEBUGSCULPTOR_HOST_GIT_USER_EMAIL": git_user_email,
        "_DEBUGSCULPTOR_ENV_KEYS": ",".join(config.extra_env_keys),
    }

    args: list[str] = []
    for key, value in debug_vars.items():
        args += ["-e", f"{key}={value}"]
    return args


def ensure_image(config: ContainerConfig) -> None:
    """Build the Docker image if the Dockerfile is co-located with this script.

    Uses Docker's layer cache so rebuilds are near-instant when nothing changed.
    Skips the build if no Dockerfile is found (e.g., using a pre-built image).
    """
    script_dir = Path(__file__).resolve().parent
    dockerfile = script_dir / "Dockerfile"
    if not dockerfile.is_file():
        return

    image = config.resolved_image()
    _log(f"Building image {image} (cached layers make this fast)")
    result = subprocess.run(
        ["docker", "build", "-t", image, str(script_dir)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        _log(f"Image build failed:\n{result.stderr}")
        sys.exit(1)
    _log("Image build complete")


def main() -> None:
    config = parse_args()

    _log(f"dev_mode={config.dev_mode} host_port={config.host_port} container_port={config.container_port}")
    _log(f"image={config.resolved_image()} host_data_volume={config.host_data_volume}")
    _log(f"claude_config_dir={config.claude_config_dir}")

    # Build the image if a Dockerfile is co-located with this script
    if not config.dev_mode:
        ensure_image(config)

    # Remove any stale container with the same name
    subprocess.run(
        ["docker", "rm", "-f", config.container_name],
        capture_output=True,
    )

    # Print the URL so Electron can discover the backend.
    # This MUST be printed before docker run starts blocking.
    print(f"http://localhost:{config.host_port}")
    sys.stdout.flush()

    docker_args = build_docker_args(config)

    _log(f"Running: docker {' '.join(docker_args)}")

    # exec replaces this process so SIGTERM from Electron goes directly to docker,
    # which forwards it to the container's PID 1.
    os.execvp("docker", ["docker", *docker_args])


if __name__ == "__main__":
    main()
