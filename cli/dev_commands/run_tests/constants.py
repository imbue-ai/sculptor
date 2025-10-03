import re

ANSI_PATTERN = re.compile(r"\x1B\[\d+(;\d+){0,2}m")
REMOTE_JUNIT_PATH = "/tmp/junit.xml"

TEST_RUNNER_CPU = 2
TEST_RUNNER_RAM_MB = 8192


PYTEST_REPORT_BANNER = """
┌────────────────────────────────────────┐
│ ┌─┐┬ ┬┌┬┐┌─┐┌─┐┌┬┐  ┬─┐┌─┐┌─┐┌─┐┬─┐┌┬┐ │
│ ├─┘└┬┘ │ ├┤ └─┐ │   ├┬┘├┤ ├─┘│ │├┬┘ │  │
│ ┴   ┴  ┴ └─┘└─┘ ┴   ┴└─└─┘┴  └─┘┴└─ ┴  │
└────────────────────────────────────────┘
""".strip()
