# Database

Sculptor uses SQLite. All data is stored in dual form: an immutable event log (`${table_name}`) and a materialized current-state view (`${table_name}_latest`). See `automanaged.py` for implementation.

Schema definitions are in `sculptor/sculptor/database/models.py`. All `DatabaseModel` subclasses become tables; non-`DatabaseModel` classes are serialized as JSON.

Each table has a specific ID class inheriting from `ObjectID` (defined in `imbue_core/imbue_core/agents/data_types/ids.py`) with a unique prefix/tag. The table-specific subclasses live in `sculptor/sculptor/primitives/ids.py`.

## Migrations

We use Alembic. Migrations run automatically at server startup for local instances.

### SQL Schema Migrations

When you change a database model's SQL schema without creating a migration, `test_there_are_no_missing_sql_schema_migrations()` will fail.

```bash
uv run --project sculptor python sculptor/sculptor/scripts/bump_migrations.py <migration_message>
```

Review the auto-generated migration and adjust if needed.

### JSON Schema Migrations

When you change a JSON-serialized pydantic model in a database field, `test_there_are_no_missing_json_schema_migrations()` will fail.

1. Run `uv run --project sculptor python sculptor/sculptor/scripts/bump_migrations.py <migration_message>`
2. Check `sculptor/sculptor/database/alembic/frozen_pydantic_schemas.json`
3. Decide if a data migration is needed (adding a field with a default is backwards-compatible)
4. If needed, implement logic in the generated migration file (see `sculptor/sculptor/database/alembic/examples/json_schema_migration.py`)
5. Commit the migration file (if needed) and the updated `frozen_pydantic_schemas.json`

### Migration Tests

Every migration must have a test fixture in `sculptor/sculptor/database/alembic/version_tests/`. The `bump_migrations` script generates a stub at `version_tests/test_<revision_id>.py`.

Fill in `seed(connection)` (insert data before migration) and `verify(connection)` (assert data after migration). For no-op migrations, the default empty methods are sufficient.

### Manual Testing

Run this from `sculptor/sculptor/database/` (where `alembic.ini` lives):

```bash
uv run alembic -x dburl=sqlite:///~/.sculptor/database.db upgrade head
```

Back up your database first.
