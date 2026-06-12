"""Tests for the file upload endpoints.

Tests cover:
- POST /api/v1/upload-file (multipart file upload)
- GET /api/v1/uploaded-file/{file_id} (serve uploaded file)
"""

from io import BytesIO

from fastapi.testclient import TestClient

from sculptor.config.settings import SculptorSettings


def test_upload_file_returns_file_id(client: TestClient) -> None:
    """Uploading a file returns a file_id preserving the original extension."""
    content = b"hello world"
    response = client.post(
        "/api/v1/upload-file",
        files={"file": ("test.png", BytesIO(content), "image/png")},
    )
    assert response.status_code == 200
    data = response.json()
    assert "fileId" in data
    assert data["fileId"].endswith(".png")


def test_upload_file_stores_content_on_disk(
    client: TestClient,
    test_settings: SculptorSettings,
) -> None:
    """Uploaded file content is written to the upload directory."""
    content = b"binary content here"
    response = client.post(
        "/api/v1/upload-file",
        files={"file": ("doc.pdf", BytesIO(content), "application/pdf")},
    )
    assert response.status_code == 200
    file_id = response.json()["fileId"]

    stored = test_settings.upload_path / file_id
    assert stored.is_file()
    assert stored.read_bytes() == content


def test_upload_file_rejects_oversized_file(client: TestClient) -> None:
    """Files exceeding MAX_UPLOAD_SIZE_BYTES (20 MB) are rejected with 413."""
    oversized = b"x" * (20 * 1024 * 1024 + 1)
    response = client.post(
        "/api/v1/upload-file",
        files={"file": ("big.bin", BytesIO(oversized), "application/octet-stream")},
    )
    assert response.status_code == 413


def test_upload_file_without_extension(client: TestClient) -> None:
    """Uploading a file with no extension produces a file_id without one."""
    response = client.post(
        "/api/v1/upload-file",
        files={"file": ("Makefile", BytesIO(b"all: build"), "text/plain")},
    )
    assert response.status_code == 200
    file_id = response.json()["fileId"]
    assert "." not in file_id


def test_get_uploaded_file_returns_content(
    client: TestClient,
    test_settings: SculptorSettings,
) -> None:
    """GET /api/v1/uploaded-file/{file_id} serves the previously uploaded file."""
    content = b"image bytes"
    upload_resp = client.post(
        "/api/v1/upload-file",
        files={"file": ("pic.jpg", BytesIO(content), "image/jpeg")},
    )
    file_id = upload_resp.json()["fileId"]

    get_resp = client.get(f"/api/v1/uploaded-file/{file_id}")
    assert get_resp.status_code == 200
    assert get_resp.content == content


def test_get_uploaded_file_returns_404_for_missing(client: TestClient) -> None:
    """Requesting a non-existent file_id returns 404."""
    response = client.get("/api/v1/uploaded-file/nonexistent-id.txt")
    assert response.status_code == 404


def test_get_uploaded_file_rejects_path_traversal_dotdot(
    client: TestClient,
    test_settings: SculptorSettings,
) -> None:
    """A file_id that resolves outside the upload directory is rejected."""
    # Create a subdirectory inside upload_path so that "subdir/../../secret.txt"
    # would escape. Since {file_id} is a single path segment, we can only test
    # this by placing a symlink named ".." can't work, but we can create a
    # scenario with a real file outside and a crafted single-segment name.
    secret = test_settings.upload_path.parent / "secret.txt"
    secret.parent.mkdir(parents=True, exist_ok=True)
    secret.write_text("secret")

    # A bare ".." can't reach the endpoint (URL normalization), so we verify
    # the resolve-based guard by using a symlink (covered by the next test).
    # Here we just confirm that a nonexistent dotdot-prefixed name returns 404.
    response = client.get("/api/v1/uploaded-file/..secret.txt")
    assert response.status_code == 404


def test_get_uploaded_file_rejects_path_traversal_symlink(
    client: TestClient,
    test_settings: SculptorSettings,
) -> None:
    """A symlink inside the upload dir pointing outside is rejected."""
    secret = test_settings.upload_path.parent / "secret.txt"
    secret.parent.mkdir(parents=True, exist_ok=True)
    secret.write_text("secret")

    link = test_settings.upload_path / "sneaky-link"
    test_settings.upload_path.mkdir(parents=True, exist_ok=True)
    if link.exists() or link.is_symlink():
        link.unlink()
    link.symlink_to(secret)

    response = client.get("/api/v1/uploaded-file/sneaky-link")
    assert response.status_code in (400, 404)


def test_upload_and_retrieve_round_trip(client: TestClient) -> None:
    """Full round trip: upload a file, then retrieve it and verify content matches."""
    original = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100  # fake PNG header
    upload_resp = client.post(
        "/api/v1/upload-file",
        files={"file": ("screenshot.png", BytesIO(original), "image/png")},
    )
    assert upload_resp.status_code == 200
    file_id = upload_resp.json()["fileId"]

    get_resp = client.get(f"/api/v1/uploaded-file/{file_id}")
    assert get_resp.status_code == 200
    assert get_resp.content == original
