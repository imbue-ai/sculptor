import shutil
from pathlib import Path

from loguru import logger

from imbue_core.agents.data_types.ids import ProjectID
from sculptor.interfaces.environments.v1.base import LocalImage
from sculptor.primitives.ids import LocalImageID
from sculptor.services.environment_service.providers.local.constants import LOCAL_IMAGE_DIR
from sculptor.utils.file_utils import copy_dir


def build_local_image(
    code_directory: Path,
    project_id: ProjectID,
) -> LocalImage:
    full_id = LocalImageID()
    image_path = _copy_code_directory_to_image_directory(code_directory, full_id)
    return LocalImage(image_id=full_id, image_path=image_path, project_id=project_id)


def _copy_code_directory_to_image_directory(code_directory: Path, image_id: LocalImageID) -> Path:
    assert code_directory.exists(), f"Code directory {code_directory} does not exist"
    image_path = LOCAL_IMAGE_DIR / image_id.suffix
    image_path.mkdir(parents=True, exist_ok=True)

    logger.info("Copying {} to {}", code_directory, image_path)
    if code_directory.is_dir():
        copy_dir(code_directory, image_path, dirs_exist_ok=True)
    else:
        image_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(code_directory, image_path)

    return image_path
