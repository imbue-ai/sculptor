"""PostHog settings for Sculptor.

How the production token reaches the FE bundle:

  1. This file: defines ``SCULPTOR_PRODUCTION_FRONTEND_POSTHOG_TOKEN`` etc.,
     sourced from the build environment (token values are not checked in).
  2. ``sculptor/builder/cli.py::setup_build_vars`` reads the value and prints
     ``export SCULPTOR_FRONTEND_POSTHOG_TOKEN=...`` (alongside Sentry vars).
  3. The justfile's packaging recipes run ``builder setup-build-vars`` and
     ``eval`` its output, so those ``export`` lines populate the shell env
     before ``pnpm run electron:*``.
  4. Vite (``vite.base.config.ts``) reads ``SCULPTOR_FRONTEND_POSTHOG_TOKEN``
     via ``loadEnv`` and bakes it as a compile-time ``define`` constant named
     ``FRONTEND_POSTHOG_TOKEN``.
  5. ``sculptor/frontend/src/common/telemetry/telemetry.ts`` reads
     ``FRONTEND_POSTHOG_TOKEN`` at runtime to initialize posthog-js.

Phase 1 (SCU-763): only the FE-facing tokens are wired into the build. The
BE-side tokens in ``services/user_config/telemetry_info.py`` are no longer in
the runtime path because BE telemetry is dormant — Phase 2 (SCU-764) will
reunify these.

An empty token disables PostHog: the SDK then no-ops, so builds without these
variables simply have analytics disabled.
"""

import os

# Used whenever a user is using a built version of the Frontend.
SCULPTOR_PRODUCTION_FRONTEND_POSTHOG_TOKEN = os.environ.get("SCULPTOR_PRODUCTION_FRONTEND_POSTHOG_TOKEN", "")

# Used when running Sculptor from source.
SCULPTOR_DEV_FRONTEND_POSTHOG_TOKEN = os.environ.get("SCULPTOR_DEV_FRONTEND_POSTHOG_TOKEN", "")

# Used whenever tests are running, either from source or in CI. We disable PostHog
# in tests by passing an empty token; the SDK then no-ops.
SCULPTOR_TESTING_FRONTEND_POSTHOG_TOKEN = ""

# All environments hit the same PostHog ingestion host.
SCULPTOR_FRONTEND_POSTHOG_HOST = "https://us.i.posthog.com"
