from pathlib import Path

import modal

from imbue_core.processes.local_process import run_blocking
from sculptor.services.environment_service.providers.modal.environment_utils import get_ssh_info_from_modal_sandbox


# FIXME: deduplicate this with the other process maybe?  idk if it matters though
def get_ssh_connection_command_as_args(sandbox, is_tty: bool = True, keyfile: str = "modal_ssh_key") -> list[str]:
    host, port, username = get_ssh_info_from_modal_sandbox(sandbox)
    default_ssh_args = [
        "ssh",
        *(["-t"] if is_tty else []),
        "-i",
        keyfile,
        # set the port
        "-p",
        str(port),
        # disable host key checking
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        # make ssh quiet
        "-o",
        "LogLevel=ERROR",
        # where to connect
        f"{username}@{host}",
    ]
    return default_ssh_args


def ensure_ssh_key_for_modal():
    if not Path("modal_ssh_key").exists():
        run_blocking(["ssh-keygen", "-t", "rsa", "-f", "modal_ssh_key", "-N", ""])
    run_blocking(["chmod", "600", "modal_ssh_key"])


def get_code_rsync_command(sandbox: modal.Sandbox, keyfile: str = "modal_ssh_key") -> list[str]:
    current_dir = Path(".").absolute()
    ssh_args = get_ssh_connection_command_as_args(sandbox, is_tty=False, keyfile=keyfile)
    user_and_host = ssh_args.pop(-1)
    ssh_args_str = " ".join(ssh_args)
    return [
        "rsync",
        "-rvzc",
        # this doesn't work because the patterns like "**/.venv" are not interpretted correctly
        # "--filter=':- .gitignore'",
        "--files-from=<(git ls-files)",
        "-e",
        f"'{ssh_args_str}'",
        str(current_dir).rstrip("/") + "/",
        f"{user_and_host}:/user_home/workspace/",
    ]
