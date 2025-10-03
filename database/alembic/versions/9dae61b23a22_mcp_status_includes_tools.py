"""mcp status includes tools

Revision ID: 9dae61b23a22
Revises: 21c68f672a21
Create Date: 2025-07-15 22:39:34.323723

"""

import json
from typing import Any
from typing import Callable
from typing import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9dae61b23a22"
down_revision: str | None = "21c68f672a21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    _bulk_update(_nest_mcp_servers)


def downgrade() -> None:
    _bulk_update(_extract_mcp_status)


OBJECT_TYPE = "MCPStateUpdateAgentMessage"
TABLES_AND_PRIMARY_KEYS = (("saved_agent_message", "snapshot_id"),)


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


def _nest_mcp_servers(message: dict[str, Any]) -> None:
    mcp_servers = message.get("mcp_servers", {})
    message["mcp_servers"] = {
        server: {
            "status": status,
            "server_type": "imbue_cli",
            "tools": [],
        }
        for server, status in mcp_servers.items()
    }


def _extract_mcp_status(message: dict[str, Any]) -> None:
    message["mcp_servers"] = {
        server_name: server_info["status"] for server_name, server_info in message.get("mcp_servers", {}).items()
    }


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
