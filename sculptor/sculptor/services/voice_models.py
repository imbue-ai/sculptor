"""The static, in-repo pin for the "voice models" managed artifact bundle.

Both Moonshine precisions are pinned: fp32 for WebGPU inference and q8 for the
WASM fallback — the renderer picks per machine at load time, mirroring
Local-Vocal's device selection.

The chat input's on-device speech-to-text runs entirely in the renderer
(Moonshine via transformers.js, plus Silero VAD for utterance detection). The
model files are deliberately not shipped in the built app: the backend
downloads them on demand as one logical bundle, verifies each file against the
sha256 pinned here, stores the bundle like other managed dependencies, and
serves the files to the renderer over local HTTP
(``GET /api/v1/voice-models/{path}``).

Voice models are deliberately NOT a ``Dependency`` enum member: that enum is
the agent-execution-environment tool vocabulary (``get_tool_binary_path``),
and this bundle is a host-app concern that must never be provisioned into
agent environments.
"""

from pydantic import Field

from sculptor.foundation.pydantic_serialization import FrozenModel

# Identifier accepted by ``POST /api/v1/dependencies/install`` and reported in
# ``InstallProgress.tool``. Deliberately shaped like a ``Dependency`` member name
# so the install request looks the same for every managed artifact.
VOICE_MODELS_TOOL_NAME = "VOICE_MODELS"


class VoiceModelFile(FrozenModel):
    """One pinned file of the voice-models bundle."""

    serve_path: str = Field(description="Relative path the file is served (and stored on disk) at")
    url: str = Field(description="Pinned upstream download URL")
    sha256: str = Field(description="Expected sha256 of the file contents")
    size_bytes: int = Field(description="Expected size of the file in bytes")


class VoiceModelsPin(FrozenModel):
    """The pinned contents of one voice-models bundle version (style of ``PiPin``).

    The bundle version is bumped whenever any pinned file changes; all files of
    a version activate atomically together.
    """

    version: str
    files: tuple[VoiceModelFile, ...]

    @property
    def total_size_bytes(self) -> int:
        """Aggregate download size, so the UI gets a single 0-100% for the bundle."""
        return sum(file.size_bytes for file in self.files)


_MOONSHINE_REVISION = "b1e9b6aae3c3c7298f10c3798393fdf38e8fbbad"
_MOONSHINE_PIN_BASE_URL = f"https://huggingface.co/onnx-community/moonshine-base-ONNX/resolve/{_MOONSHINE_REVISION}"
# Serve paths mirror the Hugging Face hub URL layout (``<repo>/resolve/main/<file>``)
# so transformers.js in the renderer can fetch through ``env.remoteHost`` with its
# default path template; the pinned download URLs use the immutable commit revision.
_MOONSHINE_SERVE_PREFIX = "onnx-community/moonshine-base-ONNX/resolve/main"

# The renderer pins the same @ricky0123/vad-web package version for its VAD
# runtime; keep the two pins in sync when upgrading.
_VAD_WEB_NPM_VERSION = "0.0.30"


def _moonshine_file(relative_path: str, sha256: str, size_bytes: int) -> VoiceModelFile:
    """A Moonshine repo file, served at the HF-shaped path and downloaded from the pinned revision."""
    return VoiceModelFile(
        serve_path=f"{_MOONSHINE_SERVE_PREFIX}/{relative_path}",
        url=f"{_MOONSHINE_PIN_BASE_URL}/{relative_path}",
        sha256=sha256,
        size_bytes=size_bytes,
    )


VOICE_MODELS_PIN = VoiceModelsPin(
    version="2",
    files=(
        _moonshine_file(
            "config.json",
            sha256="fab7241d1e9fc6c2370c4c6dfb5da79bb54d67ed9ab6b507ac51d29d2abe01d1",
            size_bytes=922,
        ),
        _moonshine_file(
            "generation_config.json",
            sha256="f9b3f711b57be7def2e50a8942f64f36ee0a55fad5b84ff93a687b6c5bcc1d44",
            size_bytes=147,
        ),
        _moonshine_file(
            "tokenizer.json",
            sha256="7b913404bdd039af4756783218af4440bc07fb7d6d8258d677e34f95b3ec416f",
            size_bytes=3761754,
        ),
        _moonshine_file(
            "tokenizer_config.json",
            sha256="edaee394565d428ea98a663ae7209cdcfeefc5585c42d7a570ff7c986df2cd15",
            size_bytes=135735,
        ),
        _moonshine_file(
            "preprocessor_config.json",
            sha256="fa43a7017ef85cd1d0fba0d9aae77c8adb16990ae6f11115631f41ec5d8aa679",
            size_bytes=128,
        ),
        _moonshine_file(
            "onnx/encoder_model.onnx",
            sha256="153e128e7abd64a74ee47f2c3f585c3171c4d46cbb368b032827934c4e01e779",
            size_bytes=80818781,
        ),
        _moonshine_file(
            "onnx/decoder_model_merged.onnx",
            sha256="58778763ca8438963190244d6b26572bdca2cedec56a4b91e828f3f2d69ef3c5",
            size_bytes=166211345,
        ),
        _moonshine_file(
            "onnx/encoder_model_quantized.onnx",
            sha256="1dd9ab0a7f987113d30affcba5a068d11c8f90fa0223caa3e491ade431ad9751",
            size_bytes=20513063,
        ),
        _moonshine_file(
            "onnx/decoder_model_merged_quantized.onnx",
            sha256="cc9f3cd6698a369c6008b41aa60aa3fb3322e7f03c9bdf19d8e6b7200afca4f3",
            size_bytes=42498870,
        ),
        VoiceModelFile(
            serve_path="vad/silero_vad_v5.onnx",
            url=f"https://cdn.jsdelivr.net/npm/@ricky0123/vad-web@{_VAD_WEB_NPM_VERSION}/dist/silero_vad_v5.onnx",
            sha256="2623a2953f6ff3d2c1e61740c6cdb7168133479b267dfef114a4a3cc5bdd788f",
            size_bytes=2327524,
        ),
    ),
)


_FILES_BY_SERVE_PATH = {file.serve_path: file for file in VOICE_MODELS_PIN.files}


def find_voice_model_file(serve_path: str) -> VoiceModelFile | None:
    """Look up a pinned bundle file by its exact serve path.

    This is the serving endpoint's allowlist: anything not literally pinned
    resolves to None.
    """
    return _FILES_BY_SERVE_PATH.get(serve_path)
