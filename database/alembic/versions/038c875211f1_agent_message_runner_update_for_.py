import json

import sqlalchemy as sa
from alembic import op

"""Agent message runner update for suggestions/checks

Revision ID: 038c875211f1
Revises: 3a4b4d2f533d
Create Date: 2025-09-09 07:23:20.725886

"""

from typing import Sequence

revision: str = "038c875211f1"
down_revision: str | None = "3a4b4d2f533d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def find_snapshot_user_message_mapping(snapshots, user_messages, other_messages):
    mappings = []

    all_messages = []
    for snapshot_id, msg, created_at in snapshots:
        all_messages.append(("snapshot", snapshot_id, msg, created_at))
    for user_snapshot_id, msg, created_at in user_messages:
        all_messages.append(("user", user_snapshot_id, msg, created_at))
    for other_snapshot_id, msg, created_at in other_messages:
        all_messages.append(("other", other_snapshot_id, msg, created_at))

    all_messages.sort(key=lambda x: x[3])
    current_user_message = None

    for msg_type, snapshot_id, msg, created_at in all_messages:
        if msg_type == "user":
            current_user_message = msg
        elif msg_type == "snapshot":
            if current_user_message:
                mappings.append((snapshot_id, current_user_message["message_id"]))

    return mappings


def upgrade() -> None:
    conn = op.get_bind()
    dialect_name = conn.dialect.name

    if dialect_name == "postgresql":
        result = conn.execute(
            sa.text("""
            SELECT DISTINCT task_id
            FROM saved_agent_message
            WHERE message->>'object_type' = 'AgentSnapshotRunnerMessage'
        """)
        )
    else:
        result = conn.execute(
            sa.text("""
            SELECT DISTINCT task_id
            FROM saved_agent_message
            WHERE json_extract(message, '$.object_type') = 'AgentSnapshotRunnerMessage'
        """)
        )

    tasks_with_snapshots = [row[0] for row in result]
    all_updates = []

    for task_id in tasks_with_snapshots:
        if dialect_name == "postgresql":
            result = conn.execute(
                sa.text("""
                SELECT snapshot_id, message, created_at
                FROM saved_agent_message
                WHERE task_id = :task_id
                ORDER BY created_at
            """),
                {"task_id": task_id},
            )
        else:
            result = conn.execute(
                sa.text("""
                SELECT snapshot_id, message, created_at
                FROM saved_agent_message
                WHERE task_id = :task_id
                ORDER BY created_at
            """),
                {"task_id": task_id},
            )

        messages = result.fetchall()

        user_messages = []
        snapshots = []
        other_messages = []

        for snapshot_id, message_json, created_at in messages:
            msg = json.loads(message_json)
            msg_type = msg.get("object_type")

            if msg_type == "ChatInputUserMessage":
                user_messages.append((snapshot_id, msg, created_at))
            elif msg_type == "AgentSnapshotRunnerMessage":
                snapshots.append((snapshot_id, msg, created_at))
            else:
                other_messages.append((snapshot_id, msg, created_at))

        mappings = find_snapshot_user_message_mapping(snapshots, user_messages, other_messages)

        for snapshot_id, user_message_id in mappings:
            for snap_snapshot_id, snapshot_msg, _ in snapshots:
                if snap_snapshot_id == snapshot_id:
                    snapshot_msg["forUserMessageId"] = user_message_id
                    all_updates.append({"snapshot_id": snapshot_id, "message": json.dumps(snapshot_msg)})
                    break

    if all_updates:
        conn.execute(
            sa.text("UPDATE saved_agent_message SET message = :message WHERE snapshot_id = :snapshot_id"), all_updates
        )


def downgrade() -> None:
    conn = op.get_bind()
    dialect_name = conn.dialect.name
    if dialect_name == "postgresql":
        result = conn.execute(
            sa.text("""
            SELECT snapshot_id, message
            FROM saved_agent_message
            WHERE message->>'object_type' = 'AgentSnapshotRunnerMessage'
        """)
        )
    else:
        result = conn.execute(
            sa.text("""
            SELECT snapshot_id, message
            FROM saved_agent_message
            WHERE json_extract(message, '$.object_type') = 'AgentSnapshotRunnerMessage'
        """)
        )

    updates = []
    for row in result:
        snapshot_id = row[0]
        message_json = json.loads(row[1])
        if "forUserMessageId" in message_json:
            del message_json["forUserMessageId"]
            updates.append({"snapshot_id": snapshot_id, "message": json.dumps(message_json)})

    if updates:
        conn.execute(
            sa.text("UPDATE saved_agent_message SET message = :message WHERE snapshot_id = :snapshot_id"), updates
        )
