"""Unit tests for parsing 422 response bodies in the generated sculpt client.

FastAPI serves 422 bodies with `detail` in more than one shape: request
validation failures carry a list of structured errors, while a hand-raised
`HTTPException(422, detail=...)` carries whatever was passed — a plain string,
or a structured object. The generated `HTTPValidationError.from_dict` must
tolerate any of these so a non-list detail surfaces instead of crashing.
"""

from sculpt.client.models.http_validation_error import HTTPValidationError
from sculpt.client.models.validation_error import ValidationError


def test_from_dict_tolerates_string_detail() -> None:
    message = "Testing model is only available when integration testing is enabled"

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
    detail = {"code": "agent_plugin_loading_disabled", "message": "Agent plugin loading is disabled."}

    result = HTTPValidationError.from_dict({"detail": detail})

    assert result.detail == detail
