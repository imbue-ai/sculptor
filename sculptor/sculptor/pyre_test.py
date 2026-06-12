import subprocess

import pytest
from loguru import logger


def test_pyre_type_checking() -> None:
    # NOTE: if this is failing locally, it may be because you're using `uv run --project sculptor pytest` instead of `uv sync --project sculptor && uv run pytest`.
    #       the former doesn't work, presumably because pyre looks at the files in the venv
    result = subprocess.run(
        ["uv", "run", "pyre", "--noninteractive", "--log-level=CRITICAL"],
        capture_output=True,
        text=True,
    )

    # ENOEXEC (Errno 8) indicates the binary format is incompatible with this platform
    if "[Errno 8]" in result.stderr or "Exec format error" in result.stderr:
        pytest.skip("pyre-check binary is not compatible with this platform (exec format error)")

    # stderr has debugging info; stdout has the identified errors
    logger.debug("pyre stderr:\n{}", result.stderr)
    logger.warning("pyre stdout:\n{}", result.stdout)
    assert result.returncode == 0, result.stdout
