from imbue_core.frozen_utils import FrozenDict
from imbue_core.frozen_utils import JSON
from imbue_core.frozen_utils import deep_freeze_json


def test_frozen_dict_hash() -> None:
    """Ensure that FrozenDict hashes and compares correctly."""
    assert FrozenDict() == FrozenDict()
    assert hash(FrozenDict()) == hash(FrozenDict())

    a = FrozenDict({1: 1, 2: 2})
    b = FrozenDict({2: 2, 1: 1})
    assert len({a, b}) == 1
    assert tuple(a) != tuple(b)


def test_deep_freeze_json() -> None:
    """Ensure that deep_freeze_json exhibits reasonable behavior."""
    json: JSON = {
        "a": [1, 2, 3],
        "b": {
            "c": 4,
            "d": {
                "e": [5, 6, 7],
            },
        },
        "c": False,
        "d": None,
    }

    assert deep_freeze_json(json) == FrozenDict(
        {
            "a": (1, 2, 3),
            "b": FrozenDict(
                {
                    "c": 4,
                    "d": FrozenDict(
                        {
                            "e": (5, 6, 7),
                        }
                    ),
                }
            ),
            "c": False,
            "d": None,
        }
    )
