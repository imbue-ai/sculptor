"""Seed or reset the local dev Sculptor config folder for the `just start` recipes.

Both operations resolve their target from the same functions the running
backend uses (``get_config_path`` / ``get_sculptor_folder``) rather than
hard-coding a path, so they always act on the folder the from-source app
actually reads — which is ``<repo_root>/.dev_sculptor`` when running from source,
not ``~/.dev_sculptor``.
"""

import shutil

import typer
from loguru import logger

from sculptor.services.user_config.user_config import get_config_path
from sculptor.services.user_config.user_config import seed_onboarded_config_if_needed
from sculptor.utils.build import get_sculptor_folder

app = typer.Typer(help="Seed or reset the local dev Sculptor config folder.")


@app.command()
def seed() -> None:
    """Seed a valid, onboarded UserConfig so `just start` boots past onboarding.

    Idempotent: an already-onboarded config is preserved so local settings
    survive repeated launches. Telemetry is left disabled so local QA sessions
    are not reported to Sentry/PostHog.
    """
    config_path = get_config_path()
    if seed_onboarded_config_if_needed(config_path, is_telemetry_enabled=False):
        logger.info("Seeded onboarded dev config at {}", config_path)
    else:
        logger.info("Dev config at {} is already onboarded; leaving it untouched", config_path)


@app.command()
def reset() -> None:
    """Delete the entire dev Sculptor folder so the next launch is a clean first-run.

    Refuses to touch a non-dev folder (e.g. a production ``~/.sculptor``) as a
    safety rail, since this is destructive.
    """
    folder = get_sculptor_folder()
    if "dev" not in folder.name:
        logger.error("Refusing to delete {}: not a dev Sculptor folder", folder)
        raise typer.Exit(code=1)
    if folder.exists():
        logger.info("Removing dev Sculptor folder for a clean first-run: {}", folder)
        shutil.rmtree(folder)
    else:
        logger.info("Dev Sculptor folder {} does not exist; nothing to reset", folder)


if __name__ == "__main__":
    app()
