#!/usr/bin/env bash
# Usage: build_git.sh <version> <prefix>
#
# Builds a release of git from source into <prefix>, for testing Sculptor
# against old gits. Does nothing if <prefix> already holds that version. The
# build leaves out what the VCS tests do not use, so it needs only a C
# compiler, make and the zlib headers.
set -euo pipefail

version="$1"
prefix="$2"

case "$version" in
  2.39.5) sha256=c58da92c378df4a986ca33266897a7397e86c22ee266a284d8c2432c39066b59 ;;
  2.42.0) sha256=3278210e9fd2994b8484dd7e3ddd9ea8b940ef52170cdb606daa94d887c93b0d ;;
  *)
    echo "No sha256 is pinned for git $version; add it from https://mirrors.edge.kernel.org/pub/software/scm/git/sha256sums.asc" >&2
    exit 1
    ;;
esac

if [ "$("$prefix/bin/git" --version 2>/dev/null)" = "git version $version" ]; then
  echo "git $version is already built in $prefix."
  exit 0
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
tarball="git-$version.tar.xz"
echo "Downloading $tarball..."
curl -fsSL "https://mirrors.edge.kernel.org/pub/software/scm/git/$tarball" -o "$tmp/$tarball"
if command -v sha256sum >/dev/null; then
  actual_sha256="$(sha256sum "$tmp/$tarball" | cut -d' ' -f1)"
else
  actual_sha256="$(shasum -a 256 "$tmp/$tarball" | cut -d' ' -f1)"
fi
if [ "$actual_sha256" != "$sha256" ]; then
  echo "sha256 mismatch for $tarball: expected $sha256, got $actual_sha256" >&2
  exit 1
fi
tar -xJf "$tmp/$tarball" -C "$tmp"

echo "Building git $version into $prefix..."
rm -rf "$prefix"
if ! make -C "$tmp/git-$version" -j"$(getconf _NPROCESSORS_ONLN)" prefix="$prefix" \
  NO_GETTEXT=1 NO_TCLTK=1 NO_OPENSSL=1 NO_CURL=1 NO_EXPAT=1 NO_PERL=1 NO_PYTHON=1 NO_INSTALL_HARDLINKS=1 \
  install >"$tmp/build.log" 2>&1; then
  tail -n 50 "$tmp/build.log" >&2
  echo "Building git $version failed; the end of the build log is above." >&2
  exit 1
fi
echo "Built $("$prefix/bin/git" --version) in $prefix."
