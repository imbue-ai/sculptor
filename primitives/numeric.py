from pydantic import GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import core_schema


class NormalizedScore(float):
    """
    A normalized score that is always between 0.0 and 1.0.
    """

    def __new__(cls, value: float):
        if not (0.0 <= value <= 1.0):
            raise ValueError("Score must be between 0.0 and 1.0")
        return super().__new__(cls, value)

    @classmethod
    def __get_pydantic_json_schema__(
        cls, core_schema: core_schema.CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        return {"type": "number"}


class Probability(NormalizedScore):
    """
    A probability score that is always between 0.0 and 1.0.

    This class exists mostly to clarify the intent of the score.
    """
