from importlib import resources
from pathlib import Path
from typing import Final

from sculptor.primitives.ids import OrganizationReference
from sculptor.primitives.ids import UserReference

USER_FACING_LOG_TYPE: Final = "command_log"
MESSAGE_LOG_TYPE: Final = "message_log"
ANONYMOUS_USER_REFERENCE = UserReference("777777777")
ANONYMOUS_ORGANIZATION_REFERENCE = OrganizationReference("77777777-7777-7777-7777-777777777777")
TEST_IMAGE_METADATA_CACHE_PATH = Path("sculptor/docker/cached_modal_docker_cache.json")
TEST_DOCKERFILE_PATH = Path("sculptor/docker/Dockerfile.slim")

_BASE_DIRECTORY = resources.files("sculptor")
CONTROL_PLANE_TAG_PATH = _BASE_DIRECTORY / "primitives" / "hashes" / "control_plane_tag.txt"
CONTROL_PLANE_MANIFEST_PATH = _BASE_DIRECTORY / "primitives" / "hashes" / "control_plane_manifests.json"
