# Sculptor

Sculptor is a tool for getting things done with AI agents (with a special focus on software development-related tasks).

It provides a web interface for creating and managing tasks, agents, and the environments in which they run.

## Quickstart

### Install prerequisites

Install ttyd using instructions [here](https://github.com/tsl0922/ttyd) and install tmux using `brew install tmux`.

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
