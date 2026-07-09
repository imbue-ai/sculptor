/*
 * Demo-recorder cursor overlay.
 *
 * Headless Chromium paints no OS cursor, so a screen recording of a
 * Playwright-driven session shows the page reacting to an invisible mouse.
 * Injected with Playwright's add_init_script(), this overlay draws a
 * synthetic macOS-style cursor (arrow / pointing hand / I-beam), a press
 * animation, and a click ripple, all driven by the real mouse events the
 * automation dispatches.
 *
 * Constraints shaping this code:
 * - Init scripts run at document start, possibly before
 *   document.documentElement exists; DOM setup is deferred until the root
 *   element appears. Mouse listeners attach immediately so no events are
 *   lost while waiting.
 * - The overlay must be inert for the recorded app: it attaches directly to
 *   <html> (frameworks own #root / <body> content and may replace it
 *   wholesale), uses pointer-events:none, and must never affect layout,
 *   focus, or event delivery.
 * - The cursor position gets NO CSS transition: the driver already emits
 *   ~60Hz interpolated mousemove streams, so smoothing here would only add
 *   lag to the recording.
 * - No console output, ever; recordings are checked for a clean console.
 *
 * API (window.__demoCursor):
 *   show()        make the cursor visible at its current position
 *   hide()        hide the entire overlay
 *   moveTo(x, y)  place the cursor without a real mouse event, e.g. to
 *                 restore its position right after a navigation
 */
(() => {
  'use strict';

  // Iframes receive the same init script; only the top frame draws a cursor.
  if (window.top !== window) return;

  // Guard against the script being injected twice into the same document.
  if (window.__demoCursorInstalled) return;
  window.__demoCursorInstalled = true;

  const PRESS_SCALE = 0.82; // cursor shrink while a mouse button is held
  const PRESS_MS = 90;
  const RIPPLE_FROM_PX = 12; // ripple start / mid / end diameters
  const RIPPLE_MID_PX = 51;
  const RIPPLE_TO_PX = 64;
  const RIPPLE_MS = 500;
  const RIPPLE_START_OPACITY = 0.45;
  const RIPPLE_MID_OPACITY = 0.42;
  const RIPPLE_MID_OFFSET = 0.45; // fraction of RIPPLE_MS where the mid keyframe sits

  // -------------------------------------------------------------------------
  // Glyph artwork. Inline SVG keeps the cursor crisp at any devicePixelRatio.
  // Each glyph declares a hotspot: the viewBox point that must sit exactly on
  // the mouse coordinates (arrow tip, index fingertip, I-beam center). The
  // SVG element is offset by -hotspot so that point lands on the overlay
  // origin, which in turn is translated to the mouse position.
  // -------------------------------------------------------------------------
  const SHADOW = 'filter:drop-shadow(0 1px 1.2px rgba(0,0,0,0.4)) drop-shadow(0 3px 6px rgba(0,0,0,0.18));';
  const IBEAM_D =
    'M 5.5 2.5 C 7.1 2.5 8.3 3 9 3.9 C 9.7 3 10.9 2.5 12.5 2.5 ' +
    'M 9 3.9 L 9 18.1 ' +
    'M 5.5 19.5 C 7.1 19.5 8.3 19 9 18.1 C 9.7 19 10.9 19.5 12.5 19.5';

  const GLYPHS = {
    // Classic arrow: black body, white outline, soft shadow. The path's tip
    // vertex is at (2,2) so the hotspot matches it exactly.
    arrow: {
      hotspot: [2, 2],
      svg:
        `<svg data-glyph="arrow" xmlns="http://www.w3.org/2000/svg" width="26" height="26" viewBox="0 0 26 26" style="${SHADOW}">` +
        '<path d="M 2 2 L 2 17.7 L 5.8 14.2 L 8 19.6 L 10.6 18.5 L 8.3 13.2 L 12.6 13.2 Z" ' +
        'fill="#000" stroke="#fff" stroke-width="1.4" stroke-linejoin="round"/>' +
        '</svg>',
    },
    // Pointing hand (link cursor): white glove with a black outline, index
    // finger extended. Hotspot at the fingertip.
    hand: {
      hotspot: [9.7, 1.2],
      svg:
        `<svg data-glyph="hand" xmlns="http://www.w3.org/2000/svg" width="26" height="26" viewBox="0 0 26 26" style="${SHADOW}">` +
        '<path d="M 8 12 L 8 3.4 C 8 2.45 8.75 1.7 9.7 1.7 C 10.65 1.7 11.4 2.45 11.4 3.4 L 11.4 9.6 ' +
        'C 11.7 8.9 12.6 8.5 13.3 8.7 C 14.1 8.9 14.6 9.5 14.6 10.3 ' +
        'C 14.9 9.5 15.9 9.2 16.6 9.5 C 17.3 9.8 17.7 10.4 17.7 11.2 ' +
        'C 18 10.6 18.9 10.4 19.5 10.8 C 20.1 11.2 20.4 11.8 20.4 12.5 ' +
        'L 20.4 16.4 C 20.4 19.2 18.4 21 15.5 21 L 11.8 21 C 9.6 21 8 20.1 6.8 18.4 ' +
        'C 6 17.2 5 15.5 4.1 14.1 C 3.4 13 3.5 11.9 4.4 11.4 C 5.2 10.9 6.3 11.2 7 12.2 ' +
        'C 7.3 12.6 7.7 12.4 8 12 Z" fill="#fff" stroke="#000" stroke-width="1.3" stroke-linejoin="round"/>' +
        '<path d="M 14.6 10.5 L 14.6 13.2 M 17.7 11.3 L 17.7 13.8" ' +
        'stroke="#000" stroke-width="1.1" stroke-linecap="round"/>' +
        '</svg>',
    },
    // Text I-beam: black bar with a white halo so it reads on both light and
    // dark backgrounds. Hotspot at the center of the bar.
    ibeam: {
      hotspot: [9, 11],
      svg:
        '<svg data-glyph="ibeam" xmlns="http://www.w3.org/2000/svg" width="18" height="22" viewBox="0 0 18 22">' +
        `<path d="${IBEAM_D}" fill="none" stroke="rgba(255,255,255,0.95)" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"/>` +
        `<path d="${IBEAM_D}" fill="none" stroke="#000" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>` +
        '</svg>',
    },
  };

  // Parked off-screen until the first moveTo()/mousemove reveals it.
  const state = {
    x: -100,
    y: -100,
    visible: false,
    pressed: false,
    glyph: 'arrow',
  };

  // DOM references; null until the document root exists and the overlay is
  // built. Every sync function tolerates the not-yet-built window.
  let rootEl = null; // fixed, viewport-covering, inert layer under <html>
  let holderEl = null; // translated to the mouse position (no transition)
  let pressEl = null; // scales around the hotspot while a button is held
  let rippleLayerEl = null; // static layer: ripples must not move with the cursor
  const glyphEls = Object.create(null);

  function syncPosition() {
    if (holderEl) holderEl.style.transform = `translate3d(${state.x}px,${state.y}px,0)`;
  }

  function syncVisibility() {
    if (rootEl) rootEl.style.visibility = state.visible ? 'visible' : 'hidden';
  }

  function syncPressed() {
    if (pressEl) pressEl.style.transform = state.pressed ? `scale(${PRESS_SCALE})` : 'scale(1)';
  }

  function syncGlyph() {
    for (const name in glyphEls) {
      glyphEls[name].style.display = name === state.glyph ? 'block' : 'none';
    }
  }

  function buildOverlay() {
    rootEl = document.createElement('div');
    rootEl.setAttribute('data-demo-cursor', '');
    rootEl.setAttribute('aria-hidden', 'true');
    rootEl.style.cssText =
      'position:fixed;inset:0;pointer-events:none;z-index:2147483647;visibility:hidden;';

    // Ripples live in their own non-translated layer so they stay anchored at
    // the click point while the cursor moves on. Painted before (= beneath)
    // the cursor holder.
    rippleLayerEl = document.createElement('div');
    rippleLayerEl.setAttribute('data-demo-cursor-part', 'ripples');
    rippleLayerEl.style.cssText = 'position:absolute;inset:0;overflow:hidden;';
    rootEl.appendChild(rippleLayerEl);

    holderEl = document.createElement('div');
    holderEl.setAttribute('data-demo-cursor-part', 'holder');
    holderEl.style.cssText = 'position:absolute;left:0;top:0;width:0;height:0;will-change:transform;';

    // The press wrapper is a zero-size box whose origin coincides with the
    // glyph hotspot, so transform-origin:0 0 makes the press scale pivot on
    // the exact mouse point (the arrow tip stays planted while shrinking).
    pressEl = document.createElement('div');
    pressEl.setAttribute('data-demo-cursor-part', 'press');
    pressEl.style.cssText =
      'position:absolute;left:0;top:0;width:0;height:0;transform-origin:0 0;' +
      `transition:transform ${PRESS_MS}ms ease-out;`;
    holderEl.appendChild(pressEl);

    const template = document.createElement('div');
    for (const name in GLYPHS) {
      template.innerHTML = GLYPHS[name].svg;
      const svg = template.firstElementChild;
      svg.style.position = 'absolute';
      svg.style.left = `${-GLYPHS[name].hotspot[0]}px`;
      svg.style.top = `${-GLYPHS[name].hotspot[1]}px`;
      svg.style.display = 'none';
      pressEl.appendChild(svg);
      glyphEls[name] = svg;
    }

    rootEl.appendChild(holderEl);
    document.documentElement.appendChild(rootEl);

    syncPosition();
    syncPressed();
    syncVisibility();
    syncGlyph();
    scheduleGlyphUpdate();
  }

  function installWhenReady() {
    if (document.documentElement) {
      buildOverlay();
      return;
    }
    // At document start <html> may not have been parsed yet; watch for it.
    const observer = new MutationObserver(() => {
      if (!document.documentElement) return;
      observer.disconnect();
      buildOverlay();
    });
    observer.observe(document, { childList: true });
  }

  // --- Glyph selection -------------------------------------------------------

  function isTextEntry(el) {
    if (el.isContentEditable) return true;
    const tag = el.tagName;
    if (tag === 'TEXTAREA') return true;
    if (tag === 'INPUT') {
      const type = (el.getAttribute('type') || 'text').toLowerCase();
      return ['text', 'search', 'url', 'tel', 'email', 'password', 'number'].indexOf(type) !== -1;
    }
    return false;
  }

  function glyphFor(cursorStyle, el) {
    if (cursorStyle === 'pointer') return 'hand';
    if (cursorStyle === 'text' || cursorStyle === 'vertical-text') return 'ibeam';
    // Text controls typically keep cursor:auto and rely on the browser to
    // render an I-beam; mirror that behavior for the common editable cases.
    if (cursorStyle === 'auto' && isTextEntry(el)) return 'ibeam';
    return 'arrow';
  }

  // Glyph picking does hit-testing + getComputedStyle, so it is throttled to
  // one lookup per frame instead of running for every mousemove event.
  let glyphUpdateQueued = false;

  function updateGlyphFromHover() {
    if (!rootEl || !document.documentElement) return;
    // The overlay itself is pointer-events:none, so it never occludes this
    // hit test. Outside the viewport this returns null; keep the last glyph.
    const el = document.elementFromPoint(state.x, state.y);
    if (!el) return;
    const next = glyphFor(getComputedStyle(el).cursor, el);
    if (next !== state.glyph) {
      state.glyph = next;
      syncGlyph();
    }
  }

  function scheduleGlyphUpdate() {
    if (glyphUpdateQueued) return;
    glyphUpdateQueued = true;
    requestAnimationFrame(() => {
      glyphUpdateQueued = false;
      updateGlyphFromHover();
    });
  }

  // --- Click ripple ------------------------------------------------------------

  function sizeKeyframe(diameterPx) {
    return {
      width: `${diameterPx}px`,
      height: `${diameterPx}px`,
      marginLeft: `${-diameterPx / 2}px`,
      marginTop: `${-diameterPx / 2}px`,
    };
  }

  function spawnRipple(x, y) {
    if (!rippleLayerEl) return;
    const ripple = document.createElement('div');
    // Dual-tone ring: a bright core stroke with a darker edge on both sides.
    // The dark edge is what reads on light backgrounds; the white core (plus
    // a soft glow) is what reads on dark ones. The ring thickness stays
    // constant because the box grows via width/height (a scale transform
    // would fatten the stroke as it expands).
    ripple.style.cssText =
      'position:absolute;border-radius:50%;pointer-events:none;' +
      `left:${x}px;top:${y}px;` +
      `width:${RIPPLE_FROM_PX}px;height:${RIPPLE_FROM_PX}px;` +
      `margin-left:${-RIPPLE_FROM_PX / 2}px;margin-top:${-RIPPLE_FROM_PX / 2}px;` +
      `opacity:${RIPPLE_START_OPACITY};` +
      'border:2px solid rgba(255,255,255,0.98);' +
      'box-shadow:0 0 0 1px rgba(0,0,0,0.45),inset 0 0 0 1px rgba(0,0,0,0.28),0 0 14px rgba(255,255,255,0.4);';
    if (typeof ripple.animate !== 'function') return; // Web Animations API required
    rippleLayerEl.appendChild(ripple);
    // Two phases: race out to most of the final size while staying nearly
    // fully drawn (so even a brief click registers on camera), then drift the
    // last few pixels while fading away.
    const animation = ripple.animate(
      [
        {
          ...sizeKeyframe(RIPPLE_FROM_PX),
          opacity: RIPPLE_START_OPACITY,
          easing: 'cubic-bezier(0.16,0.6,0.35,1)',
        },
        {
          ...sizeKeyframe(RIPPLE_MID_PX),
          opacity: RIPPLE_MID_OPACITY,
          offset: RIPPLE_MID_OFFSET,
          easing: 'cubic-bezier(0.3,0.3,0.6,1)',
        },
        { ...sizeKeyframe(RIPPLE_TO_PX), opacity: 0 },
      ],
      { duration: RIPPLE_MS, fill: 'forwards' }
    );
    const cleanup = () => ripple.remove();
    animation.onfinish = cleanup;
    animation.oncancel = cleanup;
  }

  // --- Real mouse tracking ------------------------------------------------------

  function reveal() {
    if (!state.visible) {
      state.visible = true;
      syncVisibility();
    }
  }

  function onMouseMove(event) {
    state.x = event.clientX;
    state.y = event.clientY;
    reveal();
    syncPosition();
    scheduleGlyphUpdate();
  }

  function onMouseDown(event) {
    state.x = event.clientX;
    state.y = event.clientY;
    reveal();
    syncPosition();
    // The pressed pose is held until mouseup, so drags keep the cursor
    // visually "gripping" whatever it picked up.
    state.pressed = true;
    syncPressed();
    spawnRipple(event.clientX, event.clientY);
    scheduleGlyphUpdate();
  }

  function onMouseUp() {
    state.pressed = false;
    syncPressed();
  }

  // Capture phase so page code calling stopPropagation() cannot starve the
  // overlay of events; passive because the overlay never preventDefault()s.
  const LISTENER_OPTIONS = { capture: true, passive: true };
  window.addEventListener('mousemove', onMouseMove, LISTENER_OPTIONS);
  window.addEventListener('mousedown', onMouseDown, LISTENER_OPTIONS);
  window.addEventListener('mouseup', onMouseUp, LISTENER_OPTIONS);

  // --- Public API -----------------------------------------------------------------

  window.__demoCursor = {
    show() {
      state.visible = true;
      syncVisibility();
    },
    hide() {
      state.visible = false;
      syncVisibility();
    },
    moveTo(x, y) {
      state.x = Number(x);
      state.y = Number(y);
      state.visible = true;
      syncVisibility();
      syncPosition();
      scheduleGlyphUpdate();
    },
  };

  installWhenReady();
})();
