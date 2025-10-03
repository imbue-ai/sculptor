"""
Runs pytest and uploads the HTML report to S3, in a place that Buildbot expects to find.

This is intended to run on Computronium nodes (by being part of --command to worker.py), but can be run locally during development too.
"""

import os
import subprocess
import sys
from pathlib import Path
from threading import Event

import boto3

from imbue_core.thread_utils import ObservableThread
from sculptor.cli.dev_commands.common import SHARED_BUCKET
from sculptor.cli.dev_commands.common import TEST_RESULTS_DIR
from sculptor.cli.dev_commands.common import upload_file
from sculptor.cli.dev_commands.common import upload_file_continually


def format_file_size(size_bytes: int) -> str:
    """Format file size in bytes to human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def collect_files_to_upload() -> list[Path]:
    """Collect all files that should be uploaded to S3.

    Returns:
        List of file paths to upload
    """
    files_to_upload: list[Path] = []

    test_results_dir = TEST_RESULTS_DIR
    if test_results_dir.exists() and test_results_dir.is_dir():
        print(f"Found {test_results_dir} directory, collecting files...")
        for file_path in test_results_dir.rglob("*"):
            if file_path.is_file():
                files_to_upload.append(file_path)
    else:
        print(f"Note: {test_results_dir} directory not found locally (this is expected for some tests)")

    return files_to_upload


def upload_files_to_s3(client: boto3.client, files_to_upload: list[Path], bucket: str, s3_dir: str) -> tuple[int, int]:
    """Upload collected files to S3 with progress tracking.

    Args:
        client: Boto3 S3 client
        files_to_upload: List of file paths to upload
        bucket: S3 bucket name
        s3_dir: Base S3 directory for uploads

    Returns:
        Tuple of (uploaded_count, total_size_bytes)
    """
    if not files_to_upload:
        print("\nNo files to upload.")
        return 0, 0

    total_size = 0
    uploaded_count = 0
    total_count = len(files_to_upload)

    print(f"\nUploading {total_count} file(s) to S3...")
    for i, local_path in enumerate(files_to_upload, 1):
        file_size = local_path.stat().st_size
        total_size += file_size

        # Format file size for display
        size_str = format_file_size(file_size)

        # Compose full S3 key by converting Path to POSIX format
        s3_key = f"{s3_dir}/{local_path.as_posix()}"

        print(f"[{i}/{total_count}] Uploading {local_path} ({size_str}) to s3://{bucket}/{s3_key}")

        upload_file(local_path, s3_key, bucket, client)
        uploaded_count += 1

    # Format total size for display
    total_size_str = format_file_size(total_size)

    print(f"\nUpload complete: {uploaded_count} file(s) uploaded, total size: {total_size_str}")

    return uploaded_count, total_size


def run_test_in_ci_implementation(command_id: str, pytest_args: list[str]):
    commit_hash = os.getenv("CI_COMMIT_SHA")
    job_name = os.getenv("CI_JOB_NAME")
    job_id = os.getenv("CI_JOB_ID")

    # start background threads to upload stdout and stderr files
    upload_stop_event = Event()
    client = boto3.client("s3")
    stdout_uploader_thread = ObservableThread(
        target=upload_file_continually,
        args=(
            client,
            Path(f"/tmp/stdout_{command_id}.txt"),
            f"gitlab-ci-artifacts/{commit_hash}/{job_name}/{job_id}/{command_id}/stdout.txt",
            upload_stop_event,
        ),
        name="stdout-uploader-thread",
    )
    stderr_uploader_thread = ObservableThread(
        target=upload_file_continually,
        args=(
            client,
            Path(f"/tmp/stderr_{command_id}.txt"),
            f"gitlab-ci-artifacts/{commit_hash}/{job_name}/{job_id}/{command_id}/stderr.txt",
            upload_stop_event,
        ),
        name="stderr-uploader-thread",
    )
    stdout_uploader_thread.start()
    stderr_uploader_thread.start()

    # run the process via popen where we pass our own stdout and stderr handles in
    is_input_allowed = os.environ.get("ALLOW_DEBUG_INPUT", "0").lower() in ("1", "true", "t")
    test_process = subprocess.Popen(
        ["pytest"] + pytest_args,
        stdin=sys.stdin if is_input_allowed else subprocess.DEVNULL,
        stdout=sys.stdout,
        stderr=sys.stderr,
        env={**os.environ},
    )
    exit_code = test_process.wait()

    # this will cause a final pass to upload the full stdout and stderr
    sys.stdout.flush()
    sys.stderr.flush()
    upload_stop_event.set()

    # FIXME: convert to doing this in parallel
    # upload all other artifact files that were created as well:
    files_to_upload = collect_files_to_upload()
    # s3_dir = f"gitlab-ci-artifacts/{commit_hash}/{job_name}/{job_id}/{command_id}"
    s3_dir = f"gitlab-ci-artifacts/{commit_hash}/{job_name}/{job_id}"
    upload_files_to_s3(client, files_to_upload, SHARED_BUCKET, s3_dir)

    # upload the junit and coverage files
    if Path("/tmp/junit.xml").exists():
        upload_file(Path("/tmp/junit.xml"), f"{s3_dir}/{command_id}/junit.xml", SHARED_BUCKET, client)
    if Path("/tmp/coverage.xml").exists():
        upload_file(Path("/tmp/coverage.xml"), f"{s3_dir}/{command_id}/coverage.xml", SHARED_BUCKET, client)

    # make sure all output has been uploaded before exiting
    stdout_uploader_thread.join()
    stderr_uploader_thread.join()

    sys.exit(exit_code)
