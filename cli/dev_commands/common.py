import mimetypes
import time
from pathlib import Path
from threading import Event

SHARED_BUCKET = "int8-shared-internal"
TEST_RESULTS_DIR = Path("test-results")
TEST_REPORT_XML = Path("pytest_junit.xml")
TEST_REPORT_HTML = Path("pytest_junit.html")
TEST_REPORT_COVERAGE = Path("pytest_cov.xml")


def upload_file(local_path: Path, s3_key: str, bucket: str, client):
    # Automatically determine content type from file extension
    content_type, _ = mimetypes.guess_type(str(local_path))
    extra_args = {}
    if content_type:
        extra_args["ContentType"] = content_type

    client.upload_file(str(local_path), bucket, s3_key, ExtraArgs=extra_args)


def test_data_url_for_s3_key(s3_key: str) -> str:
    return f"https://go.snake-blues.ts.net/shared/{s3_key}"


def upload_file_continually(client, local_path: Path, s3_key: str, stop_event: Event):
    while True:
        # we first check, then upload, to make sure that when we're done we do a final upload
        is_done = stop_event.is_set()
        if is_done:
            # wait just a little bit to make sure everything makes it into the files
            time.sleep(1.0)
        if local_path.exists():
            try:
                upload_file(local_path, s3_key, SHARED_BUCKET, client)
            except Exception as e:
                print(f"Failed to upload {local_path} to S3: {e}")
        if is_done:
            print(f"Uploaded final output file to {s3_key}")
            break
        stop_event.wait(10)
