import os
from pathlib import Path

import modal
from dockerfile_parse import DockerfileParser
from modal.secret import Secret

from imbue_core.agents.data_types.ids import ProjectID
from sculptor.interfaces.environments.v1.base import ModalEnvironmentConfig
from sculptor.interfaces.environments.v1.base import ModalImage
from sculptor.interfaces.environments.v1.constants import CONTAINER_SSH_PORT
from sculptor.primitives.ids import ModalImageObjectID
from sculptor.services.environment_service.providers.modal.app_context import use_modal_app
from sculptor.services.environment_service.providers.modal.environment_utils import build_sandbox_in_app


def build_modal_image_from_baseline_repo(
    relative_file_path: Path,
    baseline_repo_path: Path,
    run_id: str,
    project_id: ProjectID,
    secrets: dict[str, str] | None = None,
) -> ModalImage:
    with use_modal_app(run_id) as app:
        # define the image with the contents from the file
        modal_image = build_image_from_dockerfile_contents(relative_file_path.read_text(), baseline_repo_path, secrets)

        sandbox = None
        sandbox_config = ModalEnvironmentConfig(unencrypted_ports=[CONTAINER_SSH_PORT])
        try:
            sandbox = build_sandbox_in_app(app, modal_image, sandbox_config, None, should_run_ssh_server=False)
        finally:
            if sandbox is not None:
                try:
                    sandbox.terminate()
                except modal.exception.SandboxTimeoutError:
                    pass

        return ModalImage(image_id=ModalImageObjectID(modal_image.object_id), app_name=run_id, project_id=project_id)


def build_image_from_dockerfile_contents(
    dockerfile_contents: str,
    context_dir: Path | None = None,
    secrets: dict[str, str] | None = None,
    initial_image: modal.Image | None = None,
    is_each_layer_cached: bool = True,
) -> modal.Image:
    dfp = DockerfileParser()
    dfp.content = dockerfile_contents
    try:
        assert not dfp.is_multistage, "Multistage Dockerfiles are not supported yet"
        last_from_index = None
        for i, instr in enumerate(dfp.structure):
            if instr["instruction"] == "FROM":
                last_from_index = i
        if initial_image is None:
            assert last_from_index is not None, "Dockerfile must have a FROM instruction"
            instructions = dfp.structure[last_from_index + 1 :]
            if secrets is not None:
                modal_image = modal.Image.from_registry(dfp.baseimage, Secret.from_dict(secrets))
            else:
                modal_image = modal.Image.from_registry(dfp.baseimage)
        else:
            assert last_from_index is None, "If initial_image is provided, Dockerfile cannot have a FROM instruction"
            instructions = list(dfp.structure)
            modal_image = initial_image

        if len(instructions) > 0:
            if is_each_layer_cached:
                for instr in instructions:
                    modal_image = modal_image.dockerfile_commands([instr["content"]], context_dir=context_dir)
            else:
                # the downside of doing them all at once is that if any one of them fails, modal will re-run all of them
                modal_image = modal_image.dockerfile_commands(
                    [x["content"] for x in instructions], context_dir=context_dir
                )

        return modal_image
    finally:
        # this is really silly, but that library actually writes to a file...
        os.unlink("Dockerfile")
