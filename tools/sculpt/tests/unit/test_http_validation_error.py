"""Unit tests for parsing 422 response bodies in the generated sculpt client.

FastAPI serves two differently-shaped 422 bodies: request-validation failures
carry a list of structured errors under `detail`, while a hand-raised
`HTTPException(422, detail="...")` carries a plain string. The generated
`HTTPValidationError.from_dict` must tolerate both so a plain-string detail
surfaces its message instead of crashing.
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
