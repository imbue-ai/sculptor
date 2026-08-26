#!/usr/bin/env python3
"""
Batch Claude Runner - Run Claude programmatically against collections of files.

This script batches files and runs Claude against each batch, collecting results
for a final summary report. Useful for:
- Scrubbing codebases for sensitive data
- Auditing files for style guide violations
- Checking source code for security concerns

Uses only Python standard library (no third-party dependencies).
"""

import argparse
import glob
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path



@dataclass
class BatchResult:
    """Result from processing a single batch of files."""

    batch_index: int
    files: list[str]
    success: bool
    output: str
    error: str | None = None
    parsed_findings: list[dict] = field(default_factory=list)


@dataclass
class RunConfig:
    """Configuration for a batch run."""

    prompt_template: str
    file_patterns: list[str]
    batch_size: int
    working_dir: str
    output_format: str
    max_batches: int | None
    exclude_patterns: list[str]
    verbose: bool
    timeout_seconds: int


def find_files(
    patterns: list[str],
    working_dir: str,
    exclude_patterns: list[str],
) -> list[str]:
    """Find all files matching the given glob patterns."""
    all_files: set[str] = set()

    for pattern in patterns:
        if os.path.isabs(pattern):
            matched = glob.glob(pattern, recursive=True)
        else:
            matched = glob.glob(
                str(Path(working_dir) / pattern),
                recursive=True,
            )

        for f in matched:
            if os.path.isfile(f):
                rel_path = os.path.relpath(f, working_dir)
                all_files.add(rel_path)

    if exclude_patterns:
        excluded: set[str] = set()
        for pattern in exclude_patterns:
            if os.path.isabs(pattern):
                matched = glob.glob(pattern, recursive=True)
            else:
                matched = glob.glob(
                    str(Path(working_dir) / pattern),
                    recursive=True,
                )
            for f in matched:
                if os.path.isfile(f):
                    rel_path = os.path.relpath(f, working_dir)
                    excluded.add(rel_path)
        all_files -= excluded

    return sorted(all_files)


def create_batches(files: list[str], batch_size: int) -> list[list[str]]:
    """Split files into batches of the specified size."""
    batches = []
    for i in range(0, len(files), batch_size):
        batches.append(files[i : i + batch_size])
    return batches


FINDINGS_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "file": {"type": "string", "description": "The filename where the finding was detected"},
                    "category": {"type": "string", "description": "Category of the finding"},
                    "severity": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "critical"],
                        "description": "Severity level of the finding",
                    },
                    "description": {"type": "string", "description": "Brief description of the finding"},
                    "recommendation": {"type": "string", "description": "Recommended action to address the finding"},
                    "line_numbers": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Line numbers where the issue was found (optional)",
                    },
                },
                "required": ["file", "category", "severity", "description", "recommendation"],
            },
        },
        "summary": {"type": "string", "description": "Brief summary of findings in this batch"},
        "files_reviewed": {"type": "integer", "description": "Number of files reviewed in this batch"},
    },
    "required": ["findings", "summary", "files_reviewed"],
}


def build_batch_prompt(
    prompt_template: str,
    files: list[str],
    batch_index: int,
    total_batches: int,
) -> str:
    """Build the prompt for a single batch."""
    file_list = "\n".join(f"- {f}" for f in files)

    prompt = f"""You are processing batch {batch_index + 1} of {total_batches}.

IMPORTANT: Read each of the following files using your Read tool, then analyze them according to the instructions below.

Files to read and analyze:
{file_list}

{prompt_template}

If no issues are found, return an empty findings array.
"""
    return prompt


def run_claude_on_batch(
    prompt: str,
    files: list[str],
    working_dir: str,
    batch_index: int,
    verbose: bool,
    timeout_seconds: int,
) -> BatchResult:
    """Run Claude on a batch of files."""
    schema_json = json.dumps(FINDINGS_JSON_SCHEMA)

    try:
        cmd = [
            "claude",
            "--print",
            "--dangerously-skip-permissions",
            "--output-format",
            "json",
            "--json-schema",
            schema_json,
            # Prompt is passed as the final positional argument
            prompt,
        ]

        if verbose:
            print(f"  Running: claude --print ... ({len(files)} files)")

        result = subprocess.run(
            cmd,
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )

        output = result.stdout
        error = result.stderr if result.returncode != 0 else None

        parsed_findings = []
        try:
            response = json.loads(output)
            # With --output-format json and --json-schema, the structured output
            # is in the "structured_output" field
            if "structured_output" in response:
                content = response["structured_output"]
                if isinstance(content, dict):
                    parsed_findings = content.get("findings", [])
            elif "result" in response:
                # Fallback: try to parse from result field if it's JSON
                content = response["result"]
                if isinstance(content, str) and content.strip():
                    try:
                        content = json.loads(content)
                        parsed_findings = content.get("findings", [])
                    except json.JSONDecodeError:
                        pass
                elif isinstance(content, dict):
                    parsed_findings = content.get("findings", [])
            else:
                # Last fallback: try to parse findings directly from response
                parsed_findings = response.get("findings", [])
        except json.JSONDecodeError as e:
            if verbose:
                print(f"  Warning: Failed to parse JSON response: {e}")
                # Print raw output for debugging (first 500 chars)
                print(f"  Raw output (first 500 chars): {output[:500]!r}")

        return BatchResult(
            batch_index=batch_index,
            files=files,
            success=result.returncode == 0,
            output=output,
            error=error,
            parsed_findings=parsed_findings,
        )

    except subprocess.TimeoutExpired:
        return BatchResult(
            batch_index=batch_index,
            files=files,
            success=False,
            output="",
            error=f"Timeout expired ({timeout_seconds}s)",
            parsed_findings=[],
        )
    except Exception as e:
        return BatchResult(
            batch_index=batch_index,
            files=files,
            success=False,
            output="",
            error=str(e),
            parsed_findings=[],
        )


def generate_summary_report(
    results: list[BatchResult],
    config: RunConfig,
) -> dict:
    """Generate a summary report from all batch results."""
    all_findings: list[dict] = []
    files_with_findings: set[str] = set()
    total_files_reviewed = 0
    failed_batches: list[int] = []
    findings_by_severity: dict[str, list[dict]] = {
        "critical": [],
        "high": [],
        "medium": [],
        "low": [],
    }
    findings_by_category: dict[str, list[dict]] = {}

    for result in results:
        total_files_reviewed += len(result.files)

        if not result.success:
            failed_batches.append(result.batch_index)
            continue

        for finding in result.parsed_findings:
            all_findings.append(finding)
            file_name = finding.get("file", "unknown")
            files_with_findings.add(file_name)

            severity = finding.get("severity", "low").lower()
            if severity in findings_by_severity:
                findings_by_severity[severity].append(finding)
            else:
                findings_by_severity["low"].append(finding)

            category = finding.get("category", "uncategorized")
            if category not in findings_by_category:
                findings_by_category[category] = []
            findings_by_category[category].append(finding)

    report = {
        "summary": {
            "total_files_reviewed": total_files_reviewed,
            "total_batches": len(results),
            "successful_batches": len(results) - len(failed_batches),
            "failed_batches": failed_batches,
            "total_findings": len(all_findings),
            "files_with_findings": len(files_with_findings),
        },
        "findings_by_severity": {severity: len(findings) for severity, findings in findings_by_severity.items()},
        "findings_by_category": {category: len(findings) for category, findings in findings_by_category.items()},
        "all_findings": all_findings,
        "files_requiring_attention": sorted(files_with_findings),
    }

    return report


def format_report_for_display(report: dict) -> str:
    """Format the report for human-readable display."""
    lines = []
    lines.append("=" * 60)
    lines.append("BATCH CLAUDE RUNNER - SUMMARY REPORT")
    lines.append("=" * 60)
    lines.append("")

    summary = report["summary"]
    lines.append("OVERVIEW:")
    lines.append(f"  Files reviewed: {summary['total_files_reviewed']}")
    lines.append(f"  Batches: {summary['successful_batches']}/{summary['total_batches']} successful")
    lines.append(f"  Total findings: {summary['total_findings']}")
    lines.append(f"  Files with findings: {summary['files_with_findings']}")
    lines.append("")

    if summary["failed_batches"]:
        lines.append(f"  WARNING: {len(summary['failed_batches'])} batch(es) failed")
        lines.append("")

    lines.append("FINDINGS BY SEVERITY:")
    for severity in ["critical", "high", "medium", "low"]:
        count = report["findings_by_severity"].get(severity, 0)
        if count > 0:
            lines.append(f"  {severity.upper()}: {count}")
    lines.append("")

    if report["findings_by_category"]:
        lines.append("FINDINGS BY CATEGORY:")
        for category, count in sorted(
            report["findings_by_category"].items(),
            key=lambda x: -x[1],
        ):
            lines.append(f"  {category}: {count}")
        lines.append("")

    if report["all_findings"]:
        lines.append("DETAILED FINDINGS:")
        lines.append("-" * 40)
        for i, finding in enumerate(report["all_findings"], 1):
            lines.append(f"\n{i}. [{finding.get('severity', 'unknown').upper()}] {finding.get('file', 'unknown')}")
            lines.append(f"   Category: {finding.get('category', 'unknown')}")
            lines.append(f"   Description: {finding.get('description', 'N/A')}")
            if finding.get("line_numbers"):
                lines.append(f"   Lines: {finding.get('line_numbers')}")
            lines.append(f"   Recommendation: {finding.get('recommendation', 'N/A')}")
    lines.append("")

    if report["files_requiring_attention"]:
        lines.append("FILES REQUIRING ATTENTION:")
        for f in report["files_requiring_attention"]:
            lines.append(f"  - {f}")
    lines.append("")

    lines.append("=" * 60)
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Claude programmatically against collections of files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scrub Python files for sensitive data
  %(prog)s --pattern "**/*.py" --prompt-file scrub_prompt.txt

  # Audit TypeScript files with custom batch size
  %(prog)s --pattern "src/**/*.ts" --batch-size 5 --prompt "Check for security issues"

  # Multiple patterns with exclusions
  %(prog)s --pattern "**/*.py" --pattern "**/*.js" --exclude "**/node_modules/**"
""",
    )

    parser.add_argument(
        "--pattern",
        "-p",
        action="append",
        dest="patterns",
        required=True,
        help="Glob pattern for files to process (can be specified multiple times)",
    )

    parser.add_argument(
        "--exclude",
        "-e",
        action="append",
        dest="exclude_patterns",
        default=[],
        help="Glob pattern for files to exclude (can be specified multiple times)",
    )

    parser.add_argument(
        "--prompt",
        type=str,
        help="The prompt template to use for each batch",
    )

    parser.add_argument(
        "--prompt-file",
        type=str,
        help="Path to a file containing the prompt template",
    )

    parser.add_argument(
        "--batch-size",
        "-b",
        type=int,
        default=10,
        help="Number of files per batch (default: 10)",
    )

    parser.add_argument(
        "--max-batches",
        "-m",
        type=int,
        default=None,
        help="Maximum number of batches to process (for testing)",
    )

    parser.add_argument(
        "--output",
        "-o",
        type=str,
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )

    parser.add_argument(
        "--output-file",
        type=str,
        help="Write report to this file instead of stdout",
    )

    parser.add_argument(
        "--working-dir",
        "-w",
        type=str,
        default=".",
        help="Working directory for file paths (default: current directory)",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List files that would be processed without running Claude",
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Per-batch timeout in seconds for the claude invocation (default: 300)",
    )

    args = parser.parse_args()

    if not args.prompt and not args.prompt_file:
        parser.error("Either --prompt or --prompt-file is required")

    if args.prompt and args.prompt_file:
        parser.error("Specify either --prompt or --prompt-file, not both")

    if args.prompt_file:
        prompt_path = Path(args.prompt_file)
        if not prompt_path.exists():
            print(f"Error: Prompt file not found: {args.prompt_file}", file=sys.stderr)
            return 1
        prompt_template = prompt_path.read_text()
    else:
        prompt_template = args.prompt

    working_dir = os.path.abspath(args.working_dir)
    if not os.path.isdir(working_dir):
        print(f"Error: Working directory not found: {working_dir}", file=sys.stderr)
        return 1

    config = RunConfig(
        prompt_template=prompt_template,
        file_patterns=args.patterns,
        batch_size=args.batch_size,
        working_dir=working_dir,
        output_format=args.output,
        max_batches=args.max_batches,
        exclude_patterns=args.exclude_patterns,
        verbose=args.verbose,
        timeout_seconds=args.timeout,
    )

    if config.verbose:
        print(f"Finding files matching: {config.file_patterns}")
        if config.exclude_patterns:
            print(f"Excluding patterns: {config.exclude_patterns}")

    files = find_files(
        config.file_patterns,
        config.working_dir,
        config.exclude_patterns,
    )

    if not files:
        print("No files found matching the specified patterns.", file=sys.stderr)
        return 1

    if config.verbose:
        print(f"Found {len(files)} files")

    batches = create_batches(files, config.batch_size)

    if config.max_batches:
        batches = batches[: config.max_batches]

    if config.verbose:
        print(f"Created {len(batches)} batches")

    if args.dry_run:
        print(f"\nDRY RUN - Would process {len(files)} files in {len(batches)} batches:\n")
        for i, batch in enumerate(batches):
            print(f"Batch {i + 1}:")
            for f in batch:
                print(f"  - {f}")
            print()
        return 0

    print(f"Processing {len(files)} files in {len(batches)} batches...")
    print()

    results: list[BatchResult] = []
    for i, batch in enumerate(batches):
        print(f"Processing batch {i + 1}/{len(batches)} ({len(batch)} files)...")

        prompt = build_batch_prompt(
            config.prompt_template,
            batch,
            i,
            len(batches),
        )

        result = run_claude_on_batch(
            prompt,
            batch,
            config.working_dir,
            i,
            config.verbose,
            config.timeout_seconds,
        )

        results.append(result)

        if result.success:
            findings_count = len(result.parsed_findings)
            print(f"  Batch {i + 1}: {findings_count} finding(s)")
        else:
            print(f"  Batch {i + 1}: FAILED - {result.error}")

    print()

    report = generate_summary_report(results, config)

    if config.output_format == "json":
        output = json.dumps(report, indent=2)
    else:
        output = format_report_for_display(report)

    if args.output_file:
        Path(args.output_file).write_text(output)
        print(f"Report written to: {args.output_file}")
    else:
        print(output)

    return 0 if not report["summary"]["failed_batches"] else 1


if __name__ == "__main__":
    sys.exit(main())
