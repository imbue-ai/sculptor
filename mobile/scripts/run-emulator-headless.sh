#!/usr/bin/env bash
# Boot a headless Android emulator, install the debug APK, launch the app, and
# save a screenshot. Headless (-no-window) so it works without a display and in
# an agent context; frames are grabbed over adb. Apple-silicon hosts run the
# arm64 system image natively via Hypervisor.framework.
#
# Usage: mobile/scripts/run-emulator-headless.sh [output-screenshot.png]
set -euo pipefail

export JAVA_HOME="${JAVA_HOME:-/opt/homebrew/opt/openjdk@21}"
export ANDROID_HOME="${ANDROID_HOME:-/opt/homebrew/share/android-commandlinetools}"
export PATH="$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator:$PATH"

AVD_NAME="sculptor_pixel"
SYSTEM_IMAGE="system-images;android-35;google_apis;arm64-v8a"
APK="$(cd "$(dirname "$0")/.." && pwd)/android/app/build/outputs/apk/debug/app-debug.apk"
SHOT="${1:-/tmp/sculptor-emulator.png}"

if ! avdmanager list avd 2>/dev/null | grep -q "Name: $AVD_NAME"; then
  echo "Creating AVD $AVD_NAME..."
  echo "no" | avdmanager create avd -n "$AVD_NAME" -k "$SYSTEM_IMAGE" --device pixel_7 --force
fi

# Reuse an already-running emulator if present; otherwise boot one headless and
# leave it running (boot is the slow part, so keeping it up speeds up reruns).
if ! adb devices | grep -q "emulator-"; then
  echo "Booting emulator (headless)..."
  nohup emulator "@$AVD_NAME" -no-window -no-audio -no-boot-anim -no-snapshot \
    -gpu swiftshader_indirect >/tmp/emulator.log 2>&1 &
fi

adb wait-for-device
echo "Waiting for boot to complete..."
until [ "$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ]; do
  sleep 2
done

echo "Installing APK..."
adb install -r "$APK"
echo "Launching app..."
# Use an explicit component start (not `monkey`, which returns non-zero and
# trips `set -e` when it can't resolve a category). Then give the WebView a
# few seconds to lay out the onboarding page before grabbing a frame.
adb shell am start -n com.imbue.sculptor/.MainActivity >/dev/null
sleep 5

echo "Capturing screenshot -> $SHOT"
adb exec-out screencap -p > "$SHOT"
echo "Done. Emulator left running (avd: $AVD_NAME); stop with: adb emu kill"
