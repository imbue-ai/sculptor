"""Sentry settings for the Sculptor frontend.

The Sculptor backend no longer reports to Sentry (SCU-1291); only the frontend
does. DSN values are not checked in: they are injected from the environment at
build time (see ``builder/cli.py::setup_build_vars``). When a DSN is empty,
the frontend skips Sentry initialization entirely (see
``frontend/src/instrument.ts``), so builds without these variables simply have
error reporting disabled.
"""

import os

# Used whenever a user is using a built version of the Frontend.
SCULPTOR_PRODUCTION_FRONTEND_SENTRY_DSN = os.environ.get("SCULPTOR_PRODUCTION_FRONTEND_SENTRY_DSN", "")

# Used when running Sculptor from source.
SCULPTOR_DEV_FRONTEND_SENTRY_DSN = os.environ.get("SCULPTOR_DEV_FRONTEND_SENTRY_DSN", "")

# Used whenever tests are running, either from source or in CI.
SCULPTOR_TESTING_FRONTEND_SENTRY_DSN = os.environ.get("SCULPTOR_TESTING_FRONTEND_SENTRY_DSN", "")
