# Sculptor mobile (thin Capacitor shell)

A minimal [Capacitor](https://capacitorjs.com/) wrapper that ships the existing
Sculptor web UI as a native mobile app. It is a **thin shell**: the native
WebView loads the live UI directly from an OpenHost-hosted Sculptor backend —
it does **not** bundle a frontend build.

This is exploration scaffolding for [SCU-1617](https://linear.app/imbue/issue/SCU-1617).
The first target is a sideloadable Android APK (downloaded from GitHub, not the
Play Store). iOS is a later `npx cap add ios` away.

## One universal app, configured at runtime (Home-Assistant style)

Each OpenHost instance is separate, so the app is **not** built per-instance.
A single universal APK ships a small onboarding screen
([`www/index.html`](./www/index.html)); on first launch you enter your Sculptor
URL, it's persisted, and the WebView navigates there. Subsequent launches go
straight in, with a "Use a different server" escape hatch to reconfigure.

The saved URL lives in `localStorage` on the app's own local origin
(`https://localhost`), which the bundled page reads on every cold start before
redirecting — so it survives restarts even though the app then navigates to the
remote origin.

[`capacitor.config.ts`](./capacitor.config.ts) sets `allowNavigation: ["*"]`,
without which Capacitor would treat the remote instance as "external" and bounce
it to the system browser instead of loading it inside the app.

## Why a thin shell (loads remote, bundles nothing)

- **No version skew.** The app is always exactly whatever the server is serving.
- **Same-origin, so no CORS work.** With the WebView pointed at the remote, its
  origin *is* the remote origin — every `fetch`/WebSocket call is same-origin, so
  the backend's localhost-only CORS allow-list never applies.
- **Auth just works.** Sculptor's web mode self-bootstraps its session-token
  cookie from the (OpenHost-SSO-protected) SPA on load; a persistent WebView
  keeps that cookie across launches. No login UI is added by the shell.

The web frontend already runs in "web mode" whenever `window.sculptor` (the
Electron preload bridge) is absent, degrading every desktop-only feature
gracefully — so the shell needs no frontend changes to function.

## Build a debug APK

### In CI (recommended)

The [`Mobile APK`](../.github/workflows/mobile-apk.yml) workflow builds the APK
on `ubuntu-latest` (it provisions the Android SDK/JDK, which this repo's dev
machines don't carry):

- **Manual:** run it via *Actions → Mobile APK → Run workflow*. The APK is
  uploaded as a build artifact. No inputs — the same universal APK works for any
  instance.
- **Release:** push a `mobile-v*` tag and the APK is also attached to the
  matching GitHub Release.

### Locally

Needs a JDK (21) and the Android SDK (cmdline-tools + platform 35 +
build-tools 35). On an Apple-silicon Mac with Homebrew, no sudo required:

```bash
# One-time toolchain install
brew install openjdk@21                          # keg-only; no sudo
brew install --cask android-commandlinetools     # provides sdkmanager
export JAVA_HOME=/opt/homebrew/opt/openjdk@21
export ANDROID_HOME=/opt/homebrew/share/android-commandlinetools
yes | sdkmanager --licenses
sdkmanager "platform-tools" "platforms;android-35" "build-tools;35.0.0"
echo "sdk.dir=$ANDROID_HOME" > android/local.properties   # gitignored

# Build (JAVA_HOME must be set so Gradle finds the keg-only JDK)
cd mobile
npm ci
JAVA_HOME=/opt/homebrew/opt/openjdk@21 npm run build:apk
# -> android/app/build/outputs/apk/debug/app-debug.apk  (~4 MB, debug-signed)
```

Install on a device with `adb install -r <path>` (or just open the APK on the
phone with "install from unknown sources" enabled). Or open the native project
in Android Studio, which supplies its own JDK/SDK: `npm run open:android`.

### Run in an emulator

On Apple silicon the arm64 system image runs natively via Hypervisor.framework.
One-time: `sdkmanager "emulator" "system-images;android-35;google_apis;arm64-v8a"`.

`scripts/run-emulator-headless.sh [out.png]` boots a headless emulator (creating
the AVD on first run), installs the freshly built APK, launches the app, and
saves a screenshot — handy for verifying the shell renders without a device or a
display. It reuses an already-running emulator and leaves it up between runs
(`adb emu kill` to stop it).

## Open questions / not yet done

- **Signing & distribution.** This produces a *debug*-signed APK — fine for
  sideloading, not for the Play Store. A release build needs a real keystore.
- **Reconfigure UX.** The "Use a different server" affordance lives on the
  onboarding screen (reachable on cold start / device back). A nicer long-term
  option is a native menu item so you can switch servers from inside the app.
- **iOS.** Not scaffolded yet. `npx cap add ios` plus a signing identity; the
  same runtime-URL approach applies.
- **Native polish.** Edge-to-edge / safe areas are handled (the
  `@capawesome/capacitor-android-edge-to-edge-support` plugin insets the WebView
  so content stays out from under the Android 15 system bars; tune the bar tint
  via `EdgeToEdge.backgroundColor` in `capacitor.config.ts`). Still wanted:
  `Keyboard` (viewport resize) and routing `target="_blank"` links to the system
  browser via the `Browser` plugin.
- **Push notifications.** The highest-value mobile-native add ("your agent
  finished / needs input" while backgrounded) — needs a backend signal and is a
  separate effort, not part of this shell.
- **Relation to the Electron desktop build.** Independent: this consumes the
  same web frontend over HTTP but shares none of the Electron packaging. The
  `window.sculptor` bridge is desktop-only and intentionally absent here.
- **Cold-start cookie persistence.** Expected to survive on Android WebView;
  worth confirming on a real device once an APK is in hand.
