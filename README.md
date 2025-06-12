# Sculptor

Sculptor is a tool for getting things done with AI agents (with a special focus on software development-related tasks).

It provides a web interface for creating and managing tasks, agents, and the environments in which they run.

## Quickstart

### Install prerequisites

Install ttyd using instructions [here](https://github.com/tsl0922/ttyd).

### Run

```
# start the server
uv run uvicorn sculptor.web.app:APP --reload --port 5050

# send a request for the current version
curl http://localhost:5050/api/v1/version
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
