"""Tests for clone_strategy module — verifying remote layout, ref copying, and upstream mirroring."""

import subprocess
from pathlib import Path

from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.services.workspace_service.environment_manager.environments.clone_strategy import clone_repository


def _make_repo(path: Path, branch: str = "main") -> None:
    """Create a minimal git repo with one commit on the given branch."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path, check=True, capture_output=True)
    (path / "file.txt").write_text("content")
    subprocess.run(["git", "add", "."], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)
    # Ensure we're on the expected branch name
    current = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=path, check=True, capture_output=True, text=True
    ).stdout.strip()
    if current != branch:
        subprocess.run(["git", "branch", "-m", current, branch], cwd=path, check=True, capture_output=True)


def _add_remote_with_branches(repo_path: Path, remote_path: Path) -> None:
    """Point repo_path's origin at remote_path and fetch, creating origin/* refs."""
    subprocess.run(
        ["git", "remote", "add", "origin", str(remote_path)], cwd=repo_path, check=True, capture_output=True
    )
    subprocess.run(["git", "fetch", "origin"], cwd=repo_path, check=True, capture_output=True)


def _get_ref_hash(repo_path: Path, ref: str) -> str | None:
    """Resolve a ref to its hash, or None if it doesn't exist."""
    result = subprocess.run(["git", "rev-parse", "--verify", ref], cwd=repo_path, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _list_remote_refs(repo_path: Path, remote: str) -> list[str]:
    """List all remote-tracking branch names for a given remote."""
    result = subprocess.run(
        ["git", "branch", "-r", "--format=%(refname:short)"], cwd=repo_path, capture_output=True, text=True
    )
    if result.returncode != 0:
        return []
    return [b.strip() for b in result.stdout.strip().splitlines() if b.strip().startswith(f"{remote}/")]


def _list_remotes(repo_path: Path) -> list[str]:
    """List the remotes configured on a repo."""
    result = subprocess.run(["git", "remote"], cwd=repo_path, check=True, capture_output=True, text=True)
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _get_remote_url(repo_path: Path, remote: str) -> str:
    """Return the URL for a given remote."""
    result = subprocess.run(
        ["git", "remote", "get-url", remote], cwd=repo_path, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


class TestCloneRepositoryCopiesOriginRefs:
    """Tests that clone_repository copies origin/* refs from the source into the clone."""

    def test_clone_copies_origin_refs(self, tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup) -> None:
        """Origin refs in the source repo should be available in the clone."""
        # Set up a "remote" bare-ish repo with multiple branches
        remote_repo = tmp_path / "remote"
        _make_repo(remote_repo, "main")
        subprocess.run(["git", "checkout", "-b", "develop"], cwd=remote_repo, check=True, capture_output=True)
        (remote_repo / "dev.txt").write_text("dev")
        subprocess.run(["git", "add", "."], cwd=remote_repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "dev commit"], cwd=remote_repo, check=True, capture_output=True)
        subprocess.run(["git", "checkout", "main"], cwd=remote_repo, check=True, capture_output=True)

        # User's local repo with origin pointing to remote
        source = tmp_path / "source"
        _make_repo(source, "main")
        _add_remote_with_branches(source, remote_repo)

        # Clone via our strategy
        clone_dest = tmp_path / "clone"
        clone_repository(source, clone_dest, test_root_concurrency_group)

        # Verify origin/main and origin/develop exist in the clone
        clone_refs = _list_remote_refs(clone_dest, "origin")
        assert "origin/main" in clone_refs
        assert "origin/develop" in clone_refs

        # Verify hashes match the source
        for ref in ("origin/main", "origin/develop"):
            source_hash = _get_ref_hash(source, ref)
            clone_hash = _get_ref_hash(clone_dest, ref)
            assert source_hash is not None
            assert clone_hash == source_hash

    def test_clone_without_origin_skips_ref_copy(
        self, tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
    ) -> None:
        """When source has no remotes, the clone falls back to a single origin pointing at the source path."""
        source = tmp_path / "source"
        _make_repo(source, "main")

        clone_dest = tmp_path / "clone"
        clone_repository(source, clone_dest, test_root_concurrency_group)

        # No synthetic `local` remote
        local_refs = _list_remote_refs(clone_dest, "local")
        assert len(local_refs) == 0
        assert "local" not in _list_remotes(clone_dest)

        # Fallback origin remote points at the source path and has origin/main populated
        assert _list_remotes(clone_dest) == ["origin"]
        assert Path(_get_remote_url(clone_dest, "origin")).resolve() == source.resolve()
        assert "origin/main" in _list_remote_refs(clone_dest, "origin")

    def test_clone_origin_refs_resolvable_for_merge_base(
        self, tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
    ) -> None:
        """merge-base should work against origin/main in the clone."""
        remote_repo = tmp_path / "remote"
        _make_repo(remote_repo, "main")

        # Clone remote so source shares history with origin/main
        source = tmp_path / "source"
        subprocess.run(["git", "clone", str(remote_repo), str(source)], check=True, capture_output=True)

        # Create a feature branch in source
        subprocess.run(["git", "checkout", "-b", "feature"], cwd=source, check=True, capture_output=True)
        (source / "feature.txt").write_text("feature")
        subprocess.run(["git", "add", "."], cwd=source, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "feature commit"], cwd=source, check=True, capture_output=True)

        clone_dest = tmp_path / "clone"
        clone_repository(source, clone_dest, test_root_concurrency_group, target_branch="feature")

        # merge-base HEAD origin/main should succeed in the clone
        result = subprocess.run(
            ["git", "merge-base", "HEAD", "origin/main"],
            cwd=clone_dest,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert result.stdout.strip() != ""


def test_clone_checkout_branch_not_on_source_head(
    tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    """Clone checks out ``target_branch`` even when it differs from the source's current branch."""
    remote_repo = tmp_path / "remote"
    _make_repo(remote_repo, "main")

    # Source repo cloned from remote, then switched to a feature branch
    source = tmp_path / "source"
    subprocess.run(["git", "clone", str(remote_repo), str(source)], check=True, capture_output=True)
    subprocess.run(["git", "checkout", "-b", "feature"], cwd=source, check=True, capture_output=True)
    (source / "feature.txt").write_text("feature")
    subprocess.run(["git", "add", "."], cwd=source, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "feature commit"], cwd=source, check=True, capture_output=True)

    # Clone with target_branch="main" — source HEAD is on "feature", not "main"
    clone_dest = tmp_path / "clone"
    clone_repository(source, clone_dest, test_root_concurrency_group, target_branch="main")

    # Verify the clone is on main
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=clone_dest, capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "main"


def test_clone_no_origin_checkout_branch_not_on_source_head(
    tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    """Clone of a no-remote source can check out a branch that only exists via the synthetic origin.

    The fallback ``origin`` needs a fetch refspec for ``git checkout <branch>``
    to DWIM to ``refs/remotes/origin/<branch>``; without it, git refuses to
    create a local branch from the remote-tracking ref.
    """
    source = tmp_path / "source"
    _make_repo(source, "main")
    # Add two more branches on top of the initial main branch.
    subprocess.run(["git", "checkout", "-b", "testing"], cwd=source, check=True, capture_output=True)
    (source / "testing.txt").write_text("testing")
    subprocess.run(["git", "add", "."], cwd=source, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "testing commit"], cwd=source, check=True, capture_output=True)
    subprocess.run(["git", "checkout", "-b", "feature_branch"], cwd=source, check=True, capture_output=True)
    (source / "feature.txt").write_text("feature")
    subprocess.run(["git", "add", "."], cwd=source, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "feature commit"], cwd=source, check=True, capture_output=True)
    # Leave source HEAD on testing, not feature_branch.
    subprocess.run(["git", "checkout", "testing"], cwd=source, check=True, capture_output=True)

    clone_dest = tmp_path / "clone"
    clone_repository(source, clone_dest, test_root_concurrency_group, target_branch="feature_branch")

    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=clone_dest, capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "feature_branch"


def test_clone_with_origin_only_has_single_remote_and_no_local(
    tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    """Cloning a source with only origin produces a clone with exactly one remote (origin) and no local remote."""
    remote_repo = tmp_path / "remote"
    _make_repo(remote_repo, "main")

    source = tmp_path / "source"
    _make_repo(source, "main")
    _add_remote_with_branches(source, remote_repo)

    clone_dest = tmp_path / "clone"
    clone_repository(source, clone_dest, test_root_concurrency_group)

    # Exactly one remote named origin
    assert _list_remotes(clone_dest) == ["origin"]

    # origin URL matches source
    assert _get_remote_url(clone_dest, "origin") == _get_remote_url(source, "origin")

    # checkout.defaultRemote is not set
    result = subprocess.run(
        ["git", "config", "--get", "checkout.defaultRemote"], cwd=clone_dest, capture_output=True, text=True
    )
    assert result.returncode != 0

    # No local/* remote-tracking refs
    assert _list_remote_refs(clone_dest, "local") == []


def test_clone_preserves_multiple_source_remotes(
    tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    """Cloning a source with origin + upstream carries both remotes and their tracking refs."""
    remote_origin = tmp_path / "remote_origin"
    _make_repo(remote_origin, "main")

    remote_upstream = tmp_path / "remote_upstream"
    _make_repo(remote_upstream, "main")

    source = tmp_path / "source"
    _make_repo(source, "main")
    _add_remote_with_branches(source, remote_origin)
    subprocess.run(
        ["git", "remote", "add", "upstream", str(remote_upstream)], cwd=source, check=True, capture_output=True
    )
    subprocess.run(["git", "fetch", "upstream"], cwd=source, check=True, capture_output=True)

    clone_dest = tmp_path / "clone"
    clone_repository(source, clone_dest, test_root_concurrency_group)

    # Both remotes present
    assert sorted(_list_remotes(clone_dest)) == ["origin", "upstream"]

    # URLs match source
    assert _get_remote_url(clone_dest, "origin") == _get_remote_url(source, "origin")
    assert _get_remote_url(clone_dest, "upstream") == _get_remote_url(source, "upstream")

    # Both remote-tracking branch sets are populated
    assert "origin/main" in _list_remote_refs(clone_dest, "origin")
    assert "upstream/main" in _list_remote_refs(clone_dest, "upstream")

    # upstream/main is resolvable without a fetch
    result = subprocess.run(
        ["git", "log", "upstream/main", "--format=%H", "-n", "1"],
        cwd=clone_dest,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert result.stdout.strip() != ""


def test_clone_with_zero_remotes_falls_back_to_origin_at_source_path(
    tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    """Cloning a source with no remotes creates a single origin pointing at the source path."""
    source = tmp_path / "source"
    _make_repo(source, "main")
    # Add a second branch with a new commit so source has refs/heads/main and refs/heads/other
    subprocess.run(["git", "checkout", "-b", "other"], cwd=source, check=True, capture_output=True)
    (source / "other.txt").write_text("other")
    subprocess.run(["git", "add", "."], cwd=source, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "other commit"], cwd=source, check=True, capture_output=True)
    subprocess.run(["git", "checkout", "main"], cwd=source, check=True, capture_output=True)

    clone_dest = tmp_path / "clone"
    clone_repository(source, clone_dest, test_root_concurrency_group)

    # Exactly one remote named origin
    assert _list_remotes(clone_dest) == ["origin"]

    # origin URL equals the source path on disk (resolve for macOS /var ↔ /private/var symlinks)
    assert Path(_get_remote_url(clone_dest, "origin")).resolve() == source.resolve()

    # origin/main and origin/other refs populated from source's local branches
    clone_refs = _list_remote_refs(clone_dest, "origin")
    assert "origin/main" in clone_refs
    assert "origin/other" in clone_refs

    for branch in ("main", "other"):
        source_hash = _get_ref_hash(source, f"refs/heads/{branch}")
        clone_hash = _get_ref_hash(clone_dest, f"refs/remotes/origin/{branch}")
        assert source_hash is not None
        assert clone_hash == source_hash


def test_clone_preserves_every_remote_config_key(
    tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    """Every remote.<name>.* config key on source, including multi-valued ones, is replayed on the clone."""
    remote_repo = tmp_path / "remote"
    _make_repo(remote_repo, "main")

    source = tmp_path / "source"
    _make_repo(source, "main")
    _add_remote_with_branches(source, remote_repo)

    # Set a rich set of remote config keys on source
    subprocess.run(
        ["git", "config", "remote.origin.pushurl", "https://example.com/other.git"],
        cwd=source,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "config", "remote.origin.tagopt", "--tags"], cwd=source, check=True, capture_output=True)
    # Explicit override of the default fetch refspec (so it becomes a tracked value), then an additional one.
    subprocess.run(
        ["git", "config", "--replace-all", "remote.origin.fetch", "+refs/heads/*:refs/remotes/origin/*"],
        cwd=source,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "--add", "remote.origin.fetch", "+refs/tags/*:refs/tags/*"],
        cwd=source,
        check=True,
        capture_output=True,
    )

    clone_dest = tmp_path / "clone"
    clone_repository(source, clone_dest, test_root_concurrency_group)

    def _get_single(repo: Path, key: str) -> str:
        result = subprocess.run(["git", "config", "--get", key], cwd=repo, check=True, capture_output=True, text=True)
        return result.stdout.strip()

    def _get_all(repo: Path, key: str) -> list[str]:
        result = subprocess.run(
            ["git", "config", "--get-all", key], cwd=repo, check=True, capture_output=True, text=True
        )
        return [line for line in result.stdout.splitlines() if line]

    assert _get_single(clone_dest, "remote.origin.pushurl") == _get_single(source, "remote.origin.pushurl")
    assert _get_single(clone_dest, "remote.origin.tagopt") == _get_single(source, "remote.origin.tagopt")
    assert _get_single(clone_dest, "remote.origin.url") == _get_single(source, "remote.origin.url")
    assert _get_all(clone_dest, "remote.origin.fetch") == _get_all(source, "remote.origin.fetch")


def test_clone_mirrors_source_branch_upstream_when_set(
    tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    """When source's current branch tracks origin/main, the clone's branch tracks origin/main too."""
    remote_repo = tmp_path / "remote"
    _make_repo(remote_repo, "main")

    # `git clone` sets source's main upstream to origin/main naturally
    source = tmp_path / "source"
    subprocess.run(["git", "clone", str(remote_repo), str(source)], check=True, capture_output=True)

    # Sanity check: source's main tracks origin/main
    sanity = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "main@{upstream}"],
        cwd=source,
        check=True,
        capture_output=True,
        text=True,
    )
    assert sanity.stdout.strip() == "origin/main"

    clone_dest = tmp_path / "clone"
    clone_repository(source, clone_dest, test_root_concurrency_group)

    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "main@{upstream}"],
        cwd=clone_dest,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "origin/main"


def test_clone_leaves_upstream_unset_when_source_has_none(
    tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    """When source's branch has no upstream, the clone's branch has no upstream either."""
    remote_repo = tmp_path / "remote"
    _make_repo(remote_repo, "main")

    source = tmp_path / "source"
    _make_repo(source, "main")
    _add_remote_with_branches(source, remote_repo)

    # source's main has no upstream set (we didn't do `git branch --set-upstream-to`)
    source_upstream = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "main@{upstream}"],
        cwd=source,
        capture_output=True,
        text=True,
    )
    assert source_upstream.returncode != 0

    clone_dest = tmp_path / "clone"
    clone_repository(source, clone_dest, test_root_concurrency_group)

    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "main@{upstream}"],
        cwd=clone_dest,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0


def test_clone_with_only_non_origin_remote_does_not_create_fallback_origin(
    tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    """A source with a single non-origin remote (e.g. only `upstream`) must not gain a phantom `origin`."""
    remote_repo = tmp_path / "remote"
    _make_repo(remote_repo, "main")

    source = tmp_path / "source"
    _make_repo(source, "main")
    subprocess.run(["git", "remote", "add", "upstream", str(remote_repo)], cwd=source, check=True, capture_output=True)
    subprocess.run(["git", "fetch", "upstream"], cwd=source, check=True, capture_output=True)

    clone_dest = tmp_path / "clone"
    clone_repository(source, clone_dest, test_root_concurrency_group)

    # Only `upstream` — the fallback-origin branch is only for sources with zero remotes.
    assert _list_remotes(clone_dest) == ["upstream"]
    assert _get_remote_url(clone_dest, "upstream") == str(remote_repo)
    assert "upstream/main" in _list_remote_refs(clone_dest, "upstream")


def test_clone_with_detached_head_source_skips_checkout_and_upstream(
    tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    """Source in detached HEAD with no target_branch → clone_repository returns cleanly and sets no upstream."""
    source = tmp_path / "source"
    _make_repo(source, "main")
    (source / "second.txt").write_text("second")
    subprocess.run(["git", "add", "."], cwd=source, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "second"], cwd=source, check=True, capture_output=True)
    first = subprocess.run(
        ["git", "rev-parse", "HEAD~1"], cwd=source, check=True, capture_output=True, text=True
    ).stdout.strip()
    subprocess.run(["git", "checkout", "--detach", first], cwd=source, check=True, capture_output=True)

    clone_dest = tmp_path / "clone"
    # Must not raise — the code path: _get_current_branch returns None, `if branch_to_checkout` is
    # false, so neither the checkout nor the upstream-mirror runs.
    clone_repository(source, clone_dest, test_root_concurrency_group)

    # Clone is on the same detached commit as source, with no symbolic branch name.
    assert _get_ref_hash(clone_dest, "HEAD") == first
    head_name = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=clone_dest, check=True, capture_output=True, text=True
    ).stdout.strip()
    assert head_name == "HEAD"


class TestCloneRepositoryFromWorktree:
    """Cloning when the source path is a git worktree (its ``.git`` is a gitfile pointer to a parent repo).

    Repro of the bug a user hit: a Sculptor instance launched from inside a
    worktree auto-registers that worktree path as a project. Subsequent clone
    workspaces fail because ``git clone --reference <worktree>`` is rejected by
    upstream git as a "linked checkout." The fix resolves the worktree to its
    parent repo before passing it to ``--reference``.
    """

    def test_clone_succeeds_when_source_is_a_worktree(
        self, tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
    ) -> None:
        """Cloning from a worktree path must succeed without ``not supported as a linked checkout`` errors."""
        main_repo = tmp_path / "main"
        _make_repo(main_repo, "main")

        worktree_path = tmp_path / "wt_branch"
        subprocess.run(
            ["git", "worktree", "add", str(worktree_path), "-b", "wt_branch"],
            cwd=main_repo,
            check=True,
            capture_output=True,
        )
        # Sanity: a worktree's ``.git`` is a file (gitfile pointer), not a directory.
        # If this stops being true we are no longer testing the bug repro.
        assert (worktree_path / ".git").is_file()

        clone_dest = tmp_path / "clone"
        clone_repository(worktree_path, clone_dest, test_root_concurrency_group)

        # Clone is a real, on-disk repo with the worktree's branch checked out
        # and its commits visible (objects came across via the parent repo).
        head_branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=clone_dest,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        assert head_branch == "wt_branch"

        worktree_head = _get_ref_hash(worktree_path, "HEAD")
        clone_head = _get_ref_hash(clone_dest, "HEAD")
        assert worktree_head is not None
        assert clone_head == worktree_head


def test_clone_supports_push_back_to_source_path(
    tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    """The workflow CLONE_MODE_PROMPT describes — `git push <repo_path> HEAD:refs/heads/<new>` — works end-to-end.

    Verifies that the combination of `--reference` (object sharing) and the new remote layout
    actually supports pushing a new branch back to the user's on-disk source repo.
    """
    source = tmp_path / "source"
    _make_repo(source, "main")

    clone_dest = tmp_path / "clone"
    clone_repository(source, clone_dest, test_root_concurrency_group)

    # Simulate Claude making a change in the clone
    subprocess.run(["git", "config", "user.email", "agent@test.com"], cwd=clone_dest, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Agent"], cwd=clone_dest, check=True, capture_output=True)
    (clone_dest / "agent_change.txt").write_text("agent work")
    subprocess.run(["git", "add", "."], cwd=clone_dest, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "agent commit"], cwd=clone_dest, check=True, capture_output=True)

    # Push to a *different* branch name per the prompt's receive.denyCurrentBranch caveat.
    push_result = subprocess.run(
        ["git", "push", str(source), "HEAD:refs/heads/sculptor-work"],
        cwd=clone_dest,
        capture_output=True,
        text=True,
    )
    assert push_result.returncode == 0, f"push failed: {push_result.stderr}"

    # Source now has the new branch at the clone's HEAD commit — objects transferred despite
    # the clone sharing its object store with source via --reference.
    assert _get_ref_hash(source, "refs/heads/sculptor-work") == _get_ref_hash(clone_dest, "HEAD")
