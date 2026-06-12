# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Analyze git contributions by author for a given date range.

Usage:
    uv run git_contributions.py                          # defaults to last month
    uv run git_contributions.py --after 2026-01-31 --before 2026-03-01
    uv run git_contributions.py --exclude-dirs agent_docs     # exclude directories
    uv run git_contributions.py --exclude-files '*.md' '*.lock' # exclude file patterns
"""

import argparse
import fnmatch
import subprocess
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

# Directories that typically contain auto-generated or non-code content
DEFAULT_EXCLUDE_DIRS = [
    "agent_docs",
    ".claude",
]

# Files that are typically auto-generated and not meaningful code contributions
DEFAULT_EXCLUDE_FILES = [
    # Lock files
    "*.lock",
    "*.lockb",
    "package-lock.json",
    "uv.lock",
    "yarn.lock",
    "pnpm-lock.yaml",
    "Cargo.lock",
    "Gemfile.lock",
    "poetry.lock",
    # Generated / minified
    "*.generated.*",
    "*.min.js",
    "*.min.css",
    # Documentation / non-code
    "*.md",
    "*.excalidraw",
    # Database snapshots
    "*.llm_cache_db",
    "frozen_pydantic_schemas.json",
]


@dataclass
class AuthorStats:
    commits: int = 0
    added: int = 0
    removed: int = 0
    files_touched: int = 0
    dirs: dict = field(default_factory=lambda: defaultdict(lambda: {"added": 0, "removed": 0}))

    @property
    def net(self) -> int:
        return self.added - self.removed


def run_git(args: list[str]) -> str:
    result = subprocess.run(
        ["git"] + args,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def is_excluded_file(filepath: str, exclude_patterns: list[str]) -> bool:
    """Check if a filepath matches any of the exclusion glob patterns."""
    filename = filepath.rsplit("/", 1)[-1]
    return any(
        fnmatch.fnmatch(filename, pat) or fnmatch.fnmatch(filepath, pat)
        for pat in exclude_patterns
    )


def parse_contributions(
    after: str,
    before: str,
    exclude_dirs: list[str],
    exclude_files: list[str],
    author_aliases: dict[str, str],
) -> dict[str, AuthorStats]:
    """Parse git log numstat output into per-author statistics."""
    raw = run_git([
        "log",
        f"--after={after}",
        f"--before={before}",
        "--no-merges",
        "--numstat",
        "--format=%an",
    ])

    stats: dict[str, AuthorStats] = defaultdict(AuthorStats)
    current_author = None

    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue

        parts = line.split("\t")
        if len(parts) >= 3:
            # numstat line: added<tab>removed<tab>filepath
            added_str, removed_str, filepath = parts[0], parts[1], parts[2]

            if current_author is None:
                continue

            # Skip binary files (shown as "-")
            if added_str == "-" or removed_str == "-":
                continue

            # Check directory exclusions (match directory name anywhere in path)
            if any(f"/{d}/" in f"/{filepath}" for d in exclude_dirs):
                continue

            # Check file exclusions (match filename or full path against glob patterns)
            if is_excluded_file(filepath, exclude_files):
                continue

            added = int(added_str)
            removed = int(removed_str)
            author = stats[current_author]
            author.added += added
            author.removed += removed
            author.files_touched += 1

            # Track by top-level directory grouping
            path_parts = filepath.split("/")
            if len(path_parts) >= 3:
                dir_key = f"{path_parts[0]}/{path_parts[1]}"
            else:
                dir_key = path_parts[0]
            author.dirs[dir_key]["added"] += added
            author.dirs[dir_key]["removed"] += removed
        else:
            # Author name line
            name = line
            name = author_aliases.get(name, name)
            current_author = name

    # Count commits separately (numstat format does not lend itself to counting inline)
    commit_log = run_git([
        "log",
        f"--after={after}",
        f"--before={before}",
        "--no-merges",
        "--format=%an",
    ])
    for line in commit_log.splitlines():
        name = line.strip()
        if not name:
            continue
        name = author_aliases.get(name, name)
        stats[name].commits += 1

    return dict(stats)


def count_merges(after: str, before: str) -> int:
    output = run_git([
        "log",
        f"--after={after}",
        f"--before={before}",
        "--merges",
        "--oneline",
    ])
    return len([line for line in output.splitlines() if line.strip()])


def print_report(
    stats: dict[str, AuthorStats],
    after: str,
    before: str,
    exclude_dirs: list[str],
    exclude_files: list[str],
) -> None:
    merge_count = count_merges(after, before)

    total_commits = sum(s.commits for s in stats.values())
    total_added = sum(s.added for s in stats.values())
    total_removed = sum(s.removed for s in stats.values())
    total_net = total_added - total_removed

    exclusions = []
    if exclude_dirs:
        exclusions.append(f"dirs: {', '.join(exclude_dirs)}")
    if exclude_files:
        exclusions.append(f"files: {', '.join(exclude_files)}")
    excluded_label = f" (excl. {'; '.join(exclusions)})" if exclusions else ""

    print(f"\n{'=' * 70}")
    print(f"  Git Contributions: {after} to {before}{excluded_label}")
    print(f"{'=' * 70}\n")

    print("OVERALL")
    print(f"  Non-merge commits : {total_commits:>10,}")
    print(f"  Merge commits     : {merge_count:>10,}")
    print(f"  Lines added       : {total_added:>10,}")
    print(f"  Lines removed     : {total_removed:>10,}")
    print(f"  Net lines         : {total_net:>10,}")

    # Sort by net lines descending
    sorted_authors = sorted(stats.items(), key=lambda x: x[1].net, reverse=True)

    print(f"\n{'─' * 70}")
    print("BY CONTRIBUTOR")
    print(f"{'─' * 70}")
    header = f"  {'Name':<25} {'Commits':>8} {'Added':>10} {'Removed':>10} {'Net':>10} {'Files':>7}"
    print(header)
    print(f"  {'─' * 67}")

    for name, author in sorted_authors:
        added_str = f"+{author.added}"
        removed_str = f"-{author.removed}"
        print(
            f"  {name:<25} {author.commits:>8,} {added_str:>10} {removed_str:>10} {author.net:>+10,} {author.files_touched:>7,}"
        )

    # Per-author directory breakdown for top contributors
    print(f"\n{'─' * 70}")
    print("DIRECTORY BREAKDOWN (top 5 dirs per contributor)")
    print(f"{'─' * 70}")

    for name, author in sorted_authors:
        if author.added == 0 and author.removed == 0:
            continue
        print(f"\n  {name} ({author.commits} commits, net {author.net:+,})")
        sorted_dirs = sorted(
            author.dirs.items(),
            key=lambda x: x[1]["added"] + x[1]["removed"],
            reverse=True,
        )
        for dir_name, dir_stats in sorted_dirs[:5]:
            net = dir_stats["added"] - dir_stats["removed"]
            print(
                f"    {dir_name:<35} +{dir_stats['added']:<8,} -{dir_stats['removed']:<8,} net: {net:+,}"
            )


def default_date_range() -> tuple[str, str]:
    """Return the first and last day of the previous month."""
    today = datetime.now()
    first_of_this_month = today.replace(day=1)
    last_of_prev_month = first_of_this_month - timedelta(days=1)
    first_of_prev_month = last_of_prev_month.replace(day=1)
    after = (first_of_prev_month - timedelta(days=1)).strftime("%Y-%m-%d")
    before = first_of_this_month.strftime("%Y-%m-%d")
    return after, before


def main() -> None:
    default_after, default_before = default_date_range()

    parser = argparse.ArgumentParser(description="Analyze git contributions by author.")
    parser.add_argument("--after", default=default_after, help=f"Start date exclusive (default: {default_after})")
    parser.add_argument("--before", default=default_before, help=f"End date exclusive (default: {default_before})")
    parser.add_argument("--exclude-dirs", nargs="*", default=DEFAULT_EXCLUDE_DIRS, help="Directories to exclude (default: agent_docs, .claude)")
    parser.add_argument(
        "--exclude-files",
        nargs="*",
        default=DEFAULT_EXCLUDE_FILES,
        help="File glob patterns to exclude (default: lock files, generated files)",
    )
    parser.add_argument(
        "--no-default-excludes",
        action="store_true",
        help="Disable default file exclusions (lock files, etc.)",
    )
    parser.add_argument(
        "--alias",
        nargs=2,
        action="append",
        default=[],
        metavar=("FROM", "TO"),
        help="Map author name FROM to TO (e.g. --alias jdoe 'Jane Doe')",
    )
    args = parser.parse_args()

    # Build alias map, with a default for known duplicates
    author_aliases: dict[str, str] = {}
    for from_name, to_name in args.alias:
        author_aliases[from_name] = to_name

    # Auto-detect aliases: group by email
    email_log = run_git([
        "log",
        f"--after={args.after}",
        f"--before={args.before}",
        "--no-merges",
        "--format=%an <%ae>",
    ])
    email_to_names: dict[str, list[str]] = defaultdict(list)
    for line in email_log.splitlines():
        line = line.strip()
        if " <" not in line:
            continue
        name, email = line.rsplit(" <", 1)
        email = email.rstrip(">")
        if name not in email_to_names[email]:
            email_to_names[email].append(name)

    for email, names in email_to_names.items():
        if len(names) > 1:
            # Use the longest name as canonical
            canonical = max(names, key=len)
            for name in names:
                if name != canonical and name not in author_aliases:
                    author_aliases[name] = canonical

    exclude_files = [] if args.no_default_excludes else args.exclude_files

    stats = parse_contributions(args.after, args.before, args.exclude_dirs, exclude_files, author_aliases)
    print_report(stats, args.after, args.before, args.exclude_dirs, exclude_files)


if __name__ == "__main__":
    main()
