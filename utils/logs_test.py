import time
from pathlib import Path

from loguru import logger

from sculptor.utils.logs import setup_default_test_logging
from sculptor.utils.logs import setup_loggers


def test_log_rotation(tmp_path: Path):
    try:
        logger.remove()
        log_file = tmp_path / "logs.jsonl"
        setup_loggers(log_file, level="TRACE", rotation="1 KB", retention=2)
        # write a small line
        logger.info("hello")
        # check that the log file exists
        time.sleep(1.0)
        assert log_file.exists(), "log file should exist"
        # write a really big line
        message = "x" * 1024
        logger.info(message)
        # make sure that the log file has rotated by making sure there is 1 .json.gz file
        time.sleep(1.0)
        rotated_files = list(log_file.parent.glob("logs*.jsonl.gz"))
        # it's ok to get more than 1, it just depends on exactly when the rotation and other logging happened
        # esp when running in CI with multiple tests in parallel
        assert len(rotated_files) >= 1, f"should have at least 1 rotated file, got {rotated_files}"
    finally:
        logger.remove()
        setup_default_test_logging()
