#!/usr/bin/env python3
"""Drive an iOS Simulator + idb to QA the Sculptor mobile web UI headlessly.

A single CLI an agent can drive step by step. It wraps `xcrun simctl` (boot a
notched device, open URLs, screenshot) and `idb` (taps/swipes the simulator CLI
can't do), and it can launch + manage the local frontend server itself, parsing
the port out of its output (no hardcoded port).

Subcommands:
  setup               Ensure an iOS runtime + idb, then create/boot the device.
  detect              List running Sculptor servers + which one `open` would use.
  serve               Resolve a server URL (attach to a running one, else launch).
  open                Resolve a server URL as above, then open it in MobileSafari.
  screenshot          Capture the current screen to a numbered PNG.
  tap X Y             Tap a point (or --frac FX FY for a screenshot fraction).
  swipe X1 Y1 X2 Y2   Swipe between two points (--frac to use fractions).
  describe            Dump the foreground app's accessibility tree (JSON).
  add-to-home-screen  Drive the Add-to-Home-Screen flow (screenshot per step).
  launch-icon X Y     Tap the home-screen clip to launch the app standalone.
  remove-home-screen  Guidance for removing the clip (iOS caches launch config).
  teardown            Shut the simulator down and stop the managed server.
  status              Print the current device/server state.

URL resolution for `serve`/`open`: --url/--port > auto-detect a running Sculptor
dev server > launch --command (override with --launch). No port is hardcoded.

State (UDID, points, server pid/url, screenshot counter) is persisted to
<screenshots-dir>/.iphone-sim-state.json so subcommands chain without
re-passing the UDID. Stdlib only; shells out to xcrun/idb/just.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
from devices import DEFAULT_PRESET, PRESETS, get_preset  # noqa: E402

STATE_FILENAME = ".iphone-sim-state.json"
SERVER_LOG = "frontend-server.log"
DEFAULT_COMMAND = "just frontend-custom"
DEFAULT_IDB_VENV = Path.home() / ".cache" / "sculptor-iphone-qa" / "idb-venv"
# Homebrew bin dirs so the idb python client can find `idb_companion`.
BREW_BINS = ["/opt/homebrew/bin", "/usr/local/bin"]

# Port-parsing patterns, in priority order. The first two are frontend-specific
# (so they never match the backend URL the custom-command path also prints).
PORT_PATTERNS = [
    re.compile(r"SCULPTOR_FRONTEND_PORT=(\d+)"),
    re.compile(r"Local:\s+https?://[\d.]+:(\d+)"),
]


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def eprint(*a: object) -> None:
    print(*a, file=sys.stderr)


def repo_root() -> Path:
    """Repo root: ask git, falling back to the skill's known location."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(out.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        # scripts/ -> auto-qa-iphone -> skills -> .claude -> <repo root>
        return Path(__file__).resolve().parents[4]


def default_screenshots_dir() -> Path:
    """Prefer the Sculptor workspace attachments dir; else a repo-local dir."""
    env = os.environ.get("SCULPTOR_IPHONE_QA_DIR")
    if env:
        return Path(env).expanduser()
    attachments = repo_root().parent / "attachments"
    if attachments.is_dir():
        return attachments / "iphone-screenshots"
    return repo_root() / ".iphone-qa" / "screenshots"


def child_env() -> Dict[str, str]:
    env = dict(os.environ)
    extra = [p for p in BREW_BINS if Path(p).is_dir()]
    if extra:
        env["PATH"] = os.pathsep.join(extra + [env.get("PATH", "")])
    return env


def run(cmd: Sequence[str], check: bool = True, quiet: bool = False) -> subprocess.CompletedProcess:
    if not quiet:
        eprint("$", " ".join(cmd))
    return subprocess.run(cmd, capture_output=True, text=True, check=check, env=child_env())


def simctl(*args: str, check: bool = True, quiet: bool = False) -> subprocess.CompletedProcess:
    return run(["xcrun", "simctl", *args], check=check, quiet=quiet)


def have(binary: str) -> bool:
    return shutil.which(binary, path=os.pathsep.join(BREW_BINS + [os.environ.get("PATH", "")])) is not None


def port_open(port: int, host: str = "127.0.0.1", timeout: float = 1.0) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex((host, port)) == 0


def http_ready(url: str, timeout: float = 2.0) -> bool:
    """True if the URL serves an HTTP response (any status counts as 'up')."""
    try:
        urllib.request.urlopen(url, timeout=timeout)
        return True
    except urllib.error.HTTPError:
        return True  # responded with 4xx/5xx — still a live server
    except Exception:
        return False  # connection refused / timeout — not serving


# --------------------------------------------------------------------------- #
# state
# --------------------------------------------------------------------------- #
class State:
    def __init__(self, screenshots_dir: Path):
        self.dir = screenshots_dir
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / STATE_FILENAME
        self.data: Dict[str, object] = {}
        if self.path.exists():
            self.data = json.loads(self.path.read_text())

    def save(self) -> None:
        self.path.write_text(json.dumps(self.data, indent=2))

    def get(self, key: str, default: object = None) -> object:
        return self.data.get(key, default)

    def require_udid(self) -> str:
        udid = self.data.get("udid")
        if not udid:
            raise SystemExit("No device set up. Run `iphone_sim.py setup` first.")
        return str(udid)

    def points(self) -> Sequence[int]:
        pts = self.data.get("points")
        if not pts:
            raise SystemExit("No device points in state. Run `setup` first.")
        return pts  # type: ignore[return-value]

    def next_counter(self) -> int:
        n = int(self.data.get("counter", 0)) + 1
        self.data["counter"] = n
        self.save()
        return n


def state_for(args: argparse.Namespace) -> State:
    return State(Path(args.screenshots_dir).expanduser())


# --------------------------------------------------------------------------- #
# idb
# --------------------------------------------------------------------------- #
def idb_bin(state: State) -> Optional[str]:
    venv = state.data.get("idb_venv")
    if not venv:
        return None
    candidate = Path(str(venv)) / "bin" / "idb"
    return str(candidate) if candidate.exists() else None


def idb(state: State, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    binary = idb_bin(state)
    if not binary:
        raise SystemExit(
            "idb is not installed. Re-run `iphone_sim.py setup` (it creates the "
            "idb venv and installs idb_companion)."
        )
    return run([binary, *args], check=check)


# --------------------------------------------------------------------------- #
# screenshots
# --------------------------------------------------------------------------- #
def take_screenshot(state: State, label: str) -> Path:
    udid = state.require_udid()
    n = state.next_counter()
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", label).strip("_") or "shot"
    out = state.dir / f"{n:04d}_{safe}.png"
    simctl("io", udid, "screenshot", str(out), quiet=True)
    return out


def report_shot(path: Path) -> None:
    print(f"screenshot: {path}")
    print(f'<img src="{path}" alt="iphone-sim {path.name}">')


# --------------------------------------------------------------------------- #
# server lifecycle
# --------------------------------------------------------------------------- #
def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def server_alive(state: State) -> bool:
    server = state.data.get("server")
    if not isinstance(server, dict):
        return False
    pid = server.get("pid")
    return bool(pid) and _pid_alive(int(pid))


def stop_server(state: State) -> None:
    server = state.data.get("server")
    if not isinstance(server, dict):
        return
    pgid = server.get("pgid")
    pid = server.get("pid")
    killed = False
    if pgid:
        try:
            os.killpg(int(pgid), signal.SIGTERM)
            killed = True
        except OSError:
            pass
    if not killed and pid and _pid_alive(int(pid)):
        try:
            os.kill(int(pid), signal.SIGTERM)
        except OSError:
            pass
    eprint(f"Stopped frontend server (pid={pid}).")
    state.data["server"] = None
    state.save()


def parse_port(line: str) -> Optional[int]:
    for pat in PORT_PATTERNS:
        m = pat.search(line)
        if m:
            return int(m.group(1))
    return None


def ensure_server(state: State, command: str, timeout: float) -> str:
    """Launch `command` detached, parse its frontend URL, and keep it alive."""
    if server_alive(state):
        server = state.data["server"]  # type: ignore[index]
        url = server.get("url")
        if url:
            eprint(f"Reusing running server: {url}")
            return str(url)

    log_path = state.dir / SERVER_LOG
    log = open(log_path, "w")
    eprint(f"$ ({command})  [detached, logging to {log_path}]")
    proc = subprocess.Popen(
        command,
        shell=True,
        cwd=str(repo_root()),
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,  # own process group so teardown can kill the tree
        env=child_env(),
    )
    try:
        pgid = os.getpgid(proc.pid)
    except OSError:
        pgid = proc.pid
    state.data["server"] = {"pid": proc.pid, "pgid": pgid, "command": command, "url": None}
    state.save()

    # Tail the log until the frontend URL appears.
    deadline = time.time() + timeout
    port: Optional[int] = None
    while time.time() < deadline:
        if proc.poll() is not None:
            tail = "\n".join(log_path.read_text().splitlines()[-25:])
            raise SystemExit(f"Server command exited early.\n--- {SERVER_LOG} (tail) ---\n{tail}")
        for line in log_path.read_text().splitlines():
            port = parse_port(line)
            if port:
                break
        if port:
            break
        time.sleep(1)
    if not port:
        tail = "\n".join(log_path.read_text().splitlines()[-25:])
        raise SystemExit(
            f"Timed out after {timeout:.0f}s waiting for the frontend port.\n"
            f"--- {SERVER_LOG} (tail) ---\n{tail}"
        )

    # Confirm the parsed port actually SERVES — not just that we saw it logged.
    # (electron-forge, for one, prints a port its renderer may never bind, and a
    # blind TCP check can also pass on a stale listener.) Fail loudly otherwise.
    url = f"http://127.0.0.1:{port}"
    ready = False
    while time.time() < deadline:
        if proc.poll() is not None:
            tail = "\n".join(log_path.read_text().splitlines()[-25:])
            raise SystemExit(f"Server command exited early.\n--- {SERVER_LOG} (tail) ---\n{tail}")
        if http_ready(url):
            ready = True
            break
        time.sleep(1)
    if not ready:
        tail = "\n".join(log_path.read_text().splitlines()[-25:])
        raise SystemExit(
            f"Parsed port {port} from the server output, but {url} never served a "
            f"response within {timeout:.0f}s.\n"
            "If a Sculptor instance is already running, attach to it instead of "
            "launching a new one:  open --port <port>  (or --url <url>).\n"
            f"--- {SERVER_LOG} (tail) ---\n{tail}"
        )

    state.data["server"]["url"] = url  # type: ignore[index]
    state.save()
    eprint(f"Frontend server ready: {url} (pid={proc.pid})")
    return url


# --------------------------------------------------------------------------- #
# auto-detect an already-running Sculptor server
# --------------------------------------------------------------------------- #
SPA_MARKERS = ("<title>Sculptor", "apple-mobile-web-app-title", 'id="root"')


def _listening_ports() -> Dict[int, str]:
    """Map of listening TCP port -> owning process command (via lsof)."""
    try:
        out = run(["lsof", "-nP", "-iTCP", "-sTCP:LISTEN"], check=False, quiet=True).stdout
    except FileNotFoundError:
        return {}
    ports: Dict[int, str] = {}
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 2:
            continue
        # The NAME column is an addr:port token (e.g. 127.0.0.1:5173, *:8080,
        # [::1]:5173), possibly followed by a (LISTEN) state token — scan for it.
        for tok in parts[1:]:
            m = re.match(r"^[\w.*\[\]:%-]+:(\d+)$", tok)
            if m:
                ports.setdefault(int(m.group(1)), parts[0])
                break
    return ports


def _fetch(url: str, timeout: float = 1.5):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.read(16384).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:
        return None, ""


def find_running_server():
    """Probe listening ports for a Sculptor SPA. Returns (port, kind) or None.

    kind is 'dev' (a vite dev server — what you want for branch QA) or 'app'
    (a packaged/production build). Dev servers are preferred.
    """
    ports = _listening_ports()
    interesting = re.compile(r"(node|vite|sculptor|electron|python|uv)", re.I)
    candidates = [p for p, c in sorted(ports.items()) if interesting.search(c)]
    for extra in (5173, 5174):
        if extra not in candidates:
            candidates.append(extra)
    fallback = None
    for port in candidates:
        status, body = _fetch(f"http://127.0.0.1:{port}")
        if status is None or not any(mk in body for mk in SPA_MARKERS):
            continue
        is_dev = "/@vite/client" in body or "/src/" in body or "/@react-refresh" in body
        if is_dev:
            return (port, "dev")
        fallback = fallback or (port, "app")
    return fallback


def resolve_url(state: State, args: argparse.Namespace) -> str:
    if getattr(args, "url", None):
        return str(args.url)
    if getattr(args, "port", None):
        return f"http://127.0.0.1:{args.port}"
    if not getattr(args, "launch", False):
        found = find_running_server()
        if found:
            port, kind = found
            eprint(f"Attached to a running Sculptor server on port {port} ({kind} build).")
            if kind == "app":
                eprint("  NOTE: that looks like a packaged/production build, not a vite dev "
                       "server — start your branch's dev server to QA your changes, or pass "
                       "--port/--url explicitly.")
            return f"http://127.0.0.1:{port}"
        eprint("No running Sculptor server detected; launching the fallback command "
               f"({args.command!r}).")
        eprint("  (Launching from inside a Sculptor agent can be flaky — if it fails, start "
               "your dev server yourself and re-run, or pass --port/--url.)")
    return ensure_server(state, args.command, args.server_timeout)


# --------------------------------------------------------------------------- #
# subcommands
# --------------------------------------------------------------------------- #
def first_ios_runtime(download: bool) -> str:
    out = simctl("list", "runtimes", "--json", quiet=True).stdout
    runtimes = json.loads(out).get("runtimes", [])
    ios = [r for r in runtimes if r.get("isAvailable") and "iOS" in r.get("name", "")]
    if ios:
        # Prefer the newest by version string.
        ios.sort(key=lambda r: r.get("version", ""), reverse=True)
        return str(ios[0]["identifier"])
    if download:
        eprint("No iOS runtime found — downloading (this is large and slow)...")
        run(["xcodebuild", "-downloadPlatform", "iOS"])
        return first_ios_runtime(download=False)
    raise SystemExit(
        "No iOS simulator runtime is installed.\n"
        "Install one (≈9 GB, slow) with:\n"
        "    xcodebuild -downloadPlatform iOS\n"
        "or re-run setup with --download-runtime to do it automatically."
    )


def ensure_idb(venv: Path) -> None:
    idb_exe = venv / "bin" / "idb"
    if not idb_exe.exists():
        eprint(f"Creating idb venv at {venv} ...")
        venv.parent.mkdir(parents=True, exist_ok=True)
        run([sys.executable, "-m", "venv", str(venv)])
        run([str(venv / "bin" / "pip"), "install", "--quiet", "--upgrade", "pip"])
        run([str(venv / "bin" / "pip"), "install", "--quiet", "fb-idb"])
    if not have("idb_companion"):
        if have("brew"):
            eprint("Installing idb_companion via Homebrew ...")
            run(["brew", "install", "idb-companion"], check=False)
        if not have("idb_companion"):
            eprint(
                "WARNING: idb_companion is not on PATH. Taps/swipes will not work "
                "until you `brew install idb-companion`. Screenshots and openurl "
                "still work via simctl."
            )


def find_device(name: str) -> Optional[dict]:
    out = simctl("list", "devices", "--json", quiet=True).stdout
    for _runtime, devices in json.loads(out).get("devices", {}).items():
        for dev in devices:
            if dev.get("name") == name:
                return dev
    return None


def cmd_setup(args: argparse.Namespace) -> None:
    preset = get_preset(args.device)
    state = state_for(args)

    runtime = first_ios_runtime(download=args.download_runtime)

    venv = Path(args.idb_venv).expanduser()
    ensure_idb(venv)

    device_name = f"SculptorQA-{preset.key}"
    dev = find_device(device_name)
    if dev is None:
        eprint(f"Creating device {device_name!r} ({preset.sim_name}) on {runtime} ...")
        udid = simctl("create", device_name, preset.sim_name, runtime).stdout.strip()
    else:
        udid = dev["udid"]
        eprint(f"Reusing device {device_name!r} ({udid}), state={dev.get('state')}.")

    if not (dev and dev.get("state") == "Booted"):
        simctl("boot", udid, check=False)
    eprint("Waiting for boot to complete ...")
    simctl("bootstatus", udid, "-b", quiet=True)

    state.data.update(
        {
            "device": preset.key,
            "sim_name": preset.sim_name,
            "device_name": device_name,
            "udid": udid,
            "points": list(preset.points),
            "notched": preset.notched,
            "idb_venv": str(venv),
            "runtime": runtime,
        }
    )
    state.save()

    if idb_bin(state):
        eprint("Connecting idb ...")
        idb(state, "connect", udid, check=False)

    print(f"Device ready: {device_name}")
    print(f"  udid:   {udid}")
    print(f"  points: {preset.points[0]}x{preset.points[1]} (notched={preset.notched})")
    print(f"  state:  {state.path}")
    print("Open the Simulator app to watch: open -a Simulator")


def cmd_serve(args: argparse.Namespace) -> None:
    state = state_for(args)
    url = ensure_server(state, args.command, args.server_timeout)
    print(f"server: {url}")


def cmd_open(args: argparse.Namespace) -> None:
    state = state_for(args)
    udid = state.require_udid()
    url = resolve_url(state, args)
    eprint(f"Opening {url} in MobileSafari ...")
    simctl("openurl", udid, url)
    time.sleep(args.settle)
    report_shot(take_screenshot(state, "open"))


def cmd_screenshot(args: argparse.Namespace) -> None:
    state = state_for(args)
    report_shot(take_screenshot(state, args.label))


def _xy(args: argparse.Namespace, state: State, fx: float, fy: float) -> List[int]:
    if args.frac:
        w, h = state.points()
        return [round(fx * w), round(fy * h)]
    return [round(fx), round(fy)]


def cmd_tap(args: argparse.Namespace) -> None:
    state = state_for(args)
    udid = state.require_udid()
    x, y = _xy(args, state, args.x, args.y)
    idb(state, "ui", "tap", "--udid", udid, str(x), str(y))
    time.sleep(args.settle)
    report_shot(take_screenshot(state, f"tap_{x}_{y}"))


def cmd_swipe(args: argparse.Namespace) -> None:
    state = state_for(args)
    udid = state.require_udid()
    x1, y1 = _xy(args, state, args.x1, args.y1)
    x2, y2 = _xy(args, state, args.x2, args.y2)
    idb(state, "ui", "swipe", "--udid", udid, "--duration", str(args.duration),
        str(x1), str(y1), str(x2), str(y2))
    time.sleep(args.settle)
    report_shot(take_screenshot(state, f"swipe_{x1}_{y1}_{x2}_{y2}"))


def cmd_describe(args: argparse.Namespace) -> None:
    state = state_for(args)
    udid = state.require_udid()
    out = idb(state, "ui", "describe-all", "--udid", udid).stdout
    print(out)


def cmd_add_to_home_screen(args: argparse.Namespace) -> None:
    state = state_for(args)
    udid = state.require_udid()
    preset = get_preset(str(state.get("device", DEFAULT_PRESET)))
    if not preset.ahs:
        raise SystemExit(
            f"No Add-to-Home-Screen reference coordinates for {preset.key!r}.\n"
            "SpringBoard/the share sheet aren't in the accessibility tree, so drive "
            "it manually: `screenshot`, find each target as a fraction, then "
            "`tap --frac FX FY` step by step (Share -> swipe up -> Add to Home Screen "
            "-> Add)."
        )

    def tap(name: str, label: str) -> None:
        x, y = preset.ahs[name]
        idb(state, "ui", "tap", "--udid", udid, str(x), str(y))
        time.sleep(args.settle)
        report_shot(take_screenshot(state, f"ahs_{label}"))

    def swipe(a: str, b: str, label: str) -> None:
        x1, y1 = preset.ahs[a]
        x2, y2 = preset.ahs[b]
        idb(state, "ui", "swipe", "--udid", udid, "--duration", "0.6",
            str(x1), str(y1), str(x2), str(y2))
        time.sleep(args.settle)
        report_shot(take_screenshot(state, f"ahs_{label}"))

    eprint("AHS coordinates are empirical — VERIFY each screenshot before trusting the next tap.")
    tap("share_button", "1_share_sheet")
    swipe("sheet_swipe_from", "sheet_swipe_to", "2_sheet_scrolled")
    tap("add_to_home_screen", "3_ahs_dialog")
    tap("add_confirm", "4_added")
    print(
        "\nDone. If a screenshot doesn't match the expected step, the coordinates "
        "drifted — re-derive with `tap --frac`. Next: `launch-icon` to open the "
        "clip standalone and see the real status bar / safe areas."
    )


def cmd_launch_icon(args: argparse.Namespace) -> None:
    state = state_for(args)
    udid = state.require_udid()
    preset = get_preset(str(state.get("device", DEFAULT_PRESET)))
    if args.x is None or args.y is None:
        if "launch_icon" not in preset.ahs:
            raise SystemExit("Pass the icon coords: `launch-icon X Y` (or --frac FX FY).")
        x, y = preset.ahs["launch_icon"]
    else:
        x, y = _xy(args, state, args.x, args.y)
    idb(state, "ui", "tap", "--udid", udid, str(x), str(y))
    time.sleep(args.settle + 1.0)  # give the standalone app a moment to launch
    report_shot(take_screenshot(state, "standalone"))


def cmd_remove_home_screen(args: argparse.Namespace) -> None:
    print(
        "iOS caches the launch config (meta tags, theme-color, icon) at add-time, "
        "so after changing index.html's <head> you must REMOVE and RE-ADD the clip "
        "— reloading isn't enough.\n\n"
        "Removal isn't reliably scriptable (long-press isn't in the a11y tree). Do it "
        "by hand in the Simulator: long-press the icon -> 'Remove App' -> 'Delete from "
        "Home Screen', then run `add-to-home-screen` again."
    )


def cmd_teardown(args: argparse.Namespace) -> None:
    state = state_for(args)
    stop_server(state)
    udid = state.data.get("udid")
    if udid:
        simctl("shutdown", str(udid), check=False)
        if args.delete:
            simctl("delete", str(udid), check=False)
            for k in ("udid", "device_name", "points", "runtime"):
                state.data.pop(k, None)
            state.save()
            print("Device deleted.")
        else:
            print("Simulator shut down (device kept for next time).")
    print("Screenshots are kept in", state.dir)


def cmd_detect(args: argparse.Namespace) -> None:
    """List running Sculptor servers and show which one `open` would attach to."""
    ports = _listening_ports()
    interesting = re.compile(r"(node|vite|sculptor|electron|python|uv)", re.I)
    candidates = [p for p, c in sorted(ports.items()) if interesting.search(c)]
    for extra in (5173, 5174):
        if extra not in candidates:
            candidates.append(extra)
    hits = []
    for port in candidates:
        status, body = _fetch(f"http://127.0.0.1:{port}")
        if status is None or not any(mk in body for mk in SPA_MARKERS):
            continue
        kind = "dev" if ("/@vite/client" in body or "/src/" in body or "/@react-refresh" in body) else "app"
        hits.append((port, kind, ports.get(port, "?")))
    if not hits:
        print("No running Sculptor server found. Start your dev server, or use "
              "`open --port <port>` / `open --launch`.")
        return
    chosen = find_running_server()
    print("Running Sculptor servers:")
    for port, kind, cmd in hits:
        mark = "   <- open would use this" if chosen and chosen[0] == port else ""
        print(f"  http://127.0.0.1:{port}   [{kind}]  ({cmd}){mark}")
    if chosen:
        note = "" if chosen[1] == "dev" else "  (NOTE: a packaged/production build — pass --port for your dev server)"
        print(f"\n`open` (no flags) will attach to: http://127.0.0.1:{chosen[0]}{note}")


def cmd_status(args: argparse.Namespace) -> None:
    state = state_for(args)
    udid = state.data.get("udid")
    booted = False
    if udid:
        dev = find_device(str(state.data.get("device_name", "")))
        booted = bool(dev and dev.get("state") == "Booted")
    print(json.dumps({
        "screenshots_dir": str(state.dir),
        "device": state.data.get("device"),
        "udid": udid,
        "booted": booted,
        "idb": bool(idb_bin(state)),
        "server_running": server_alive(state),
        "server": state.data.get("server"),
        "counter": state.data.get("counter", 0),
    }, indent=2))


# --------------------------------------------------------------------------- #
# argument parsing
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="iphone_sim.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    # Shared options, inherited by every subcommand so they can be passed AFTER
    # the subcommand (e.g. `iphone_sim.py screenshot --label foo`).
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--screenshots-dir", default=str(default_screenshots_dir()),
                        help="Where screenshots + state live (default: workspace attachments).")
    common.add_argument("--settle", type=float, default=1.0,
                        help="Seconds to wait after an action before screenshotting.")

    s = sub.add_parser("setup", parents=[common], help="Ensure runtime + idb, create/boot the device.")
    s.add_argument("--device", default=DEFAULT_PRESET, choices=sorted(PRESETS),
                   help="Device preset to create/boot.")
    s.add_argument("--idb-venv", default=str(DEFAULT_IDB_VENV))
    s.add_argument("--download-runtime", action="store_true",
                   help="Auto-download an iOS runtime if none is installed (~9 GB).")
    s.set_defaults(func=cmd_setup)

    def add_server_opts(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--command", default=DEFAULT_COMMAND,
                        help=f"Fallback server command to launch if none is running (default: {DEFAULT_COMMAND!r}).")
        sp.add_argument("--port", type=int, help="Attach to an already-running server on this port.")
        sp.add_argument("--url", help="Attach to an already-running server at this full URL.")
        sp.add_argument("--launch", action="store_true",
                        help="Skip auto-detect and launch --command directly.")
        sp.add_argument("--server-timeout", type=float, default=180.0,
                        help="Seconds to wait for the launched server to print its port.")

    s = sub.add_parser("serve", parents=[common], help="Launch the frontend server and parse its URL.")
    add_server_opts(s)
    s.set_defaults(func=cmd_serve)

    s = sub.add_parser("open", parents=[common], help="Open a URL in MobileSafari (launches server if needed).")
    add_server_opts(s)
    s.set_defaults(func=cmd_open)

    s = sub.add_parser("screenshot", parents=[common], help="Capture the current screen.")
    s.add_argument("--label", default="shot")
    s.set_defaults(func=cmd_screenshot)

    s = sub.add_parser("tap", parents=[common], help="Tap a point (--frac to use a screenshot fraction).")
    s.add_argument("x", type=float)
    s.add_argument("y", type=float)
    s.add_argument("--frac", action="store_true", help="Treat X/Y as fractions (0..1) of the screen.")
    s.set_defaults(func=cmd_tap)

    s = sub.add_parser("swipe", parents=[common], help="Swipe between two points.")
    for n in ("x1", "y1", "x2", "y2"):
        s.add_argument(n, type=float)
    s.add_argument("--frac", action="store_true", help="Treat coords as fractions (0..1).")
    s.add_argument("--duration", type=float, default=0.6)
    s.set_defaults(func=cmd_swipe)

    s = sub.add_parser("describe", parents=[common], help="Dump the foreground app's accessibility tree.")
    s.set_defaults(func=cmd_describe)

    s = sub.add_parser("add-to-home-screen", parents=[common], help="Drive the Add-to-Home-Screen flow.")
    s.set_defaults(func=cmd_add_to_home_screen)

    s = sub.add_parser("launch-icon", parents=[common], help="Tap the home-screen clip to launch standalone.")
    s.add_argument("x", type=float, nargs="?")
    s.add_argument("y", type=float, nargs="?")
    s.add_argument("--frac", action="store_true")
    s.set_defaults(func=cmd_launch_icon)

    s = sub.add_parser("remove-home-screen", parents=[common], help="How to remove the clip (caching gotcha).")
    s.set_defaults(func=cmd_remove_home_screen)

    s = sub.add_parser("teardown", parents=[common], help="Shut the simulator down and stop the server.")
    s.add_argument("--delete", action="store_true", help="Also delete the simulator device.")
    s.set_defaults(func=cmd_teardown)

    s = sub.add_parser("detect", parents=[common], help="List running Sculptor servers + which one `open` would use.")
    s.set_defaults(func=cmd_detect)

    s = sub.add_parser("status", parents=[common], help="Print current device/server state.")
    s.set_defaults(func=cmd_status)

    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except subprocess.CalledProcessError as exc:
        eprint(f"\nCommand failed ({exc.returncode}): {' '.join(exc.cmd)}")
        if exc.stdout:
            eprint(exc.stdout)
        if exc.stderr:
            eprint(exc.stderr)
        return 1
    except SystemExit as exc:
        if isinstance(exc.code, str):
            eprint(exc.code)
            return 1
        return exc.code or 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
