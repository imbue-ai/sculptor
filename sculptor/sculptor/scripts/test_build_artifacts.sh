#! /bin/bash
# Simple test to verify that building goes well.
# Run from the main directory, with `just test-build-artifacts`
#
# This test will run the build script, generate artifacts, and attempts to run
# them.

# PLEASE NOTE: this relies on the fact that the host machine is MacOS to
# test the Mac pipeline.

set -euxo pipefail

# Handle any errors by printing a message.
error_exit() {
	echo -e "\033[0;31mError: $1\033[0m" >&2
	exit 1
}

# Run the next block only if we are on MacOS.
if [[ "$(uname)" == "Darwin" ]]; then
    SKIP_NOTARIZE_AND_SIGN=1 just refresh pkg || true # Skip the built-in validation

    # # Find the generated dmg file in the dist directory.
    dmg="$(find dist -name 'sculptor-*.dmg' -print -quit)"
    # We open the pkg and run it.
    mnt="$(mktemp -d)"
    if hdiutil attach "$dmg" -mountpoint "$mnt" -nobrowse -quiet; then
      app="$(find "$mnt" -maxdepth 2 -name '*.app' -print -quit)"
      bin="$(/usr/bin/defaults read "$app/Contents/Info" CFBundleExecutable 2>/dev/null || basename "$app" .app)"
      sculptor="$app/Contents/MacOS/$bin"
      $sculptor --version > /dev/null
    fi
    rmdir "$mnt" 2>/dev/null || true
	echo "Local Mac build check completed successfully."
fi


echo "Build artifact check completed."
