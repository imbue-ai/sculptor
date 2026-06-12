import pytest

from sculptor.services.workspace_service.branch_naming import generate_random_slug
from sculptor.services.workspace_service.branch_naming import resolve_pattern
from sculptor.services.workspace_service.branch_naming import slugify_workspace_name


@pytest.mark.parametrize(
    "name, expected",
    [
        ("", ""),
        ("   ", ""),
        ("!!!", ""),
        ("Fix login bug", "fix-login-bug"),
        ("日本語 test", "ri-ben-yu-test"),
    ],
)
def test_slugify_workspace_name_basic(name: str, expected: str) -> None:
    assert slugify_workspace_name(name) == expected


def test_slugify_workspace_name_truncates_on_word_boundary() -> None:
    result = slugify_workspace_name("this is a very long workspace name")
    assert len(result) <= 20
    assert not result.endswith("-")
    assert result == "this-is-a-very-long"


def test_generate_random_slug_shape() -> None:
    slug = generate_random_slug()
    assert slug
    assert slug.count("-") == 1
    left, right = slug.split("-")
    assert any(c.isalpha() for c in left)
    assert any(c.isalpha() for c in right)


def test_generate_random_slug_is_random() -> None:
    for _ in range(3):
        if generate_random_slug() != generate_random_slug():
            return
    pytest.fail("generate_random_slug returned the same value three times in a row")


@pytest.mark.parametrize(
    "pattern, user_slug, name_slug, expected",
    [
        ("<user>/<slug>", "alice", "fix-login", "alice/fix-login"),
        ("<user>/<slug>", "", "fix-login", "fix-login"),
        ("<slug>", "alice", "fix-login", "fix-login"),
        ("<user>-<slug>", "alice", "fix-login", "alice-fix-login"),
        ("<user>/<foo>/<slug>", "alice", "bar", "alice/<foo>/bar"),
        ("<user>/<slug>", "", "", ""),
    ],
)
def test_resolve_pattern(pattern: str, user_slug: str, name_slug: str, expected: str) -> None:
    assert resolve_pattern(pattern, user_slug, name_slug) == expected
