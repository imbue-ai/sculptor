# Claude Code container

* `Dockerfile` is the Dockerfile used to build the container for running Claude Code.
  It is used from Sculptor and runs on the **user**'s machine.

  It is based on the base image ghcr.io/imbue-ai/sculptorbase.

* `Dockerfile.base` is the Dockerfile used to build the base image ghcr.io/imbue-ai/sculptorbase.

## Updating the base image

> **NOTE**: If you're using macOS, you have to use Docker Desktop to build the image.
> Rancher Desktop doesn't support multi-platform builds.

1.  Authenticate to the container registry,
    following the [official documentation](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry#authenticating-with-a-personal-access-token-classic).

2.  Change into this directory, and run:

    ```shell
    docker buildx build \
      -f Dockerfile.base \
      --platform linux/amd64,linux/arm64 \
      -t ghcr.io/imbue-ai/sculptorbase:latest \
      -t ghcr.io/imbue-ai/sculptorbase:$(date +%Y%m%d) \
      --push .
    ```

    The `$(date ...)` commands is intended to generate a unique tag.
    In the unlikely event that we are updating the base image multiple times per day,
    add an arbitrary suffix like `-2`.

3.  Update the first `FROM` claude of `Dockerfile` to point to the new tag.
