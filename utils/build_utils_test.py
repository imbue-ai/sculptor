import json

from imbue_core.git import get_git_repo_root
from sculptor.primitives.constants import TEST_IMAGE_METADATA_CACHE_PATH
from sculptor.utils.build_utils import get_current_build_metadata


def test_image_outdated_quick_faulty_version():
    """
    A quick test of whether you need to rebuild the image.

    Note that if this fails, you MUST rebuild the image.  To do so, you can run:
    ```
    uv run sculptor/sculptor/cli/dev.py refresh-image
    ```

    It's only faulty because it doesn't check everything that might matter, in particular:
    - Changes to the files that are COPY'd into the image in the Dockerfile.slim
    - Changes to code that controls how images are built / runs extra commands on top of the images

    Note that it is considered safe to change python and js dependencies, because we also refresh those on top
    of the base image anyway.  They only matter to the extent that they affect make_default_docker_images.py
    """
    cache_path = get_git_repo_root() / TEST_IMAGE_METADATA_CACHE_PATH
    last_modal_docker_cache_data = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    updated_modal_docker_cache_data = get_current_build_metadata()
    assert last_modal_docker_cache_data == updated_modal_docker_cache_data
