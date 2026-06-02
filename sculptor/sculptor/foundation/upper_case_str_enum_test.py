from enum import auto

from sculptor.foundation.upper_case_str_enum import UpperCaseStrEnum


def test_upper_case_str_enum():
    class MyTestEnum(UpperCaseStrEnum):
        SUCCESS = auto()
        INFO = auto()

    assert MyTestEnum.SUCCESS == "SUCCESS"
    assert MyTestEnum.INFO == "INFO"
