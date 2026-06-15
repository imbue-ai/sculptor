/**
 * Sculpty — a "Clippy"-style desktop buddy, as the *pure* plugin example.
 *
 * No build step, no imports, no framework: this file is hand-written ESM that
 * the host imports directly. `activate()` is handed the live page and does
 * everything with raw DOM — it appends one element to <body>, runs its own
 * animation loop, listens for activity, and returns a disposer that tears it
 * all down. (It deliberately does NOT use `registerOverlay`; that exists for
 * React overlays. The point of this example is the bare-metal escape hatch.)
 *
 * The character is a tiny state machine. Each STATE declares the parameter
 * vector it wants the drawing to settle to, plus an optional per-frame
 * `animate()` for self-motion (breathing, bobbing) and an optional auto
 * transition. Switching states does not snap: the engine lerps the parameter
 * vector from the old values to the new ones over a duration, so a single
 * parametrized `render(params)` blends smoothly between every mood.
 *
 * Graphics are intentionally a placeholder. `render(params)` and the per-state
 * parameter values below are the seam a graphics pass can replace wholesale —
 * swap in the real SVGs and richer params without touching the engine.
 */

// ---------------------------------------------------------------------------
// States & transitions
// ---------------------------------------------------------------------------

// Every numeric field here is a blendable parameter. `render()` reads them;
// the engine interpolates them. Add fields freely — the engine lerps whatever
// numbers a target state declares.
const BASE_PARAMS = { eyeOpen: 1, mouth: 0.4, lean: 0, bob: 0, scale: 1, hue: 200 };

// `hold` + `then`: after the transition into this state settles, wait `hold` ms
// then auto-transition to `then` (over `dur` ms). `animate(t)` returns a
// partial param overlay applied on top of the blended base, where `t` is ms
// since this state was entered.
const STATES = {
  asleep: {
    dur: 900,
    params: { eyeOpen: 0, mouth: 0.08, scale: 0.9, hue: 225 },
    // Slow breathing.
    animate: (t) => ({ bob: Math.sin(t / 1500) * 3, scale: 0.9 + Math.sin(t / 1500) * 0.015 }),
  },
  waking: {
    dur: 450,
    hold: 250,
    then: "awake",
    params: { eyeOpen: 0.65, mouth: 0.25, scale: 1.0, hue: 210 },
  },
  awake: {
    dur: 350,
    params: { eyeOpen: 1, mouth: 0.45, scale: 1.0, hue: 200 },
    // Gentle idle float.
    animate: (t) => ({ bob: Math.sin(t / 650) * 2 }),
  },
  excited: {
    dur: 180,
    hold: 700,
    then: "awake",
    params: { eyeOpen: 1, mouth: 0.75, scale: 1.07, hue: 150 },
    // Quick happy wobble.
    animate: (t) => ({ lean: Math.sin(t / 90) * 0.18, bob: Math.abs(Math.sin(t / 130)) * -4 }),
  },
  drowsy: {
    dur: 700,
    hold: 2200,
    then: "asleep",
    params: { eyeOpen: 0.4, mouth: 0.15, scale: 0.96, hue: 215 },
    animate: (t) => ({ bob: Math.sin(t / 1100) * 2 }),
  },
};

// How long awake-with-no-activity before drifting to drowsy.
const IDLE_TO_DROWSY_MS = 6000;
// Typing bursts faster than this (ms between keys) tip "awake" into "excited".
const EXCITED_GAP_MS = 220;

// Cursor-avoidance: Sculpty slides away from the pointer so it never obstructs
// what's underneath. Within REPEL_RADIUS px of its home, it's pushed away (up
// to REPEL_MAX px); the offset eases by REPEL_EASE/frame, so it glides out of
// the way and drifts back once the cursor leaves.
const REPEL_RADIUS = 130;
const REPEL_MAX = 96;
const REPEL_EASE = 0.18;

// ---------------------------------------------------------------------------
// Rendering (placeholder — replace with real SVGs)
// ---------------------------------------------------------------------------

const SIZE = 96;

/**
 * Turn a parameter vector into an SVG string. Parametrized so the engine can
 * hand it freely-blended values mid-transition. This placeholder is just a
 * rounded blob with two eyes and a mouth; a graphics pass replaces it.
 */
const render = (p) => {
  const cx = SIZE / 2;
  const bodyR = 34 * p.scale;
  const cy = SIZE / 2 + p.bob;
  const tilt = p.lean * 10;
  const eyeH = Math.max(0.5, p.eyeOpen) * 9;
  const eyeY = cy - 6;
  const mouthW = 10 + p.mouth * 16;
  const mouthH = p.mouth * 10;
  const mouthY = cy + 12;
  const fill = `hsl(${p.hue} 70% 60%)`;
  const dark = `hsl(${p.hue} 45% 28%)`;
  return `
    <svg width="${SIZE}" height="${SIZE}" viewBox="0 0 ${SIZE} ${SIZE}" xmlns="http://www.w3.org/2000/svg">
      <g transform="rotate(${tilt} ${cx} ${cy})">
        <ellipse cx="${cx}" cy="${cy}" rx="${bodyR}" ry="${bodyR * 0.92}" fill="${fill}" />
        <ellipse cx="${cx - 11}" cy="${eyeY}" rx="5" ry="${eyeH / 2}" fill="${dark}" />
        <ellipse cx="${cx + 11}" cy="${eyeY}" rx="5" ry="${eyeH / 2}" fill="${dark}" />
        <path d="M ${cx - mouthW / 2} ${mouthY} Q ${cx} ${mouthY + mouthH + 4} ${cx + mouthW / 2} ${mouthY}"
              fill="none" stroke="${dark}" stroke-width="3" stroke-linecap="round" />
      </g>
    </svg>`;
};

// ---------------------------------------------------------------------------
// Engine
// ---------------------------------------------------------------------------

const easeInOut = (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
const lerp = (a, b, t) => a + (b - a) * t;

/** Blend two param vectors key-by-key (keys default from BASE_PARAMS). */
const blend = (from, to, t) => {
  const out = {};
  for (const k of Object.keys(BASE_PARAMS)) {
    const a = from[k] ?? BASE_PARAMS[k];
    const b = to[k] ?? BASE_PARAMS[k];
    out[k] = lerp(a, b, t);
  }
  return out;
};

export default function activate() {
  const el = document.createElement("div");
  el.setAttribute("aria-hidden", "true");
  el.style.cssText = [
    "position:fixed",
    "right:24px",
    "bottom:24px",
    "width:" + SIZE + "px",
    "height:" + SIZE + "px",
    "pointer-events:none",
    "user-select:none",
    "z-index:60",
    "filter:drop-shadow(0 6px 12px rgba(0,0,0,0.25))",
  ].join(";");
  document.body.appendChild(el);

  // Mutable engine state.
  let state = "asleep";
  let fromParams = { ...STATES.asleep.params }; // params we are blending FROM
  let transition = null; // { to, start, dur } while blending, else null
  let stateEnteredAt = performance.now();
  let lastActivityAt = performance.now();
  let lastKeyAt = 0;
  let raf = 0;

  // Cursor tracking + the current (eased) avoidance offset applied as a
  // transform on the container.
  let pointerX = -9999;
  let pointerY = -9999;
  let offsetX = 0;
  let offsetY = 0;

  const enter = (name, now) => {
    if (name === state && !transition) return; // already settled there
    if (transition && transition.to === name) return; // already heading there
    const current = transition ? blend(fromParams, STATES[transition.to].params, 1) : fromParams;
    fromParams = { ...current };
    transition = { to: name, start: now, dur: STATES[name].dur };
  };

  const onActivity = (excite) => {
    const now = performance.now();
    lastActivityAt = now;
    if (state === "asleep" || state === "drowsy") {
      enter("waking", now);
    } else if (excite && state === "awake") {
      enter("excited", now);
    }
  };

  const onKey = () => {
    const now = performance.now();
    const burst = now - lastKeyAt < EXCITED_GAP_MS;
    lastKeyAt = now;
    onActivity(burst);
  };
  const onMove = (e) => {
    pointerX = e.clientX;
    pointerY = e.clientY;
    onActivity(false);
  };
  // Cursor gone from the window — let Sculpty drift home.
  const onLeave = () => {
    pointerX = -9999;
    pointerY = -9999;
  };

  window.addEventListener("keydown", onKey, true);
  window.addEventListener("pointermove", onMove, true);
  document.addEventListener("mouseleave", onLeave);

  // Push the home-anchored offset away from the pointer, eased per frame. Home
  // center is recomputed each frame so it follows window resizes. Measured
  // against home (not the live position) so the repulsion can't feed back on
  // itself and jitter.
  const updateAvoidance = () => {
    const homeCx = window.innerWidth - 24 - SIZE / 2;
    const homeCy = window.innerHeight - 24 - SIZE / 2;
    const vx = homeCx - pointerX;
    const vy = homeCy - pointerY;
    const dist = Math.hypot(vx, vy);
    let targetX = 0;
    let targetY = 0;
    if (dist < REPEL_RADIUS && dist > 0.001) {
      const push = (1 - dist / REPEL_RADIUS) * REPEL_MAX;
      targetX = (vx / dist) * push;
      targetY = (vy / dist) * push;
    }
    offsetX += (targetX - offsetX) * REPEL_EASE;
    offsetY += (targetY - offsetY) * REPEL_EASE;
    el.style.transform = `translate(${offsetX.toFixed(1)}px, ${offsetY.toFixed(1)}px)`;
  };

  const frame = (now) => {
    // Resolve the blended base; settle the transition when it completes.
    let base;
    if (transition) {
      const t = Math.min(1, (now - transition.start) / transition.dur);
      base = blend(fromParams, STATES[transition.to].params, easeInOut(t));
      if (t >= 1) {
        state = transition.to;
        fromParams = { ...STATES[state].params };
        stateEnteredAt = now;
        transition = null;
      }
    } else {
      base = { ...fromParams };
      // Auto-transitions only fire once a state has settled.
      const def = STATES[state];
      const inState = now - stateEnteredAt;
      if (state === "awake" && now - lastActivityAt > IDLE_TO_DROWSY_MS) {
        enter("drowsy", now);
      } else if (def.then && def.hold != null && inState > def.hold) {
        enter(def.then, now);
      }
    }

    // Layer the active state's self-animation on top of the blended base.
    const animate = STATES[transition ? transition.to : state].animate;
    const overlay = animate ? animate(now - stateEnteredAt) : null;
    const params = overlay ? { ...base, ...mergeAdditive(base, overlay) } : base;

    el.innerHTML = render(params);
    updateAvoidance();
    raf = requestAnimationFrame(frame);
  };
  raf = requestAnimationFrame(frame);

  // Disposer: the host calls this on unload/reload. Leave no trace.
  return () => {
    cancelAnimationFrame(raf);
    window.removeEventListener("keydown", onKey, true);
    window.removeEventListener("pointermove", onMove, true);
    document.removeEventListener("mouseleave", onLeave);
    el.remove();
  };
}

/**
 * Self-animation overlays are additive for the motion fields (bob/lean/scale
 * read as "wobble around the blended value"), absolute for everything else.
 * Keeps breathing/wobble from fighting the blended pose.
 */
function mergeAdditive(base, overlay) {
  const additive = new Set(["bob", "lean"]);
  const out = {};
  for (const k of Object.keys(overlay)) {
    out[k] = additive.has(k) ? (base[k] ?? 0) + overlay[k] : overlay[k];
  }
  return out;
}
