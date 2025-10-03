import shutil
from pathlib import Path

from imbue_core.processes.local_process import run_blocking
from sculptor.utils.build import get_sculptor_folder
from sculptor.utils.file_utils import copy_dir


def copy_ssh_config(dest: Path):
    # Location of this file (ssh_utils.py)
    here = Path(__file__).resolve().parent

    # Source directory: adjacent ssh_config
    src = here / "ssh_config"

    # Make sure destination exists
    dest.mkdir(parents=True, exist_ok=True)

    # Copy everything (overwrite if exists)
    for item in src.iterdir():
        target = dest / item.name
        if item.is_dir():
            # Replace dir if already exists
            if target.exists():
                shutil.rmtree(target)
            copy_dir(item, target)
        else:
            shutil.copy2(item, target)


def ensure_local_sculptor_ssh_configured() -> Path:
    dot_sculptor = get_sculptor_folder()
    copy_ssh_config(dot_sculptor / "ssh")

    keypair_directory = dot_sculptor / "task_container_keypair"
    run_blocking(["mkdir", "-p", str(keypair_directory)])
    # TODO: replace this with a "generate in a random place, then mv -n"
    run_blocking(
        [
            "bash",
            "-c",
            f"yes n | ssh-keygen -t rsa -f {keypair_directory}/id_rsa -N '' || true",
        ]
    )

    return keypair_directory
