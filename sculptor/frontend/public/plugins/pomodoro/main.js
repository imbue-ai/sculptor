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

import { createElement as h, useEffect, useRef, useState } from "react";
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
// Keep the pill on-screen even after a resize moved the viewport edges in.
const clampPos = (p) => ({
  x: Math.max(8, Math.min(p.x, window.innerWidth - 80)),
  y: Math.max(8, Math.min(p.y, window.innerHeight - 48)),
});

const Pomodoro = () => {
  const [task, setTask] = usePluginSetting("task");
  const [expanded, setExpanded] = useState(false);
  const [mode, setMode] = useState("work"); // "work" | "break"
  const [running, setRunning] = useState(false);
  const [secondsLeft, setSecondsLeft] = useState(WORK_SECONDS);

  const [posRaw, setPosRaw] = usePluginSetting("pos");
  const [pos, setPos] = useState(() => parsePos(posRaw) ?? defaultPos());
  const [dragging, setDragging] = useState(false);
  const posRef = useRef(pos);
  posRef.current = pos;

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
    setDragging(true);
    const onMove = (ev) => setPos(clampPos({ x: origin.x + ev.clientX - startX, y: origin.y + ev.clientY - startY }));
    const onUp = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      setDragging(false);
      setPosRaw(JSON.stringify(posRef.current));
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  };

  // Tick once a second while running; when a phase hits zero, flip work<->break.
  const modeRef = useRef(mode);
  modeRef.current = mode;
  useEffect(() => {
    if (!running) return;
    const id = setInterval(() => {
      setSecondsLeft((s) => {
        if (s > 1) return s - 1;
        const nextMode = modeRef.current === "work" ? "break" : "work";
        setMode(nextMode);
        return nextMode === "work" ? WORK_SECONDS : BREAK_SECONDS;
      });
    }, 1000);
    return () => clearInterval(id);
  }, [running]);

  const reset = () => {
    setRunning(false);
    setSecondsLeft(mode === "work" ? WORK_SECONDS : BREAK_SECONDS);
  };

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

  const time = h("span", { style: { fontVariantNumeric: "tabular-nums", fontWeight: 600, fontSize: 16 } }, format(secondsLeft));

  const playPause = h(
    "button",
    { onClick: () => setRunning((r) => !r), style: btn(accent) },
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
      { style: { flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: "var(--gray-11)" } },
      task || (mode === "work" ? "Focus" : "Break"),
    ),
    h(
      "button",
      { onClick: () => setExpanded((e) => !e), style: linkBtn() },
      expanded ? "▾" : "▸",
    ),
  );

  if (!expanded) return h("div", { style: shell }, header);

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
            const next = mode === "work" ? "break" : "work";
            setMode(next);
            setRunning(false);
            setSecondsLeft(next === "work" ? WORK_SECONDS : BREAK_SECONDS);
          },
          style: linkBtn(),
        },
        mode === "work" ? "Switch to break" : "Switch to work",
      ),
    ),
    h(
      "div",
      { style: { color: "var(--gray-10)", fontSize: 12 } },
      currentWorkspace
        ? `On: ${currentWorkspace.description || currentWorkspace.objectId}`
        : "Not in a workspace",
    ),
  );

  return h("div", { style: shell }, header, body);
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
