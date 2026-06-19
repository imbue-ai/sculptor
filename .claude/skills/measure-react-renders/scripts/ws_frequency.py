"""Analyze WebSocket message frequency and payload patterns during agent streaming.

Starts a fresh Sculptor backend, creates a streaming agent task, then captures
WebSocket frames via websocket-client to measure:

  - How often taskViewsByTaskId updates arrive
  - How often taskUpdateByTaskId updates arrive (chat detail)
  - Which fields in CodingAgentTaskView actually change between updates
  - Gaps between updates (min/max/mean/p95)
  - Total message count and bytes

Run with the project venv:
    uv run --project sculptor python .claude/skills/measure-react-renders/scripts/ws_frequency.py \
        --repo-dir "$(pwd)"
"""

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from collections import defaultdict
from pathlib import Path


def free_port():
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def api(port, method, path, body=None):
    data = json.dumps(body).encode() if body else (b"" if method == "POST" else None)
    headers = {"Content-Type": "application/json"} if body else {}
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/v1{path}",
        data=data,
        method=method,
        headers=headers,
    )
    try:
        return json.loads(urllib.request.urlopen(req).read())
    except Exception:
        return None


def wait_for_backend(port, timeout=90):
    for _ in range(timeout):
        try:
            resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/v1/health")
            if b"version" in resp.read():
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def start_backend(repo_dir, port, data_dir):
    env = {k: v for k, v in os.environ.items()
           if k not in ("SESSION_TOKEN", "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")}
    env["SCULPTOR_API_PORT"] = str(port)
    env["SCULPTOR_FOLDER"] = data_dir
    log = open(Path(data_dir) / "backend.log", "w")
    return subprocess.Popen(
        ["uv", "run", "--project", str(Path(repo_dir) / "sculptor"),
         "python", "-m", "sculptor.cli.main", "--no-open-browser", repo_dir],
        env=env,
        stdout=log,
        stderr=log,
        preexec_fn=os.setsid,
    )


def setup_instance(port):
    """Complete onboarding and create a streaming agent task."""
    api(port, "POST", "/config/email", {
        "userEmail": "test@example.com", "fullName": "Test", "didOptInToMarketing": False
    })
    api(port, "POST", "/config/complete")
    projects = api(port, "GET", "/projects")
    project_id = projects[0]["objectId"]
    # Use a prompt that generates a longer response to get more streaming data
    task = api(port, "POST", f"/projects/{project_id}/tasks", {
        "prompt": "Write a Python function that computes the first 20 Fibonacci numbers and returns them as a list. Include docstring and type hints.",
        "interface": "API",
        "model": "CLAUDE-4-SONNET",
        "mode": "IN_PLACE",
    })
    return task["workspaceId"], task["id"]


def analyze_ws_traffic(port, workspace_id, task_id, capture_seconds=60):
    """Capture and analyze WebSocket traffic during agent streaming.

    Uses websocket-client to connect directly to the backend WS endpoint,
    bypassing Playwright browser interception complexities.
    """
    import threading
    import websocket as ws_client

    messages: list = []  # list of (timestamp_ms, parsed_data, raw_bytes)
    connected = threading.Event()

    def on_message(wsapp, message):
        ts = time.time() * 1000
        try:
            data = json.loads(message)
            messages.append((ts, data, len(message)))
        except Exception:
            pass

    def on_error(wsapp, error):
        print(f"  [WS] Error: {error}", flush=True)

    def on_open(wsapp):
        print(f"  [WS] Connected to ws://127.0.0.1:{port}/api/v1/stream/ws", flush=True)
        connected.set()

    def on_close(wsapp, code, msg):
        print(f"  [WS] Closed: {code}", flush=True)

    wsapp = ws_client.WebSocketApp(
        f"ws://127.0.0.1:{port}/api/v1/stream/ws",
        on_message=on_message,
        on_error=on_error,
        on_open=on_open,
        on_close=on_close,
    )

    t = threading.Thread(target=wsapp.run_forever)
    t.daemon = True
    t.start()

    if not connected.wait(timeout=10):
        print("  [WS] Timed out waiting for connection", flush=True)
        return messages

    print(f"Capturing WS traffic for {capture_seconds}s...", flush=True)
    time.sleep(capture_seconds)
    wsapp.close()
    t.join(timeout=2)

    return messages


def _deep_diff_fields(prev: dict, curr: dict, path: str = "") -> list[str]:
    """Return list of dotted field paths where values changed."""
    changed = []
    all_keys = set(prev.keys()) | set(curr.keys())
    for k in all_keys:
        full_path = f"{path}.{k}" if path else k
        prev_val = prev.get(k)
        curr_val = curr.get(k)
        if prev_val != curr_val:
            if isinstance(prev_val, dict) and isinstance(curr_val, dict):
                changed.extend(_deep_diff_fields(prev_val, curr_val, full_path))
            else:
                changed.append(full_path)
    return changed


def print_report(messages):
    if not messages:
        print("No WebSocket messages captured.")
        return

    print(f"\n{'='*70}")
    print("  WebSocket Message Frequency Analysis")
    print(f"{'='*70}")
    print(f"Total messages captured: {len(messages)}")
    print(f"Total payload bytes: {sum(b for _, _, b in messages):,}")

    if len(messages) < 2:
        print("Not enough messages to compute timing statistics.")
        return

    # Time span
    first_ts = messages[0][0]
    last_ts = messages[-1][0]
    duration_s = (last_ts - first_ts) / 1000
    print(f"Capture duration: {duration_s:.1f}s")
    print(f"Overall rate: {len(messages)/duration_s:.1f} msg/sec")

    # Categorize by update type
    task_view_msgs = [(ts, d) for ts, d, _ in messages if d.get("taskViewsByTaskId")]
    task_detail_msgs = [(ts, d) for ts, d, _ in messages if d.get("taskUpdateByTaskId")]
    other_msgs = [(ts, d) for ts, d, _ in messages
                  if not d.get("taskViewsByTaskId") and not d.get("taskUpdateByTaskId")]

    print(f"\n--- Message Types ---")
    print(f"  taskViewsByTaskId updates: {len(task_view_msgs)}")
    print(f"  taskUpdateByTaskId updates: {len(task_detail_msgs)}")
    print(f"  Other (user, repo, branch): {len(other_msgs)}")

    # Timing analysis for task view updates
    if len(task_view_msgs) > 1:
        gaps_ms = [task_view_msgs[i][0] - task_view_msgs[i-1][0]
                   for i in range(1, len(task_view_msgs))]
        sorted_gaps = sorted(gaps_ms)
        n = len(sorted_gaps)
        print(f"\n--- taskViewsByTaskId Update Intervals ---")
        print(f"  Count: {len(task_view_msgs)}")
        print(f"  Rate: {len(task_view_msgs)/duration_s:.2f}/sec")
        print(f"  Min gap: {min(gaps_ms):.0f}ms")
        print(f"  Max gap: {max(gaps_ms):.0f}ms")
        print(f"  Mean gap: {sum(gaps_ms)/len(gaps_ms):.0f}ms")
        print(f"  P50 gap: {sorted_gaps[n//2]:.0f}ms")
        print(f"  P95 gap: {sorted_gaps[int(n*0.95)]:.0f}ms")

    # Timing analysis for task detail updates
    if len(task_detail_msgs) > 1:
        gaps_ms = [task_detail_msgs[i][0] - task_detail_msgs[i-1][0]
                   for i in range(1, len(task_detail_msgs))]
        sorted_gaps = sorted(gaps_ms)
        n = len(sorted_gaps)
        print(f"\n--- taskUpdateByTaskId Update Intervals ---")
        print(f"  Count: {len(task_detail_msgs)}")
        print(f"  Rate: {len(task_detail_msgs)/duration_s:.2f}/sec")
        print(f"  Min gap: {min(gaps_ms):.0f}ms")
        print(f"  Max gap: {max(gaps_ms):.0f}ms")
        print(f"  Mean gap: {sum(gaps_ms)/len(gaps_ms):.0f}ms")
        print(f"  P50 gap: {sorted_gaps[n//2]:.0f}ms")
        print(f"  P95 gap: {sorted_gaps[int(n*0.95)]:.0f}ms")

    # Field change analysis for taskViewsByTaskId
    if len(task_view_msgs) > 1:
        field_change_counts: dict[str, int] = defaultdict(int)
        tasks_unchanged_count = 0
        tasks_changed_count = 0
        per_task_prev: dict[str, dict] = {}

        for _, data in task_view_msgs:
            for task_id, task_data in data["taskViewsByTaskId"].items():
                if task_id in per_task_prev:
                    changed = _deep_diff_fields(per_task_prev[task_id], task_data)
                    if changed:
                        tasks_changed_count += 1
                        for field in changed:
                            field_change_counts[field] += 1
                    else:
                        tasks_unchanged_count += 1
                per_task_prev[task_id] = task_data

        print(f"\n--- CodingAgentTaskView Field Changes ---")
        print(f"  Updates with actual changes: {tasks_changed_count}")
        print(f"  Updates with NO changes (redundant): {tasks_unchanged_count}")
        if tasks_changed_count + tasks_unchanged_count > 0:
            redundancy = tasks_unchanged_count / (tasks_changed_count + tasks_unchanged_count) * 100
            print(f"  Redundancy rate: {redundancy:.1f}%")

        if field_change_counts:
            print(f"\n  Fields changed (sorted by frequency):")
            for field, count in sorted(field_change_counts.items(), key=lambda x: -x[1]):
                print(f"    {field:<40} {count:>5}x")
        else:
            print("  (No field changes detected in task views)")

    # Payload size analysis
    payload_sizes = [b for _, _, b in messages]
    print(f"\n--- Payload Size Analysis ---")
    print(f"  Min: {min(payload_sizes):,} bytes")
    print(f"  Max: {max(payload_sizes):,} bytes")
    print(f"  Mean: {int(sum(payload_sizes)/len(payload_sizes)):,} bytes")
    print(f"  Total: {sum(payload_sizes):,} bytes")

    print(f"\n{'='*70}")


def main():
    parser = argparse.ArgumentParser(description="Analyze WebSocket message frequency during agent streaming")
    parser.add_argument("--repo-dir", default=".", help="Path to sculptor repo root")
    parser.add_argument("--capture-seconds", type=int, default=60,
                        help="Seconds to capture WebSocket traffic (default: 60)")
    parser.add_argument("--port", type=int, default=None,
                        help="Reuse existing backend on this port (skips backend startup)")
    parser.add_argument("--workspace-id", help="Workspace ID (required if --port is set)")
    parser.add_argument("--task-id", help="Task ID (required if --port is set)")
    args = parser.parse_args()

    if args.port:
        # Use existing backend
        if not args.workspace_id or not args.task_id:
            print("--workspace-id and --task-id are required when using --port")
            sys.exit(1)
        messages = analyze_ws_traffic(args.port, args.workspace_id, args.task_id, args.capture_seconds)
        print_report(messages)
        return

    # Start a fresh backend
    port = free_port()
    data_dir = tempfile.mkdtemp(prefix="perf_ws_")
    repo_dir = str(Path(args.repo_dir).resolve())

    proc = start_backend(repo_dir, port, data_dir)
    try:
        print(f"Waiting for backend (port {port})...")
        if not wait_for_backend(port):
            print("ERROR: Backend failed to start")
            sys.exit(1)

        ws_id, task_id = setup_instance(port)
        print(f"Created task {task_id} in workspace {ws_id}")
        print(f"Waiting 5s for task to start streaming...")
        time.sleep(5)

        messages = analyze_ws_traffic(port, ws_id, task_id, args.capture_seconds)
        print_report(messages)

    finally:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        proc.wait()
        subprocess.run(["rm", "-rf", data_dir], check=False)


if __name__ == "__main__":
    main()
