from enum import StrEnum

LOW_PRIORITY_LEVEL = 37
MEDIUM_PRIORITY_LEVEL = 38
HIGH_PRIORITY_LEVEL = 39


class ExceptionPriority(StrEnum):
    # for issues that will result in the app crashing
    HIGH_PRIORITY = "HIGH_PRIORITY"
    # for issues that will cause major functionality to stop working
    MEDIUM_PRIORITY = "MEDIUM_PRIORITY"
    # everything else -- e.g. exception sites that are typically retriable, but may catch something unrecoverable
    LOW_PRIORITY = "LOW_PRIORITY"
