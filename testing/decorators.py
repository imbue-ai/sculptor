import pytest

mark_acceptance_test = pytest.mark.parametrize("testing_mode_", ["acceptance"])
flaky = pytest.mark.skip
