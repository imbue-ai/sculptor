/**
 * Pomodoro — the *React* no-build plugin example.
 *
 * Like Sculpty, this is hand-written ESM the host imports directly with no
 * build step. The difference: it's a React component. Because there's no
 * compiler, there's no JSX — we call `createElement` directly (aliased to `h`).
 * Bare imports (`react`, `@sculptor/plugin-sdk`) resolve through the host's
 * import map to the host's own singletons, so hooks and state Just Work.
 *
 * It's contributed via `api.registerOverlay`, which mounts it floating above
 * the whole app (inside the host's providers) rather than in a panel zone —
 * so it stays visible across every route. That's also why it reads the
 * "current workspace" through `useCurrentWorkspaceId` + `useWorkspaces`
 * (app-global hooks) instead of a per-panel workspace context.
 *
 * The task label is persisted with `usePluginSetting`, so it survives reloads
 * and is the kind of thing an agent could pre-fill when it spins the timer up.
 */

import { createElement as h, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useCurrentWorkspaceId, usePluginSetting, useWorkspaces } from "@sculptor/plugin-sdk";

const WORK_SECONDS = 25 * 60;
const BREAK_SECONDS = 5 * 60;

const format = (s) => `${Math.floor(s / 60)}`.padStart(2, "0") + ":" + `${s % 60}`.padStart(2, "0");

// Position is persisted via usePluginSetting (a string), so a dragged spot
// survives reloads. Default to the bottom-left corner.
const defaultPos = () => ({ x: 24, y: window.innerHeight - 132 });
const parsePos = (raw) => {
  if (!raw) return null;
  try {
    const p = JSON.parse(raw);
    if (typeof p.x === "number" && typeof p.y === "number") return p;
  } catch {
    /* fall through to default */
  }
  return null;
};
// Keep the whole pill on-screen given its measured size, with an 8px margin.
// Used both while dragging and to refit after a resize/restore. `Math.max(8,
// …)` guards viewports too small to fit the box at all (upper bound < 8).
const MARGIN = 8;
const clampPos = (p, w, h) => ({
  x: Math.min(Math.max(MARGIN, p.x), Math.max(MARGIN, window.innerWidth - w - MARGIN)),
  y: Math.min(Math.max(MARGIN, p.y), Math.max(MARGIN, window.innerHeight - h - MARGIN)),
});

const durationFor = (mode) => (mode === "work" ? WORK_SECONDS : BREAK_SECONDS);
const flip = (mode) => (mode === "work" ? "break" : "work");

// The timer is persisted via usePluginSetting too, so a hard reload or plugin
// refresh re-derives it instead of resetting. The trick: while running we store
// `endsAt` (an absolute epoch-ms deadline), not a countdown — so on reload we
// subtract the real elapsed wall-clock. While paused we store the frozen
// `secondsLeft`. Shape: { mode, running, endsAt, secondsLeft }.
const parseTimer = (raw) => {
  if (!raw) return null;
  try {
    const t = JSON.parse(raw);
    if (t && (t.mode === "work" || t.mode === "break")) return t;
  } catch {
    /* fall through to default */
  }
  return null;
};

// If a running deadline (and maybe several phases after it) passed while away,
// walk forward to the phase that contains `now`, alternating work/break, so we
// resume in the right place rather than showing a stale 00:00.
const rollForward = (mode, endsAt, now) => {
  let m = mode;
  let end = endsAt;
  while (now >= end) {
    m = flip(m);
    end += durationFor(m) * 1000;
  }
  return { mode: m, endsAt: end };
};

const remainingSeconds = (endsAt, now) => Math.max(0, Math.ceil((endsAt - now) / 1000));

// Re-derive the live phase from the persisted record at mount time.
const derivePhase = (raw, now) => {
  const t = parseTimer(raw);
  if (!t) return { mode: "work", running: false, endsAt: null, secondsLeft: WORK_SECONDS };
  if (!t.running) {
    const secondsLeft = typeof t.secondsLeft === "number" ? t.secondsLeft : durationFor(t.mode);
    return { mode: t.mode, running: false, endsAt: null, secondsLeft };
  }
  const rolled = rollForward(t.mode, t.endsAt, now);
  return { mode: rolled.mode, running: true, endsAt: rolled.endsAt, secondsLeft: remainingSeconds(rolled.endsAt, now) };
};

const Pomodoro = () => {
  const [task, setTask] = usePluginSetting("task");
  const [expanded, setExpanded] = useState(false);

  // Single source of truth for the timer, mirrored to the persisted record.
  // `nowMs` is just a 1s re-render pulse; the displayed time is *derived* from
  // `endsAt`, never decremented, so it can't drift from wall-clock.
  const [timerRaw, setTimerRaw] = usePluginSetting("timer");
  const [phase, setPhase] = useState(() => derivePhase(timerRaw, Date.now()));
  const [nowMs, setNowMs] = useState(() => Date.now());
  const persist = (next) => {
    setPhase(next);
    setTimerRaw(JSON.stringify(next));
  };
  const mode = phase.mode;
  const running = phase.running;
  const secondsLeft = running && phase.endsAt != null ? remainingSeconds(phase.endsAt, nowMs) : phase.secondsLeft;

  const [posRaw, setPosRaw] = usePluginSetting("pos");
  const [pos, setPos] = useState(() => parsePos(posRaw) ?? defaultPos());
  const [dragging, setDragging] = useState(false);
  const posRef = useRef(pos);
  posRef.current = pos;
  const boxRef = useRef(null);

  const workspaces = useWorkspaces();
  const currentWorkspaceId = useCurrentWorkspaceId();
  const currentWorkspace = workspaces?.find((w) => w.objectId === currentWorkspaceId);

  // Drag from the header. Buttons/inputs are excluded so the controls keep
  // working; the new spot is persisted once on release, not on every move.
  const onDragStart = (e) => {
    if (e.target.closest("button, input")) return;
    e.preventDefault();
    const startX = e.clientX;
    const startY = e.clientY;
    const origin = posRef.current;
    const box = boxRef.current;
    const w = box ? box.offsetWidth : 0;
    const hgt = box ? box.offsetHeight : 0;
    setDragging(true);
    const onMove = (ev) =>
      setPos(clampPos({ x: origin.x + ev.clientX - startX, y: origin.y + ev.clientY - startY }, w, hgt));
    const onUp = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      setDragging(false);
      setPosRaw(JSON.stringify(posRef.current));
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  };

  // Pull the pill back into view on mount, on viewport resize, and when it
  // changes size (expand/collapse). This is what rescues a position restored
  // from a larger viewport, and stops an expansion near an edge from spilling
  // off-screen. The corrected spot is persisted so storage stays valid.
  useLayoutEffect(() => {
    const fit = () => {
      const box = boxRef.current;
      if (!box) return;
      const next = clampPos(posRef.current, box.offsetWidth, box.offsetHeight);
      if (next.x !== posRef.current.x || next.y !== posRef.current.y) {
        setPos(next);
        setPosRaw(JSON.stringify(next));
      }
    };
    fit();
    window.addEventListener("resize", fit);
    return () => window.removeEventListener("resize", fit);
  }, [expanded]);

  // While running, pulse a re-render each second; when the deadline passes,
  // advance to the next phase (rolling through any we slept past) and persist.
  useEffect(() => {
    if (!running || phase.endsAt == null) return;
    const tick = () => {
      const now = Date.now();
      if (now >= phase.endsAt) {
        const rolled = rollForward(phase.mode, phase.endsAt, now);
        persist({
          mode: rolled.mode,
          running: true,
          endsAt: rolled.endsAt,
          secondsLeft: remainingSeconds(rolled.endsAt, now),
        });
      } else {
        setNowMs(now);
      }
    };
    const id = setInterval(tick, 1000);
    tick();
    return () => clearInterval(id);
  }, [running, phase.endsAt, phase.mode]);

  const start = () => {
    const now = Date.now();
    persist({ mode, running: true, endsAt: now + secondsLeft * 1000, secondsLeft });
    setNowMs(now);
  };
  const pause = () => persist({ mode, running: false, endsAt: null, secondsLeft });
  const reset = () => persist({ mode, running: false, endsAt: null, secondsLeft: durationFor(mode) });

  const accent = mode === "work" ? "var(--accent-9)" : "var(--grass-9)";

  // Re-enable pointer events on the box itself: the overlay layer is
  // click-through (pointer-events:none) so it never blocks the app.
  const shell = {
    pointerEvents: "auto",
    position: "fixed",
    left: pos.x,
    top: pos.y,
    minWidth: expanded ? 280 : 168,
    padding: expanded ? "12px 14px" : "8px 12px",
    borderRadius: 12,
    background: "var(--color-panel-solid)",
    border: "1px solid var(--gray-a5)",
    boxShadow: "var(--shadow-4)",
    color: "var(--gray-12)",
    font: "13px var(--default-font-family, sans-serif)",
    cursor: "default",
  };

  const dot = h("span", {
    style: { width: 8, height: 8, borderRadius: "50%", background: accent, flexShrink: 0 },
  });

  const time = h(
    "span",
    { style: { fontVariantNumeric: "tabular-nums", fontWeight: 600, fontSize: 16 } },
    format(secondsLeft),
  );

  const playPause = h(
    "button",
    { onClick: () => (running ? pause() : start()), style: btn(accent) },
    running ? "Pause" : "Start",
  );

  const header = h(
    "div",
    {
      onPointerDown: onDragStart,
      style: {
        display: "flex",
        alignItems: "center",
        gap: 8,
        cursor: dragging ? "grabbing" : "grab",
        touchAction: "none",
      },
    },
    dot,
    time,
    h(
      "span",
      {
        style: { flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: "var(--gray-11)" },
      },
      task || (mode === "work" ? "Focus" : "Break"),
    ),
    h("button", { onClick: () => setExpanded((e) => !e), style: linkBtn() }, expanded ? "▾" : "▸"),
  );

  if (!expanded) return h("div", { ref: boxRef, style: shell }, header);

  const body = h(
    "div",
    { style: { display: "flex", flexDirection: "column", gap: 10, marginTop: 10 } },
    h("input", {
      value: task,
      placeholder: "What are you working on?",
      onChange: (e) => setTask(e.target.value),
      style: {
        padding: "6px 8px",
        borderRadius: 8,
        border: "1px solid var(--gray-a6)",
        background: "var(--color-surface)",
        color: "var(--gray-12)",
        font: "inherit",
      },
    }),
    h(
      "div",
      { style: { display: "flex", gap: 6 } },
      playPause,
      h("button", { onClick: reset, style: linkBtn() }, "Reset"),
      h(
        "button",
        {
          onClick: () => {
            const next = flip(mode);
            persist({ mode: next, running: false, endsAt: null, secondsLeft: durationFor(next) });
          },
          style: linkBtn(),
        },
        mode === "work" ? "Switch to break" : "Switch to work",
      ),
    ),
    h(
      "div",
      { style: { color: "var(--gray-10)", fontSize: 12 } },
      currentWorkspace ? `On: ${currentWorkspace.description || currentWorkspace.objectId}` : "Not in a workspace",
    ),
  );

  return h("div", { ref: boxRef, style: shell }, header, body);
};

const btn = (accent) => ({
  pointerEvents: "auto",
  padding: "5px 12px",
  borderRadius: 8,
  border: "none",
  background: accent,
  color: "white",
  font: "inherit",
  fontWeight: 600,
  cursor: "pointer",
});

const linkBtn = () => ({
  pointerEvents: "auto",
  padding: "5px 8px",
  borderRadius: 8,
  border: "1px solid var(--gray-a6)",
  background: "transparent",
  color: "var(--gray-11)",
  font: "inherit",
  cursor: "pointer",
});

export default function activate(api) {
  return api.registerOverlay({ id: "pomodoro", component: Pomodoro });
}
