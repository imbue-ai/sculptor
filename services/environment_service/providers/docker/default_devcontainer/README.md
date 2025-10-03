The devcontainer we use if a user's repo doesn't already specify one.

## Building and Updating the Pre-baked Image

To update the pre-baked devcontainer image in GHCR, run this command from the `//` directory:

```bash
DOCKER_BUILDKIT=1 docker buildx build \
  --build-arg BUILDKIT_INLINE_CACHE=1 \
  -f sculptor/sculptor/services/environment_service/providers/docker/default_devcontainer/Dockerfile.unbaked \
  --platform linux/amd64,linux/arm64 \
  --cache-to=type=registry,ref=ghcr.io/imbue-ai/sculptor_default_devcontainer:buildcache,mode=max \
  --cache-from=type=registry,ref=ghcr.io/imbue-ai/sculptor_default_devcontainer:buildcache \
  sculptor/sculptor/services/environment_service/providers/docker/default_devcontainer \
  -t ghcr.io/imbue-ai/sculptor_default_devcontainer:$(date +%Y%m%d) \
  -t ghcr.io/imbue-ai/sculptor_default_devcontainer:latest \
  --push
```

After running, find the SHA here:
https://github.com/orgs/imbue-ai/packages/container/package/sculptor_default_devcontainer
And put it into the `devcontainer.json` file in this directory.

Then, run:

```sh
uv run sculptor/sculptor/cli/dev.py publish-control-plane-and-default-dev-container-to-s3
```

Note: You'll need to be logged in to GHCR with appropriate permissions (`docker login ghcr.io`).
```
echo $GITHUB_TOKEN_FOR_CONTAINER_PUSH | docker login ghcr.io -u $GITHUB_USERNAME --password-stdin
```
