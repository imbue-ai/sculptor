---
name: auto-qa-iphone
description: |
  QA the Sculptor mobile web UI on a real iOS Simulator, driven headlessly from
  a Mac. A single CLI boots a notched iPhone, launches the local frontend server
  (parsing its port — no hardcoding), opens the app in MobileSafari, taps/swipes
  via idb, and screenshots each step. Includes the Add-to-Home-Screen standalone
  flow — the only way to verify notch / status-bar / home-indicator safe-area
  rendering (env(safe-area-inset-*) is 0 everywhere except real iOS). Use when
  visually verifying mobile/responsive changes on an iPhone.
argument-hint: "[url-or-port (optional; defaults to launching `just frontend-custom`)]"
---

# iPhone Simulator QA (Simulator + idb)

This is the iPhone sibling of `/auto-qa-changes`. Instead of a headless Chromium
at desktop size, it drives a real **iOS Simulator** so you can see how the mobile
web UI actually renders on a notched iPhone — including the **standalone PWA**
chrome (the app sets `apple-mobile-web-app-capable`, `viewport-fit=cover`, and a
`black-translucent` status bar in `sculptor/frontend/index.html`).

Why a real simulator and not Playwright: `env(safe-area-inset-*)` — the insets
the mobile shell uses for the notch/Dynamic Island, status bar, and home
indicator — are **0 everywhere except a real iOS surface**. Desktop browsers,
Playwright, and the `/auto-qa-changes` Chromium harness all report 0. The only
faithful check is Add-to-Home-Screen + a standalone launch on a notched device.

Everything is driven through one CLI:

```
.claude/skills/auto-qa-iphone/scripts/iphone_sim.py
```

Stdlib-only Python (no `uv`/venv needed to run it); it shells out to
`xcrun simctl`, `idb`, and `just`.

## Prerequisites (one-time, slow)

- **macOS + Xcode** with an **iOS Simulator runtime**. `setup` checks for one and,
  if missing, prints the (~9 GB) download command `xcodebuild -downloadPlatform iOS`
  — it will not download automatically unless you pass `--download-runtime`.
- **Homebrew** + **idb** (drives taps/swipes the simulator CLI can't). `setup`
  creates an idb venv at `~/.cache/sculptor-iphone-qa/idb-venv` and
  `brew install idb-companion` for you.
- A working frontend dev env (`just rebuild` once if this is a fresh checkout),
  since the default server command is `just frontend-custom`.

## Quick start

Set a short alias and a screenshots dir (defaults to the workspace
`attachments/`, so images render in chat and survive for MR reuse):

```bash
SIM=".claude/skills/auto-qa-iphone/scripts/iphone_sim.py"
```

### Step 1: Boot the device (idempotent)

```bash
python3 "$SIM" setup            # default device: iphone-16-pro (notched)
# Other presets: --device iphone-16-pro-max | iphone-se (non-notched control)
```

This creates/reuses a `SculptorQA-<preset>` simulator, boots it, connects idb,
and prints the UDID. Re-running is safe (it reuses the device). To watch it
live: `open -a Simulator`.

### Step 2: Open the app

Have your dev server running first (e.g. `just frontend-custom` or `just start`
in your own terminal — it works reliably there). Then:

```bash
python3 "$SIM" open
```

How `open`/`serve` resolve the URL (no port is ever hardcoded — the dev port is
hashed per checkout):

1. `--url URL` / `--port N` — attach to exactly that server.
2. Otherwise **auto-detect**: probe listening ports for a running Sculptor SPA
   and attach to it (a vite **dev** server is preferred over a packaged/production
   `app` build; it warns when it could only find the latter). This is the normal,
   reliable path.
3. If nothing is found, **fall back to launching** `--command` (default
   `just frontend-custom`), parse its port from the log, and verify it actually
   serves before using it.

The simulator shares the host network, so `http://127.0.0.1:<port>` is reachable.

> **Launching from inside a Sculptor agent is flaky.** `just frontend-custom`
> drives Electron, which (a) races to load its renderer before vite is ready and
> dies under `--unhandled-rejections=strict`, (b) refuses a second instance via
> the `.dev_sculptor` single-instance lock, and (c) inherits a leaked
> `SCULPTOR_API_PORT` from the surrounding session. **Prefer keeping your own dev
> server running and letting `open` auto-detect it** (or pass `--port`/`--url`).
> Use `--launch` to force the fallback launch anyway.

Every action prints a `screenshot:` path **and an `<img>` tag** — paste the tag
into chat to show the user (see "Context management").

### Step 3: Drive the UI and narrate (see protocol below)

```bash
python3 "$SIM" screenshot --label home          # capture current screen
python3 "$SIM" tap --frac 0.5 0.93              # tap by screen fraction (0..1)
python3 "$SIM" swipe 201 620 201 320            # swipe by points
python3 "$SIM" describe                          # a11y tree of the foreground app
```

### Step 4: Verify safe areas via Add-to-Home-Screen (the important part)

Safari always shows its own chrome, so the standalone status bar and true
safe-area insets only appear after adding to the home screen and launching.

First, make sure Safari's bottom toolbar is visible: if the page auto-focused an
input, the on-screen keyboard hides the toolbar (and the Share button). Dismiss
it by tapping an empty area, then screenshot to confirm the toolbar is back:

```bash
python3 "$SIM" tap --frac 0.5 0.42              # tap empty space to blur the input
```

Then drive the flow (it screenshots after **every** tap because SpringBoard and
the share sheet aren't in the accessibility tree, so they can't be located):

```bash
python3 "$SIM" add-to-home-screen               # Share -> swipe -> Add to Home Screen -> Add
```

Verify each screenshot matches the expected step before trusting the next. Then
launch the clip. **The icon's position is not fixed**, so locate it first and tap
its **artwork center** (the text label sits ~40 pt below the artwork — aim at the
glyph, not the label) via a describe-screenshot subagent, then:

```bash
python3 "$SIM" screenshot --label home          # capture the home screen
# (locate the Sculptor icon ARTWORK center as a fraction, then:)
python3 "$SIM" launch-icon --frac 0.39 0.26 --settle 6
```

If the home screen is still showing afterward, the tap missed the artwork —
re-locate and tap again.

### Step 5: Clean up

```bash
python3 "$SIM" teardown        # stops the managed server + shuts the sim down
# python3 "$SIM" teardown --delete   # also delete the simulator device
```

## Available commands

| Command | What it does |
|---|---|
| `setup [--device P] [--download-runtime]` | Ensure runtime + idb; create/boot `SculptorQA-<P>`; connect idb; print UDID. |
| `detect` | List running Sculptor servers (tagged `dev`/`app`) and show which one `open` would attach to. |
| `serve [--port N \| --url U \| --command C \| --launch]` | Resolve a server URL: attach to `--port`/`--url`, else auto-detect a running one, else launch `--command`. |
| `open [--port N \| --url U \| --command C \| --launch]` | Same URL resolution as `serve`, then `simctl openurl` → screenshot. |
| `screenshot [--label NAME]` | Capture the current screen to a numbered PNG. |
| `tap X Y [--frac]` | `idb ui tap`. `--frac` treats X/Y as 0..1 fractions of the screen. Auto-screenshots. |
| `swipe X1 Y1 X2 Y2 [--frac] [--duration S]` | `idb ui swipe`. Auto-screenshots. |
| `describe` | `idb ui describe-all` — JSON a11y tree (foreground app only). |
| `add-to-home-screen` | Drive the AHS flow with a screenshot after each tap. |
| `launch-icon [X Y] [--frac]` | Tap the home-screen clip to launch standalone; screenshot. |
| `remove-home-screen` | Guidance for removing the clip (iOS caches launch config at add-time). |
| `teardown [--delete]` | Stop the managed server; shut down (and optionally delete) the device. |
| `status` | Print the device/server/idb state (JSON). |

Shared options (after any subcommand): `--screenshots-dir PATH`, `--settle SECONDS`.
State (UDID, point size, server pid/url, screenshot counter) persists to
`<screenshots-dir>/.iphone-sim-state.json`, so commands chain without re-passing
the UDID.

## Context management: never Read screenshots directly

Simulator screenshots are native-scale PNGs (iPhone 16 Pro is 3× → ~1206×2622),
each large. **Never call the Read tool on a screenshot yourself** — a few will
blow out your context. Same three rules as `/auto-qa-changes`:

1. **Display to the user via the `<img>` tag** the CLI prints. This is free for
   your context — it renders on the user's side; no image data enters yours.
2. **Verify state programmatically when you can.** `describe` (a11y tree),
   `status`, and the success/failure of each command tell you a lot without
   pixel inspection.
3. **When you genuinely need visual inspection** (alignment, what text appeared,
   whether the status bar overlaps content), **delegate to a subagent** with a
   narrow question:

   ```
   Agent(description="Describe screenshot",
         prompt="Read /abs/path/0007_standalone.png. Focus on the top of the
                 screen: does any header content sit UNDER the status bar / notch,
                 or is there correct safe-area padding above it? 2-3 sentences.")
   ```

   The image stays in the subagent's context and is discarded when it returns.

## Narrated visual walkthrough protocol

Same as `/auto-qa-changes`. **Every screenshot you take, you MUST:**

1. **Display it** with the `<img>` tag (absolute `src`, descriptive `alt`).
2. **Describe what you see** — inferred from `describe`/`status`, or via a
   describe-screenshot subagent. Do not Read the PNG yourself.
3. **Call out issues** — note the safe areas especially: content under the notch,
   a chat input hidden behind the home indicator, clipped headers.
4. **Announce the next action.**

Format each step:

```
<img src="/abs/path/attachments/iphone-screenshots/0002_open.png" alt="Mobile workspace shell, Safari">

**Step 2: Mobile shell in Safari**
Single-column layout: header, chat stream, floating input, agent pager at the
bottom. Safari's own toolbar is visible (expected — standalone chrome only shows
after Add-to-Home-Screen). No obvious layout issues.

**Next:** add to home screen and launch standalone to check the real status bar.
```

## Driving taps without an accessibility tree

- **Coordinates are points, not pixels.** iPhone 16 Pro is **402×874 pt**;
  screenshots come out at 3× (1206×2622 px). `idb` wants points.
- **Prefer `--frac`.** Spot the target in a screenshot, express it as a fraction
  of the image (e.g. a button 90% down the screen → `--frac 0.5 0.9`), and the
  CLI multiplies by the device's point size. This is robust across devices.
- **WebView elements** (inside MobileSafari) appear in `describe`; **SpringBoard,
  the share sheet, and the home screen do not** — drive those by coordinate and
  verify with the screenshot after every tap.

## Gotchas

- **The standalone status bar only appears via the home-screen launch**, never in
  Safari (Safari always shows its own chrome). You MUST go through
  `add-to-home-screen` + `launch-icon` to exercise `apple-mobile-web-app-status-bar-style`
  and the real safe-area insets.
- **iOS caches the launch config at add-time.** After changing `index.html`'s
  `<head>` (meta tags, theme-color, icon), **remove and re-add** the clip —
  reloading isn't enough. See `remove-home-screen`.
- **AHS coordinates are empirical and only ship for iPhone 16 Pro.** They can
  drift across iOS versions; the flow screenshots between steps so you can catch
  drift and re-derive with `tap --frac`. For other presets, drive AHS manually.
- **`env(safe-area-inset-*)` is 0 on non-notched devices** — `--device iphone-se`
  is a deliberate "insets ≈ 0" control, not a notch test.
- **Hot reload works in Safari**, since `just frontend-custom` runs the vite dev
  server: edit a `.tsx`/`.scss` and re-`screenshot` to see it. But a **standalone
  (home-screen) clip does not pick up `<head>` changes** without a remove/re-add.
- **The simulator shares the host network**, so `http://127.0.0.1:<port>` works
  (unlike a physical device). No tunneling needed.
- **The server runs detached** (own process group) and survives across turns;
  `teardown` stops it. `status` shows whether it's alive.

## Cleanup

`teardown` stops the managed server and shuts the simulator down (keeping the
device for next time; `--delete` removes it).

**NEVER delete screenshot files** — they're referenced by `<img>` tags in the
user's chat history and may be attached to MRs. Leave them in the screenshots dir.
