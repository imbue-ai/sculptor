## How to configure hooks

1. `settings.json` - these hooks are committed and will run automatically for everyone on this repo.
2. `settings.local.json` - this is gitignored and contains hooks which will run automatically for you for this repo, but not for anyone else.

Currently (as of Feb 2026) Claude code will pick up settings[.local].json updates without needing to reload (but not necessarily newly created settings[local.].json files).
