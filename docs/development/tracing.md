# Tracing

A developer-only profiling path that produces a single Chrome JSON trace file
covering the Python backend (main process), the Electron main process, and
the React renderer. Drop the file into <https://ui.perfetto.dev> to inspect
timings — the Perfetto UI parses the file locally in your browser, so the
file is not uploaded anywhere.

## How to run with tracing

Add the `--trace-to=<path>` flag when starting Sculptor:

```sh
sculptor --trace-to=/tmp/sculptor.json
```

The path is taken literally — relative or absolute. This traces from the
earliest possible point (it captures backend import time) and writes once on
clean shutdown. To instead arm/disarm a backend that is already running, see
"Ad-hoc tracing on a running backend" below. When neither is active, no
tracing code runs and overhead is near zero.

When Sculptor is launched via Electron, pass the flag through the standard
arg-forwarding prefix:

```sh
sculptor-electron --sculptor=--trace-to=/tmp/sculptor.json
```

Electron's main process picks up the flag from its own argv (so it can wire
up Node-side tracing before any windows are created) and forwards it to the
spawned Python backend.

## Ad-hoc tracing on a running backend (no restart)

The `--trace-to` flag traces from boot and writes once, on clean shutdown.
When you instead need to profile a backend that is *already running* — most
importantly a signed production build, which `py-spy`/`lldb` cannot attach to
because of the hardened runtime — arm and disarm viztracer at runtime over
HTTP. These commands live under `sculpt debug` because they exist for Sculptor
development only, not as end-user functionality:

```sh
sculpt debug trace start    # arm; prints the output path it will write to
# ...reproduce the slow path...
sculpt debug trace stop     # stop, flush the Chrome-JSON file, print its path
sculpt debug trace status   # is a trace running right now?
```

This works in-process, so it needs no debugger entitlement and no signals.
The file lands under `{LOG_PATH}/traces/trace-<timestamp>.json`
(`~/.sculptor/internal/logs/traces/` in a normal install); open it at
<https://ui.perfetto.dev> as usual.

The underlying endpoints are `POST /api/v1/trace/start`,
`POST /api/v1/trace/stop`, and `GET /api/v1/trace/status`. Unlike
`/api/v1/trace/batch`, they **require the session token** (see the security
note below); `sculpt` supplies it automatically.

Two limitations of a runtime-armed trace versus a boot-time `--trace-to` run:

- **Backend Python only.** The renderer and Electron main decide whether to
  forward their events by reading `window.__SCULPTOR_TRACING__`, which is
  injected once at page load. A trace armed after boot therefore captures the
  backend process alone — which is exactly what you want when profiling a live
  backend, but means no renderer/Electron lanes appear in the file.
- **No import-time spans.** Boot and import durations already happened; the
  capture covers only what runs between `start` and `stop`.

### Just dump thread stacks

When the backend merely looks *wedged* and you want an instant snapshot rather
than a profile:

```sh
sculpt debug threads        # Python traceback for every live thread
```

This hits `GET /api/v1/debug/threads`, which renders `sys._current_frames()`.
It is greenlet-safe (no signals, no C-stack walk — the reason the old
`faulthandler`/`SIGUSR1` route was dropped) and effectively free.

## What you get

While tracing is on:

- The backend logs `Tracing enabled, output -> /abs/path/...` at startup.
- The renderer prints the equivalent message in the browser/Electron devtools
  console. No in-app UI is added.
- viztracer captures every backend Python function call (function names +
  durations + thread/task attribution) **in the main backend process only**.
  Subprocesses (agent processes, git invocations) are NOT traced in v1 —
  only the duration of the parent's `subprocess.Popen`/`subprocess.run`
  call site appears. Subprocess capture is a deferred follow-up.
- The renderer attaches a `PerformanceObserver` covering `mark`, `measure`,
  and `resource` entry types. Fetch/XHR/WebSocket handshake timings are
  picked up automatically via Resource Timing — no globals are
  monkey-patched. Note that Resource Timing only covers the WebSocket
  *upgrade*; per-frame WS timings come solely from the hand-placed
  `performance.mark()`s below.
- Hand-placed `performance.mark()` calls fire at the Sculptor WebSocket
  wrapper's on-message point. There is no symmetric send-side mark —
  the wrapper is receive-only at the application level.
- Electron main emits `traceMark`s at `boot`, `app_ready`, `backend_ready`,
  and `shutdown_begin`.
- The renderer and Electron main flush their buffered Chrome-JSON events to
  the backend every few seconds and once more on `beforeunload` / shutdown.
- On process exit (including Ctrl-C), the backend merges its viztracer
  output with the buffered renderer / Electron-main batches and writes a
  single combined Chrome JSON file to the `--trace-to` path. It then logs:

  ```
  Trace written to <path>. Open https://ui.perfetto.dev and drop this file
  there to view.
  ```

## How sources are separated

Each source lives on its own `pid` in the combined trace, so they appear as
separate processes in Perfetto:

| Source              | `pid`       |
| ------------------- | ----------- |
| Backend Python      | OS pid      |
| Backend subprocesses| OS pid      |
| Renderer            | `9000001`   |
| Electron main       | `9000002`   |

Friendly process names (`renderer`, `electron_main`) are attached via
Chrome-JSON `process_name` metadata events.

## Clock alignment caveat

**Cross-source timing alignment is approximate in v1.** Each source uses an
independent clock and no synchronization handshake runs between them. Within
a single source, ordering and durations are exact. When comparing a backend
span against a renderer span, treat the relative offset as a hint, not a
truth — clocks may be several milliseconds apart.

A proper clock-sync handshake (e.g. NTP-style RTT-corrected per-client
offset, periodically refreshed) is a deferred follow-up.

## Sensitive data

Trace files may contain sensitive data — function names, file paths, log
fragments, and any text passed as a `performance.mark()` label. Argument
values are NOT captured (this would cause 10–50× slowdowns and trigger
lazy-load side effects on hot paths like SQLAlchemy sessions), but the
captured names and paths can still leak project structure or secrets stored
in identifiers. Developers are responsible for handling trace files
appropriately — treat them like a code dump, not like aggregate metrics.

## Security note on `/api/v1/trace/batch`

The HTTP endpoint that accepts buffered events from the renderer and from
the Electron main process is **exempt from `SessionTokenMiddleware`**. The
endpoint is a no-op when `--trace-to` is not set (no buffering happens), so
the practical exposure is "any local process on the loopback can fill the
backend's trace buffer when tracing is on." This is acceptable for a
developer-only flag; do not enable tracing in shared-host environments.

The request body accepts events of arbitrary size in the `args` field. The
buffer cap (`MAX_BUFFERED_EXTERNAL_EVENTS = 100_000`) bounds the *count* of
events but not per-event byte size, so a local process could in theory ship
a single 100 MB event. Mitigated in practice by the loopback-only network
surface and the dev-only flag gating; flagged here so a future change that
broadens the network surface (e.g. exposing the backend on a non-loopback
address while tracing is on) knows to add per-event size limits.

## Security note on the trace-control and debug endpoints

`POST /api/v1/trace/start`, `POST /api/v1/trace/stop`,
`GET /api/v1/trace/status`, and `GET /api/v1/debug/threads` are **not**
exempt from `SessionTokenMiddleware` — they require the session token,
because each is a more powerful primitive than the fire-and-forget
`/trace/batch` ingest:

- `start` allocates viztracer's ring buffer (hundreds of MB to ~2.5 GB) and
  writes a file. The output path is **not** caller-supplied — it is always a
  timestamped file under `{LOG_PATH}/traces` — specifically so the token
  holder cannot use the trace writer as an arbitrary-file-write primitive.
  `tracer_entries` is bounded server-side to cap the memory lever.
- `debug/threads` exposes Python stacks (function names, file paths), the
  same class of information a trace file contains; treat its output like a
  code dump.

## Future augmentations

Out of scope for v1, in rough priority order:

- **Subprocess capture** for spawned Python children (agent processes etc.).
  viztracer ships a `patch_subprocess` helper that rewrites
  `subprocess.Popen` invocations to wrap them in `python -m viztracer`,
  but it relies on the parent's `sys.executable` accepting `-m viztracer`,
  which the PyInstaller-packaged `sculptor_backend` does not. v1 traces
  the main backend process only; this is the highest-priority follow-up
  because for a Sculptor-shaped workload the agent subprocesses are
  exactly what one wants to see.
- **Argument-value capture** in viztracer, behind an opt-in toggle. Expected
  10–50× slowdowns on hot paths and repr side-effects (lazy-load triggers
  in SQLAlchemy sessions, etc.) make this unsafe as a default.
- **Cross-source clock synchronization** via a handshake protocol.
- **Live trace snapshot endpoint** (`GET`) so developers can sample a
  running process *without* stopping it. Runtime arm/disarm (above) already
  lets you trace a live process, but you must `stop` to get the file;
  snapshotting mid-run would require transcoding viztracer's native buffer to
  Chrome JSON on the fly, which fights the library's internals.
- **Renderer/Electron capture for runtime-armed traces.** A trace armed after
  boot is backend-only because the renderer reads its on/off flag once at page
  load; a status-poll or push would let the frontend start forwarding events
  mid-session.
- **Named "category" hot-path spans** for LLM, SQL, git, per-message-type
  WebSocket handlers, and FastAPI routes — we currently rely on
  viztracer's auto-captured function names.
- **React render profiling.** v1 has no per-render instrumentation; a
  follow-up will add it.
- **Selective subprocess filtering** (e.g. trace agent processes but skip
  short-lived git utilities).
- **End-user-facing tracing UX** (badges, banners, in-app "download trace"
  affordances).
