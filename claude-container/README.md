# Claude Code container

* `Dockerfile` is the Dockerfile used to build the container for running Claude Code.
  It is used from Sculptor and runs on the **user**'s machine.

  It is based on the base image ghcr.io/imbue-ai/sculptorbase.

* `Dockerfile.base` is the Dockerfile used to build the base image ghcr.io/imbue-ai/sculptorbase.

This directory is its own UV workspace,
separate from the monorepo's main UV workspace.
When you run `uv` commands here (like `uv add`),
they will manipulate the dependencies of this UV workspace.

## Updating the base image

### When to update the base image

* If you have changed `Dockerfile.base`,
  you should obviously update the base image for it to take effect.

* More subtly:
  to keep the image building process fast on users' machines,
  we only install dependencies that are defined in `pyproject.toml` and locked by `uv.lock` in this directory once in the base image.

  This means that if you have updated `pyproject.toml` or `uv.lock` in this directory,
  you should also update the base image.

### How to update the base image

> **NOTE**: If you're using macOS, you have to use Docker Desktop to build the image.
> Rancher Desktop doesn't support multi-platform builds.

1.  Authenticate to the container registry,
    following the [official documentation](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry#authenticating-with-a-personal-access-token-classic). (You only need to do this once.)

2.  Run this from the `sculptor` directory (we need the wheels built by this command):

    ```shell
    make install
    ```

3.  Change into this directory, and run:

    ```shell
    docker buildx build \
      -f Dockerfile.base \
      --platform linux/amd64,linux/arm64 \
      -t ghcr.io/imbue-ai/sculptorbase:latest \
      -t ghcr.io/imbue-ai/sculptorbase:$(date +%Y%m%d) \
      --push .
    ```

    > **Tip**: The `$(date ...)` commands is intended to generate a unique tag.
    In the unlikely event that we are updating the base image multiple times per day,
    add an arbitrary suffix like `-2`.

    > **Tip**: If you want to test locally first,
    just omit the `--push` flag,
    test whether Sculptor can still create new tasks locally,
    and re-run the full command with `--push`.

4.  Update the first `FROM` clause of `Dockerfile` to point to the new tag.
