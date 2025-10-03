import contextlib
import datetime
import sys
from io import StringIO
from pathlib import Path
from types import TracebackType
from typing import Generator
from typing import Sequence
from typing import TextIO

import modal
from loguru import logger
from modal._output import OutputManager

from imbue_core.computing_environment.data_types import AnyPath


class _MultiWriter(StringIO):
    """A class that writes to multiple files."""

    def __init__(self, files: Sequence[TextIO]) -> None:
        super().__init__()
        self.files = files

    # pyre-fixme[15]: This method should return an int to be consistent with the overridden method.
    def write(self, obj: str) -> None:
        for f in self.files:
            f.write(obj)
            f.flush()  # Ensure immediate output

    def flush(self) -> None:
        for f in self.files:
            f.flush()

    def close(self) -> None:
        for f in self.files:
            if hasattr(f, "close") and f != sys.stdout:
                f.close()

    def isatty(self) -> bool:
        # Under the hood modal uses rich.Console which itself uses isatty, to determine
        # if the output is to a terminal or not. If it is not a terminal, then it won't
        # display interactively in the terminal, e.g. with progress bars, etc.
        return False

    def __enter__(self) -> "_MultiWriter":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()


class _Deduper:
    def __init__(self) -> None:
        super().__init__()
        # Modal often logs the same message multiple times, so we do some deduplication
        self.last_log_message = ""

    def write(self, obj: str) -> None:
        if obj.strip() == self.last_log_message:
            return
        self.last_log_message = obj.strip()
        if obj.strip() == "":
            return
        self._actually_write(obj)

    def _actually_write(self, obj: str) -> None:
        raise NotImplementedError()


class _ModalLoguruInterface(_Deduper, TextIO):
    def __init__(self) -> None:
        super().__init__()
        self.app_id: str | None = None
        self.app_name: str | None = None

    def _actually_write(self, obj: str) -> None:
        extra = dict(
            source="modal",
            app_id=self.app_id,
            app_name=self.app_name,
        )
        logger.debug("{}", obj.strip(), extra=extra)


class DedupeStringIO(_Deduper, StringIO):
    def _actually_write(self, obj: str) -> None:
        StringIO.write(self, obj)


class LessInsaneOutputManager(OutputManager):
    @contextlib.contextmanager
    def show_status_spinner(self):
        yield

    def update_app_page_url(self, app_page_url: str) -> None:
        logger.info(f"View app at {self._app_page_url}")
        self._app_page_url = app_page_url

    def update_task_state(self, task_id: str, state: int):
        pass


@contextlib.contextmanager
def enable_sanctum_output(
    log_file_path: AnyPath | None = None,
    log_to_file: bool = False,
    log_to_terminal: bool = True,
) -> Generator[tuple[StringIO, _ModalLoguruInterface | None], None, None]:
    """Context manager for managing output from Modal apps.

    Note, modal doesn't natively provide any convenient methods for configuring output
    format, so this method handles that.
    """
    # this particular buffer is needed so that we can query the log and see when there are failures
    output_buffer = DedupeStringIO()

    # add some other sinks as well
    writers: list[TextIO] = [output_buffer]

    modal_logger: _ModalLoguruInterface | None = None
    if log_to_terminal:
        # pyre-fixme[45]:
        # _ModalLoguruInterface has unimplemented methods inherited from TextIO,
        # so Pyre considers it to be an abstract class that shouldn't be instantiated.
        # Either implement those methods,
        # or turn this into a pyre-ignore if we think it's fine.
        modal_logger = _ModalLoguruInterface()
        writers.append(modal_logger)
    if log_to_file:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_file_path = Path(f"/tmp/sanctum/sanctum-{timestamp}.log") if log_file_path is None else Path(log_file_path)
        log_file_path.parent.mkdir(parents=True, exist_ok=True)
        writers.append(open(str(log_file_path), "w"))

    if log_to_terminal and log_to_file:
        logger.info("Enabling sanctum output. Logging to `{log_file_path}` and terminal", log_file_path=log_file_path)
    elif log_to_file:
        logger.info("Enabling sanctum output. Logging to `{log_file_path}`", log_file_path=log_file_path)
    elif log_to_terminal:
        logger.info("Enabling sanctum output. Logging to terminal only")

    with _MultiWriter(writers) as f:
        with modal.enable_output(show_progress=True):
            # Here we monkeypatch the underlying modal OutputManager to log to our file
            OutputManager._instance = LessInsaneOutputManager(status_spinner_text="Running sandboxes...")  # type: ignore
            OutputManager._instance._stdout = f  # type: ignore

            yield output_buffer, modal_logger
