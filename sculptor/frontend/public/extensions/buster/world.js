// Buster's world: a tiny platformer engine that treats the host page's DOM
// as terrain. React-free on purpose - the plugin's React wrapper (main.js)
// mounts it, and a plain harness page can import it directly for testing.
//
// How the DOM becomes terrain: while he falls, document.elementsFromPoint is
// probed just under his wheels; the first sufficiently large element whose
// top edge crosses this frame's drop becomes his floor. While he stands on an
// element it is re-measured every frame, so he rides panels that move or
// scroll, and falls when his perch unmounts, shrinks, or slides out from
// under him. The viewport bottom is the ultimate floor.
//
// Controls: click him to drive (A/D or arrows, W/Space jump, Esc to
// release). S/down taps drop him through his current perch; holding S keeps
// the fall-through window open so he plummets to the viewport bottom. While
// driving, keys are only captured when the event target is not editable, so
// typing in the app is never hijacked; without control he never touches the
// keyboard at all.

'use strict';

// ---------------------------------------------------------------------------
// The rig: an inlined copy of buster.svg, which is the source-of-truth (see
// it for the joint reference). buster.svg keeps plain ids/classes; the copy
// here prefixes them (bs-*) so the embedded markup can't collide with the
// host page.
// ---------------------------------------------------------------------------
const VIEW_W = 260, VIEW_H = 320;
const H = 96;                       // display height, px
const W = H * VIEW_W / VIEW_H;      // 78
const FOOT_Y = 300 * (H / VIEW_H);  // wheel-bottom line, px from the svg top
const ROCK_PIVOT = { x: 118, y: 246 };
const WHEEL_R = 18 * (H / VIEW_H);

const GUY_SVG = `
<svg width="${W}" height="${H}" viewBox="0 0 260 320" fill="none" xmlns="http://www.w3.org/2000/svg">
  <rect x="58" y="246" width="132" height="18" rx="8" fill="#8A5A33"/>
  <path d="M66 255H182" stroke="#6D4527" stroke-width="2" stroke-linecap="round"/>
  <path d="M74 250.5H94" stroke="#6D4527" stroke-width="1.5" stroke-linecap="round" opacity="0.6"/>
  <path d="M140 259.5H162" stroke="#6D4527" stroke-width="1.5" stroke-linecap="round" opacity="0.6"/>
  <g transform="translate(92,282)">
    <g data-joint="wheelL">
      <circle r="18" fill="#B7AEA1"/>
      <circle r="5.5" fill="#7E766B"/>
      <circle cy="-10.5" r="2.8" fill="#7E766B"/>
      <path d="M-7 -16.5L-3 -9" stroke="#8F8578" stroke-width="2" stroke-linecap="round" fill="none"/>
    </g>
  </g>
  <g transform="translate(156,282)">
    <g data-joint="wheelR">
      <circle r="18" fill="#B7AEA1"/>
      <circle r="5.5" fill="#7E766B"/>
      <circle cy="-10.5" r="2.8" fill="#7E766B"/>
      <path d="M-7 -16.5L-3 -9" stroke="#8F8578" stroke-width="2" stroke-linecap="round" fill="none"/>
    </g>
  </g>
  <g data-joint="body">
    <g transform="translate(52,44)">
      <path d="M103.454 3.61361C121.524 12.5312 120.94 41.6833 117.978 52.6868C115.015 63.6904 107.821 70.0386 100.906 75.388C97.9926 106.013 134.582 64.3285 148.548 84.6428C162.514 104.957 153.627 133.736 144.739 135.005C128.703 137.296 125.232 138.624 117.845 148.001C110.459 157.379 120.69 173.484 113.322 184.73C102.996 200.492 20.5874 208.896 19.344 187.446C18.9618 180.851 19.465 174.645 22.2676 168.655C23.315 166.417 26.9455 158.371 23.1397 157.379C16.7512 155.714 0.917805 158.702 0.229106 148.748C-0.811812 133.703 1.18263 109.089 17.0262 101.84C27.9341 96.849 53.1464 99.2114 60.3123 90.9717C62.586 88.3571 62.6406 85.3365 63.0102 82.1206C59.8859 80.1425 57.3346 77.4172 54.7865 74.7714C46.0239 65.6729 45.514 50.5068 46.8776 39.144C49.4168 17.9833 55.7701 8.83934 71.3307 2.64402C80.8742 -1.1556 94.3401 -0.883824 103.454 3.61361Z" fill="#F50D00"/>
      <g stroke="#FCEFD4" stroke-width="4" stroke-linecap="round" fill="none">
        <path filter="url(#bs-scratch-a)" d="M53.1592 101.047H70.4064"/>
        <path filter="url(#bs-scratch-b)" d="M90.9717 99.2595C93.7012 99.2595 100.389 98.3314 103.73 97.2345C107.668 96.5354 110.678 96.1247 112.147 95.6959C112.879 95.451 113.582 95.1503 115.319 94.584"/>
      </g>
    </g>
    <g class="bs-face">
      <ellipse cx="124" cy="84" rx="7.5" ry="8.5" fill="#FFFFFF"/>
      <ellipse cx="150" cy="80" rx="7.5" ry="8.5" fill="#FFFFFF"/>
      <g data-joint="pupils">
        <circle cx="124" cy="86" r="3.4" fill="#1F1F1F"/>
        <circle cx="150" cy="82" r="3.4" fill="#1F1F1F"/>
      </g>
      <g transform="translate(137,103)">
        <g data-joint="mouth" transform="scale(0)">
          <ellipse rx="5.5" ry="6.5" fill="#1F1F1F"/>
        </g>
      </g>
    </g>
  </g>
  <defs>
    <filter id="bs-scratch-a" x="49.552" y="97.4397" width="24.4614" height="7.21429" filterUnits="userSpaceOnUse" color-interpolation-filters="sRGB">
      <feTurbulence type="fractalNoise" baseFrequency="0.16969696 0.16969696" numOctaves="3" seed="1005"/>
      <feDisplacementMap in="SourceGraphic" scale="3.2142861" xChannelSelector="R" yChannelSelector="G"/>
    </filter>
    <filter id="bs-scratch-b" x="87.3645" y="90.9768" width="31.5624" height="11.8901" filterUnits="userSpaceOnUse" color-interpolation-filters="sRGB">
      <feTurbulence type="fractalNoise" baseFrequency="0.16969696 0.16969696" numOctaves="3" seed="1005"/>
      <feDisplacementMap in="SourceGraphic" scale="3.2142861" xChannelSelector="R" yChannelSelector="G"/>
    </filter>
  </defs>
</svg>`;

const STYLE_CSS = `
@keyframes bs-blink {
  0%, 95%, 100% { transform: scaleY(1); }
  97% { transform: scaleY(0.08); }
}
.bs-face { animation: bs-blink 4.6s infinite; transform-box: fill-box; transform-origin: center; }
@keyframes bs-poof {
  from { opacity: 0.8; transform: translate(var(--px), var(--py)) scale(0.5); }
  to   { opacity: 0;   transform: translate(calc(var(--px) + var(--dx)), calc(var(--py) - 10px)) scale(1.6); }
}
.bs-poof {
  position: absolute; top: 0; left: 0;
  width: 8px; height: 8px; border-radius: 50%;
  background: #D9CCC5; pointer-events: none;
  animation: bs-poof 0.45s ease-out forwards;
}
.bs-bubble {
  position: absolute; top: 0; left: 0;
  background: #fff; color: #5c524d;
  border: 1px solid #EFE8E4; border-radius: 8px;
  padding: 4px 8px; font-size: 11px; white-space: nowrap;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
  box-shadow: 0 2px 10px rgba(60, 30, 20, 0.12);
  pointer-events: none; opacity: 0; transition: opacity 0.25s;
}`;

// Movement tuning (px/s, px/s^2, viewport space).
const MAX_SPEED = 150;
const ACCEL = 900;
const FRICTION = 500;   // low: the cart coasts
const GRAVITY = 2400;
const JUMP_V = 800;
const COYOTE = 0.09;
const JUMP_BUFFER = 0.12;

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const approach = (a, b, rate, dt) => b + (a - b) * Math.exp(-rate * dt);

const KEYMAP = {
  a: 'left', arrowleft: 'left',
  d: 'right', arrowright: 'right',
  w: 'jump', ' ': 'jump', arrowup: 'jump',
  s: 'crouch', arrowdown: 'crouch',
};

function isEditable(t) {
  return !!t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName || ''));
}

export function createWorld(root) {
  root.style.cssText = 'position:fixed;inset:0;pointer-events:none;overflow:hidden;';

  const style = document.createElement('style');
  style.dataset.busterPlugin = '';
  style.textContent = STYLE_CSS;
  document.head.appendChild(style);

  const guyEl = document.createElement('div');
  guyEl.style.cssText = 'position:absolute;top:0;left:0;pointer-events:auto;cursor:pointer;will-change:transform;';
  guyEl.title = 'Buster — click to drive';
  guyEl.innerHTML = GUY_SVG;
  root.appendChild(guyEl);

  const shadowEl = document.createElement('div');
  shadowEl.style.cssText = 'position:absolute;top:0;left:0;width:64px;height:9px;border-radius:50%;' +
    'background:rgba(60,20,10,0.13);filter:blur(2px);pointer-events:none;will-change:transform,opacity;';
  root.insertBefore(shadowEl, guyEl);

  const markerEl = document.createElement('div');
  markerEl.style.cssText = 'position:absolute;top:0;left:0;color:#F50D00;font-size:16px;line-height:1;' +
    'display:none;pointer-events:none;text-shadow:0 1px 3px rgba(60,20,10,0.15);will-change:transform;';
  markerEl.textContent = '▾';
  root.appendChild(markerEl);

  const bubbleEl = document.createElement('div');
  bubbleEl.className = 'bs-bubble';
  bubbleEl.innerHTML = 'a/d drive · space jump · s drop through (hold to plummet) · esc releases';
  root.appendChild(bubbleEl);

  const joint = {};
  for (const el of guyEl.querySelectorAll('[data-joint]')) joint[el.dataset.joint] = el;

  // -------------------------------------------------------------------------
  // State
  // -------------------------------------------------------------------------
  const floorY = () => window.innerHeight - 2;

  const state = {
    x: window.innerWidth * (0.2 + 0.5 * Math.random()),  // container left, px
    vx: 0,
    feetY: floorY(),     // wheel-bottom line, viewport px (y down)
    vy: 0,               // px/s, positive = up
    grounded: true,
    surface: null,       // DOM element he's standing on; null = viewport floor
    facing: 1,
    coyote: 0,
    t: Math.random() * 10,
  };

  let controlled = false;
  let disposed = false;
  let jumpQueued = false;
  let dropQueued = false;
  let jumpBuf = 0;
  let dropTimer = 0;   // while >0, landing probes are off: he falls through terrain
  let ax = 0;
  const held = { left: false, right: false, jump: false, crouch: false };

  // Pose springs: rock = unstrapped-cargo wobble from acceleration, gap =
  // daylight from the deck while airborne.
  let rock = 0, rockV = 0, gap = 0, gapV = 0;
  let mouth = 0, wheelAngle = 0;
  let pupilX = 0, pupilY = 0;

  // AI
  let aiMode = 'idle', aiT = Math.random(), aiDir = 1, aiHop = 0, aiDrop = 0;

  let bubbleTimer = 0;

  // -------------------------------------------------------------------------
  // DOM terrain
  // -------------------------------------------------------------------------
  // Find a landing surface whose top edge lies within this frame's fall span.
  function probeLanding(feetX, fromY, toY) {
    const px = clamp(feetX, 1, window.innerWidth - 1);
    const py = clamp(toY, 0, window.innerHeight - 1);
    guyEl.style.pointerEvents = 'none';   // don't land on himself
    const stack = document.elementsFromPoint(px, py);
    guyEl.style.pointerEvents = 'auto';
    for (const el of stack) {
      if (root.contains(el)) continue;
      const r = el.getBoundingClientRect();
      if (r.width < 70 || r.height < 18) continue;    // too small to perch on
      if (r.top < 24) continue;                       // window-chrome top edge
      if (r.top > floorY() - 24) continue;            // effectively the floor
      if (r.top >= fromY - 2 && r.top <= toY + 2) return { el, top: r.top };
    }
    return null;
  }

  function fall() {
    state.grounded = false;
    state.surface = null;
  }

  function land(top, el) {
    state.feetY = top;
    state.vy = 0;
    state.grounded = true;
    state.surface = el;
    dropTimer = 0;
    spawnPoof();
  }

  // -------------------------------------------------------------------------
  // Input
  // -------------------------------------------------------------------------
  function onKeyDown(e) {
    if (!controlled || disposed) return;
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    if (isEditable(e.target)) return;   // never steal typing
    if (e.key === 'Escape') {
      release();
      e.preventDefault();
      e.stopPropagation();
      return;
    }
    const act = KEYMAP[e.key.toLowerCase()];
    if (!act) return;
    e.preventDefault();
    e.stopPropagation();
    if (act === 'jump' && !e.repeat) jumpQueued = true;
    if (act === 'crouch' && !e.repeat) dropQueued = true;   // drop through a perch
    held[act] = true;
  }
  function onKeyUp(e) {
    if (!controlled) return;
    const act = KEYMAP[e.key.toLowerCase()];
    if (act) held[act] = false;
  }
  function onBlur() {
    for (const k in held) held[k] = false;
  }
  function takeControl() {
    controlled = true;
    markerEl.style.display = 'block';
    bubbleEl.style.opacity = '1';
    bubbleTimer = 3.2;
  }
  function release() {
    controlled = false;
    markerEl.style.display = 'none';
    bubbleEl.style.opacity = '0';
    for (const k in held) held[k] = false;
  }
  guyEl.addEventListener('pointerdown', takeControl);
  window.addEventListener('keydown', onKeyDown, true);
  window.addEventListener('keyup', onKeyUp, true);
  window.addEventListener('blur', onBlur);

  // -------------------------------------------------------------------------
  // Wandering
  // -------------------------------------------------------------------------
  function aiInput(dt) {
    aiT -= dt;
    if (aiT <= 0) {
      const r = Math.random();
      // Perched on an element: fair odds of dropping back down through it,
      // so he never homesteads the top of a panel.
      if (state.surface && r < 0.28) {
        aiMode = 'idle'; aiT = 0.6 + Math.random();
        aiDrop = Math.random() < 0.5 ? 2 : 1;   // 2 = all the way down
      }
      else if (r < 0.4) { aiMode = 'idle'; aiT = 1 + Math.random() * 2.2; }
      else if (r < 0.86) {
        aiMode = 'walk';
        aiT = 0.9 + Math.random() * 1.8;
        aiDir = state.x < 120 ? 1
          : state.x > window.innerWidth - W - 120 ? -1
          : Math.random() < 0.5 ? -1 : 1;
      } else { aiMode = 'hop'; aiT = 0.35; aiHop = 1; }
    }
    if (aiMode === 'walk') {
      if (state.x < 16 && aiDir < 0) aiDir = 1;
      if (state.x > window.innerWidth - W - 16 && aiDir > 0) aiDir = -1;
    }
    const hop = aiHop; aiHop = 0;
    const drop = aiDrop; aiDrop = 0;
    return {
      left: aiMode === 'walk' && aiDir < 0,
      right: aiMode === 'walk' && aiDir > 0,
      // Hold jump through the hop window so AI hops get full height.
      jumpHeld: aiMode === 'hop', jumpPressed: hop > 0,
      dropPressed: drop > 0, dropAll: drop === 2,
      crouch: false, throttle: 0.28,   // an unhurried amble when unsupervised
    };
  }

  function playerInput() {
    const jp = jumpQueued;
    const dp = dropQueued;
    jumpQueued = false;
    dropQueued = false;
    return {
      left: held.left, right: held.right,
      jumpHeld: held.jump, jumpPressed: jp,
      dropPressed: dp, dropAll: false,   // holding S is the player's plummet
      crouch: held.crouch, throttle: 1,
    };
  }

  // -------------------------------------------------------------------------
  // Physics
  // -------------------------------------------------------------------------
  function physics(dt, input) {
    const s = state;
    const prevVx = s.vx;
    const move = (input.right ? 1 : 0) - (input.left ? 1 : 0);

    const cap = MAX_SPEED * input.throttle * (input.crouch && s.grounded ? 0.45 : 1);
    if (move !== 0) {
      // Acceleration never pushes past the cap; if already over it (the cap
      // shrank, e.g. control was released), skip accel and let the bleed
      // below settle it — accel would outrun the bleed and run away.
      const hadRoom = Math.abs(s.vx) <= cap;
      if (move * s.vx <= cap) s.vx += move * ACCEL * dt;
      if (hadRoom) s.vx = clamp(s.vx, -cap, cap);
      s.facing = move;
    } else {
      s.vx -= Math.sign(s.vx) * Math.min(Math.abs(s.vx), FRICTION * dt);
    }
    if (Math.abs(s.vx) > cap) {
      s.vx = Math.sign(s.vx) * Math.max(cap, Math.abs(s.vx) - FRICTION * 1.5 * dt);
    }
    s.x += s.vx * dt;
    const minX = 4, maxX = window.innerWidth - W - 4;
    if (s.x < minX) { s.x = minX; s.vx = Math.max(0, s.vx); }
    if (s.x > maxX) { s.x = maxX; s.vx = Math.min(0, s.vx); }
    const feetX = s.x + W / 2;

    // Drop through the current perch (S / down arrow). Real app DOM is a
    // dense stack of nested containers, so a positional nudge alone just
    // lands him on the next inner element a few px down; instead, disable
    // landing probes for a window. A tap punches through the perch; holding
    // S keeps the window open so he plummets to the viewport bottom.
    if (input.dropPressed && s.grounded && s.surface) {
      s.feetY += 8;
      fall();
      dropTimer = input.dropAll ? Infinity : 0.28;
    }
    if (!s.grounded && input.crouch) dropTimer = Math.max(dropTimer, 0.06);
    dropTimer = Math.max(0, dropTimer - dt);

    s.coyote = s.grounded ? COYOTE : s.coyote - dt;
    if (input.jumpPressed) jumpBuf = JUMP_BUFFER;
    jumpBuf -= dt;
    if (jumpBuf > 0 && s.coyote > 0) {
      s.vy = JUMP_V;
      fall();
      s.coyote = 0;
      jumpBuf = 0;
    }
    if (!input.jumpHeld && s.vy > 0) s.vy *= Math.pow(0.02, dt * 6);

    if (!s.grounded) {
      // Crouch fast-fall only bites on the way down, so holding S through an
      // S+Space launch doesn't stunt the big jump.
      s.vy -= (input.crouch && s.vy < 0 ? GRAVITY * 1.8 : GRAVITY) * dt;
      const drop = -s.vy * dt;   // px downward this frame
      if (drop > 0) {
        const hit = dropTimer > 0 ? null : probeLanding(feetX, s.feetY, s.feetY + drop);
        if (hit) {
          land(hit.top, hit.el);
        } else if (s.feetY + drop >= floorY()) {
          land(floorY(), null);
        }
      }
      if (!s.grounded) s.feetY += drop;
    } else if (s.surface) {
      // Ride the perch; fall when it unmounts, shrinks, jumps, or slides away.
      const el = s.surface;
      const r = el.isConnected ? el.getBoundingClientRect() : null;
      if (!r || r.width < 10 ||
          feetX < r.left - 8 || feetX > r.right + 8 ||
          Math.abs(r.top - s.feetY) > 90) {
        fall();
      } else {
        s.feetY = r.top;
      }
    } else {
      s.feetY = floorY();
    }

    s.t += dt;
    // Guard the zero-length frame: a dt of 0 (coarse timer resolution) would
    // make ax NaN and permanently corrupt the pose springs.
    ax = dt > 0 ? (s.vx - prevVx) / dt : 0;
  }

  // -------------------------------------------------------------------------
  // Pose + render
  // -------------------------------------------------------------------------
  function pose(dt) {
    const s = state;
    const rockTarget = clamp(-ax * 0.028, -14, 14);
    rockV += (-90 * (rock - rockTarget) - 7 * rockV) * dt;
    rock += rockV * dt;

    const gapTarget = s.grounded ? 0 : 22;
    gapV += (-120 * (gap - gapTarget) - 9 * gapV) * dt;
    gap += gapV * dt;
    if (gap < -4) { gap = -4; gapV = Math.max(0, gapV); }

    wheelAngle += (s.vx * dt / WHEEL_R) * 57.3;

    const awed = !s.grounded || Math.abs(s.vx) > 0.85 * MAX_SPEED;
    mouth = approach(mouth, awed ? 1 : 0, 14, dt);

    pupilX = approach(pupilX, s.facing * (1 + 2 * Math.min(1, Math.abs(s.vx) / MAX_SPEED)), 12, dt);
    pupilY = approach(pupilY, s.grounded ? 0 : s.vy > 0 ? -1.5 : 1.5, 12, dt);
  }

  function render() {
    const s = state;
    const y = s.feetY - FOOT_Y;
    guyEl.style.transform = `translate3d(${s.x.toFixed(1)}px, ${y.toFixed(1)}px, 0)`;

    const { x: px, y: py } = ROCK_PIVOT;
    const lift = Math.max(0, gap);
    const squash = 1 + Math.min(0, gap) / 45;
    const sx = 1 + (1 - squash) * 0.8;
    joint.body.setAttribute('transform',
      `translate(0,${(-lift).toFixed(2)}) ` +
      `rotate(${rock.toFixed(2)},${px},${py}) ` +
      `translate(${px},${py}) scale(${sx.toFixed(3)},${squash.toFixed(3)}) translate(${-px},${-py})`);
    joint.wheelL.setAttribute('transform', `rotate(${(wheelAngle % 360).toFixed(1)})`);
    joint.wheelR.setAttribute('transform', `rotate(${((wheelAngle + 137) % 360).toFixed(1)})`);
    joint.pupils.setAttribute('transform', `translate(${pupilX.toFixed(2)},${pupilY.toFixed(2)})`);
    joint.mouth.setAttribute('transform', `scale(${mouth.toFixed(3)})`);

    if (s.grounded) {
      shadowEl.style.opacity = '1';
      shadowEl.style.transform = `translate3d(${(s.x + W / 2 - 32).toFixed(1)}px, ${(s.feetY - 5).toFixed(1)}px, 0)`;
    } else {
      shadowEl.style.opacity = '0';
    }

    if (controlled) {
      const bobble = 2.5 * Math.sin(s.t * 5);
      markerEl.style.transform =
        `translate3d(${(s.x + W / 2 - 5).toFixed(1)}px, ${(y - 18 + bobble).toFixed(1)}px, 0)`;
      if (bubbleTimer > 0) {
        bubbleEl.style.transform =
          `translate3d(${clamp(s.x + W / 2 - 110, 8, window.innerWidth - 240).toFixed(1)}px, ${(y - 46).toFixed(1)}px, 0)`;
      }
    }
  }

  function spawnPoof() {
    const feetX = state.x + W / 2;
    for (let i = 0; i < 3; i++) {
      const p = document.createElement('div');
      p.className = 'bs-poof';
      p.style.setProperty('--px', `${feetX + (i - 1) * 12}px`);
      p.style.setProperty('--py', `${state.feetY - 6}px`);
      p.style.setProperty('--dx', `${(i - 1) * 22}px`);
      root.appendChild(p);
      p.addEventListener('animationend', () => p.remove());
    }
  }

  // -------------------------------------------------------------------------
  // Main loop
  // -------------------------------------------------------------------------
  let last = performance.now();
  let raf = 0;
  function frame(now) {
    if (disposed) return;
    const dt = Math.min(0.033, (now - last) / 1000);
    last = now;
    if (bubbleTimer > 0) {
      bubbleTimer -= dt;
      if (bubbleTimer <= 0) bubbleEl.style.opacity = '0';
    }
    physics(dt, controlled ? playerInput() : aiInput(dt));
    pose(dt);
    render();
    raf = requestAnimationFrame(frame);
  }
  raf = requestAnimationFrame(frame);

  const world = { state, takeControl, release, get controlled() { return controlled; } };
  if (window.__BUSTER_DEBUG) window.__buster = world;

  return function dispose() {
    disposed = true;
    cancelAnimationFrame(raf);
    window.removeEventListener('keydown', onKeyDown, true);
    window.removeEventListener('keyup', onKeyUp, true);
    window.removeEventListener('blur', onBlur);
    style.remove();
    root.replaceChildren();
    if (window.__buster === world) delete window.__buster;
  };
}
