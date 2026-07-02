# OpenHost Sculptor — standing agent notes (seeded on first deploy)

This file was **seeded on the first deployment of this Sculptor app**, and it
**persists across reloads/rebuilds** — it lives in the backed-up app-data dir
(`$OPENHOST_APP_DATA_DIR`). You are running inside an **OpenHost**-hosted Sculptor;
detect that from the `OPENHOST_*` env vars (e.g. `OPENHOST_APP_NAME`).

**This file is yours.** Put any standing, system-wide instructions for agents here
freely — nothing in the deploy will overwrite it.

For the current, maintained specifics of this environment — storage and what
survives restarts, where/how to add repositories and authorize `gh`, and what the
`/proxy/<port>/` capability can and can't do — **use the `openhost-environment`
skill**. That skill ships with the deploy image and is refreshed on every release,
so it stays up to date as the environment evolves.
