import os
from pathlib import Path
from typing import Any

import libcst as cst
from loguru import logger


def _find_test_files_in_directory(directory: str) -> list[Path]:
    """
    Recursively scan directory for Python test files.

    Returns:
        List of paths to test files found
    """
    test_files: list[Path] = []

    # Convert to Path object for easier handling
    root_path = Path(directory).resolve()

    if not root_path.exists():
        print(f"Error: Directory '{directory}' does not exist")
        return test_files

    if not root_path.is_dir():
        print(f"Error: '{directory}' is not a directory")
        return test_files

    # Walk through all subdirectories
    local_cwd = Path(os.getcwd())
    for dirpath, dirnames, filenames in os.walk(root_path):
        # Skip hidden directories (optional - remove if you want to include them)
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]

        for filename in filenames:
            # Check if file matches our test file patterns
            if filename.endswith(".py"):
                if filename.startswith("test_") or filename.endswith("_test.py"):
                    full_path = (Path(dirpath) / filename).relative_to(local_cwd)
                    test_files.append(full_path)

    return test_files


class TestFunctionCollector(cst.CSTVisitor):
    def __init__(self) -> None:
        super().__init__()
        self.matches: list[dict[str, Any]] = []

    def visit_FunctionDef(self, node: cst.FunctionDef) -> None:
        name = node.name.value
        if name.startswith("test_") or name.endswith("_test"):
            # Collect decorator names
            decorator_names = []
            for decorator in node.decorators:
                # Handle simple decorators (e.g., @pytest.mark.skip)
                if isinstance(decorator.decorator, cst.Attribute):
                    # Build the full decorator name by traversing the attribute chain
                    parts = []
                    current = decorator.decorator
                    while isinstance(current, cst.Attribute):
                        parts.append(current.attr.value)
                        current = current.value
                    if isinstance(current, cst.Name):
                        parts.append(current.value)
                    decorator_names.append(".".join(reversed(parts)))
                # Handle simple name decorators (e.g., @skip)
                elif isinstance(decorator.decorator, cst.Name):
                    decorator_names.append(decorator.decorator.value)
                # Handle decorator calls (e.g., @pytest.mark.parametrize(...))
                elif isinstance(decorator.decorator, cst.Call):
                    if isinstance(decorator.decorator.func, cst.Attribute):
                        parts = []
                        current = decorator.decorator.func
                        while isinstance(current, cst.Attribute):
                            parts.append(current.attr.value)
                            current = current.value
                        if isinstance(current, cst.Name):
                            parts.append(current.value)
                        decorator_names.append(".".join(reversed(parts)))
                    elif isinstance(decorator.decorator.func, cst.Name):
                        decorator_names.append(decorator.decorator.func.value)

            self.matches.append({"name": name, "decorators": decorator_names})


def _find_test_functions_in_file(file_path: Path, is_skipping_flaky_tests: bool) -> list[str]:
    source = file_path.read_text()
    lines = source.splitlines()
    if any(x.startswith("pytest.skip(") for x in lines):
        logger.warning("Please don't skip whole modules -- skip each individual test with @pytest.mark.skip instead")
        return []
    module = cst.parse_module(source)
    collector = TestFunctionCollector()
    module.visit(collector)
    skipped = [
        x["name"] for x in collector.matches if _is_skip_decorator_present(x["decorators"], is_skipping_flaky_tests)
    ]
    if skipped:
        print("SKIPPED: " + str(skipped))
    return [
        x["name"]
        for x in collector.matches
        if not _is_skip_decorator_present(x["decorators"], is_skipping_flaky_tests)
    ]


def _is_skip_decorator_present(decorators: list[str], is_skipping_flaky_tests: bool) -> bool:
    skip_indicators = {"pytest.mark.skip", "skip", "mark_acceptance_test", "pytest.fixture", "fixture"}
    if is_skipping_flaky_tests:
        skip_indicators.add("flaky")
    return any(decorator in skip_indicators for decorator in decorators)


def find_all_tests(directory: str, is_skipping_flaky_tests: bool) -> list[str]:
    test_files = _find_test_files_in_directory(directory)
    results = []
    for test_file in test_files:
        test_functions = _find_test_functions_in_file(test_file, is_skipping_flaky_tests)
        test_commands = [f"{test_file}::{func}" for func in test_functions]
        results.extend(test_commands)
    return results


def main():
    print("Unit tests:")
    print("\n".join(find_all_tests("sculptor/sculptor", is_skipping_flaky_tests=True)))
    print("Integration tests:")
    print("\n".join(find_all_tests("sculptor/tests/integration", is_skipping_flaky_tests=True)))


if __name__ == "__main__":
    main()
