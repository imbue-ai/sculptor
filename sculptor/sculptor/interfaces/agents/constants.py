from __future__ import annotations

import signal

AGENT_EXIT_CODE_CLEAN_SHUTDOWN_ON_INTERRUPT = 5
AGENT_EXIT_CODE_SHUTDOWN_DUE_TO_EXCEPTION = 6
AGENT_EXIT_CODE_FROM_SIGTERM = 143
AGENT_EXIT_CODE_FROM_SIGINT = 130

# A process killed by signal N may surface either as the conventional positive
# ``128+N`` exit code (when its own signal handler ran to completion and called
# ``sys.exit(128+N)``) or as Python's negative-signal convention ``-N`` (when
# ``Popen.returncode`` reflects the kernel terminating the process before its
# handler finished — ``os.WTERMSIG``). Code that needs to recognize "this was a
# SIGTERM" must accept both, or it will misclassify the kernel-kill path as a
# generic failure.
SIGTERM_EXIT_CODES = frozenset({AGENT_EXIT_CODE_FROM_SIGTERM, -int(signal.SIGTERM)})
SIGINT_EXIT_CODES = frozenset({AGENT_EXIT_CODE_FROM_SIGINT, -int(signal.SIGINT)})
