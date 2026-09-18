import pytest

from sculptor.services.workspace_service.branch_naming import generate_random_slug
from sculptor.services.workspace_service.branch_naming import resolve_naming_pattern
from sculptor.services.workspace_service.branch_naming import resolve_pattern
from sculptor.services.workspace_service.branch_naming import slugify_workspace_name
from sculptor.services.workspace_service.branch_naming import user_slug_from_full_name


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


def test_resolve_naming_pattern_prefers_a_non_blank_project_pattern() -> None:
    assert resolve_naming_pattern("feature/<slug>", "<user>/<slug>") == "feature/<slug>"
    assert resolve_naming_pattern(None, "<user>/<slug>") == "<user>/<slug>"
    assert resolve_naming_pattern("   ", "<user>/<slug>") == "<user>/<slug>"


def test_user_slug_from_full_name_uses_the_first_token() -> None:
    assert user_slug_from_full_name("Dev Person") == "dev"
    assert user_slug_from_full_name("Ünal") == "unal"
    assert user_slug_from_full_name("   ") == ""
