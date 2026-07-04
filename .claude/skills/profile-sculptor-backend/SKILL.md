---
name: profile-sculptor-backend
description: |
  Capture Python-level diagnostics from a running Sculptor backend
  (`sculptor_backend`): instant thread dumps and viztracer/Perfetto traces with
  no special privileges, or py-spy CPU sampling / flamegraphs / native stacks
  against the installed signed app (one-time re-sign + sudo). Use when the
  backend is wedged, slow, pegging a CPU core, or deadlocked, or when you need a
  CPU profile or a live stack of `sculptor_backend`. Works both INSIDE Sculptor
  (where privileged steps are delegated to the user so the agent never kills its
  own backend) and from an EXTERNAL `claude`.
---

# Profile / debug a running Sculptor backend

This skill gets Python-level visibility into a live `sculptor_backend` process.
There are two routes; **prefer Route A** and fall back to Route B when you need
CPU sampling or when the running build predates the in-process debug endpoints.

| | Route A — `sculpt debug` (in-process) | Route B — py-spy (attach) |
|---|---|---|
| **Gives you** | Instant all-thread Python stacks; viztracer→Perfetto call-tree trace | Sampled CPU profile / flamegraph; live stacks; native (C) frames |
| **Privileges** | None (HTTP + session token) | `sudo` + a one-time codesign re-sign of the bundle |
| **Works on** | Only builds that ship the trace/debug endpoints (probe first) | Any build, including the shipped notarized one |
| **Safe inside Sculptor?** | Yes — never touches the process | Re-sign/restart are the user's; the agent only attaches |
| **Best for** | "What is every thread doing right now?", a wedged backend, a bounded call-tree trace, CPU-over-time | Instant all-thread stacks (`dump`), a live `top` glance, native (C) frames, CPU profile / flamegraph (`record`). (`record` suspends the target by default — pass `--nonblocking` to avoid freezing a live session; Route A is still richer for over-time CPU.) |

> **Why two routes:** macOS blocks `task_for_pid` on the hardened-runtime,
> notarized app, so py-spy can't attach until the target is re-signed with
> `get-task-allow` (which can't ship on a notarized build — see SCU-1604). The
> in-process route sidesteps that entirely but only exists in builds new enough
> to include the endpoints. Background:
> [`docs/development/tracing.md`](../../../docs/development/tracing.md) (Route A
> reference) and SCU-1604.

## Step 0 — Orient: where am I, and what's the target?

**Am I inside Sculptor or an external `claude`?** Check `SCULPT_AGENT_ID`:

```bash
if [ -n "$SCULPT_AGENT_ID" ]; then echo "INSIDE Sculptor"; else echo "EXTERNAL claude"; fi
```

- **INSIDE Sculptor** (`SCULPT_AGENT_ID` set): the `sculptor_backend` you'd
  profile is the one hosting this very agent. Route A is safe. For Route B you
  may build py-spy and attach, but **never** quit/restart the app or kill the
  backend — that terminates you. Re-sign and restart are the user's actions.
- **EXTERNAL `claude`**: you may run the privileged commands directly — codesign
  (per the always-ask rule in B3) and `sudo py-spy` when passwordless sudo is
  available (B5). The **app restart is always the user's job** (B4): an external
  process can't reliably relaunch the user's Sculptor.

**Find the running backend (pid, port, binary path):**

```bash
pgrep -fl 'sculptor_backend --port' || ps aux | grep '[s]culptor_backend --port'
# port (also in $SCULPT_API_PORT / $SCULPTOR_API_PORT when set):
ps -o command= -p "$BACKEND_PID" | grep -oE -- '--port [0-9]+' | awk '{print $2}'
```

Derive the bundle executable from the running pid rather than assuming a path
(it differs between `Sculptor.app` and `Sculptor Dev.app`); typically
`/Applications/Sculptor.app/Contents/Resources/sculptor_backend/sculptor_backend`.

## Step 1 — Is Route A available on this build? (probe)

The in-process endpoints only exist in builds that shipped them. Probe:

```bash
PORT="${SCULPT_API_PORT:-${SCULPTOR_API_PORT:-5050}}"
curl -s -H "x-session-token: $SESSION_TOKEN" "http://localhost:$PORT/api/v1/trace/status"
```

- JSON like `{"enabled":false,...}` → **Route A is available. Use it.**
- HTML (`<!doctype html>…`) or 404 → endpoints absent in this build → **use
  Route B (py-spy)**, or install a newer build if in-process tracing is desired.

## Route A — `sculpt debug` (in-process; no privileges)

No re-sign, safe from inside Sculptor. If the running build ships the new
`sculpt`, use the CLI; otherwise call the endpoints directly with `curl`. The
CLI targets the backend via `SCULPT_API_PORT` (default 5050) and authenticates
with the session token automatically.

**Instant all-thread Python stacks (greenlet-safe; best for a wedged backend):**

```bash
sculpt debug threads                 # to stdout
sculpt debug threads -o threads.txt  # to a file
# Direct equivalent (any build with the endpoint):
curl -s -H "x-session-token: $SESSION_TOKEN" "http://localhost:$PORT/api/v1/debug/threads"
```

**Bounded viztracer trace → Perfetto:**

```bash
sculpt debug trace start                 # arm (optionally --tracer-entries N)
# …reproduce the slow/interesting activity…
sculpt debug trace status                # running? buffered counts?
sculpt debug trace stop                  # flush; prints the output path
# Direct equivalents:
curl -s -XPOST -H "x-session-token: $SESSION_TOKEN" "http://localhost:$PORT/api/v1/trace/start"
curl -s -XPOST -H "x-session-token: $SESSION_TOKEN" "http://localhost:$PORT/api/v1/trace/stop"
```

Open the resulting `trace-<timestamp>.json` (written under the backend's
`{LOG_PATH}/traces/` — `~/.sculptor/internal/logs/traces/` in a normal install;
the exact path is returned by `stop`) at <https://ui.perfetto.dev>.

This is the runtime side of the tracing system; see
[`docs/development/tracing.md`](../../../docs/development/tracing.md) for the full
reference (what's captured, sources/pids, clock caveat, sensitive-data handling,
endpoint security). Operationally: only one trace runs at a time (`start` → 409
if already armed); the ring buffer holds `DEFAULT_ADHOC_TRACER_ENTRIES` events by
default (bounded server-side; raise with `--tracer-entries`) and wraps when full;
and a runtime-armed trace is **backend-Python only** — for renderer/Electron-main
lanes you need a from-boot `sculptor --trace-to=<path>` run (see tracing.md).

## Route B — py-spy (attach; CPU sampling, flamegraphs, native stacks)

### B1. Get a working py-spy

Stock py-spy mis-resolves the bundled `libpython` image base in our PyInstaller
onedir layout and fails with `Unsupported version of Python: 0.0.0`. The fix is
upstream in **benfred/py-spy#858** ("Adjust the PyInstaller MacOS image base").

py-spy source — pick the first that applies:

1. **Official, once #858 ships in a release** — prefer plain
   `cargo install py-spy` / a released binary. Check whether #858 has landed:
   `gh pr view 858 --repo benfred/py-spy --json state,mergedAt`.
2. **Until then, build the fork branch** (needs Rust/`cargo`) and cache it:

```bash
# Override PYSPY to point at any working build (e.g. a released py-spy once #858 lands).
PYSPY="${PYSPY:-$HOME/.cache/sculptor-pyspy/bin/py-spy}"
if ! "$PYSPY" --version >/dev/null 2>&1; then
  cargo install --git https://github.com/trisiak/py-spy \
    --branch pyinstaller-macos-image-base --root "$HOME/.cache/sculptor-pyspy"
  PYSPY="$HOME/.cache/sculptor-pyspy/bin/py-spy"
fi
"$PYSPY" --version
```

### B2. Is a re-sign even required? (inspect first)

Check whether the running backend's binary already allows task attachment —
don't re-sign blindly (it may already be signed, e.g. from a previous session):

```bash
codesign -d --entitlements - "$BACKEND_BIN" 2>&1 | grep -q get-task-allow \
  && echo "already attachable — skip B3/B4" || echo "re-sign needed (B3)"
```

If it already has `get-task-allow`, skip to **B5**. **Dev builds (`Sculptor
Dev.app`, from `just pkg-dev`) ship the sidecar already signed with
`get-task-allow`** (see `forge.config.ts` `postPackage` + `entitlements.dev.plist`),
so this check passes and no re-sign is needed — only the notarized production
app requires B3.

### B3. Re-sign (only if B2 says so) — always ask the user

The shipped backend is hardened-runtime signed without `get-task-allow`, so even
`sudo` can't attach. Re-signing **modifies the installed app in place**,
**invalidates its notarization seal locally** (fine for dev; persists until the
app is reinstalled/updated), and a re-signed file only takes effect after a
restart (B4).

**Always present the choice to the user — in both internal and external
contexts** — and let them pick:

- **(a) Agent runs it** — the agent executes the commands below itself.
- **(b) User runs it** — hand them the exact commands to run themselves.

Either way the commands are:

```bash
cat > /tmp/pyspy-entitlements.plist <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>com.apple.security.get-task-allow</key><true/>
  <key>com.apple.security.cs.allow-get-task-allow</key><true/>
</dict></plist>
PLIST
codesign -s - -f --entitlements /tmp/pyspy-entitlements.plist "$BACKEND_BIN"
codesign -d --entitlements - "$BACKEND_BIN" 2>&1 | grep get-task-allow   # verify
```

Re-signing just the `sculptor_backend` executable is sufficient — the bundled
`libpython` dylib does not need re-signing.

### B4. Restart — always the user

A re-signed on-disk file does not change the already-running process. **Ask the
user to restart Sculptor** (quit fully and relaunch) so the new signature takes
effect. Never quit/relaunch the app yourself — inside Sculptor it kills you, and
externally it isn't reliable. After they confirm the restart, **re-discover the
pid and port** (both change) via Step 0.

### B5. Attach and profile

py-spy needs root. Try passwordless sudo; if it isn't available, hand the exact
command to the user instead of prompting blindly.

```bash
if sudo -n true 2>/dev/null; then RUN="sudo -n"; else
  echo "No passwordless sudo — ask the user to run the command below themselves."; RUN="sudo"
fi
$RUN "$PYSPY" dump --pid "$BACKEND_PID"   # one-shot all-thread stacks (brief pause)
$RUN "$PYSPY" top  --pid "$BACKEND_PID"   # live top-functions view
# add --native for C frames

# CPU profile / flamegraph over time. --nonblocking is essential against a live
# backend (see note below): it samples without suspending the process.
$RUN "$PYSPY" record --pid "$BACKEND_PID" --nonblocking --rate 50 --duration 20 \
  --output ~/sculptor-backend-flame.svg                       # open in any browser
# Scrubbable timeline instead of a flat flamegraph (open at https://speedscope.app):
$RUN "$PYSPY" record --pid "$BACKEND_PID" --nonblocking --rate 50 --duration 20 \
  --format speedscope --output ~/sculptor-backend-profile.speedscope.json
```

**`py-spy record` against the backend: pass `--nonblocking`.** By default py-spy
samples by *suspending* the target, and `record`'s continuous suspend-sample over
a duration blocks the backend heavily on macOS — enough to freeze a live session
(and inside Sculptor that's the very session you're running in). `--nonblocking`
reads stacks without pausing the process, so it doesn't freeze anything; the
tradeoff is occasional partial/inconsistent stacks and higher sampling error,
which is usually fine for a hotspot flamegraph. Keep `--rate` modest and
`--duration` bounded regardless. For the **richest over-time CPU picture, Route A
viztracer is still better** — it runs in-process with a full call tree — but when
Route A is absent (the build that pushed you to Route B), `--nonblocking record`
is the right fallback. `dump`/`top` pause only briefly and don't need the flag.

## Cleanup

- Stop any armed Route-A trace (`sculpt debug trace stop`) you started.
- The re-signed bundle stays re-signed; tell the user they can reinstall/update
  to restore the pristine notarized app.

## Pitfalls

- **Don't kill your own backend / app.** Inside Sculptor, the restart in B4 is
  always the user's action.
- **pid/port change on restart** — re-discover them (Step 0) after any relaunch.
- **Inspect before re-signing** (B2) — the binary may already be attachable.
- **Stock py-spy fails** with `0.0.0` on our bundle — use the patched fork (B1).
- **`py-spy record` blocks the backend by default** (suspend-based continuous
  sampling) — pass **`--nonblocking`** to sample without pausing the process, or
  use Route A viztracer for the richest sustained CPU profile (B5).
- **One Route-A trace at a time** (`start` → 409 if already running).
