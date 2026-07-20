"""Unit tests for parsing 422 response bodies in the generated sculpt client.

FastAPI's request-validation 422s carry a list of structured errors, but
`detail` is not guaranteed to be list-shaped: any endpoint can hand-raise
`HTTPException(422, detail=...)` with a plain string or a structured object.
The generated `HTTPValidationError.from_dict` must tolerate every shape so an
unexpected detail surfaces instead of crashing the client.
"""

from sculpt.client.models.http_validation_error import HTTPValidationError
from sculpt.client.models.validation_error import ValidationError


def test_from_dict_tolerates_string_detail() -> None:
    message = "this endpoint hand-raised a plain-string detail"

    result = HTTPValidationError.from_dict({"detail": message})

    assert result.detail == message
    assert message in str(result)


def test_from_dict_parses_list_detail() -> None:
    result = HTTPValidationError.from_dict(
        {"detail": [{"loc": ["body", "model"], "msg": "field required", "type": "value_error.missing"}]}
    )

    assert isinstance(result.detail, list)
    assert len(result.detail) == 1
    assert isinstance(result.detail[0], ValidationError)
    assert result.detail[0].msg == "field required"


def test_from_dict_tolerates_object_detail() -> None:
    # A hand-raised `detail` object must surface its content rather than
    # crash the client.
    result = HTTPValidationError.from_dict({"detail": {"error": "environment not ready"}})

    assert "environment not ready" in str(result)
