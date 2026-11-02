from pathlib import Path

from sculptor.services.workspace_service.vcs.repo_urls import extract_remote_hostname
from sculptor.services.workspace_service.vcs.repo_urls import file_url_to_path
from sculptor.services.workspace_service.vcs.repo_urls import is_github_remote_url
from sculptor.services.workspace_service.vcs.repo_urls import parse_remote_owner_and_name


def test_extract_remote_hostname_reads_scp_style_urls() -> None:
    assert extract_remote_hostname("git@github.com:owner/repo.git") == "github.com"


def test_extract_remote_hostname_reads_https_and_ssh_urls() -> None:
    assert extract_remote_hostname("https://github.example.com/owner/repo") == "github.example.com"
    assert extract_remote_hostname("ssh://git@gitlab.com:22/owner/repo.git") == "gitlab.com"


def test_extract_remote_hostname_is_empty_for_a_local_path() -> None:
    assert extract_remote_hostname("/srv/git/repo.git") == ""


def test_is_github_remote_url_matches_github_and_github_enterprise_hosts() -> None:
    assert is_github_remote_url("git@github.com:owner/repo.git")
    assert is_github_remote_url("https://GitHub.example.com/owner/repo")
    assert not is_github_remote_url("https://gitlab.com/owner/repo")


def test_parse_remote_owner_and_name_strips_the_git_suffix() -> None:
    assert parse_remote_owner_and_name("git@github.com:owner/repo.git") == ("owner", "repo")
    assert parse_remote_owner_and_name("https://github.com/owner/repo") == ("owner", "repo")


def test_parse_remote_owner_and_name_rejects_paths_that_are_not_owner_and_name() -> None:
    assert parse_remote_owner_and_name("https://gitlab.com/group/subgroup/repo.git") is None
    assert parse_remote_owner_and_name("https://github.com/owner") is None


def test_file_url_to_path_strips_only_the_scheme() -> None:
    assert file_url_to_path("file:///Users/dev/file:///repo") == Path("/Users/dev/file:///repo")


def test_file_url_to_path_is_none_for_other_urls() -> None:
    assert file_url_to_path("https://github.com/owner/repo") is None
    assert file_url_to_path(None) is None
