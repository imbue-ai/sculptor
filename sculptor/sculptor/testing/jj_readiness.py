"""One readiness per jj blocker, split by whether Sculptor's jj can still read a repository, for parametrized tests."""

import pytest

from sculptor.services.jj_version import JJ_MINIMUM_GIT_VERSION
from sculptor.web.data_types import JjBlocker
from sculptor.web.data_types import JjIdentity
from sculptor.web.data_types import JjNoIdentity
from sculptor.web.data_types import JjNotInstalled
from sculptor.web.data_types import JjNotRunnable
from sculptor.web.data_types import JjShadowed
from sculptor.web.data_types import JjUnsupportedGit
from sculptor.web.data_types import JjUnsupportedVersion

BLOCKERS_THAT_LET_JJ_READ = (
    pytest.param(
        JjNoIdentity(blocker=JjBlocker.NO_IDENTITY, suggested_identity=JjIdentity(name="", email="")),
        id="no-identity",
    ),
    pytest.param(
        JjShadowed(blocker=JjBlocker.SHADOWED, path="/home/dev/.cargo/bin/jj", version="0.28.2"), id="shadowed"
    ),
    pytest.param(
        JjUnsupportedGit(
            blocker=JjBlocker.UNSUPPORTED_GIT,
            path="/usr/bin/git",
            version="2.39.5",
            minimum_version=JJ_MINIMUM_GIT_VERSION,
        ),
        id="unsupported-git",
    ),
)

BLOCKERS_THAT_STOP_JJ_READING = (
    pytest.param(JjNotInstalled(blocker=JjBlocker.NOT_INSTALLED), id="not-installed"),
    pytest.param(JjNotRunnable(blocker=JjBlocker.NOT_RUNNABLE, error="dyld: Library not loaded"), id="not-runnable"),
    pytest.param(
        JjUnsupportedVersion(blocker=JjBlocker.UNSUPPORTED_VERSION, path="/opt/jj", version="0.28.2"),
        id="unsupported-version",
    ),
)
