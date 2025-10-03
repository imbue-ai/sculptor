import contextlib
from io import StringIO
from typing import Iterator
from typing import cast

import modal

from sculptor.services.environment_service.providers.modal.log_utils import enable_sanctum_output


class ModalAppWithOutputBuffer(modal.App):
    # pyre-ignore[13]: Pyre doesn't like uninitialized attributes; we're initializing it, although hackily outside the __init__ method.
    output_buffer: StringIO


@contextlib.contextmanager
def use_modal_app(
    run_name: str,
    log_to_file: bool = False,
    log_to_terminal: bool = True,
    is_detached: bool = False,
) -> Iterator[ModalAppWithOutputBuffer]:
    with enable_sanctum_output(log_to_file=log_to_file, log_to_terminal=log_to_terminal) as (
        output_buffer,
        modal_logger,
    ):
        sanctum_app = modal.App(run_name)
        with sanctum_app.run(detach=is_detached) as app:
            app.output_buffer = output_buffer

            # smuggle info about the app into the modal log writer so we can add the following to extras
            assert modal_logger is not None
            modal_logger.app_id = sanctum_app.app_id
            modal_logger.app_name = sanctum_app.name

            yield cast(ModalAppWithOutputBuffer, app)
