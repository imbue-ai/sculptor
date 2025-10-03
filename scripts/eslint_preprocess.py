#!/usr/bin/env python3
"""
ESLint preprocessing script for pre-commit hooks.

This script:
1. Configures the correct Node version via nvm
2. Installs npm dependencies
"""

import subprocess
import sys
from pathlib import Path

from imbue_core.git import get_git_repo_root


def get_frontend_path() -> Path:
    return get_git_repo_root() / "sculptor" / "frontend"


def setup_node_version(frontend_path: Path) -> None:
    """Setup the correct Node version using nvm."""
    nvmrc_path = frontend_path / ".nvmrc"
    if not nvmrc_path.exists():
        print(f"Warning: No .nvmrc file found at {nvmrc_path}")
        return

    expected_version = nvmrc_path.read_text().strip()
    print(f"Setting up Node.js version {expected_version} via nvm...")

    # Use nvm to install and use the correct version
    nvm_commands = [
        f"source ${{NVM_DIR:-~/.nvm}}/nvm.sh && nvm install {expected_version}",
        f"source ${{NVM_DIR:-~/.nvm}}/nvm.sh && nvm use {expected_version}",
    ]

    for cmd in nvm_commands:
        try:
            result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True, cwd=frontend_path)
            if result.stdout.strip():
                print(f"  {result.stdout.strip()}")
        except subprocess.CalledProcessError as e:
            print(f"Warning: nvm command failed: {e}")
            print(f"  stdout: {e.stdout}")
            print(f"  stderr: {e.stderr}")
            print("  Continuing anyway...")


def install_npm_dependencies(frontend_path: Path) -> None:
    """Install npm dependencies."""
    print("Installing npm dependencies...")
    try:
        result = subprocess.run(
            ["npm", "install", "--silent"], check=True, cwd=frontend_path, capture_output=True, text=True
        )
        print("  npm dependencies installed successfully")
        if result.stdout.strip():
            print(f"  {result.stdout.strip()}")
    except subprocess.CalledProcessError as e:
        print(f"Error installing npm dependencies: {e}")
        print(f"  stdout: {e.stdout}")
        print(f"  stderr: {e.stderr}")
        sys.exit(1)


def print_files_to_lint(frontend_path: Path, files_to_check: list[str]) -> None:
    """Print the files that will be linted."""
    if not files_to_check:
        # Get all matching files if no specific files provided
        patterns = ["**/*.vue", "**/*.ts", "**/*.tsx", "**/*.js", "**/*.jsx"]
        all_files = []
        for pattern in patterns:
            files = list(frontend_path.glob(pattern))
            all_files.extend(files)

        all_files = sorted(set(all_files))
        relative_files = [str(f.relative_to(frontend_path)) for f in all_files]
    else:
        # Convert provided files to relative paths from frontend directory
        relative_files = []
        for file_path in files_to_check:
            abs_path = Path(file_path).resolve()
            try:
                rel_path = abs_path.relative_to(frontend_path.resolve())
                relative_files.append(str(rel_path))
            except ValueError:
                # File is not in frontend directory, skip it
                continue

    if relative_files:
        print(f"\nESLint will process {len(relative_files)} files:")
        for file in sorted(relative_files):
            print(f"  {file}")
    else:
        print("\nNo frontend files to lint.")


def main() -> None:
    """ESLint preprocessing: setup Node, install deps, and list files to lint."""
    # Get files from command line arguments
    files_to_check = sys.argv[1:] if len(sys.argv) > 1 else []

    frontend_path = get_frontend_path()

    print("=== ESLint Pre-processing ===")

    # 1. Setup Node version via nvm
    setup_node_version(frontend_path)

    # 2. Install npm dependencies
    install_npm_dependencies(frontend_path)

    # 3. Print files to be linted
    print_files_to_lint(frontend_path, files_to_check)

    print("=== Pre-processing complete ===\n")


if __name__ == "__main__":
    main()
