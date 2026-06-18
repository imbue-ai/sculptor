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
 * Sculpty has two independent axes:
 *
 *   • MOOD — which squiggle it shows. One of three feeling logos, picked
 *     automatically from how busy you are: long idle → `sleeping` (sage), normal
 *     → `idle` (amber), and ~20s of *continuous* typing → `active` (orange).
 *     Moods crossfade cleanly (one shape on screen at a time) and also set the
 *     slow ambient motion's character.
 *   • ACTIVITY — a continuous "how busy right now" scalar. Every keystroke
 *     pumps it; it decays fast toward the mood's resting level. It drives only
 *     the fast jitter, so Sculpty shudders while you type and quickly settles to
 *     a slow bob/sway. At rest the color + slow sway carry the mood, not jitter.
 *
 * The squiggle artwork is embedded (the plugin must stay import-free); the path
 * data matches src/assets/logos/{peace,joy,excitement}.svg.
 */

// ---------------------------------------------------------------------------
// Squiggle artwork + per-mood tuning
// ---------------------------------------------------------------------------

const SHAPES = {
  sleeping: {
    fill: "#B4D3BA",
    d: "M284.395 124.51C275.806 109.855 263.906 100.571 249.598 96.8434C255.062 82.9293 259.855 71.9323 259.947 71.7007C261.522 68.1122 261.174 63.9912 259.044 60.7269C256.914 57.4625 253.256 55.4714 249.344 55.4714H170.975C167.966 55.4714 165.072 56.6522 162.919 58.7358C147.847 73.3445 141.781 91.5417 141.087 114.809C129.395 105.896 112.795 101.011 91.8894 106.822C75.6369 111.336 63.2276 120.736 55.9348 134.025C47.7623 148.935 46.6742 168.174 52.8325 188.2C53.8975 191.649 55.2403 194.891 56.8378 197.947C46.4658 220.728 41.8123 256.613 41.2798 261.012C40.8863 264.184 41.8355 267.379 43.8728 269.833C45.9102 272.287 48.8736 273.792 52.0685 273.977C55.0782 274.162 125.714 278.422 141.434 279.07C141.596 279.07 141.758 279.07 141.897 279.07C146.875 279.07 151.32 275.875 152.894 271.106C156.344 260.595 159.284 250.107 161.715 239.898C166.345 250.339 172.689 259.576 181.857 266.962C191.534 274.764 200.887 279.116 210.449 280.274C212 280.459 213.551 280.552 215.079 280.552C235.522 280.552 254.738 264.438 257.539 243.949C258.743 235.151 257.725 227.627 255.479 220.473C262.448 217.163 269.162 212.37 275.667 206.027C297.499 184.727 300.926 152.755 284.395 124.556V124.51ZM169.656 165.349C179.588 143.957 193.965 131.062 204.545 126.038C208.643 124.093 212.556 122.542 216.33 121.315C214.686 126.616 213.32 131.687 212.347 136.132C208.481 154.236 211.236 178.939 219.015 196.21C219.872 198.086 220.705 199.891 221.539 201.628C189.242 194.451 176.231 178.453 169.656 165.372V165.349ZM175.976 78.6231H231.934C229.896 83.6238 227.581 89.4349 225.266 95.5701C215.635 96.8203 205.356 99.9921 194.59 105.109C183.732 110.271 173.36 118.976 164.493 130.02C162.942 104.622 166.507 89.6896 175.976 78.6231ZM76.2388 145.138C80.4988 137.336 87.861 131.965 98.0709 129.117C102.261 127.959 106.035 127.45 109.438 127.45C126.177 127.45 133.701 139.512 135.878 143.841C136.734 145.555 137.66 147.569 138.586 149.676C115.504 148.518 90.6855 158.01 73.2986 174.841C70.9371 163.404 71.9095 153.009 76.2388 145.115V145.138ZM144.49 173.73C141.92 186.927 133.979 197.576 123.214 201.396C112.355 205.263 99.7609 204.73 90.3845 200.007C88.3935 199.012 86.5645 197.808 84.8976 196.488C99.0432 179.286 124.371 169.655 144.513 173.73H144.49ZM133.516 255.502C116.199 254.599 83.902 252.677 66.0753 251.612C67.8348 241.426 70.5667 228.229 74.1552 217.255C76.0073 218.482 77.9058 219.663 79.9431 220.682C88.4398 224.942 98.2098 227.118 108.119 227.118C115.805 227.118 123.561 225.821 130.923 223.205C135.16 221.7 139.119 219.617 142.8 217.07C140.6 229.271 137.475 242.328 133.493 255.502H133.516ZM234.596 240.777C233.277 250.432 222.881 258.419 213.227 257.261C208.088 256.636 202.577 253.904 196.35 248.904C185.005 239.759 179.518 224.918 175.722 206.999C187.112 215.102 200.98 220.89 217.533 224.455C222.21 225.451 226.771 225.96 231.216 225.96C231.772 225.96 232.327 225.937 232.883 225.914C234.689 231.054 235.314 235.522 234.596 240.777ZM259.484 189.404C255.039 193.756 250.64 196.998 246.149 199.197C244.181 195.284 242.167 191.233 240.129 186.672C235.152 175.652 231.887 155.51 234.99 140.924C236.333 134.65 238.694 126.871 241.472 118.791C251.034 120.69 258.72 126.478 264.416 136.201C275.551 155.186 273.653 175.582 259.507 189.404H259.484Z",
  },
  idle: {
    fill: "#F7B032",
    d: "M233.577 163.381C245.5 154.861 251.751 141.41 251.751 128.469C251.751 113.165 244.412 98.2324 232.582 89.4811C218.251 78.8777 199.729 78.924 184.38 84.1099C182.157 81.9337 179.819 79.8269 177.342 77.8127C151.805 56.6752 92.2593 56.6058 85.5454 56.6752C80.3825 56.7215 75.868 60.1943 74.4789 65.1719L62.5558 108.512C61.7455 111.475 62.139 114.67 63.6671 117.333C65.1951 120.018 67.7417 121.963 70.7052 122.75C70.983 122.82 80.7993 125.482 96.1951 130.413C59.6387 140.623 50.5864 162.432 50.5864 181.555C50.5864 213.111 79.7806 233.484 124.973 233.484C130.575 233.484 135.97 233.183 141.132 232.605C142.545 234.642 144.05 236.703 145.693 238.832C155.093 251.01 181.532 279.348 223.992 279.348C263.79 279.348 285.275 253.048 285.275 228.298C285.275 203.549 269.717 184.31 233.508 163.381H233.577ZM218.806 108.072C224.756 112.471 228.599 120.481 228.599 128.445C228.599 134.812 224.733 143.563 214.732 147.291C213.042 131.293 208.249 116.846 200.378 104.02C206.953 103.256 213.62 104.229 218.806 108.072ZM178.754 113.188C184.496 121.662 188.385 131.061 190.469 141.526C181.463 137.428 172.526 133.631 163.844 130.112C168.266 123.12 173.267 117.471 178.754 113.188ZM125.32 188.408C126.084 196.488 127.45 203.549 129.672 210.217C128.121 210.286 126.57 210.31 125.019 210.31C93.88 210.31 73.7843 199.012 73.7843 181.532C73.7843 158.242 101.52 150.277 130.205 148.24C125.829 162.085 124.162 175.721 125.32 188.385V188.408ZM141.92 121.616C118.976 113.096 99.5058 106.984 87.93 103.557L94.4356 79.85C135.622 80.8687 157.431 91.3796 162.548 95.6163C162.71 95.7552 162.895 95.8941 163.057 96.033C155 102.631 147.916 111.174 141.897 121.592L141.92 121.616ZM153.102 206.721C150.509 200.54 149.097 194.15 148.356 186.255C147.175 173.545 150.023 161.135 153.681 151.041C166.067 156.019 178.985 161.599 191.788 167.711C188.918 189.195 172.758 201.28 153.102 206.721ZM224.039 256.173C194.358 256.173 174.633 237.443 166.021 227.095C190.839 218.459 207.624 201.466 213.296 178.592C214.454 179.217 215.611 179.842 216.746 180.467C257.007 202.623 262.169 217.649 262.169 228.275C262.169 242.143 249.066 256.173 224.039 256.173Z",
  },
  active: {
    fill: "#EA8554",
    d: "M246.148 205.795C251.242 199.891 255.455 194.567 258.141 190.422C293.031 136.247 267.101 106.22 248.533 93.1391C230.753 80.6141 211.004 79.7574 192.112 89.7821C191.974 87.5596 191.765 85.3601 191.441 83.2302C189.08 68.2511 181.926 56.9299 170.79 50.4937C144.86 35.4915 102.817 42.4601 80.1279 79.8732C63.1346 107.91 66.2832 144.258 87.4438 164.423C91.2407 168.035 95.2228 171.021 99.0891 173.892C99.529 174.216 99.9457 174.54 100.386 174.864C74.9188 216.468 50.4938 264.508 50.2391 265.04C48.3175 268.814 48.6185 273.328 51.0031 276.824C53.1794 279.996 56.7679 281.871 60.5647 281.871C60.9352 281.871 61.3287 281.871 61.6992 281.825L176.485 270.434C192.83 279.209 219.709 293.031 239.596 293.031C267.564 293.031 287.081 275.134 287.081 249.505C287.081 227.28 273.305 212.671 246.148 205.841V205.795ZM176.856 244.366C176.624 244.25 176.416 244.134 176.184 244.018C164.84 238.115 154.144 232.535 149.537 220.774C147.43 215.403 146.064 210.078 144.605 204.429C142.059 194.567 139.419 184.426 132.891 174.679C142.128 168.266 152.268 160.348 162.525 150.254C162.965 153.032 163.566 155.88 164.4 158.797C172.341 186.533 186.139 206.837 203.688 217.533C193.941 227.558 184.148 237.258 176.879 244.319L176.856 244.366ZM235.175 112.077C242.977 117.564 266.73 134.303 238.647 177.897C235.267 183.13 228.414 191.186 220.172 200.169C199.243 190.978 189.381 162.085 186.649 152.477C183.708 142.197 184.472 132.775 187.089 122.542C207.763 100.825 224.455 104.507 235.175 112.054V112.077ZM99.8763 91.8658C108.79 77.1645 125.69 66.0517 142.197 66.0517C148.009 66.0517 153.796 67.4408 159.144 70.5199C170.998 77.3728 170.165 98.4871 167.086 108.257C166.785 109.206 166.484 110.156 166.206 111.128C164.863 112.679 163.52 114.277 162.201 115.943C146.758 135.576 130.228 148.587 116.337 157.917C115.179 157.038 114.022 156.181 112.887 155.324C109.415 152.731 106.15 150.301 103.372 147.638C88.5551 133.539 89.9673 108.188 99.8763 91.8426V91.8658ZM116.545 192.761C118.976 197.924 120.458 203.642 122.148 210.217C123.722 216.283 125.32 222.534 127.936 229.201C131.525 238.369 136.988 245.107 143.124 250.408L80.6604 256.613C89.2959 240.36 102.585 215.936 116.545 192.761ZM239.55 269.833C228.576 269.833 211.791 262.493 198.317 255.71C206.258 247.908 217.209 236.98 227.789 225.868C263.859 230.498 263.883 243.764 263.883 249.459C263.883 262.216 254.784 269.833 239.55 269.833Z",
  },
};

// Per-mood tuning.
//   energy — slow-ambient intensity (bob/sway amplitude & speed).
//   rest   — activity (fast jitter) decays toward this; ~0 so a resting mood
//            shows only slow ambient, not constant jitter.
//   max    — the limit: how high a typing burst can push activity in this mood.
const MOOD = {
  sleeping: { energy: 0.12, rest: 0.0, max: 0.4 },
  idle: { energy: 0.5, rest: 0.03, max: 0.8 },
  active: { energy: 1.0, rest: 0.12, max: 1.3 },
};

// Mood selection from idleness + sustained typing.
const SLEEP_AFTER_MS = 6000; // no input this long → drift to sleep
const ACTIVE_AFTER_S = 20; // continuous typing this long → "very active"
const ENGAGE_GAP_MS = 2500; // a typing gap longer than this breaks "continuous"
const KEY_PUMP = 0.3; // activity added per keystroke (only typing stirs jitter)

// Motion tuning (viewBox-336 units, so it scales with SIZE).
const DECAY_TAU = 0.4; // fast settle
const ENERGY_TAU = 0.45; // how quickly slow-ambient adapts on a mood change
const JIT_U = 13; // max jitter translate at activity 1
const JIT_DEG = 4; // max jitter rotation at activity 1
const JIT_SMOOTH = 0.6; // higher = smoother/slower shudder (less strobe)
const MOOD_DUR = 600; // mood crossfade ms

// Cursor-avoidance: Sculpty slides away from the pointer so it never obstructs
// what's underneath. (Position transform on the container; motion lives on the
// inner <g>, so the two never fight.)
const REPEL_RADIUS = 130;
const REPEL_MAX = 96;
const REPEL_EASE = 0.18;

const SIZE = 96;
const VIEWBOX = 336;
const SVG_NS = "http://www.w3.org/2000/svg";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const lerp = (a, b, t) => a + (b - a) * t;
const easeInOut = (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
const reducedMotion = () => typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;

// ---------------------------------------------------------------------------
// Plugin entry
// ---------------------------------------------------------------------------

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

  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", `0 0 ${VIEWBOX} ${VIEWBOX}`);
  svg.setAttribute("width", String(SIZE));
  svg.setAttribute("height", String(SIZE));
  svg.style.overflow = "visible";
  // The <g> we transform for motion; two stacked paths we crossfade on mood.
  const g = document.createElementNS(SVG_NS, "g");
  g.style.transformBox = "fill-box";
  g.style.transformOrigin = "center";
  const layers = [0, 1].map(() => {
    const p = document.createElementNS(SVG_NS, "path");
    g.appendChild(p);
    return p;
  });
  svg.appendChild(g);
  el.appendChild(svg);
  document.body.appendChild(el);

  const calm = reducedMotion();

  // --- Mood (shape/color) ---
  let mood = "sleeping";
  let activeLayer = 0;
  const paintLayer = (i, name, opacity) => {
    layers[i].setAttribute("d", SHAPES[name].d);
    layers[i].setAttribute("fill", SHAPES[name].fill);
    layers[i].style.opacity = String(opacity);
  };
  paintLayer(0, "sleeping", 1);
  paintLayer(1, "sleeping", 0);
  let moodTo = "sleeping";
  let moodStart = performance.now();

  // --- Motion / activity ---
  let energy = MOOD.sleeping.energy;
  let energyTo = MOOD.sleeping.energy;
  let activity = MOOD.sleeping.rest;
  let restLevel = MOOD.sleeping.rest;
  let maxActivity = MOOD.sleeping.max;
  let jx = 0;
  let jy = 0;
  let jr = 0;
  // Start already-idle (asleep) so Sculpty wakes on your first keystroke/move,
  // rather than springing awake the instant it mounts.
  let lastActivityAt = performance.now() - SLEEP_AFTER_MS - 1000;
  let lastKeyAt = -Infinity; // last keystroke; drives the engagement timer
  let engagedFor = 0; // seconds of continuous typing so far
  let last = performance.now();
  let raf = 0;

  // --- Cursor avoidance ---
  let pointerX = -9999;
  let pointerY = -9999;
  let offsetX = 0;
  let offsetY = 0;

  const setMood = (name) => {
    restLevel = MOOD[name].rest;
    maxActivity = MOOD[name].max;
    energyTo = MOOD[name].energy;
    mood = name;
    if (SHAPES[name].d === SHAPES[moodTo].d) return;
    paintLayer(1 - activeLayer, name, 0);
    moodTo = name;
    moodStart = performance.now();
  };

  const pump = (amount) => {
    activity = Math.min(maxActivity, activity + amount);
    lastActivityAt = performance.now();
  };

  const onKey = () => {
    pump(KEY_PUMP);
    lastKeyAt = performance.now();
  };
  // Pointer motion only WAKES Sculpty and feeds cursor-avoidance — it never
  // pumps activity. (pointermove fires many times per sweep; pumping here would
  // flood activity far faster than it decays and spike it straight to `active`.)
  const onMove = (e) => {
    pointerX = e.clientX;
    pointerY = e.clientY;
    lastActivityAt = performance.now();
  };
  const onLeave = () => {
    pointerX = -9999;
    pointerY = -9999;
  };
  window.addEventListener("keydown", onKey, true);
  window.addEventListener("pointermove", onMove, true);
  document.addEventListener("mouseleave", onLeave);

  // Choose the mood. `active` requires *sustained* typing: the engagement timer
  // only accrues while keystrokes keep coming (gaps under ENGAGE_GAP_MS) and
  // resets on a real pause — so a stray key or a mouse sweep never tips it in,
  // and it falls back to `idle` once you stop.
  const updateMood = (now, dt) => {
    if (now - lastKeyAt < ENGAGE_GAP_MS) engagedFor += dt;
    else engagedFor = 0;

    const sinceActivity = now - lastActivityAt;
    let want;
    if (sinceActivity > SLEEP_AFTER_MS) want = "sleeping";
    else if (engagedFor > ACTIVE_AFTER_S) want = "active";
    else want = "idle";
    if (want !== mood) setMood(want);
  };

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
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;

    updateMood(now, dt);

    // Mood crossfade (exactly one shape once settled).
    const me = easeInOut(Math.min(1, (now - moodStart) / MOOD_DUR));
    const incoming = 1 - activeLayer;
    layers[activeLayer].style.opacity = String(1 - me);
    layers[incoming].style.opacity = String(me);
    if (me >= 1 && layers[activeLayer].getAttribute("d") !== SHAPES[moodTo].d) {
      activeLayer = incoming;
      paintLayer(1 - activeLayer, moodTo, 0);
    }

    // Ease the two drivers (frame-rate independent).
    energy += (energyTo - energy) * (1 - Math.exp(-dt / ENERGY_TAU));
    activity += (restLevel - activity) * (1 - Math.exp(-dt / DECAY_TAU));

    const t = now / 1000;
    // Slow ambient: delicate low-frequency bob + slow sway, growing with energy.
    const breathe = 1 + Math.sin(t * 0.9) * 0.01;
    const bob = Math.sin(t * lerp(1.5, 3.0, energy)) * lerp(6, 9, energy);
    const sway = Math.sin(t * lerp(0.9, 1.7, energy) + 0.7) * lerp(1.3, 4, energy);

    // Fast jitter: only while activity is high (mid-typing).
    if (!calm && activity > 0.001) {
      jx = lerp((Math.random() * 2 - 1) * activity * JIT_U, jx, JIT_SMOOTH);
      jy = lerp((Math.random() * 2 - 1) * activity * JIT_U, jy, JIT_SMOOTH);
      jr = lerp((Math.random() * 2 - 1) * activity * JIT_DEG, jr, JIT_SMOOTH);
    } else {
      jx = lerp(0, jx, JIT_SMOOTH);
      jy = lerp(0, jy, JIT_SMOOTH);
      jr = lerp(0, jr, JIT_SMOOTH);
    }

    const scale = breathe + activity * 0.05;
    g.style.transform =
      `translate(${jx.toFixed(2)}px, ${(bob + jy).toFixed(2)}px) ` +
      `rotate(${(sway + jr).toFixed(2)}deg) scale(${scale.toFixed(4)})`;

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
