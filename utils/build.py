import os
from functools import cache
from pathlib import Path
from typing import Final

from loguru import logger
from packaging.version import Version
from pydantic import BaseModel

from sculptor import sentry_settings
from sculptor import version

_SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG: Final = "SCULPTOR_FOLDER_OVERRIDE"


class BuildMetadata(BaseModel):
    """BuildMetadata contains the metadata about the build that is consumed by the Sculptor middleware.

    It is used to configure Sentry.
    """

    sentry_dsn: str
    version: str
    git_commit_sha: str
    is_production: bool


def is_dev_build() -> bool:
    # If the version is a dev release, then we are in a dev build, otherwise we are in a production build.
    return Version(version.__version__).is_devrelease


@cache
def get_sculptor_folder() -> Path:
    path_from_env = os.environ.get("SCULPTOR_FOLDER")
    if path_from_env:
        path = Path(path_from_env)
        logger.debug("Using '{}' for get_sculptor_folder() because the SCULPTOR_FOLDER env is set", path)
    elif is_dev_build():
        path = Path.home() / ".dev_sculptor"
        logger.debug("Using '{}' for get_sculptor_folder() because is_dev_build() is True", path)
    else:
        path = Path.home() / ".sculptor"
        logger.debug("Using default '{}' for get_sculptor_folder()", path)
    path.mkdir(parents=True, exist_ok=True)
    return path


@cache
def get_build_metadata(in_testing: bool = False) -> BuildMetadata:
    """Returns a dictionary of Metadata associated with the build.

    The sole consumer of this object is Sentry.
    """
    if in_testing:
        SENTRY_DSN = sentry_settings.SCULPTOR_TESTING_SENTRY_DSN
        is_production = False
    elif is_dev_build():
        SENTRY_DSN = sentry_settings.SCULPTOR_DEV_BACKEND_SENTRY_DSN
        is_production = False
    else:
        SENTRY_DSN = sentry_settings.SCULPTOR_PRODUCTION_BACKEND_SENTRY_DSN
        is_production = True

    metadata = BuildMetadata(
        sentry_dsn=SENTRY_DSN,
        version=version.__version__,
        git_commit_sha=version.__git_sha__,
        is_production=is_production,
    )
    logger.info("Running Sculptor version {}", metadata)
    return metadata
