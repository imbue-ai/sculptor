After creating a user's Docker image using the devcontainer spec, we inherit from their image with our own image.

Imbue's layers:
* Expect that `/imbue` will be volume mounted when the container is create to provide the Imbue control plane.
* Set up a symlink pointing from `/nix` to `/imbue/nix`.
* COPY the user's git repo into the correct place.
* Set some system configuration (tmux, sshd, users).
* Put our claude wrapper into `/imbue_addons/agent_path_extension_bin/claude`

Note that since we're volume-mounting the Imbue control plane in `/imbue/...` and `/imbue/nix/...`,
anything we eventually get from there is NOT yet available when we `docker build` the `Dockerfile.imbue_addons`.
That's the reason for the `imbue_post_container_build.sh` script in this directory, which
gets run after the container starts and `/imbue/...` and `/nix/...` are available.

# Expected layout

```
/imbue/: Imbue's control plane (Read Only, volume mounted)
  /imbue/nix/store: The entire Nix store that we depend on.
  /imbue/nix_bin: Symlinks to binaries in /nix/store, all in one place, ready for $PATH.  Get claude, git, bash, ncdu, less, strace, etc.
  /imbue/bin: Imbue's extra things we want on our $PATH.
  /imbue/imbue_env.sh: Environment variables required to make things work.
  /imbue/.venv: A Python environment where Imbue's CLIs are installed.
/nix: A symlink pointing at /imbue/nix
/imbue_addons/: A writeable layer created by Dockerfile.imbue_addons
  /imbue_addons/bin/claude: (Read-Write!) Our claude wrapper in a writeable place so that unit tests can overwrite it.
```

## Some useful commands for mucking around with devcontainers

```sh
# Once:
npm install -g @devcontainers/cli
# See: https://github.com/devcontainers/cli?tab=readme-ov-file#npm-install

export DEFAULT_DEVCONTAINER_IMAGE=$(
WF=sculptor/sculptor/services/environment_service/providers/docker/default_devcontainer && \
devcontainer build \
    --config $WF/devcontainer.json \
    --workspace-folder $WF \
|  jq -r '.imageName[0]'
)

IMBUE_ADDONS=sculptor/sculptor/services/environment_service/providers/docker/imbue_addons && \
export IMBUE_WRAPPED_IMAGE=$(
docker build --quiet \
    -f ${IMBUE_ADDONS}/Dockerfile.imbue_addons \
    ${IMBUE_ADDONS} \
    --build-arg BASE_IMAGE=${DEFAULT_DEVCONTAINER_IMAGE} \
    --build-arg USER_UID=$(id -u) --build-arg GROUP_GID=$(id -g) \
    --build-context imbue_user_repo=$GI_ROOT
)

docker run \
    -u root \
    -v imbue_control_plane_20250916_ea70c3d9ff68558328e8be8d0aa43b67607aaf0d075e352e2291535a83ee230d:/imbue:ro \
    -it $IMBUE_WRAPPED_IMAGE bash
```
