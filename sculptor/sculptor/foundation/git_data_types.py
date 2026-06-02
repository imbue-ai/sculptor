from datetime import datetime
from typing import Annotated

from pydantic.functional_validators import PlainValidator

from sculptor.foundation.pydantic_serialization import SerializableModel


def _validate_git_timestamp(value: str) -> str:
    try:
        datetime.fromisoformat(value)
        return value
    except ValueError:
        raise ValueError(f"Invalid git timestamp: {value}")


class CommitTimestamp(SerializableModel):
    author_ts: Annotated[str, PlainValidator(_validate_git_timestamp)]
    committer_ts: Annotated[str, PlainValidator(_validate_git_timestamp)]
