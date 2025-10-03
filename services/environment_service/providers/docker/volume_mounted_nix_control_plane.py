"""Downloads the Imbue control plane from ghcr.io and makes it available as Docker volumes.

TODO: MAJOR: Figure out a plan for how we're going to clean up these Docker volumes when we move to the next version.

This is very much an optimization to prevent paying a "layer tax" for the control plane.

The idea here is that for content that doesn't change often, we can just fetch it from the image once,
copy it into a volume, and attach it to containers as a read-only volume, rather than a layer.


The alternative would be something like this inside Dockerfile.imbue_addons, which would
copy the control plane directly into the image:
```
ARG SCULPTORBASE_NIX=ghcr.io/imbue-ai/sculptorbase_nix:...
FROM ${SCULPTORBASE_NIX} AS sculptorbase_nix
FROM ubuntu:24.04
COPY --from=sculptorbase_nix /imbue /imbue
```

But the problems with layers are:
1. Changing them invalidates all subsequent layers, and you have to decide an ordering.
2. They're slow to build.

Doing it the "volume mounted" way enables:
* Shorter image build and export times, because the control plane isn't actually a layer in the user's image.
* Theoretically, we can "swap out" the control plane for a newer version without rebuilding the image, but just attaching a different volume.
"""

import json
import os
import subprocess
from typing import Final

from loguru import logger

from imbue_core.background_setup import BackgroundSetup
from imbue_core.itertools import only
from imbue_core.processes.local_process import run_streaming
from sculptor.primitives.constants import CONTROL_PLANE_MANIFEST_PATH
from sculptor.primitives.constants import CONTROL_PLANE_TAG_PATH
from sculptor.services.environment_service.providers.docker.image_utils import fetch_image_from_cdn
from sculptor.services.environment_service.providers.docker.image_utils import get_platform_architecture
from sculptor.utils.timeout import log_runtime_decorator

# Pinning to a SHA lets Docker avoid a network call to check with ghcr.io if the tag has been updated.
# See: https://github.com/orgs/imbue-ai/packages/container/package/sculptorbase_nix.
# disgusting:
_CONTROL_PLANE_TAG: Final[str] = CONTROL_PLANE_TAG_PATH.read_text().strip()
_MANIFEST_DATA = json.loads(CONTROL_PLANE_MANIFEST_PATH.read_text().strip())["manifests"]
_OUR_PLATFORM = get_platform_architecture()
_CONTROL_PLANE_ENTRY = only(x for x in _MANIFEST_DATA if x["platform"]["architecture"] == _OUR_PLATFORM)
_CONTROL_PLANE_SHA: Final[str] = _CONTROL_PLANE_ENTRY["digest"].split("sha256:")[-1]

# There are so many assumptions scattered around the code about what the control plane "can do"
# that it makes sense (to Thad) that a single version of the code only supports a single version
# of the control plane.
CONTROL_PLANE_IMAGE_URL: Final[str] = (
    f"ghcr.io/imbue-ai/sculptorbase_nix:{_CONTROL_PLANE_TAG}@sha256:{_CONTROL_PLANE_SHA}"
)
# We keep each version of the control plane in its own volume.
# It's nice that the same volume can be shared between images; these must be read-only, though.
# TODO: These volumes will need to be garbage collected somehow.

_CONTROL_PLANE_VOLUME_NAME: Final[str] = (
    os.environ.get("SCULPTOR_CONTROL_PLANE_VOLUME") or f"imbue_control_plane_{_CONTROL_PLANE_TAG}_{_CONTROL_PLANE_SHA}"
)


# Docker volume mount arguments for control plane volumes
CONTROL_PLANE_VOLUME_DOCKER_ARGS: Final[tuple[str, ...]] = (
    # Mount the volume as read-only to safely make the same volume available to multiple images.
    *("-v", f"{_CONTROL_PLANE_VOLUME_NAME}:/imbue:ro"),
)


class ControlPlaneFetchError(Exception):
    pass


@log_runtime_decorator()
def _fetch_control_plane_volume() -> None:
    """Fetches /imbue from the control plane image into a single volume.

    There's a race condition here.
    To summarize:
    * Two processes can start populating the volume at the same time, and copy all the same files into it.
    * But once one of them writes the VOLUME_READY.TXT file, all the files should have been written at least once.
    * However, the second process can still be copying files into the volume, and would "overwrite" with the same contents.
    * I talked this through with ChatGPT and convinced myself this is OK: https://chatgpt.com/share/68b090b9-b354-8004-a487-8a6f003d6dee
    * I've looked at Docker's volume auto-initialization and it doesn't handle the race well: https://imbue-ai.slack.com/archives/C06MFB87T4P/p1757356166569579?thread_ts=1757349096.985299&cid=C06MFB87T4P
    """
    # Try to fetch the control plane image from CDN first.
    fetch_image_from_cdn(CONTROL_PLANE_IMAGE_URL)

    logger.info("Making sure {} volume exists.", _CONTROL_PLANE_VOLUME_NAME)

    command = f"""
    set -e
    if [ -f /imbue_volume/VOLUME_READY.TXT ]; then
        echo "_fetch_control_plane_volume: {_CONTROL_PLANE_VOLUME_NAME} already exists and is ready."
    else
        echo "_fetch_control_plane_volume: Initializing {_CONTROL_PLANE_VOLUME_NAME} volume, copying from /imbue to /imbue_volume..."

        # Copy /imbue contents to /imbue_volume/
        # /imbue/. means everything in the directory, including the ".venv" directory, which wouldn't match a * glob.
        rsync -a /imbue/. /imbue_volume/

        touch /imbue_volume/VOLUME_READY.TXT
        echo "_fetch_control_plane_volume: {_CONTROL_PLANE_VOLUME_NAME} finished rsync'ing from image into volume."
    fi
    """

    try:
        finished_process = run_streaming(
            command=[
                *("docker", "run", "--rm"),
                *("-v", f"{_CONTROL_PLANE_VOLUME_NAME}:/imbue_volume"),
                CONTROL_PLANE_IMAGE_URL,
                *("sh", "-c", command),
            ],
            on_output=lambda line, is_stderr: logger.debug(line.strip()),
        )
        logger.info(
            "Finished process to fetch volume_name={}: stdout={}, stderr={}",
            _CONTROL_PLANE_VOLUME_NAME,
            finished_process.stdout,
            finished_process.stderr,
        )
    except subprocess.CalledProcessError as e:
        raise ControlPlaneFetchError(
            f"Failed to fetch control plane volume {_CONTROL_PLANE_VOLUME_NAME} from image {CONTROL_PLANE_IMAGE_URL}"
        ) from e


CONTROL_PLANE_FETCH_BACKGROUND_SETUP: Final[BackgroundSetup] = BackgroundSetup(
    "SculptorControlPlaneVolumeFetchBackgroundSetup",
    _fetch_control_plane_volume,
)
