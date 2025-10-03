#!/usr/bin/env bash

# The imbue control plane in /nix/... and /imbue/... is not available during image build
# since we mount it as a volume into the container.

# This script is meant to run after the container has access to the imbue control plane.

# This script needs to be run as root.
# For now, USER_UID and GROUP_GID are set in the Dockerfile.imbue_addons file into the environment.
# But Thad thinks they should just go away.

set -euo pipefail
set -x

# TODO: Find/Make a unit test that fails if the lines below are removed.
# Currently, having a ".sculptor/user_setup.sh" inside the repo will require that sculptoradmin can sudo without a password.
# But maybe we want to delete that mechanism?
/imbue/nix_bin/groupadd sculptoradmin || echo "sculptoradmin group already existed -- can happen subsequent task restarts."
/imbue/nix_bin/echo "Created sculptoradmin group"
/imbue/nix_bin/mkdir -p /etc/sudoers.d/
/imbue/nix_bin/echo "%sculptoradmin ALL=(root) NOPASSWD:ALL" > /etc/sudoers.d/sculptoradmin
/imbue/nix_bin/chmod 0440 /etc/sudoers.d/sculptoradmin
/imbue/nix_bin/echo "Created /etc/sudoers.d/sculptoradmin"

# Make our claude wrapper executable.
/imbue/nix_bin/chmod +x /imbue_addons/agent_path_extension_bin/claude

# Must be root, otherwise: "could not lock config file /etc/gitconfig: Permission denied"
/imbue/nix_bin/git config --system --add safe.directory /user_home/workspace
/imbue/nix_bin/echo "Added /user_home/workspace to git safe.directory"

# We're creating workspace under root so it needs to be owned by the user running sculptor.
# TODO: Delete if possible -- this should only be affecting the GROUP_GID, USER_UID should already be correct.
#/imbue/nix_bin/chown ${USER_UID}:${GROUP_GID} ${ROOT_PATH}

# We only know our USER_UID, and have to look up the username to pass to `su`.
# USERNAME=$(getent passwd ${USER_UID} | cut -d: -f1)

# If below isn't run as USER_UID, git complains about "suspicious ownership."
# It doesn't make sense to do the below step when this directory is bind-mounted into the container.
# /imbue/nix_bin/echo "Trying to git reset --hard /user_home/workspace as ${USERNAME}"
# su - ${USERNAME} -c "/imbue/nix_bin/git -C /user_home/workspace reset --hard"
# /imbue/nix_bin/echo "Reset /user_home/workspace to HEAD"

########################### SSHD SETUP ###########################
set -euo pipefail
set -x


if ! id -u sshd > /dev/null 2>&1; then
    echo "Adding sshd user."
    useradd -r -s /usr/sbin/nologin sshd
else
    echo "sshd user already exists."
fi

echo "Making /var/empty for sshd."
mkdir -p /var/empty
chown root:root /var/empty && \
chmod 700 /var/empty

echo "Making host keys for sshd."
mkdir -p /sshd_config
# shellcheck disable=SC2046
yes n | ssh-keygen -t ed25519 -f /sshd_config/ssh_host_ed25519_key -N "" || true

echo "Making sshd config."
echo "Setting up ssh config."
# shellcheck disable=SC2046
SFTP_SERVER_PATH=$(readlink -f $(find $(dirname $(readlink -f /imbue/nix_bin/sshd))/../ -executable -name sftp-server | head -n 1))
cat > /sshd_config/sshd_config <<EOF
Port 2222
PermitRootLogin yes           # Only in containers / test environments
PermitUserEnvironment yes

PubkeyAuthentication yes
PasswordAuthentication no
ChallengeResponseAuthentication no
UsePAM no

AuthorizedKeysFile /home/sculptoruser/.ssh/authorized_keys
HostKey /sshd_config/ssh_host_ed25519_key

PidFile /var/run/sshd.pid
LogLevel INFO
Subsystem sftp $SFTP_SERVER_PATH
EOF
