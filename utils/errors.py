import sys
from pathlib import Path
from sqlite3 import OperationalError
from typing import Callable

import psutil
from loguru import logger
from pydantic import EmailStr
from sentry_sdk import get_current_scope
from sentry_sdk.types import Event
from sentry_sdk.types import Hint

from imbue_core.common import is_live_debugging
from imbue_core.error_utils import BeforeSendType
from imbue_core.error_utils import RATE_LIMITED_EXCEPTION_TYPES
from imbue_core.error_utils import get_traceback_with_vars
from imbue_core.error_utils import setup_sentry as setup_sentry_
from imbue_core.s3_uploader import EXTRAS_UPLOADED_FILES_KEY
from imbue_core.s3_uploader import get_s3_upload_key
from imbue_core.s3_uploader import get_s3_upload_url
from imbue_core.s3_uploader import upload_to_s3_with_key
from imbue_core.thread_utils import ObservableThread
from sculptor.config.user_config import get_user_config_instance
from sculptor.services.data_model_service.sql_implementation import MissingSQLTableError
from sculptor.utils.build import BuildMetadata
from sculptor.utils.logs import LOG_EXTENSION
from sculptor.utils.logs import ZIPPED_LOG_EXTENSION

# sentry's size limits are annoyingly hard to evaluate before sending the event. we'll just try to be conservative.
# https://docs.sentry.io/concepts/data-management/size-limits/
# https://develop.sentry.dev/sdk/data-model/envelopes/#size-limits
MAX_SENTRY_ATTACHMENT_SIZE = 10 * 1024 * 1024


def _get_sculptor_log_folder_from_scope() -> Path | None:
    # Fall back to Sentry's context
    scope = get_current_scope()
    sculptor_config = scope._contexts.get("sculptor_config", {})
    log_folder_path_str = sculptor_config.get("log_folder_path")

    if log_folder_path_str:
        logger.info("Using Sentry context log_folder_path: {}", log_folder_path_str)
        log_folder_path = Path(log_folder_path_str)
        if log_folder_path.exists():
            return log_folder_path

    logger.info("No log file path found")
    return None


def get_sculptor_db_contents() -> bytes | None:
    scope = get_current_scope()
    sculptor_config = scope._contexts.get("sculptor_config", {})
    db_path_str = sculptor_config.get("db_path")
    if db_path_str:
        db_path = Path(db_path_str)
        if db_path.exists():
            return db_path.read_bytes()
    return None


def get_disk_percentage_full() -> float | None:
    scope = get_current_scope()
    sculptor_config = scope._contexts.get("sculptor_config", {})
    db_path_str = sculptor_config.get("db_path")
    if not db_path_str:
        return None
    return psutil.disk_usage(db_path_str).percent


def _upload_traceback(key: str, exception: BaseException) -> None:
    tb_with_vars = get_traceback_with_vars(exception)
    if tb_with_vars is not None:
        upload_to_s3_with_key(key, tb_with_vars.encode())


def _upload_sculptor_logs(key: str, file_path: Path) -> None:
    upload_to_s3_with_key(key, file_path.read_bytes())


def _upload_sculptor_db(key: str) -> None:
    sculptor_db = get_sculptor_db_contents()
    if sculptor_db is not None:
        upload_to_s3_with_key(key, sculptor_db)


def add_extra_info_hook(event: Event, hint: Hint) -> tuple[Event, Hint, tuple[Callable, ...]]:
    """The add_extra_info_hook gets called in the SentryEventHandler. This seems a little too early in the process for
    sending things to s3.
    """
    # Add live debugging state as a tag for easy filtering in Sentry UI
    if "tags" not in event:
        event["tags"] = {}
    event["tags"]["is_live_debugging"] = str(is_live_debugging())

    # upload data to S3 and include them in the event
    s3_uploads = []
    callbacks = []

    # this traceback is from the logger call site!
    tb_s3_key = get_s3_upload_key("logsite_traceback_with_vars", ".txt")
    s3_uploads.append(get_s3_upload_url(tb_s3_key))
    exception = sys.exception()
    if exception is not None:
        callbacks.append(lambda key=tb_s3_key, exc=exception: _upload_traceback(key, exc))
    else:
        try:
            raise Exception("this is an exception to get the current traceback")
        except Exception as e:
            callbacks.append(lambda captured_exception=e: _upload_traceback(tb_s3_key, captured_exception))

    sculptor_log_folder = _get_sculptor_log_folder_from_scope()
    if sculptor_log_folder is not None:
        # upload each of the uncompressed log files
        for log_file in sculptor_log_folder.glob(f"*.{LOG_EXTENSION}"):
            s3_key = get_s3_upload_key(log_file.stem, f".{LOG_EXTENSION}")
            s3_url = get_s3_upload_url(s3_key)
            callbacks.append(lambda key=s3_key, file_path=log_file: _upload_sculptor_logs(key, file_path))
            s3_uploads.append(s3_url)
        # upload each of the compressed log files
        for log_file in sculptor_log_folder.glob(f"*.{ZIPPED_LOG_EXTENSION}"):
            s3_key = get_s3_upload_key(log_file.stem, f".{ZIPPED_LOG_EXTENSION}")
            s3_url = get_s3_upload_url(s3_key)
            callbacks.append(lambda key=s3_key, file_path=log_file: _upload_sculptor_logs(key, file_path))
            s3_uploads.append(s3_url)
        # see if there are any electronic logs as well
        electron_log_folder = sculptor_log_folder.parent / "electron"
        if electron_log_folder.exists():
            for log_file in electron_log_folder.glob(f"*.log"):
                s3_key = get_s3_upload_key(log_file.stem, f".log")
                s3_url = get_s3_upload_url(s3_key)
                callbacks.append(lambda key=s3_key, file_path=log_file: _upload_sculptor_logs(key, file_path))
                s3_uploads.append(s3_url)

    sculptor_db_s3_key = get_s3_upload_key("sculptor_db", ".db")
    s3_uploads.append(get_s3_upload_url(sculptor_db_s3_key))
    callbacks.append(lambda key=sculptor_db_s3_key: _upload_sculptor_db(key))

    s3_uploads = [upload for upload in s3_uploads if upload is not None]

    if s3_uploads:
        if EXTRAS_UPLOADED_FILES_KEY in event["extra"]:
            obj = event["extra"].get(EXTRAS_UPLOADED_FILES_KEY + "_extras", None)
            if obj:
                # pyre-fixme[16]: Not sure what this type is
                obj.extend(s3_uploads)
        else:
            event["extra"][EXTRAS_UPLOADED_FILES_KEY + "_extras"] = s3_uploads
    event["extra"]["disk_usage_percent"] = get_disk_percentage_full()

    return event, hint, tuple(callbacks)


def setup_sentry(
    build_metadata: BuildMetadata,
    log_folder: Path,
    db_path: str,
    environment: str | None = None,
    before_send: BeforeSendType | None = None,
) -> None:
    # make sure all of our threads explode if we run into an irrecoverable exception
    ObservableThread.set_irrecoverable_exception_handler(is_irrecoverable_exception)

    # Get user email from config for Sentry initialization
    user_config = get_user_config_instance()
    # if None - then username is determined dynamically, on a per-request basis.
    user_email = user_config.user_email if user_config else None

    rate_limited_exceptions = RATE_LIMITED_EXCEPTION_TYPES + (MissingSQLTableError,)

    setup_sentry_(
        dsn=build_metadata.sentry_dsn,
        username=user_email,
        release_id=build_metadata.version,
        add_extra_info_hook=add_extra_info_hook,
        environment=environment,
        rate_limited_exceptions=rate_limited_exceptions,
        before_send=before_send,
    )
    # Store the log file path in Sentry's global context
    scope = get_current_scope()
    scope.set_context("sculptor_config", {"log_folder_path": log_folder, "db_path": db_path})
    scope.set_tag("git_sha", build_metadata.git_commit_sha)
    logger.info("Sentry initialized with DSN: {}", build_metadata.sentry_dsn)
    logger.info("Sentry initialized with log folder: {}", log_folder)


def set_sentry_user_for_current_scope(user_email: EmailStr) -> None:
    scope = get_current_scope()
    scope.set_user({"username": str(user_email)})


def is_irrecoverable_exception(exception: BaseException) -> bool:
    """
    For some exceptions, we want to crash the app immediately.

    By convention, in these cases we also:
        - don't want to send the exception to Sentry because we can't really act on it
        - but we want to emit a posthog event to keep an eye on how often this happens

    """
    exception_message = str(exception)
    if isinstance(exception, OperationalError) and (
        "disk I/O error" in exception_message or "unable to open database file" in exception_message
    ):
        return True
    # Add more such cases here if needed.
    return False
