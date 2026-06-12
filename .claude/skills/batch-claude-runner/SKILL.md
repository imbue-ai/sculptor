---
name: batch-claude-runner
disable-model-invocation: true
description: |
  Run Claude programmatically against collections of files in the codebase.
  Use for batch analysis: scrubbing sensitive data, auditing style violations, security reviews.
---

# Batch Claude Runner

Runs Claude against batches of files, collecting structured findings into a summary report.

## Quick Start

```bash
# Basic usage
python .claude/skills/batch-claude-runner/scripts/batch_claude_runner.py \
  --pattern "**/*.py" \
  --prompt "Check for hardcoded credentials or API keys."

# See all options
python .claude/skills/batch-claude-runner/scripts/batch_claude_runner.py --help
```

## Key Options

- `--pattern` / `-p`: Glob pattern for files (required, repeatable)
- `--exclude` / `-e`: Exclude pattern (repeatable)
- `--prompt`: Analysis prompt
- `--batch-size` / `-b`: Files per batch (default: 10)
- `--max-batches` / `-m`: Limit batches (for testing)
- `--dry-run`: Preview files without running
- `--output json`: Machine-readable output

## Notes

- Claude reads files via its Read tool and can make edits if prompted
- Structured JSON output is enforced automatically via `--json-schema`
- Use `--dry-run` first to verify file selection
