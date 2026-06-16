import io
import platform
import shutil
import sys
import time
import zipfile
from datetime import datetime
from datetime import timezone
from pathlib import Path
from uuid import uuid4

import boto3
from botocore import UNSIGNED
from botocore.config import Config as BotoConfig
from fastapi import HTTPException
from loguru import logger

from sculptor import version
from sculptor.config.settings import SculptorSettings
from sculptor.services.dependency_management_service import DependencyManagementService
from sculptor.utils import build as build_utils
from sculptor.utils.build import get_install_path
from sculptor.utils.build import is_packaged
from sculptor.web.data_types import UploadDiagnosticsRequest
from sculptor.web.data_types import UploadDiagnosticsResponse

REPORT_BUCKET = "traceback-uploads-production"
REPORT_S3_PREFIX = "error-reports"

_BYTES_PER_GIBIBYTE = 1024 * 1024 * 1024
# When disk usage is unavailable, assume ample free space so diagnostics never block on it.
_ASSUMED_FREE_BYTES_WHEN_UNKNOWN = 1_000_000_000_000


def _collect_server_diagnostics(
    server_start_time: float,
    dependency_management_service: DependencyManagementService | None = None,
) -> dict[str, str | float | int | None]:
    """Collect diagnostics from the server side."""
    free_gb = (_get_disk_bytes_free() or _ASSUMED_FREE_BYTES_WHEN_UNKNOWN) / _BYTES_PER_GIBIBYTE

    result: dict[str, str | float | int | None] = {
        "version": str(version.__version__),
        "git_sha": str(version.__git_sha__),
        "python_version": sys.version.split()[0],
        "platform": platform.system(),
        "platform_version": platform.release(),
        "free_disk_gb": round(free_gb, 2),
        "data_directory": str(build_utils.get_sculptor_folder()),
        "install_mode": "packaged" if is_packaged() else "source",
        "install_path": str(get_install_path()),
        "uptime_seconds": round(time.time() - server_start_time, 1),
        "ci_job_id": version.ci_job_id,
        "ci_ref": version.ci_ref,
    }
    if dependency_management_service is not None:
        dep_status = dependency_management_service.get_status()
        result["claude_binary_mode"] = dep_status.claude.mode
        result["claude_binary_version"] = dep_status.claude.version
        result["claude_binary_path"] = dep_status.claude.path
        result["claude_binary_in_range"] = (
            str(dep_status.claude.is_version_in_range) if dep_status.claude.is_version_in_range is not None else None
        )
    return result


def _get_disk_bytes_free() -> int | None:
    """Get free disk space in bytes. Duplicated from app.py to avoid circular imports."""
    data_dir = build_utils.get_sculptor_folder()
    try:
        return shutil.disk_usage(data_dir).free
    except FileNotFoundError:
        return None


def _build_report_markdown(
    report_id: str,
    now: datetime,
    description: str,
    current_url: str,
    diagnostics: dict[str, str | float | int | None],
) -> str:
    diagnostics_lines = [f"- **{k}**: {v}" for k, v in diagnostics.items() if v is not None]
    diagnostics_block = "\n".join(diagnostics_lines)
    return (
        "\n\n".join(
            [
                "# Diagnostics Report",
                f"**Report ID**: `{report_id}`\n**Date**: {now.isoformat()}\n**URL**: {current_url}",
                f"## User Description\n\n{description}",
                f"## Diagnostics\n\n{diagnostics_block}",
            ]
        )
        + "\n"
    )


def upload_diagnostics(
    request_body: UploadDiagnosticsRequest,
    settings: SculptorSettings,
    server_start_time: float,
    dependency_management_service: DependencyManagementService | None = None,
) -> UploadDiagnosticsResponse:
    """Bundle diagnostic data and logs into a zip, upload to S3, and return the report ID."""
    log_dir = Path(settings.LOG_PATH)

    now = datetime.now(tz=timezone.utc)
    report_uuid = str(uuid4())
    timestamp = now.strftime("%Y-%m-%dT%H-%M-%S")
    report_id = f"{timestamp}_{report_uuid}"
    s3_key = f"{REPORT_S3_PREFIX}/{report_id}.zip"

    # Merge server-collected diagnostics with any frontend extras
    diagnostics = _collect_server_diagnostics(server_start_time, dependency_management_service)
    for key, value in request_body.frontend_diagnostics.items():
        diagnostics[f"frontend.{key}"] = value

    markdown = _build_report_markdown(report_id, now, request_body.description, request_body.current_url, diagnostics)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("report.md", markdown)

        # Include unrotated server log
        server_log = log_dir / "server" / "logs.jsonl"
        if server_log.is_file():
            zf.write(server_log, "logs/server.jsonl")

        # Include unrotated electron log
        electron_log = log_dir / "electron" / "electron.log"
        if electron_log.is_file():
            zf.write(electron_log, "logs/electron.log")

    zip_bytes = buf.getvalue()

    s3_client = boto3.client(
        "s3",
        config=BotoConfig(signature_version=UNSIGNED),
        region_name="us-west-2",
    )
    # boto3 clients own an underlying connection pool; close it on every path so
    # this per-upload client does not leak its socket fds.
    try:
        s3_client.put_object(Bucket=REPORT_BUCKET, Key=s3_key, Body=zip_bytes)
    except Exception as e:
        logger.error("Failed to upload diagnostics report to S3: {}", e)
        raise HTTPException(status_code=502, detail=f"Failed to upload report: {e}") from e
    finally:
        s3_client.close()

    s3_url = f"s3://{REPORT_BUCKET}/{s3_key}"

    return UploadDiagnosticsResponse(report_id=report_id, s3_url=s3_url)
