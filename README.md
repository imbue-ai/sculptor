# Sculptor

## Quickstart

```
uv run fastapi run sculptor/server.py

curl http://localhost:8000/version
```

## Changing the database

By default, Sculptor saves its data in a semi-ephemeral way in an SQLite database under `/tmp/sculptor.db`.

If you'd like to change this, set the DATABASE_URL environment variable. For example:

- `DATABASE_URL="sqlite:////var/lib/sculptor/sculptor.db" uv run fastapi run sculptor/server.py
- `DATABASE_URL="postgresql+psycopg://..." uv run fastapi run sculptor/server.py
