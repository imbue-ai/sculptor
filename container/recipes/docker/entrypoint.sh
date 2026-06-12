#!/bin/sh
# Container entrypoint:
#   1. Ensure the running UID has a valid /etc/passwd entry
#   2. Download backend binaries if not already present (bind-mounted or cached)
#
# When the container is started with --user UID:GID, the effective UID may
# differ from the sculptor user (1000) baked into the image. This script
# updates the sculptor entry in /etc/passwd to match the runtime UID/GID so
# that whoami, git, ssh, and other tools see a real user.

# -- UID remapping ----------------------------------------------------------
current_uid=$(id -u)

if ! getent passwd "$current_uid" > /dev/null 2>&1; then
    current_gid=$(id -g)
    # sed -i needs write access to the directory for temp files; /etc is
    # read-only for non-root. Use a temp file in /tmp instead.
    tmp=$(mktemp /tmp/passwd.XXXXXX)
    sed "s/^sculptor:x:1000:1000:/sculptor:x:${current_uid}:${current_gid}:/" /etc/passwd > "$tmp"
    cat "$tmp" > /etc/passwd
    rm -f "$tmp"
fi

# -- Binary provisioning ----------------------------------------------------
# If sculptor_backend is not already on PATH (e.g., bind-mounted or from a
# previous download), run the download script using SCULPTOR_VERSION.
if ! command -v sculptor_backend > /dev/null 2>&1; then
    version="${SCULPTOR_VERSION:-latest}"
    echo "[entrypoint] sculptor_backend not found, downloading version: $version" >&2
    download-sculptor-backend.sh "$version" /opt/sculptor
fi

exec "$@"
