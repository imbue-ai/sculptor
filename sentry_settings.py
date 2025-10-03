"""Sentry settings for Sculptor."""

# Used whenever a user is using a built version of Sculptor Backend.
SCULPTOR_PRODUCTION_BACKEND_SENTRY_DSN = (
    "https://341e91b4e3409624cc30e65dea668aff@o4504335315501056.ingest.us.sentry.io/4509629913038848"
)

# Used whenever tests are running, either from source or in CI
SCULPTOR_TESTING_SENTRY_DSN = (
    "https://e8c2ef1c8a5ba2b3195b6bb08ebb692b@o4504335315501056.ingest.us.sentry.io/4509674080436224"
)

# Used whenever Imbumans run Sculptor from source.
SCULPTOR_DEV_BACKEND_SENTRY_DSN = (
    "https://19db0a11d653c03f1ac2d1196ed7fa21@o4504335315501056.ingest.us.sentry.io/4509724899213313"
)

# Used whenever a user is using a built version of the Frontend.
SCULPTOR_PRODUCTION_FRONTEND_SENTRY_DSN = (
    "https://0068c22e8d10500b6c854838870f137a@o4504335315501056.ingest.us.sentry.io/4509531732049920"
)

# Used whenever Imbumans run Sculptor from source.
SCULPTOR_DEV_FRONTEND_SENTRY_DSN = (
    "https://60712d56ac0cb234bc5b1aac5d08f937@o4504335315501056.ingest.us.sentry.io/4509759864504320"
)

# Used whenever tests are running, either from source or in CI
SCULPTOR_TESTING_FRONTEND_SENTRY_DSN = (
    "https://f5972a6df675ac67540b0c5db3ea2d75@o4504335315501056.ingest.us.sentry.io/4509759869419520"
)
