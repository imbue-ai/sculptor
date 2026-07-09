# Sculptor guy

The Sculptor logo blob, rigged with arms and legs, plus a little playground
where he walks around the screen.

- `sculptor-guy.svg` — the rigged character asset (viewable standalone; blinks).
- `index.html` — the playground. Open it directly in a browser (`file://` works,
  no server needed). **A/D** or **←/→** to walk, **W/Space** to jump, **S** to
  crouch (and fast-fall in the air).

## The rig

Every posable joint is a `<g data-joint="...">` group. Each one sits inside a
positioning wrapper (`<g transform="translate(x,y)">`) that places its pivot,
so posing a joint is just setting a rotation on the group:

```js
svg.querySelector('[data-joint="armL"]').setAttribute('transform', 'rotate(35)');
```

| Joint | Pivot (viewBox 260×310) | Notes |
| --- | --- | --- |
| `body` | hip center (122, 197) | torso + face + both arms; lean/bob/squash |
| `armL` / `elbowL` | shoulder (62, 146) / 28 below | near arm, drawn in front |
| `armR` / `elbowR` | shoulder (176, 150) / 28 below | far arm, drawn behind |
| `thighL` / `calfL` / `footL` | hip (104, 198) / knee 38 below / ankle 32 below | near leg |
| `thighR` / `calfR` / `footR` | hip (140, 198) / knee 38 below / ankle 32 below | far leg |
| `pupils` | — | translate-only, look direction |

Rotation sign: SVG `rotate()` is clockwise, so on a downward-hanging limb a
positive angle swings the tip toward screen-left. Feet rest at y=278.5 in
viewBox units.

Design decisions worth knowing before you re-pose him:

- **Noodle limbs.** Limbs are stroked paths with round linecaps. The near
  (left) limbs share the body red (`#F50D00`) so the shoulder/hip overlaps are
  seamless; the far (right) limbs are darker (`#C90B00`) and drawn *behind*
  the torso. Keep that z-order: far limbs → body → near limbs.
- **Arms are parented inside `body`**, so torso lean and squash carry them
  along. Legs live at the root so they stay planted under him.
- **The silhouette has blind spots.** A raised near arm disappears against the
  torso's left edge past ~140°, and a raised far arm hides behind the logo's
  top-right curl past horizontal. The playground's jump pose (one arm up-left,
  one out-down-right) is shaped around this — check poses against the
  silhouette, not just the joint angles.
- The original logo path is untouched; it's only wrapped in a translate.

## The playground

Everything is procedural — there are no keyframed animations. The walk is a
pair of antiphase leg pendulums with knee bend on the recovery swing, arms
counter-swinging with an outward bias, plus body bob and lean. Jump/fall/land
are target poses that the rig eases toward (`updatePose` smooths every joint
toward its target each frame), so all transitions blend for free.

Movement is a tiny platformer controller: acceleration + friction, gravity,
coyote time, a jump input buffer, and short-hops when you release jump early.
A contact shadow scales with height and a dust poof spawns on landing.

For deterministic poses (screenshots, tinkering in the console):

```js
guy.demo('idle' | 'walk' | 'rise' | 'fall' | 'land');  // freeze a settled pose
guy.demo('walk', 2.6);                                  // walk at a given phase
guy.paused = false;                                     // hand control back
```

The character markup in `index.html` is a copy of `sculptor-guy.svg` (inlined
so the page works from `file://` without fetch restrictions) — if you change
the rig, change both.
