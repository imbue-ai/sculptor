from __future__ import annotations

import json
import time
from io import TextIOWrapper
from typing import Literal

from loguru import logger


class TranscriptCollector:
    def __init__(self, verbose: bool, file: TextIOWrapper) -> None:
        self._verbose = verbose
        self._file = file
        self._sequence_counter: int = 0
        self._turn_index: int = 0
        self._turn_entry_count: int = 0
        self._turn_stdin_count: int = 0
        self._turn_start_time: float | None = None
        self._turn_subagent_count: int = 0

    def record_stdin(self, line: str) -> None:
        msg_type = "non_json"
        subtype: str | None = None
        detail: str | None = None
        payload: dict | None = None

        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            detail = f"len={len(line)}"
            logger.debug(f"[pipe] [stdin] non_json len={len(line)}")
            if self._verbose:
                logger.debug(f"[pipe-verbose] [stdin] {line}")
            self._write_entry("IN", msg_type, subtype, detail, payload)
            return

        if not isinstance(data, dict):
            msg_type = "non_object"
            detail = f"type={type(data).__name__}"
            logger.debug(f"[pipe] [stdin] non_object type={type(data).__name__}")
            if self._verbose:
                logger.debug(f"[pipe-verbose] [stdin] {line}")
            self._write_entry("IN", msg_type, subtype, detail, payload)
            return

        if self._verbose:
            payload = data

        raw_type = data.get("type", "unknown")

        if raw_type == "user":
            msg_type = "user"
        elif raw_type == "control_request":
            msg_type = "control_request"
            request = data.get("request", {})
            if isinstance(request, dict):
                subtype = request.get("subtype")
        else:
            msg_type = raw_type

        log_parts = [f"type={msg_type}"]
        if subtype:
            log_parts.append(f"subtype={subtype}")
        logger.debug(f"[pipe] [stdin] {' '.join(log_parts)}")
        if self._verbose:
            logger.debug(f"[pipe-verbose] [stdin] {line}")

        self._write_entry("IN", msg_type, subtype, detail, payload)

    def record_stdout(self, line: str) -> None:
        msg_type = "non_json"
        subtype: str | None = None
        detail: str | None = None
        payload: dict | None = None

        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            detail = f"len={len(line)}"
            logger.debug(f"[pipe] [stdout] non_json len={len(line)}")
            if self._verbose:
                logger.debug(f"[pipe-verbose] [stdout] {line}")
            self._write_entry("OUT", msg_type, subtype, detail, payload)
            return

        if not isinstance(data, dict):
            msg_type = "non_object"
            detail = f"type={type(data).__name__}"
            logger.debug(f"[pipe] [stdout] non_object type={type(data).__name__}")
            if self._verbose:
                logger.debug(f"[pipe-verbose] [stdout] {line}")
            self._write_entry("OUT", msg_type, subtype, detail, payload)
            return

        if self._verbose:
            payload = data

        raw_type = data.get("type", "unknown")

        if raw_type == "system":
            msg_type = "system"
            subtype = data.get("subtype")
        elif raw_type == "stream_event":
            msg_type = "stream_event"
            event = data.get("event", {})
            if isinstance(event, dict):
                event_type = event.get("type", "unknown")
                if event_type == "content_block_start":
                    content_block = event.get("content_block", {})
                    block_type = content_block.get("type", "unknown") if isinstance(content_block, dict) else "unknown"
                    detail = f"event={event_type} block_type={block_type}"
                elif event_type == "content_block_delta":
                    delta = event.get("delta", {})
                    delta_type = delta.get("type", "unknown") if isinstance(delta, dict) else "unknown"
                    detail = f"event={event_type} delta_type={delta_type}"
                else:
                    detail = f"event={event_type}"
            else:
                detail = "event=unknown"
        elif raw_type in ("assistant", "user"):
            msg_type = raw_type
            role = data.get("message", {}).get("role") if isinstance(data.get("message"), dict) else None
            if role:
                detail = f"role={role}"
        elif raw_type == "result":
            msg_type = "result"
            subtype = data.get("subtype")
        elif raw_type == "rate_limit_event":
            msg_type = "rate_limit_event"
        elif raw_type == "control_response":
            msg_type = "control_response"
        else:
            msg_type = raw_type

        log_parts = [f"type={msg_type}"]
        if subtype:
            log_parts.append(f"subtype={subtype}")
        if detail:
            log_parts.append(detail)
        logger.debug(f"[pipe] [stdout] {' '.join(log_parts)}")
        if self._verbose:
            logger.debug(f"[pipe-verbose] [stdout] {line}")

        self._write_entry("OUT", msg_type, subtype, detail, payload)

    def close(self) -> None:
        """Close the underlying transcript file.

        Idempotent: closing an already-closed file object is a no-op, so this is
        safe to call from every ``ClaudeProcessManager.stop()`` path (including
        repeated stops).
        """
        self._file.close()

    def finalize_turn(self, status: Literal["completed", "interrupted"], cost_usd: float | None = None) -> None:
        turn_start = self._turn_start_time
        duration = (time.monotonic() - turn_start) if turn_start is not None else 0.0

        boundary = {
            "turn_boundary": True,
            "turn_index": self._turn_index,
            "status": status,
            "summary": {
                "total_count": self._turn_entry_count,
                "stdin_count": self._turn_stdin_count,
                "stdout_count": self._turn_entry_count - self._turn_stdin_count,
                "duration_seconds": round(duration, 3),
                "cost_usd": cost_usd,
                "subagent_count": self._turn_subagent_count,
            },
        }
        self._file.write(json.dumps(boundary) + "\n")
        self._file.flush()

        self._turn_index += 1
        self._turn_entry_count = 0
        self._turn_stdin_count = 0
        self._turn_start_time = None
        self._turn_subagent_count = 0

    def _write_entry(
        self,
        direction: Literal["IN", "OUT"],
        msg_type: str,
        subtype: str | None,
        detail: str | None,
        payload: dict | None,
    ) -> None:
        now = time.monotonic()
        if self._turn_start_time is None:
            self._turn_start_time = now

        entry: dict = {
            "sequence": self._sequence_counter,
            "direction": direction,
            "timestamp": now,
            "msg_type": msg_type,
        }
        if subtype is not None:
            entry["subtype"] = subtype
        if detail is not None:
            entry["detail"] = detail
        if payload is not None:
            entry["payload"] = payload

        self._file.write(json.dumps(entry) + "\n")
        self._file.flush()

        self._sequence_counter += 1
        self._turn_entry_count += 1
        if direction == "IN":
            self._turn_stdin_count += 1
        if subtype == "task_started":
            self._turn_subagent_count += 1
