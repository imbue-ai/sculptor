"""Well-formedness tests for the pinned voice-models bundle (no network)."""

import json
import re
from pathlib import Path
from pathlib import PurePosixPath

from sculptor.services.voice_models import VOICE_MODELS_PIN
from sculptor.services.voice_models import find_voice_model_file

_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")


def test_every_pinned_file_has_https_url_sha256_and_positive_size() -> None:
    for file in VOICE_MODELS_PIN.files:
        assert file.url.startswith("https://"), file.serve_path
        assert _SHA256_HEX_RE.fullmatch(file.sha256), file.serve_path
        assert file.size_bytes > 0, file.serve_path


def test_serve_paths_are_unique() -> None:
    serve_paths = [file.serve_path for file in VOICE_MODELS_PIN.files]
    assert len(serve_paths) == len(set(serve_paths))


def test_serve_paths_are_relative_and_traversal_free() -> None:
    for file in VOICE_MODELS_PIN.files:
        path = PurePosixPath(file.serve_path)
        assert not path.is_absolute(), file.serve_path
        assert ".." not in path.parts, file.serve_path
        assert "\\" not in file.serve_path, file.serve_path


def test_total_size_is_sum_of_pinned_sizes() -> None:
    assert VOICE_MODELS_PIN.total_size_bytes == sum(file.size_bytes for file in VOICE_MODELS_PIN.files)
    assert VOICE_MODELS_PIN.total_size_bytes > 0


def test_moonshine_urls_are_pinned_to_an_immutable_revision() -> None:
    """Moonshine downloads must target a commit sha, never the movable ``main`` ref."""
    for file in VOICE_MODELS_PIN.files:
        if not file.serve_path.startswith("onnx-community/"):
            continue
        match = re.search(r"/resolve/([^/]+)/", file.url)
        assert match is not None, file.url
        assert re.fullmatch(r"[0-9a-f]{40}", match.group(1)), file.url


def test_bundle_contains_the_expected_serve_paths() -> None:
    expected = {
        "onnx-community/moonshine-base-ONNX/resolve/main/config.json",
        "onnx-community/moonshine-base-ONNX/resolve/main/generation_config.json",
        "onnx-community/moonshine-base-ONNX/resolve/main/tokenizer.json",
        "onnx-community/moonshine-base-ONNX/resolve/main/tokenizer_config.json",
        "onnx-community/moonshine-base-ONNX/resolve/main/preprocessor_config.json",
        "onnx-community/moonshine-base-ONNX/resolve/main/onnx/encoder_model_quantized.onnx",
        "onnx-community/moonshine-base-ONNX/resolve/main/onnx/decoder_model_merged_quantized.onnx",
        "vad/silero_vad_v5.onnx",
    }
    assert {file.serve_path for file in VOICE_MODELS_PIN.files} == expected


def test_find_voice_model_file_returns_pinned_entry_for_exact_serve_path() -> None:
    file = find_voice_model_file("vad/silero_vad_v5.onnx")
    assert file is not None
    assert file.url.endswith("/dist/silero_vad_v5.onnx")


def test_find_voice_model_file_rejects_unknown_and_traversal_paths() -> None:
    assert find_voice_model_file("onnx-community/moonshine-base-ONNX/resolve/main/README.md") is None
    assert find_voice_model_file("../vad/silero_vad_v5.onnx") is None
    assert find_voice_model_file("vad/silero_vad_v5.onnx/") is None
    assert find_voice_model_file("") is None


def test_vad_model_url_matches_the_frontend_vad_web_pin() -> None:
    """The Silero weight is pinned to a vad-web npm release, and the renderer runs
    that package's runtime — the two versions must move in lockstep."""
    package_json_path = Path(__file__).parents[2] / "frontend" / "package.json"
    frontend_version = json.loads(package_json_path.read_text())["dependencies"]["@ricky0123/vad-web"]
    vad_file = find_voice_model_file("vad/silero_vad_v5.onnx")
    assert vad_file is not None
    assert f"/@ricky0123/vad-web@{frontend_version}/" in vad_file.url
