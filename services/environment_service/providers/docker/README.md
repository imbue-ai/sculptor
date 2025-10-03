Docker agentic environment

* [Bowei's awesome diagram](https://app.eraser.io/workspace/IHdplYZudcXuBYvXVJWJ)

# How container images are built

1. We use devcontainers to provide a way for repositories to self-describe their development environments using Dockerfiles.
2. If the user's repo doesn't have a devcontainer, we use what's in `default_devcontainer`, which has a "vanilla" Dockerfile suitable for python development.
3. Once the user's image has been built from the devcontainer, we wrap it with our own Dockerfile in `imbue_addons`,
   which inherits from their image, but also bakes their git repo directly into the image and adds a few Imbue knobs.
4. Finally, at container runtime, we volume mount our "control plane" into the container.

To summarize:
By putting our wrapper on top of the user's dockerfile, we allow the user to start from a clean canvas,
without adding substantial build time when the user's Dockerfile changes (since our wrapper is small and the bulk of our stuff lives in the volume).

# How this fits together

* We build the entire control plane (everything in /imbue/...) in Dockerfile.base_nix
* We copy the /imbue directory into a Docker volume.
  * This filesystem is largish, around 1.6 GB.
  * It has symlinks pointing at /nix/store/..., which isn't in the volume, but there's a copy of what should be in /nix/store/... in /imbue/nix/store/...
* Dockerfile.imbue_addons is built often, for ever task container build.
  * It is much thinner, and meant to be fast to build and start.
  * It "wraps around" the user's image, adding a few things, like ssh access.
  * The building of Dockerfile.imbue_addons itself happens without a volume being attached, so there's no /imbue/... yet.
  * But it does create a /nix symlink pointing at -> /imbue/nix, anticipating that the volume containing /imbue will be mounted there.
  * Initialization that requires the control plane is deferred until container start, see below.
* At container start
  * We run a Dockerfile.imbue_addons wrapper image.
  * We mount the control plane volume at /imbue (read-only).
  * We run `imbue_post_container_build.sh`.
  * The PATH for the container is the imbue control plane path.
  * When we run user-space things (claude, terminal), we restore the user's PATH, with one extra directory for Imbue tools.

This design is addmittedly a little weird.  It exists mostly because of an optimization:
we don't want to make Imbue's control plane as a layer because it slows the build and makes snapshots big.


## Useful tests

`Dockerfile.imbue_addons` and `imbue_post_container_build.sh` are covered on several different base images by running:

```sh
uv run --package sculptor pytest -sv \
    'sculptor/tests/acceptance/environment/test_control_plane_atop_sample_devcontainers.py::test_environment' \
    --skip-build-artifacts \
    --snapshot-update
```

## Why we run claude from `/imbue_addons/bin/claude`

Some of our unit tests want to overwrite the `claude` binary with a simple bash script that just prints JSON, so that they can simulate errors.
That meant I had to put claude somewhere that's writeable, rather than the readonly control plane inside /imbue.
So I made `/imbue_addons/bin/` for that.
