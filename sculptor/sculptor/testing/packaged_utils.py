"""Shared utilities for packaged test frontends (Electron and direct backend)."""

import os
import signal
import subprocess
from pathlib import Path

import httpx
from loguru import logger
from tenacity import retry
from tenacity import retry_if_exception_type
from tenacity import stop_after_delay
from tenacity import wait_fixed

from sculptor.testing.subprocess_utils import Forwarder


def register_project(backend_port: int, session_token: str, project_path: Path) -> None:
    """Register a project with the backend so the frontend skips the setup page."""
    url = f"http://127.0.0.1:{backend_port}/api/v1/projects/initialize"
    headers = {"x-session-token": session_token, "Content-Type": "application/json"}
    body = {"project_path": str(project_path)}
    logger.info("Registering project at {} via {}", project_path, url)
    response = httpx.post(url, json=body, headers=headers, timeout=10)
    response.raise_for_status()
    logger.info("Project registered successfully")


def _poll_backend_health(
    health_url: str,
    process: subprocess.Popen | None,
) -> None:
    logger.debug("Polling backend health at {}", health_url)
    if process is not None:
        ret = process.poll()
        if ret is not None:
            raise RuntimeError(f"Packaged process exited with code {ret} before becoming healthy")
    response = httpx.get(health_url, timeout=5)
    response.raise_for_status()


def wait_for_backend_health(
    backend_port: int,
    process: subprocess.Popen | None = None,
    timeout_seconds: int = 120,
) -> None:
    """Poll the backend health endpoint until it responds 200."""
    health_url = f"http://127.0.0.1:{backend_port}/api/v1/health"
    retry_poll = retry(
        stop=stop_after_delay(timeout_seconds),
        wait=wait_fixed(1),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )(_poll_backend_health)
    retry_poll(health_url, process)
    logger.info("Backend health check passed on port {}", backend_port)


def kill_process_tree(
    process: subprocess.Popen | None,
    forwarder: Forwarder | None,
    backend_port: int,
) -> None:
    """Terminate a packaged process and clean up any leftover listeners on the port.

    Sends SIGTERM, waits up to 10 seconds for graceful shutdown, then escalates
    to SIGKILL on the process group. Finishes with a safety-net port scan.

    TODO: When tests start spawning terminals (real Claude), the backend's child
    shells call os.setsid() and won't be killed by SIGTERM to the process alone.
    We'll need to walk the process tree or SIGTERM the backend's process group.
    """
    if forwarder is not None:
        forwarder.stop()

    if process is None:
        return

    try:
        process.send_signal(signal.SIGTERM)
    except (ProcessLookupError, OSError):
        pass

    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            pgid = os.getpgid(process.pid)
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, OSError):
            pass

    _kill_listeners_on_port(backend_port)

    try:
        if process.stdout:
            process.stdout.close()
    except Exception:
        pass

    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass


def _kill_listeners_on_port(port: int) -> None:
    """Safety net: find and kill any process still listening on the given port."""
    try:
        result = subprocess.run(
            ["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return
        for pid_str in result.stdout.strip().split("\n"):
            try:
                pid = int(pid_str.strip())
                pgid = os.getpgid(pid)
                logger.debug("Killing leftover process pid={} pgid={} on port {}", pid, pgid, port)
                os.killpg(pgid, signal.SIGKILL)
            except (ProcessLookupError, OSError, ValueError):
                pass
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
