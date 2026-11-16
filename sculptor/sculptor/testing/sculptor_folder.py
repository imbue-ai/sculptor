"""A pytest fixture giving a test its own Sculptor data folder."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from sculptor.utils.build import SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG
from sculptor.utils.build import get_sculptor_folder


@pytest.fixture
def isolated_sculptor_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point the Sculptor data folder, and so the internal folder, at a fresh directory for one test.

    Tests that run a binary through a link Sculptor keeps in its internal folder
    use this, so a concurrent test cannot replace or remove the link under them.
    """
    sculptor_folder = tmp_path / "sculptor_folder"
    monkeypatch.setenv(SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG, str(sculptor_folder))
    get_sculptor_folder.cache_clear()
    yield sculptor_folder
    get_sculptor_folder.cache_clear()
