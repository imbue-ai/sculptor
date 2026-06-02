import contextlib
import shutil
import tempfile
from pathlib import Path
from typing import Generator


@contextlib.contextmanager
def create_temp_dir(root_dir: Path) -> Generator[Path, None, None]:
    with tempfile.TemporaryDirectory(dir=root_dir) as temp_dir:
        yield Path(temp_dir)
        shutil.rmtree(temp_dir)
