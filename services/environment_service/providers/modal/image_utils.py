import base64
import hashlib
import json
from pathlib import Path
from typing import Mapping
from typing import Sequence
from typing import cast

import modal
from modal import FilePatternMatcher

from imbue_core.agents.data_types.ids import ProjectID
from imbue_core.frozen_utils import empty_mapping
from sculptor.interfaces.environments.v1.base import ModalEnvironmentConfig
from sculptor.interfaces.environments.v1.base import ModalImage
from sculptor.interfaces.environments.v1.constants import BASHRC_CONTENTS
from sculptor.interfaces.environments.v1.constants import BashMode
from sculptor.interfaces.environments.v1.constants import CONTAINER_SSH_PORT
from sculptor.interfaces.environments.v1.constants import TMUX_CONTENTS
from sculptor.interfaces.environments.v1.constants import TmuxMode
from sculptor.primitives.ids import ModalImageObjectID
from sculptor.services.environment_service.providers.modal.app_context import use_modal_app
from sculptor.services.environment_service.providers.modal.environment_utils import build_sandbox_in_app
from sculptor.utils.secret import Secret


def build_modal_image(
    relative_file_path: str,
    run_id: str,
    project_id: ProjectID,
    secrets: Mapping[str, str | Secret] = empty_mapping(),
    is_including_ssh: bool = True,
    tmux_mode: TmuxMode = TmuxMode.APPEND,
    bash_mode: BashMode = BashMode.APPEND,
    python: str | None = "3.11",
    base_image: str | None = None,
    disable_cache: bool = False,
) -> ModalImage:
    with use_modal_app(run_id) as app:
        # figure out where they want the commands to start from, if anywhere
        base_modal_image = None
        if base_image:
            base_modal_image = modal.Image.from_registry(base_image)

        # define the image with the contents from the file
        modal_dockerfile_contents = Path(relative_file_path).read_text()
        modal_image, copy_layer_cache_keys = _build_image_from_dockerfile_contents(
            modal_dockerfile_contents,
            secrets,
            is_including_ssh=is_including_ssh,
            tmux_mode=tmux_mode,
            bash_mode=bash_mode,
            add_python=python,
            base_image=base_modal_image,
            disable_cache=disable_cache,
        )

        sandbox = None
        sandbox_config = ModalEnvironmentConfig(unencrypted_ports=[CONTAINER_SSH_PORT])
        try:
            sandbox = build_sandbox_in_app(
                app, modal_image, sandbox_config, copy_layer_cache_keys, should_run_ssh_server=False
            )
        finally:
            if sandbox is not None:
                try:
                    sandbox.terminate()
                except modal.exception.SandboxTimeoutError:
                    pass

        return ModalImage(image_id=ModalImageObjectID(modal_image.object_id), app_name=run_id, project_id=project_id)


def _build_image_from_dockerfile_contents(
    dockerfile_contents: str,
    secrets: Mapping[str, str | Secret],
    is_including_ssh: bool,
    tmux_mode: TmuxMode,
    bash_mode: BashMode,
    add_python: str | None,
    base_image: modal.Image | None,
    disable_cache: bool,
) -> tuple[modal.Image, list[str]]:
    """
    Builds a modal image from a LIMITED SUBSET of the dockerfile syntax line-by-line.

    This gets proper caching behavior, which unfortunately you don't get with modal.Image.from_dockerfile.

    Optionally, you can supply an existing base image to build on top of. In that case, your dockerfile_contents should not include a FROM line.

    Known limitations:
    - ARGs do not carry over between lines, and thus don't work. You can use ENV instead, although this is not as ideal.
    """
    copy_layer_cache_keys: list[str] = []
    cache_key_data = [
        json.dumps({**{k: v.unwrap() if isinstance(v, Secret) else v for k, v in secrets.items()}}, sort_keys=True),
        add_python,
        base_image,
    ]
    cache_key_data = [str(x) for x in cache_key_data if x is not None]
    secrets_tuple = (modal.Secret.from_dict(cast(dict[str, str | None], secrets)),) if secrets else ()
    ignore = FilePatternMatcher.from_file(".dockerignore") if Path(".dockerignore").exists() else None
    image: modal.Image | None = base_image
    for line in dockerfile_contents.splitlines():
        line = line.strip()
        if line == "":
            continue
        if line.startswith("#"):
            continue
        if line.startswith("ARG"):
            raise ValueError("ARGs will not work in line-by-line dockerfile execution; use ENV instead.")
        if line.startswith("USER"):
            raise ValueError("USER will not work in line-by-line dockerfile execution.")

        # we need to actually process this line
        cache_key_data.append(line)
        if line.startswith("COPY"):
            line_parts = line.split("COPY ", maxsplit=1)[-1].split()
            assert len(line_parts) == 2, (
                "COPY line must have exactly two arguments. If you are using spaces in your path, sorry, this is not supported"
            )
            source, dest = line_parts
            cached_image_or_key = _get_cached_image_at_copy_line(cache_key_data, line, source, dest)
            if isinstance(cached_image_or_key, str) or disable_cache:
                # pyre-fixme[6]: cached_image_or_key can be Image here (when disable_cache is true), but copy_layer_cache_keys should only contain str's
                copy_layer_cache_keys.append(cached_image_or_key)
                assert image is not None, "image must be set before COPY -- either add a FROM line or set base_image"
                image = image.add_local_dir(
                    Path(source).absolute(),
                    copy=True,
                    remote_path=dest,
                    ignore=ignore if ignore is not None else [],
                )
            else:
                image = cached_image_or_key
        elif line.startswith("FROM"):
            assert len(line.split(" ")) == 2, "FROM line must have exactly one argument"
            assert image is None, "FROM line must be the first nontrivial line"
            # note: modal deps will get injected after this step. may want to undo those.
            image = modal.Image.from_registry(line.split(" ")[1], add_python=add_python, force_build=disable_cache)
        else:
            assert image is not None, (
                f"either base_image needs to be supplied or FROM line must be first nontrivial line, got {line}"
            )
            image = image.dockerfile_commands([line], force_build=disable_cache, secrets=secrets_tuple)

    assert image is not None, "FROM line must be present"

    # Add required content (tmux, ssh, etc.) after all Dockerfile commands are processed
    image = _add_required_content(image, is_including_ssh, tmux_mode, bash_mode)

    return image, copy_layer_cache_keys


def _add_required_content(
    modal_image: modal.Image, is_including_ssh: bool, tmux_mode: TmuxMode, bash_mode: BashMode
) -> modal.Image:
    # include SSH if desired
    if is_including_ssh:
        # install SSH server
        modal_image = modal_image.apt_install("openssh-server")
        modal_image = modal_image.run_commands(["mkdir -p /run/sshd"])
        # make sure the server allows for setting environment variables
        # Ref: https://github.com/ronf/asyncssh/issues/622
        # Ref: https://asyncssh.readthedocs.io/en/latest/api.html#asyncssh.SSHClientConnectionOptions (see `env` argument)
        modal_image = modal_image.run_commands(
            ["sed -i 's/#PermitUserEnvironment no/PermitUserEnvironment yes/' /etc/ssh/sshd_config"],
            ["sed -i 's/AcceptEnv LANG LC_*/AcceptEnv */' /etc/ssh/sshd_config"],
        )

    modal_image = modal_image.run_commands(
        [
            "mkdir -p /root/.tmux/plugins",
            "git clone https://github.com/tmux-plugins/tmux-resurrect /root/.tmux/plugins/tmux-resurrect/",
        ]
    )

    # include tmux content if desired
    if tmux_mode in (TmuxMode.APPEND, TmuxMode.REPLACE):
        is_appending = tmux_mode == TmuxMode.APPEND
        command = _command_to_write_str_to_file(TMUX_CONTENTS, "/root/.tmux.conf", is_appending=is_appending)
        modal_image = modal_image.run_commands([command])

    # include bashrc content if desired
    if bash_mode in (BashMode.APPEND, BashMode.REPLACE):
        is_appending = bash_mode == BashMode.APPEND
        command = _command_to_write_str_to_file(BASHRC_CONTENTS, "/root/.bashrc", is_appending=is_appending)
        modal_image = modal_image.run_commands([command])

    return modal_image


def _command_to_write_str_to_file(contents: str, path: str, is_appending: bool = False) -> str:
    operator = ">>" if is_appending else ">"
    # use base64 to avoid issues with quotes and special characters
    encoded = base64.b64encode(contents.encode()).decode()
    return f"mkdir -p $(dirname '{path}') && echo '{encoded}' | base64 -d {operator} {path}"


def _get_cached_image_at_copy_line(
    cache_key_data: Sequence[str], copy_line: str, source: str, dest: str
) -> modal.Image | str:
    """
    Returns a valid cached image at this line (if any), otherwise returns the cache key (at which to store it)

    Note that for a line to be "valid", it means that all files touched by any layers *after* this copy (and before
    the next copy) must have the same content/permissions hashes now as they did originally.
    """
    hash_str = hashlib.md5()
    hash_str.update("\n".join(cache_key_data).encode("UTF-8"))
    cache_key = hash_str.hexdigest()

    # with database.open_transaction_sync() as transaction:
    #     image_id_record = transaction.maybe_get_by_id(ModalImageRecord, cache_key)
    #     if image_id_record is not None:
    #         return modal.Image.from_id(image_id_record.modal_image_id)

    return cache_key
