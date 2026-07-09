# Sculptor guys

The Sculptor logo blob, rigged three ways, plus a playground where the whole
cast wanders around and you can take control of any of them.

- `index.html` — the playground. Open it directly in a browser (`file://`
  works, no server needed). Everyone walks around on their own; **left-click a
  guy to take control**: **A/D** or **←/→** to move, **W/Space** to jump,
  **S** to crouch (and fast-fall in the air).
- `sculptor-guy.svg` — the original: big bust, stubby noodle limbs.
- `sculptor-guy-tall.svg` — normal proportions: the logo as the bust, plus a
  pelvis and thick two-segment limbs with mannequin ball joints.
- `sculptor-guy-cart.svg` — no limbs at all: the sculpture riding a wheeled
  dolly, the way sculptures actually get around.

All three assets are viewable standalone (they blink).

## The rigs

Every posable joint is a `<g data-joint="...">` group. Each one sits inside a
positioning wrapper (`<g transform="translate(x,y)">`) that places its pivot,
so posing a joint is just setting a rotation on the group:

```js
svg.querySelector('[data-joint="armL"]').setAttribute('transform', 'rotate(35)');
```

Rotation sign: SVG `rotate()` is clockwise, so on a downward-hanging limb a
positive angle swings the tip toward screen-left. Each SVG's header comment
lists its joints and pivot coordinates.

### Walkers (`sculptor-guy.svg`, `sculptor-guy-tall.svg`)

Both share the same joint set: `body` (lean/bob/squash), `armL/R` + `elbowL/R`,
`thighL/R` + `calfL/R` + `footL/R`, and translate-only `pupils`. The tall guy
adds a root-level pelvis under the bust and ball-joint discs at every pivot.

Design decisions worth knowing before you re-pose them:

- **Noodle limbs.** Limbs are stroked paths with round linecaps. The near
  (left) limbs share the body fill (`#F50D00`) so the shoulder/hip overlaps are
  seamless; the far (right) limbs are darker (`#C90B00`) and drawn *behind*
  the torso. Keep that z-order: far limbs → body → near limbs.
- **Arms are parented inside `body`**, so torso lean and squash carry them
  along. Legs live at the root so they stay planted.
- **The silhouette has blind spots.** A raised near arm disappears against the
  torso's left edge past ~140°, and a raised far arm hides behind the logo's
  top-right curl past horizontal. The jump poses (one arm up-left, one
  out-down-right) are shaped around this — check poses against the silhouette,
  not just the joint angles.
- On the tall guy, socket discs (shoulders/hips, low contrast) sit on body
  mass while hinge discs (elbows/knees, darker) sit on exposed limb; that
  contrast split is what keeps them from reading as stains.
- The original logo path is untouched in all three files; it is only ever
  wrapped in a translate.

### Cart (`sculptor-guy-cart.svg`)

Joints: `body` (the sculpture — rocks about its deck contact point and lifts
to open a gap), `wheelL`/`wheelR` (rolling rotation), `pupils`, and `mouth`
(a little "O", hidden at `scale(0)`, scaled toward 1 for awe). The
sculpture's rounded base touches the deck only at its center dip, which is
why rocking pivots there; keep rock within ±14° or the base corners dig into
the deck.

## The playground

Everything is procedural — no keyframed animations. Each character runs the
same small platformer controller (acceleration + friction, gravity, coyote
time, jump buffering, short-hops when you release jump early) and eases every
joint toward state-dependent targets, so all transitions blend for free.

- The two walkers share one pose system (`WalkerGuy`) parameterized per build:
  antiphase leg pendulums with knee bend on the recovery swing, arms
  counter-swinging with an outward bias, body bob and lean.
- The cart guy (`CartGuy`) is two springs: *rock*, driven by measured
  horizontal acceleration, so he wobbles like unstrapped cargo when the cart
  speeds up or brakes; and *gap*, which pops him off the deck while airborne
  and turns its touchdown dip into squash. His cart also coasts (low
  friction), and a little "O" mouth scales in whenever he's airborne or at
  full speed.
- Unsupervised characters wander: stroll at half speed, pause, occasionally
  hop, and turn around near screen edges. Clicking one routes the keyboard to
  it (a ▾ marker shows who's yours); the rest keep wandering.

For deterministic poses (screenshots, tinkering in the console):

```js
guys[1].demo('idle' | 'walk' | 'rise' | 'fall' | 'land');  // freeze a settled pose
guys[0].demo('walk', 2.6);   // walk at a given stride phase
scene.takeControl(guys[2]);  // grab a guy programmatically
scene.resume();              // hand the loop back
```

The character markup in `index.html` (three `<template>`s) is a copy of the
standalone SVGs, inlined so the page works from `file://` without fetch
restrictions — if you change a rig, change both.

## The Sculptor plugin (`plugin/`)

Cart guy as a desktop pet inside the Sculptor UI itself: a frontend plugin
that registers a full-app overlay where he wanders and **treats the app's DOM
as terrain** — while falling, `document.elementsFromPoint` is probed under
his wheels and the first sufficiently large element whose top edge crosses
the fall becomes his floor. He re-measures his perch every frame, so he rides
panels that move, and falls when his perch unmounts or slides away. The
viewport bottom is the ultimate floor.

Click him to drive: **A/D** or **←/→** roll, **W/Space** jump, **S/↓** drops
him through whatever he's perched on — a tap punches through to the next
surface below, holding it plummets him all the way to the bottom of the
screen (the app DOM is a dense stack of nested containers, so drops disable
landing for a window rather than nudging him past one edge). **Esc** releases
him back to wandering. The wander AI also drops through its perch every once
in a while — sometimes one step, sometimes all the way down — so he never
homesteads the top of a panel.
While driving, keys are only captured when the event target isn't editable,
so typing in the app is never hijacked; uncontrolled, he never touches the
keyboard at all.

- `plugin/world.js` — the engine, deliberately React-free so a plain harness
  page can import it directly for testing.
- `plugin/main.js` — the plugin entry: React overlay wrapper + `activate`.
- `plugin/manifest.json` — plugin manifest (`id: cart-guy`).

Dev loop (mutating ops need Settings → Plugins → "Agent plugin loading"):

```bash
sculpt plugin load marketing/sculptor-guy/plugin      # load into the live UI
sculpt plugin reload cart-guy                         # after editing
sculpt plugin remove cart-guy                         # clean up
sculpt plugin load marketing/sculptor-guy/plugin --persist   # keep it installed
```

The rig markup in `world.js` is the cart SVG with `cg-`-prefixed filter ids
and class names so nothing collides with the host page — same
change-both-copies rule as the playground templates.
