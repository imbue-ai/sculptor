"""Compare React component render counts between two Sculptor frontend builds.

Starts two backends (baseline and current), injects a React DevTools hook
via Playwright to count fiber commits per component during a scenario,
and prints a side-by-side comparison.

Run with the project venv:
    uv run --project sculptor python .claude/skills/measure-react-renders/scripts/perf_compare.py \
        --baseline-dir /tmp/sculptor_baseline \
        --current-dir "$(pwd)" \
        --scenario path/to/scenario.py
"""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

from playwright.sync_api import sync_playwright

DEVTOOLS_HOOK_SCRIPT = """
window.__REACT_DEVTOOLS_GLOBAL_HOOK__ = {
    renderers: new Map(),
    supportsFiber: true,
    inject: function(renderer) {
        var id = this.renderers.size + 1;
        this.renderers.set(id, renderer);
        return id;
    },
    onScheduleFiberRoot: function() {},
    onCommitFiberRoot: function() {},
    onCommitFiberUnmount: function() {},
    isDisabled: false,
    checkDCE: function() {},
};
"""

COUNTER_SCRIPT = """
window.__RENDER_COUNTS__ = {};
window.__COMMIT_COUNT__ = 0;
var hook = window.__REACT_DEVTOOLS_GLOBAL_HOOK__;
// PerformedWork flag (React 17-19): set on a fiber only when its component
// actually rendered during the commit. Without this check the walk counts
// every MOUNTED fiber per commit, which can't distinguish a component that
// re-rendered from one that bailed out (e.g. via React.memo or unchanged
// atom subscriptions).
var PERFORMED_WORK = 1;
hook.onCommitFiberRoot = function(id, root) {
    if (!root || !root.current) return;
    window.__COMMIT_COUNT__++;
    function walk(fiber) {
        if (!fiber) return;
        var flags = fiber.flags !== undefined ? fiber.flags : (fiber.effectTag || 0);
        if (flags & PERFORMED_WORK) {
            var name = fiber.type?.displayName || fiber.type?.name;
            if (name && typeof name === 'string' && name.length < 100) {
                window.__RENDER_COUNTS__[name] =
                    (window.__RENDER_COUNTS__[name] || 0) + 1;
            }
        }
        walk(fiber.child);
        walk(fiber.sibling);
    }
    walk(root.current);
};
"""


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
    env = {k: v for k, v in os.environ.items() if k not in ("SESSION_TOKEN", "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")}
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
    """Complete onboarding and create a task. Returns (workspace_id, task_id)."""
    api(port, "POST", "/config/email", {"userEmail": "test@example.com", "fullName": "Test", "didOptInToMarketing": False})
    api(port, "POST", "/config/complete")
    projects = api(port, "GET", "/projects")
    project_id = projects[0]["objectId"]
    task = api(port, "POST", f"/projects/{project_id}/tasks", {
        "prompt": "Say hello",
        "interface": "API",
        "model": "CLAUDE-4-SONNET",
        "mode": "IN_PLACE",
    })
    return task["workspaceId"], task["id"]


def measure_renders(port, workspace_id, task_id, scenario, label):
    base_url = f"http://127.0.0.1:{port}"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1400, "height": 900})
        ctx.add_init_script(DEVTOOLS_HOOK_SCRIPT)
        ctx.add_cookies([{
            "name": "x-session-token", "value": "",
            "domain": "127.0.0.1", "path": "/",
            "httpOnly": True, "sameSite": "Strict",
        }])
        page = ctx.new_page()

        scenario.setup(page, base_url, workspace_id, task_id)

        # Poll for React renderer registration — on slower machines React may
        # finish hydrating slightly after networkidle + setup sleep.
        renderers = 0
        for _attempt in range(10):
            renderers = page.evaluate(
                "window.__REACT_DEVTOOLS_GLOBAL_HOOK__?.renderers?.size ?? 0"
            )
            if renderers > 0:
                break
            time.sleep(0.5)

        if renderers == 0:
            print(
                f"[{label}] WARNING: No React renderers detected after 5s. "
                "Render counts will be zero. Check that the build uses React and "
                "that add_init_script ran before React loaded."
            )

        page.evaluate(COUNTER_SCRIPT)
        time.sleep(0.5)
        page.evaluate("window.__RENDER_COUNTS__ = {}; window.__COMMIT_COUNT__ = 0;")

        scenario.action(page)
        time.sleep(1)

        commits = page.evaluate("window.__COMMIT_COUNT__")
        counts = page.evaluate("window.__RENDER_COUNTS__")
        browser.close()
        return {"commits": commits, "counts": counts}


def build_frontend(repo_dir):
    """Build frontend with --minify false to preserve component names."""
    frontend_dir = Path(repo_dir) / "sculptor" / "frontend"
    subprocess.run(
        ["npx", "vite", "build", "--minify", "false", "-l", "error"],
        cwd=frontend_dir, check=True, capture_output=True,
    )


def print_comparison(baseline, current, target_components, description):
    w = 70
    print()
    print("=" * w)
    print(f"  {description}")
    print("=" * w)
    print(f"\n{'Component':<40} {'Baseline':>10} {'Current':>10} {'Change':>8}")
    print("-" * w)
    print(f"{'Total fiber commits':<40} {baseline['commits']:>10} {current['commits']:>10} {current['commits'] - baseline['commits']:>+8}")
    print("-" * w)

    for name in target_components:
        b = baseline["counts"].get(name, 0)
        c = current["counts"].get(name, 0)
        if b == 0 and c == 0:
            continue
        delta = c - b
        tag = ""
        if b > 0 and c == 0:
            tag = " FIXED"
        elif delta < 0:
            tag = f" ({delta / b:+.0%})" if b > 0 else ""
        elif delta > 0:
            tag = f" ({delta / b:+.0%})" if b > 0 else " NEW"
        print(f"{name:<40} {b:>10} {c:>10} {delta:>+8}{tag}")

    other = []
    for name in set(list(baseline["counts"].keys()) + list(current["counts"].keys())):
        if name in target_components:
            continue
        b = baseline["counts"].get(name, 0)
        c = current["counts"].get(name, 0)
        if abs(c - b) >= 10:
            other.append((name, b, c))

    if other:
        print("-" * w)
        print("Other notable changes:")
        for name, b, c in sorted(other, key=lambda x: -(x[1] - x[2]))[:10]:
            print(f"  {name:<38} {b:>10} {c:>10} {c - b:>+8}")

    print("=" * w)


def load_scenario(path):
    spec = importlib.util.spec_from_file_location("scenario", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    parser = argparse.ArgumentParser(description="Compare render performance between two frontend builds")
    parser.add_argument("--baseline-dir", required=True, help="Path to baseline repo checkout")
    parser.add_argument("--current-dir", required=True, help="Path to current repo checkout")
    parser.add_argument("--scenario", required=True, help="Path to scenario Python file")
    parser.add_argument("--skip-build", action="store_true", help="Skip frontend builds (use existing dist/)")
    args = parser.parse_args()

    scenario = load_scenario(args.scenario)

    if not args.skip_build:
        print("Building baseline frontend...")
        build_frontend(args.baseline_dir)
        print("Building current frontend...")
        build_frontend(args.current_dir)

    port_b = free_port()
    port_c = free_port()
    dir_b = tempfile.mkdtemp(prefix="perf_baseline_")
    dir_c = tempfile.mkdtemp(prefix="perf_current_")

    proc_b = start_backend(args.baseline_dir, port_b, dir_b)
    proc_c = start_backend(args.current_dir, port_c, dir_c)

    try:
        print(f"Waiting for baseline backend (port {port_b})...")
        if not wait_for_backend(port_b):
            print("ERROR: Baseline backend failed to start")
            sys.exit(1)

        print(f"Waiting for current backend (port {port_c})...")
        if not wait_for_backend(port_c):
            print("ERROR: Current backend failed to start")
            sys.exit(1)

        ws_b, task_b = setup_instance(port_b)
        ws_c, task_c = setup_instance(port_c)

        print("Measuring baseline...")
        baseline = measure_renders(port_b, ws_b, task_b, scenario, "baseline")

        print("Measuring current...")
        current = measure_renders(port_c, ws_c, task_c, scenario, "current")

        print_comparison(baseline, current, scenario.TARGET_COMPONENTS, scenario.DESCRIPTION)

    finally:
        os.killpg(os.getpgid(proc_b.pid), signal.SIGTERM)
        os.killpg(os.getpgid(proc_c.pid), signal.SIGTERM)
        proc_b.wait()
        proc_c.wait()
        subprocess.run(["rm", "-rf", dir_b, dir_c], check=False)


if __name__ == "__main__":
    main()
