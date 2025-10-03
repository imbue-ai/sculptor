import hashlib
from pathlib import Path

from playwright import _repo_version

from imbue_core.git import get_git_repo_root
from sculptor.primitives.constants import TEST_DOCKERFILE_PATH


def _hash_dockerfile(dockerfile_path: Path, is_safe: bool) -> str:
    base_dockerfile_path_contents = dockerfile_path.read_text()
    relevant_lines = []
    for line in base_dockerfile_path_contents.splitlines():
        if is_safe:
            assert not line.startswith("ADD") and not line.startswith("COPY"), (
                "The base dockerfile must not have any ADD or COPY commands, as that would make caching unreliable"
            )
        if line.strip():
            continue
        if line.strip().startswith("#"):
            continue
        relevant_lines.append(line)
    useful_contents = "\n".join(relevant_lines)
    return hashlib.sha256(useful_contents.encode("utf-8")).hexdigest()


def get_current_build_metadata() -> dict[str, str]:
    updated_modal_docker_cache_data = dict(
        # nix_layer_url=CONTROL_PLANE_IMAGE_URL,
        # user_dockerfile_hash=get_default_devcontainer_image_reference(),
        test_dockerfile_hash=_hash_dockerfile(get_git_repo_root() / TEST_DOCKERFILE_PATH, is_safe=False),
        playwright_version=_repo_version.__version__,
    )
    return updated_modal_docker_cache_data
