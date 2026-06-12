"""Compare React component render counts between two Sculptor frontend builds.

Injects a React DevTools hook via Playwright to count fiber commits per
component during a scenario.

Two-tree mode (starts two backends, prints a side-by-side comparison):
    uv run --project sculptor python .claude/skills/measure-react-renders/scripts/perf_compare.py \
        --baseline-dir /tmp/sculptor_baseline \
        --current-dir "$(pwd)" \
        --scenario path/to/scenario.py

Single-tree iteration loop (one build + one backend per run):
    # once, save a baseline measurement:
    ... perf_compare.py --current-dir "$(pwd)" --scenario s.py --save-json /tmp/base.json
    # then after each change, compare against it:
    ... perf_compare.py --current-dir "$(pwd)" --scenario s.py --against-json /tmp/base.json
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
// Resolve a component name through memo/forwardRef wrappers: the fiber's
// `type` for those is an object whose displayName is usually unset — the
// real function lives at `.type` (memo) or `.render` (forwardRef).
function componentName(type) {
    if (!type) return null;
    if (typeof type === 'function') return type.displayName || type.name || null;
    if (typeof type === 'object') {
        return type.displayName || componentName(type.type) || componentName(type.render) || null;
    }
    return null;
}
hook.onCommitFiberRoot = function(id, root) {
    if (!root || !root.current) return;
    window.__COMMIT_COUNT__++;
    function walk(fiber) {
        if (!fiber) return;
        var flags = fiber.flags !== undefined ? fiber.flags : (fiber.effectTag || 0);
        if (flags & PERFORMED_WORK) {
            var name = componentName(fiber.type);
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


def start_preview_server(repo_dir, frontend_port, api_port, data_dir):
    """Serve the freshly built dist via `vite preview` (proxying API/WS to the
    backend, same as the dev server).

    Measuring against the backend's own static route is wrong: it prefers the
    packaged `sculptor/frontend-dist` copy when one exists, which is minified —
    component names would not survive into the measured page.
    """
    frontend_dir = Path(repo_dir) / "sculptor" / "frontend"
    env = {
        **os.environ,
        "SCULPTOR_API_PORT": str(api_port),
        "SCULPTOR_FRONTEND_PORT": str(frontend_port),
    }
    log = open(Path(data_dir) / "preview.log", "w")
    return subprocess.Popen(
        ["npx", "vite", "preview", "--port", str(frontend_port), "--strictPort", "--host", "127.0.0.1"],
        cwd=frontend_dir,
        env=env,
        stdout=log,
        stderr=log,
        preexec_fn=os.setsid,
    )


def wait_for_preview(port, timeout=60):
    for _ in range(timeout):
        try:
            resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/")
            if resp.status == 200:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


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


def print_single(result, target_components, description):
    """Single-column table for one measurement (no baseline)."""
    w = 60
    print()
    print("=" * w)
    print(f"  {description}")
    print("=" * w)
    print(f"\n{'Component':<45} {'Renders':>10}")
    print("-" * w)
    print(f"{'Total fiber commits':<45} {result['commits']:>10}")
    print("-" * w)
    for name in target_components:
        count = result["counts"].get(name, 0)
        if count > 0:
            print(f"{name:<45} {count:>10}")
    others = sorted(
        ((name, count) for name, count in result["counts"].items() if name not in target_components and count >= 10),
        key=lambda item: -item[1],
    )
    if others:
        print("-" * w)
        print("Other components rendering >= 10 times:")
        for name, count in others[:15]:
            print(f"  {name:<43} {count:>10}")
    print("=" * w)


def load_scenario(path):
    spec = importlib.util.spec_from_file_location("scenario", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_measurement(repo_dir, scenario, label):
    """Start one backend + preview server for `repo_dir`, run the scenario, and tear down."""
    api_port = free_port()
    frontend_port = free_port()
    data_dir = tempfile.mkdtemp(prefix=f"perf_{label}_")
    backend_proc = start_backend(repo_dir, api_port, data_dir)
    preview_proc = start_preview_server(repo_dir, frontend_port, api_port, data_dir)
    try:
        print(f"Waiting for {label} backend (port {api_port})...")
        if not wait_for_backend(api_port):
            print(f"ERROR: {label} backend failed to start")
            sys.exit(1)
        if not wait_for_preview(frontend_port):
            print(f"ERROR: {label} preview server failed to start")
            sys.exit(1)
        workspace_id, task_id = setup_instance(api_port)
        print(f"Measuring {label} (frontend port {frontend_port})...")
        return measure_renders(frontend_port, workspace_id, task_id, scenario, label)
    finally:
        for proc in (preview_proc, backend_proc):
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                proc.wait()
            except ProcessLookupError:
                pass
        subprocess.run(["rm", "-rf", data_dir], check=False)


def main():
    parser = argparse.ArgumentParser(description="Compare render performance between two frontend builds")
    parser.add_argument(
        "--baseline-dir",
        default=None,
        help="Path to baseline repo checkout (omit for single-tree mode)",
    )
    parser.add_argument("--current-dir", required=True, help="Path to current repo checkout")
    parser.add_argument("--scenario", required=True, help="Path to scenario Python file")
    parser.add_argument("--skip-build", action="store_true", help="Skip frontend builds (use existing dist/)")
    parser.add_argument("--save-json", default=None, help="Write the current measurement to this JSON file")
    parser.add_argument(
        "--against-json",
        default=None,
        help="Compare against a measurement previously saved with --save-json (instead of --baseline-dir)",
    )
    args = parser.parse_args()

    if args.baseline_dir and args.against_json:
        parser.error("--baseline-dir and --against-json are mutually exclusive")

    scenario = load_scenario(args.scenario)

    if not args.skip_build:
        if args.baseline_dir:
            print("Building baseline frontend...")
            build_frontend(args.baseline_dir)
        print("Building current frontend...")
        build_frontend(args.current_dir)

    if args.baseline_dir:
        baseline = run_measurement(args.baseline_dir, scenario, "baseline")
    elif args.against_json:
        with open(args.against_json) as f:
            baseline = json.load(f)
    else:
        baseline = None

    current = run_measurement(args.current_dir, scenario, "current")

    if args.save_json:
        with open(args.save_json, "w") as f:
            json.dump(current, f, indent=2)
        print(f"Saved measurement to {args.save_json}")

    if baseline is None:
        print_single(current, scenario.TARGET_COMPONENTS, scenario.DESCRIPTION)
    else:
        print_comparison(baseline, current, scenario.TARGET_COMPONENTS, scenario.DESCRIPTION)


if __name__ == "__main__":
    main()
