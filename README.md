# Sculptor

Sculptor is a tool for getting things done with AI agents (with a special focus on software development-related tasks).

It provides a web interface for creating and managing tasks, agents, and the environments in which they run.

## Quickstart

### Install prerequisites

Install ttyd using instructions [here](https://github.com/tsl0922/ttyd).

On Docker Desktop, set the file sharing implementation to gRPC FUSE under Settings -> General

### Run

From the root of the generally intelligent repo, run the following command to build the project:

```bash
cd sculptor
make install
```

Then run the following command to start the frontend and backend (this will also install dependencies):

```bash
make start REPO_PATH=<path_to_your_repo>
```

`path_to_your_repo` should be a path to the **root** of the git repository that you want to use with Sculptor.


Note, you may need to clear you state if we've made any updates via

```bash
make rm-state
```

See the Makefile for all supported commands.

Finally, you should get a "startup wizard" - make sure you specify your `@imbue.com` email address when prompted for it!!

```
bowei@Boweis-MacBook-Pro sculptor % cd /Users/bowei/code/generally_intelligent/sculptor && DEV_MODE=True uv run python -m sculptor.cli.main
Welcome to Sculptor!
Starting from the following repo: /Users/bowei/code/generally_intelligent/sculptor
Config file not found at /Users/bowei/.sculptor/config.toml

Please provide the following details (press enter to accept):
Email [bowei@generallyintelligent.com]: bowei@imbue.com
Please consider enabling telemetry to help us improve Sculptor:
  0. Nothing at all
  1. Error reports
  2. Error reports and product analytics
  3. Error reports, product analytics and LLM logs
  4. Error reports, product analytics, LLM logs and session recordings
Your choice [3]: 4
Enable repo backup and allow Imbue to improve code generation using the repo? [Y/n]: y
Configuration saved successfully!
Starting Sculptor server version 0.0.1rc1+boweistupid
INFO:     Started server process [88935]
INFO:     Waiting for application startup.

```

If you screwed up, you can edit your `~/.sculptor/config.toml`:

It should look like

```
user_email = "bowei@imbue.com"
user_id = "83105a938568ad9d3b9afd33f83347f2"
organization_id = "5f3e7b675f8f7334e15f91dfcddf868d"
instance_id = "46acaf3c6fd91c41000513a32d2c97f0"
is_error_reporting_enabled = true
is_product_analytics_enabled = true
is_llm_logs_enabled = true
is_session_recording_enabled = true
is_repo_backup_enabled = true
```

## Changing the database

By default, Sculptor saves its data in a semi-ephemeral way in an SQLite database under `/tmp/sculptor.db`.

If you'd like to change this, set the DATABASE_URL environment variable. For example:

- `DATABASE_URL="sqlite:////var/lib/sculptor/sculptor.db" uv run fastapi run sculptor/server.py`
- `DATABASE_URL="postgresql+psycopg://..." uv run fastapi run sculptor/server.py`

## Tests

```
uv run pytest .
```


## Authentication

By default, authentication is off. If you want to enable it, set the `ALLOW_ANONYMOUS_USERS` environment variable to `false`.

When you do that, you need to authenticate using the `Authorization: Bearer` header, e.g.:

```
curl -H "Authorization: Bearer <token>" http://localhost:5050/modal-sandboxes
```

You can get a token by running

```
uv run python sculptor/scripts/create_token.py <username>@imbue.com
```

## Learning More

Take a look at the [docs/](docs/README.md) folder to learn more about the architecture, design, and implementation details of Sculptor.
