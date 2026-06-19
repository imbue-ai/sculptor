"""
An example migration showing the removal of the "goal" field from the "UpdateGoalAgentMessage" class.

"""

import json
from typing import Any
from typing import Callable
from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "xyz123"
down_revision: str | None = "abc789"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    _bulk_update(_remove_goal)


def downgrade() -> None:
    _bulk_update(_add_empty_goal)


OBJECT_TYPE = "UpdateGoalAgentMessage"
TABLES_AND_PRIMARY_KEYS = (("saved_agent_message", "snapshot_id"),)


def _select_rows(table_name: str, primary_key: str) -> sa.TextClause:
    # Selecting as narrow a set of rows as possible is critical for migration performance.
    # (Especially when the table is large.)
    return sa.text(
        f"""
        SELECT {primary_key}, message
        FROM {table_name}
        WHERE json_extract(message, '$.object_type') = :target
    """
    ).bindparams(sa.bindparam("target", OBJECT_TYPE))


def _remove_goal(message: dict[str, Any]) -> None:
    del message["goal"]


def _add_empty_goal(message: dict[str, Any]) -> None:
    message["goal"] = ""


def _bulk_update(update_message_in_place_function: Callable[[dict[str, Any]], None]) -> None:
    connection = op.get_bind()
    for table_name, primary_key in TABLES_AND_PRIMARY_KEYS:
        select_statement = _select_rows(table_name, primary_key)
        rows = connection.execute(select_statement).mappings().all()
        update_data = []
        for row in rows:
            message = json.loads(row.message) if isinstance(row.message, str) else row.message
            update_message_in_place_function(message)
            update_data.append({primary_key: row[primary_key], "message": json.dumps(message)})

        if update_data:
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
