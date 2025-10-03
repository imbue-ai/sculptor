# Sculptor CLI User Setup Wizard

Sculptor `sculptor/cli/main.py` entrypoint startup sequence:

1. Anonymous Posthog instance creation (for logging onboarding flow!)
2. User Setup Wizard (`user_setup_wizard.py`)
    - email address
        - **IMPORTANT** immediately after user email, we associate posthog instance with the user (using `.alias`), at this point, posthog events are no longer anonymous (important for attributing onboarding dropoffs).
    - privacy consent
    - telemetry consent
    - git repo mirroring consent
    - API key caching
    - fixing up bad config IDs (auto-generated from email address)
3. Startup Checks
    - executes a list of checks to makes sure product can function
    - exits program if any of them fails with user-friendly error message
4. Backend server startup ('final step')
