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

The path is taken literally — relative or absolute. The flag's presence is
the only on/off control; there is no separate env var or runtime toggle.
When the flag is absent, no tracing code runs and overhead is near zero.

When Sculptor is launched via Electron, pass the flag through the standard
arg-forwarding prefix:

```sh
sculptor-electron --sculptor=--trace-to=/tmp/sculptor.json
```

Electron's main process picks up the flag from its own argv (so it can wire
up Node-side tracing before any windows are created) and forwards it to the
spawned Python backend.

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
  running process without stopping it. v1 only writes at process exit;
  fetching mid-run would require transcoding viztracer's native buffer to
  Chrome JSON on the fly, which fights the library's internals.
- **Named "category" hot-path spans** for LLM, SQL, git, per-message-type
  WebSocket handlers, and FastAPI routes — we currently rely on
  viztracer's auto-captured function names.
- **React render profiling.** v1 has no per-render instrumentation; a
  follow-up will add it.
- **Selective subprocess filtering** (e.g. trace agent processes but skip
  short-lived git utilities).
- **Runtime start/stop control** — explicitly out of scope; lifecycle is
  whole-process only.
- **End-user-facing tracing UX** (badges, banners, in-app "download trace"
  affordances).
