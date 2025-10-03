"""
An example migration showing the removal of the "goal" field from the "UpdateGoalAgentMessage" class.

"""

import json
from typing import Any
from typing import Callable

import sqlalchemy as sa
from alembic import op

revision = "xyz123"
down_revision = "abc789"
branch_labels = None
depends_on = None


def upgrade() -> None:
    _bulk_update(_remove_goal)


def downgrade() -> None:
    _bulk_update(_add_empty_goal)


OBJECT_TYPE = "UpdateGoalAgentMessage"
TABLES_AND_PRIMARY_KEYS = (
    ("saved_agent_message", "snapshot_id"),
    # ("saved_agent_message_latest", "object_id"),
)


def _select_rows(dialect: str, table_name: str, primary_key: str) -> sa.TextClause:
    # Selecting as narrow a set of rows as possible is critical for migration performance.
    # (Especially when the table is large.)
    if dialect == "postgresql":
        return sa.text(
            f"""
            SELECT {primary_key}, message
            FROM {table_name}
            WHERE message  ->> 'object_type' = :target
        """
        ).bindparams(sa.bindparam("target", OBJECT_TYPE))
    elif dialect == "sqlite":
        return sa.text(
            f"""
            SELECT {primary_key}, message
            FROM {table_name}
            WHERE json_extract(message, '$.object_type') = :target
        """
        ).bindparams(sa.bindparam("target", OBJECT_TYPE))
    else:
        raise ValueError(f"Unsupported dialect: {dialect}")


def _remove_goal(message: dict[str, Any]) -> None:
    del message["goal"]


def _add_empty_goal(message: dict[str, Any]) -> None:
    message["goal"] = ""


def _bulk_update(update_message_in_place_function: Callable[[dict[str, Any]], None]) -> None:
    connection = op.get_bind()
    dialect = connection.dialect.name
    for table_name, primary_key in TABLES_AND_PRIMARY_KEYS:
        select_statement = _select_rows(dialect, table_name, primary_key)
        rows = connection.execute(select_statement).mappings().all()
        update_data = []
        for row in rows:
            message = json.loads(row.message) if isinstance(row.message, str) else row.message
            update_message_in_place_function(message)
            update_data.append({primary_key: row[primary_key], "message": json.dumps(message)})

        if len(update_data) > 0:
            connection.execute(
                sa.text(
                    f"""
                    UPDATE {table_name}
                    SET message = :message
                    WHERE {primary_key} = :{primary_key}
                """
                ).bindparams(
                    sa.bindparam(primary_key, type_=sa.String),
                    sa.bindparam("message", type_=sa.Text),
                ),
                update_data,
            )
