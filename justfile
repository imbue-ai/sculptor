default: help

# Use bash with strict flags
set shell := ["bash", "-eu", "-o", "pipefail", "-c"]
set dotenv-load := true

# Show a help message listing all the commands
help:
    @echo "Generally Intelligent's Justfile"
    @echo "Contains commands for working with our monorepo"
    @just --list --unsorted

# === Global Variables ===

# Reusable, embeddable snippet to ensure Node via nvm is active in THIS shell.
# Pinned to 24.17.0 (LTS security release). Anything >=24.16.0 needs the `yauzl`
# override in sculptor/frontend/package.json to avoid the extract-zip packaging
# hang (Node 24's stream-cleanup change vs extract-zip 2.0.1).
nvm_use := '''
set +u
: "${NVM_DIR:="$HOME/.nvm"}"
. "$NVM_DIR/nvm.sh"
nvm use --silent 24.17.0 2>/dev/null || nvm install 24.17.0 >/dev/null
nvm use --silent 24.17.0
set -u
'''

# Reusable snippet to abort early when the `offload` CLI is not installed.
_require_offload := '''
if ! command -v offload &>/dev/null; then
    echo "Error: 'offload' is not installed."
    echo "Install it with: cargo install offload"
    echo "(On macOS, install Rust first if needed: brew install rust)"
    exit 1
fi
'''

# Pinned version of the `ratchets` lint binary (https://crates.io/crates/ratchets).
# Bump this and re-run `just install-ratchets` (and update CI) when adopting a new release.
ratchets_version := "0.3.1"

# Reusable snippet to abort early when the `ratchets` CLI is not installed.
_require_ratchets := '''
if ! command -v ratchets &>/dev/null; then
    echo "Error: 'ratchets' is not installed."
    echo "Install it with: just install-ratchets"
    echo "(On macOS, install Rust first if needed: brew install rust)"
    exit 1
fi
'''

# -------- Sculptor Defaults / Vars --------
# Derive unique-per-repo defaults so multiple checkouts can `just start` concurrently.
# Session name and ports are hashed from the full repo path so each checkout gets
# unique defaults.  All three can still be overridden via env vars.
_repo_hash := `printf '%s' "$(pwd)" | cksum | awk '{printf "%05d", ($1 % 100000)}'`
_default_api_port := `printf '%s' "$(pwd)" | cksum | awk '{print ($1 % 50000) + 10000}'`
_default_frontend_port := `printf '%s' "$(pwd)" | cksum | awk '{print ($1 % 50000) + 10001}'`

session_name := env('SESSION_NAME', 'sculptor-' + _repo_hash)
ENABLED_FRONTEND_ARTIFACT_VIEWS := env('ENABLED_FRONTEND_ARTIFACT_VIEWS', '')
MODE := env('MODE', '')  # lets you override --mode if desired
_ENV_SHELL := env('SHELL', '/bin/bash')
export ENVIRONMENT := env('ENVIRONMENT',  'dev')
SCULPTOR_FOLDER := env('SCULPTOR_FOLDER', '~/.sculptor')
DEV_SCULPTOR_FOLDER := '~/.dev_sculptor/'
SCULPTOR_API_PORT := env('SCULPTOR_API_PORT', _default_api_port)
SCULPTOR_FRONTEND_PORT := env('SCULPTOR_FRONTEND_PORT', _default_frontend_port)

# Directory for command log files (quiet mode)
_logs_dir := justfile_directory() / ".just-logs"

# Reusable bash snippet that defines a `quiet_by_default` function.
# Usage: quiet_by_default <step_name> <command...>
# In quiet mode, captures all output to a log file under .just-logs/ and prints
# only a pass/fail summary line with the log file path.
# In verbose mode (when JUST_VERBOSE=1), runs the command normally.
# Set JUST_VERBOSE=1 in the environment for full output (used in CI).
#
# When JUST_LOG_FILE is set (by a parent meta-command like `check` or `test-unit`),
# leaf commands append to that shared log file instead of creating their own.
_quiet_by_default_fn := '''
_LOGS_DIR="''' + _logs_dir + '''"
quiet_by_default() {
  local step_name="$1"; shift
  if [ "${JUST_VERBOSE:-}" = "1" ]; then
    "$@"
    return
  fi
  mkdir -p "$_LOGS_DIR"
  # Run the command in a subshell with `set -e` so that mid-function failures
  # are not silently swallowed.  We temporarily disable `set -e` in the parent
  # so it doesn't abort when the subshell exits non-zero, but `set -e` inside
  # the subshell still works because it's not on the left side of `||`.
  local exit_code
  if [ -n "${JUST_LOG_FILE:-}" ]; then
    # Leaf command invoked by a parent meta-command: append to the shared log.
    printf "%-40s" "$step_name..."
    echo "=== $step_name ===" >> "$JUST_LOG_FILE"
    set +e
    (set -e; "$@") >> "$JUST_LOG_FILE" 2>&1
    exit_code=$?
    set -e
  else
    # Standalone invocation: create an individual log file.
    local log_file="$_LOGS_DIR/${step_name}-$(date +%Y%m%d-%H%M%S).log"
    echo "log: $log_file"
    printf "%-40s" "$step_name..."
    set +e
    (set -e; "$@") > "$log_file" 2>&1
    exit_code=$?
    set -e
  fi
  if [ "$exit_code" -eq 0 ]; then
    echo "OK"
  else
    echo "FAILED"
    echo ""
    echo "Last 20 lines of output:"
    tail -20 "${JUST_LOG_FILE:-$log_file}"
    return $exit_code
  fi
}
'''

# -------- Sculptor Aliases --------
alias start := tmux-dev
alias start-no-project := tmux-dev-no-project
alias stop := tmux-stop
alias app := build-desktop-app
alias pkg := package-desktop-installer
alias refresh := refresh-assets
alias snapshot := snapshot-build-artifacts
alias publish := publish-build-artifacts
alias promote := promote-release
alias fixup := fixup-release
alias hotfix := hotfix-release

# === CI Commands ===

# Format Python and JS/TS code (auto-fix)
[group("ci")]
format:
    #!/usr/bin/env bash
    set -euo pipefail
    {{ _quiet_by_default_fn }}
    _do_format() {
      echo "Formatting Python files..."
      uv run ruff check --select UP006,UP007,I,F401 --fix --force-exclude --config pyproject.toml sculptor/
      uv run ruff format --force-exclude --config pyproject.toml sculptor/
      echo "Formatting JS/TS files..."
      {{ nvm_use }}
      cd "{{justfile_directory()}}/sculptor/frontend" && npm run format -- .
      echo "Formatting SCSS files..."
      cd "{{justfile_directory()}}/sculptor/frontend" && npx stylelint --fix --cache --cache-location node_modules/.cache/stylelint-fix 'src/**/*.scss'
    }
    quiet_by_default format _do_format

# Lint and format-check Python, JS/TS, and SCSS code
[group("ci")]
lint:
    #!/usr/bin/env bash
    set -euo pipefail
    {{ _quiet_by_default_fn }}
    _do_lint() {
      echo "Checking Python formatting..."
      uv run ruff format --check --force-exclude --config pyproject.toml sculptor/
      echo "Linting Python files..."
      uv run ruff check --force-exclude --config pyproject.toml sculptor/
      echo "Linting JS/TS files..."
      {{ nvm_use }}
      cd "{{justfile_directory()}}/sculptor/frontend" && npm run lint -- .
      echo "Linting SCSS files..."
      cd "{{justfile_directory()}}/sculptor/frontend" && npm run lint:styles
    }
    quiet_by_default lint _do_lint

# Type check Python (pyrefly) and JS/TS (tsc) code
[group("ci")]
typecheck:
    #!/usr/bin/env bash
    set -euo pipefail
    {{ _quiet_by_default_fn }}
    _do_typecheck() {
      echo "Type checking Python files with pyrefly..."
      cd "{{justfile_directory()}}" && uv run --project sculptor pyrefly check
      echo "Type checking JS/TS files with tsc..."
      {{ nvm_use }}
      cd "{{justfile_directory()}}/sculptor/frontend" && npm run tsc
    }
    quiet_by_default typecheck _do_typecheck

# Exclude pattern for style checks (test fixtures and snapshots)
_style_exclude := '__snapshots__|test_data'

# File patterns to skip in hygiene checks (binary and cache files)
_binary_file_pattern := '*.png|*.ico|*.jpg|*.jpeg|*.gif|*.webp|*.pdf|*.woff|*.woff2|*.ttf|*.eot'
_cache_file_pattern := '*.raw|*.llm_cache_json|*.transport_cache_jsonl|*.count_tokens_cache_json|*.golden.html'

# Check file hygiene: trailing whitespace and EOF formatting
[group("ci")]
check-file-hygiene:
    #!/usr/bin/env bash
    set -euo pipefail
    {{ _quiet_by_default_fn }}
    _do_check_file_hygiene() {
      cd "{{justfile_directory()}}"
      echo "Checking file hygiene (trailing whitespace and EOF formatting)..."
      # Helper function to check if file should be skipped
      # Using a function avoids bash 3.2 bug with case statements inside $()
      should_skip() {
        case "$1" in
          {{_binary_file_pattern}}|{{_cache_file_pattern}}) return 0 ;;
          *) return 1 ;;
        esac
      }
      PROBLEMS=""
      while IFS= read -r f; do
        should_skip "$f" && continue
        [ -f "$f" ] || continue
        # Check for trailing whitespace
        if grep -q '[[:blank:]]$' "$f" 2>/dev/null; then
          PROBLEMS="${PROBLEMS}${f}: trailing whitespace\n"
        fi
        # Skip empty files for EOF checks
        [ -s "$f" ] || continue
        # Check for missing trailing newline
        if [ -n "$(tail -c 1 "$f")" ]; then
          PROBLEMS="${PROBLEMS}${f}: missing trailing newline\n"
        # Check for multiple trailing newlines
        elif [ "$(tail -c 2 "$f" | wc -l)" -gt 1 ]; then
          PROBLEMS="${PROBLEMS}${f}: multiple trailing newlines\n"
        fi
      done < <(git ls-files | grep -Ev '{{_style_exclude}}')
      if [ -n "$PROBLEMS" ]; then
        echo "File hygiene issues found:"
        echo -e "$PROBLEMS"
        exit 1
      fi
      echo "All files pass hygiene checks."
    }
    quiet_by_default check-file-hygiene _do_check_file_hygiene

# Check for large files being staged (default threshold: 500KB)
# Only checks files staged for commit, not all files in repo
[group("ci")]
check-large-files maxkb="500":
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{justfile_directory()}}"
    echo "Checking for large staged files (>{{maxkb}}KB)..."
    # Get files staged for commit (excluding uv.lock)
    STAGED=$(git diff --cached --name-only --diff-filter=ACM 2>/dev/null | grep -v 'uv.lock' || true)
    if [ -z "$STAGED" ]; then
      echo "No staged files to check."
      exit 0
    fi
    LARGE_FILES=$(echo "$STAGED" | while read -r f; do
      [ -f "$f" ] || continue
      size=$(wc -c < "$f")
      if [ "$size" -gt $(({{maxkb}} * 1024)) ]; then
        echo "$f ($(( size / 1024 ))KB)"
      fi
    done || true)
    if [ -n "$LARGE_FILES" ]; then
      echo "Large files detected:"
      echo "$LARGE_FILES"
      exit 1
    fi
    echo "No large staged files found."

# Check YAML file syntax
[group("ci")]
check-yaml:
    #!/usr/bin/env bash
    set -euo pipefail
    {{ _quiet_by_default_fn }}
    _do_check_yaml() {
      cd "{{justfile_directory()}}"
      echo "Checking YAML file syntax..."
      YAML_FILES=$(git ls-files '*.yaml' '*.yml' | grep -Ev '{{_style_exclude}}|authentik')
      if [ -z "$YAML_FILES" ]; then
        echo "No YAML files to check."
        exit 0
      fi
      ERRORS=""
      while IFS= read -r f; do
        if ! uv run python -c "import yaml; yaml.safe_load(open('$f'))" 2>/dev/null; then
          ERRORS="$ERRORS$f\n"
        fi
      done <<< "$YAML_FILES"
      if [ -n "$ERRORS" ]; then
        echo "Invalid YAML files:"
        echo -e "$ERRORS"
        exit 1
      fi
      echo "All YAML files are valid."
    }
    quiet_by_default check-yaml _do_check_yaml

# Check that uv.lock is up to date with pyproject.toml
[group("ci")]
check-uv-lock:
    #!/usr/bin/env bash
    set -euo pipefail
    {{ _quiet_by_default_fn }}
    _do_check_uv_lock() {
      cd "{{justfile_directory()}}"
      echo "Checking uv.lock is up to date..."
      # Find all pyproject.toml files that have corresponding uv.lock files
      for lockfile in $(git ls-files '**/uv.lock' 'uv.lock'); do
        dir=$(dirname "$lockfile")
        if [ -f "$dir/pyproject.toml" ]; then
          echo "Checking $lockfile..."
          if ! uv lock --check --directory "$dir" 2>/dev/null; then
            echo "ERROR: $lockfile is out of date. Run 'uv lock' in $dir to update."
            exit 1
          fi
        fi
      done
      echo "All uv.lock files are up to date."
    }
    quiet_by_default check-uv-lock _do_check_uv_lock

# Run shellcheck on shell scripts
[group("ci")]
check-shellcheck:
    #!/usr/bin/env bash
    set -euo pipefail
    {{ _quiet_by_default_fn }}
    _do_check_shellcheck() {
      cd "{{justfile_directory()}}"
      echo "Running shellcheck on shell scripts..."
      SHELL_FILES=$(git ls-files '*.sh' '*.bash' | grep -Ev '{{_style_exclude}}|infra_scripts')
      if [ -z "$SHELL_FILES" ]; then
        echo "No shell scripts to check."
        exit 0
      fi
      echo "$SHELL_FILES" | xargs uv tool run --from shellcheck-py shellcheck --severity=warning
      echo "Shellcheck passed."
    }
    quiet_by_default check-shellcheck _do_check_shellcheck

# Internal: run a single check step, printing OK/FAILED with error tail.
# Used by `check` to run steps under concurrently.
_run-check step:
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p "{{ _logs_dir }}"
    step_log="{{ _logs_dir }}/{{step}}.log"
    if JUST_VERBOSE=1 just {{step}} > "$step_log" 2>&1; then
      echo "OK"
    else
      echo "FAILED"
      echo ""
      tail -20 "$step_log"
      exit 1
    fi
    if [ -n "${JUST_LOG_FILE:-}" ]; then
      { echo "=== {{step}} ==="; cat "$step_log"; echo; } >> "$JUST_LOG_FILE"
    fi

# Run all checks: format, lint, typecheck, newlines, and ratchets
# Set JUST_VERBOSE=1 in the environment for full output (used in CI).
[group("ci")]
check:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ "${JUST_VERBOSE:-}" != "1" ] && [ -z "${JUST_LOG_FILE:-}" ]; then
      mkdir -p "{{ _logs_dir }}"
      export JUST_LOG_FILE="{{ _logs_dir }}/check-$(date +%Y%m%d-%H%M%S).log"
      echo "log: $JUST_LOG_FILE"
    fi
    just install-frontend
    just generate-sculpt-client
    # Note: check-large-files is not included here as it checks staged files only (for pre-commit hooks)
    # Run checks in parallel (fastest first for quicker feedback).
    ./sculptor/frontend/node_modules/.bin/concurrently \
      --names check-yaml,check-uv-lock,check-shellcheck,ratchets,typecheck,check-file-hygiene,lint \
      --prefix-colors auto \
      "just _run-check check-yaml" \
      "just _run-check check-uv-lock" \
      "just _run-check check-shellcheck" \
      "just _run-check ratchets" \
      "just _run-check typecheck" \
      "just _run-check check-file-hygiene" \
      "just _run-check lint" \
      2>&1 | grep -v 'exited with code 0'

# Run all unit tests (backend, frontend, foundation, and sculpt CLI)
# Pass junitxml="true" to output JUnit XML files for CI
# Set JUST_VERBOSE=1 in the environment for full output (used in CI).
[group("ci")]
test-unit junitxml="":
    #!/usr/bin/env bash
    set -euo pipefail
    if [ "${JUST_VERBOSE:-}" != "1" ] && [ -z "${JUST_LOG_FILE:-}" ]; then
      mkdir -p "{{ _logs_dir }}"
      export JUST_LOG_FILE="{{ _logs_dir }}/test-unit-$(date +%Y%m%d-%H%M%S).log"
      echo "log: $JUST_LOG_FILE"
    fi
    just test-unit-backend {{ if junitxml != "" { "sculptor/pytest_junit.xml" } else { "" } }}
    just test-unit-frontend
    just test-unit-foundation
    just test-unit-sculpt {{ if junitxml != "" { "sculpt_junit.xml" } else { "" } }}

# Run foundation unit tests (the former imbue_core library, now sculptor.foundation).
# Runs with sculptor/sculptor/foundation/ as the pytest rootdir (via its own pytest.ini) so it
# keeps the isolated test environment it had as a standalone package, independent of sculptor/conftest.py.
[group("ci")]
test-unit-foundation:
    #!/usr/bin/env bash
    set -euo pipefail
    {{ _quiet_by_default_fn }}
    _do_test_unit_foundation() {
      env -u SESSION_TOKEN PROJECT_PATH=/tmp/repo GOOGLE_API_KEY=fake ANTHROPIC_API_KEY=fake uv run --project sculptor pytest -n "${SCULPTOR_TEST_WORKERS:-8}" sculptor/sculptor/foundation/ -m "not integration and not acceptance"
    }
    quiet_by_default test-unit-foundation _do_test_unit_foundation

# Run sculpt CLI unit tests
# Pass a path to junitxml to output JUnit XML for CI
[group("ci")]
test-unit-sculpt junitxml="":
    #!/usr/bin/env bash
    set -euo pipefail
    {{ _quiet_by_default_fn }}
    _do_test_unit_sculpt() {
      just generate-sculpt-client
      env -u SESSION_TOKEN uv run --project tools/sculpt python -m pytest tools/sculpt/tests/ {{ if junitxml != "" { "--junitxml=" + quote(junitxml) } else { "" } }}
    }
    quiet_by_default test-unit-sculpt _do_test_unit_sculpt

# === Testing ===

# Run pytest for a specific project (all args passed to pytest)
[group("testing")]
test project *args:
    uv run --project {{project}} python -m pytest {{args}}

# === Ratchets ===
# Lint enforcement is handled by the `ratchets` binary (crates.io). Config lives
# in ratchets.toml + ratchets/ at the repo root; budgets in ratchet-counts.toml.

# Install the pinned `ratchets` lint binary from crates.io. Plain `cargo install`
# no-ops once the version is in cargo's ledger; CI runs this under an isolated,
# cached CARGO_HOME so the no-op holds on a cache hit (see checks.yml).
[group("ratchets")]
install-ratchets:
    cargo install ratchets --version {{ ratchets_version }} --locked

# Check all ratchets (fails if any rule exceeds its budget in ratchet-counts.toml)
[group("ratchets")]
ratchets:
    #!/usr/bin/env bash
    set -euo pipefail
    {{ _require_ratchets }}
    {{ _quiet_by_default_fn }}
    _do_ratchets() {
      ratchets check
    }
    quiet_by_default ratchets _do_ratchets

# Run after adding or fixing rules. Mirrors the old `update`:
# re-pin every rule's budget to its current violation count (raises or lowers).
[group("ratchets")]
ratchets-update:
    #!/usr/bin/env bash
    set -euo pipefail
    {{ _require_ratchets }}
    ratchets bump --all

# Show ratchet violations in files you've changed since origin/main
[group("ratchets")]
ratchets-broken:
    #!/usr/bin/env bash
    set -euo pipefail
    {{ _require_ratchets }}
    ratchets check --since origin/main --verbose

# === API Client Generation ===

# Generate the sculpt CLI Python client from the OpenAPI spec
[group("codegen")]
generate-sculpt-client:
    #!/usr/bin/env bash
    set -euo pipefail
    {{ _quiet_by_default_fn }}
    _do_generate_sculpt_client() {
      echo "Generating sculpt CLI Python client..."
      # Use a per-invocation temp dir so parallel runs in separate clones
      # don't clobber each other's schema file.
      tmp_dir=$(mktemp -d)
      trap 'rm -rf "$tmp_dir"' EXIT
      tmp_schema="$tmp_dir/sculpt_openapi.json"
      uv run --project sculptor python sculptor/sculptor/scripts/generate_json_schema.py "$tmp_schema" >/dev/null 2>&1
      # Skip openapi-python-client when neither the schema nor the pinned
      # generator version changed since the last successful codegen. The
      # digest lives inside the generated client directory so it disappears
      # together with the output.
      cached_digest="tools/sculpt/sculpt/client/.codegen-digest"
      new_digest=$({
        cat "$tmp_schema"
        grep -A1 '^name = "openapi-python-client"' uv.lock || true
      } | shasum | awk '{print $1}')
      if [ -f "$cached_digest" ] && [ "$new_digest" = "$(cat "$cached_digest")" ]; then
        echo "Codegen inputs unchanged, skipping codegen: tools/sculpt/sculpt/client/"
        return 0
      fi
      uv run --project tools/sculpt openapi-python-client generate \
          --path "$tmp_schema" \
          --output-path tools/sculpt/sculpt/client_tmp \
          --overwrite \
          >/dev/null 2>&1
      rm -rf tools/sculpt/sculpt/client
      mv tools/sculpt/sculpt/client_tmp/sculptor_v1_api_client tools/sculpt/sculpt/client
      rm -rf tools/sculpt/sculpt/client_tmp
      echo "$new_digest" > "$cached_digest"
      echo "Done: tools/sculpt/sculpt/client/"
    }
    quiet_by_default generate-sculpt-client _do_generate_sculpt_client

# Generate the frontend TypeScript client from the OpenAPI spec
[group("codegen")]
generate-frontend-client:
    just generate-api

# Generate all API clients (sculpt CLI and frontend)
[group("codegen")]
generate-clients: generate-sculpt-client generate-frontend-client

# -------- Sculptor Development Commands --------

# Show last 256 log lines, then follow logs in real-time
[group("dev")]
tail-logs dev="":
    # if dev mode, tail from dev sculptor folder
    tail -n 256 -F {{ if dev != "" { DEV_SCULPTOR_FOLDER } else { SCULPTOR_FOLDER } }}"/logs/server/logs.jsonl" \
      | jq -r '(.record.file.path // "") + " | " + (.text // "")' \
      | sed '/^[[:space:]]*$/d'

# Patch the Electron binary's Info.plist so macOS shows the given name
# instead of "Electron" in the menu bar and dock.
# Usage: just _patch-electron-app-name "Sculptor (from source)"
[no-exit-message]
_patch-electron-app-name label:
    #!/usr/bin/env bash
    set -euo pipefail
    PLIST="{{justfile_directory()}}/sculptor/frontend/node_modules/electron/dist/Electron.app/Contents/Info.plist"
    if [ ! -f "$PLIST" ]; then
      echo "Warning: Electron Info.plist not found, skipping app name patch" >&2
      exit 0
    fi
    /usr/libexec/PlistBuddy -c "Set :CFBundleName '{{label}}'" "$PLIST" 2>/dev/null || true
    /usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName '{{label}}'" "$PLIST" 2>/dev/null || \
      /usr/libexec/PlistBuddy -c "Add :CFBundleDisplayName string '{{label}}'" "$PLIST" 2>/dev/null || true

# Start the Electron server
[group("dev")]
frontend:
    #!/usr/bin/env bash
    just _patch-electron-app-name "Sculptor (from source)"
    cd "{{justfile_directory()}}/sculptor/frontend"
    env SCULPTOR_ICON_LABEL="src" \
      npm run electron:start -- --  --unhandled-rejections=strict --trace-warnings

# Start Electron with the backend running in a Docker container (dev mode).
# Requires: Docker, ANTHROPIC_API_KEY (or ~/anthropic_key.txt).
# Usage:  just frontend-container
[group("dev")]
frontend-container:
    #!/usr/bin/env bash
    set -euo pipefail
    REPO_ROOT="{{justfile_directory()}}"
    IMAGE_NAME="sculptor-backend-dev"
    SCRIPT="$REPO_ROOT/container/run-backend-in-container.sh"

    # Build the Docker image if it doesn't exist
    if ! docker image inspect "$IMAGE_NAME" >/dev/null 2>&1; then
      echo "Building Docker image $IMAGE_NAME ..."
      docker build -f "$REPO_ROOT/container/container-backend-dev.dockerfile" -t "$IMAGE_NAME" "$REPO_ROOT"
    fi

    # Resolve ANTHROPIC_API_KEY
    if [ -z "${ANTHROPIC_API_KEY:-}" ] && [ -f "$HOME/anthropic_key.txt" ]; then
      export ANTHROPIC_API_KEY="$(cat "$HOME/anthropic_key.txt")"
    fi

    # Generate a shared SESSION_TOKEN so backend and frontend agree on CSRF
    export SESSION_TOKEN="${SESSION_TOKEN:-$(uuidgen)}"

    # Tell Electron to spawn the container and where to proxy
    export SCULPTOR_CUSTOM_BACKEND_CMD="$SCRIPT --dev"
    export SCULPTOR_CUSTOM_BACKEND_URL="http://localhost:${HOST_PORT:-8080}"

    just _patch-electron-app-name "Sculptor (from source)"
    export SCULPTOR_ICON_LABEL="src"
    cd "$REPO_ROOT/sculptor/frontend"
    exec npm run electron:start -- --  --unhandled-rejections=strict --trace-warnings

# Start Electron in custom-command mode WITHOUT Docker.
# Runs the backend from source via uv, but exercises the full custom-command
# code path (stdout URL parsing, HTTP file uploads, capabilities flags).
# This is the fastest way to iterate on custom-command changes.
# Usage:  just frontend-custom
[group("dev")]
frontend-custom:
    #!/usr/bin/env bash
    set -euo pipefail
    REPO_ROOT="{{justfile_directory()}}"
    PORT="${SCULPTOR_API_PORT:-5050}"

    export SESSION_TOKEN="${SESSION_TOKEN:-$(uuidgen)}"

    # A minimal "custom backend command" that runs the backend from source.
    # It prints the URL to stdout (so Electron can discover it) then execs the backend.
    export SCULPTOR_CUSTOM_BACKEND_CMD="echo http://localhost:${PORT} && cd ${REPO_ROOT}/sculptor && exec uv run python -m sculptor.cli.main --no-open-browser --port ${PORT}"

    just _patch-electron-app-name "Sculptor (from source)"
    export SCULPTOR_ICON_LABEL="src"
    cd "$REPO_ROOT/sculptor/frontend"
    exec npm run electron:start -- --  --unhandled-rejections=strict --trace-warnings

# Start the Storybook dev server
[group("dev")]
storybook:
    #!/usr/bin/env bash
    {{ nvm_use }}
    cd "{{justfile_directory()}}/sculptor/frontend"
    npm run storybook

# Start the Backend server. Pass repo_path="none" to skip auto-creating a project.
[group("dev")]
backend repo_path=".":
    #!/usr/bin/env bash
    # Generate the source-built sculpt CLI client so `.venv/bin/sculpt` actually
    # imports and runs (digest-cached; a no-op when the API schema is unchanged).
    # Together with sculpt being a dev dependency of sculptor, this guarantees dev
    # agents resolve `sculpt` to the source build instead of a stale packaged
    # binary (SCU-1360). Run from the repo root, before the cd into sculptor/.
    just generate-sculpt-client
    echo "Starting backend server..."
    cd "{{justfile_directory()}}/sculptor"
    if [ "{{repo_path}}" = "none" ]; then
      echo "Starting without initial project..."
      uv run --project sculptor python -m sculptor.cli.main --no-open-browser --no-serve-static
    else
      echo "Using repository path: {{repo_path}}"
      uv run --project sculptor python -m sculptor.cli.main --no-open-browser --no-serve-static "{{justfile_directory()}}/{{repo_path}}"
    fi

[group("dev")]
tmux-dev repo_path=".":
    #!/bin/bash
    just stop || true
    echo "Starting tmux development session..."
    echo "Using repository path: {{repo_path}}"
    echo "Killing existing session if present..."
    tmux kill-session -t {{session_name}} 2>/dev/null || true
    echo "Creating new tmux session..."
    tmux new-session -d -s {{session_name}} -n frontend `shell echo $$SHELL`
    tmux new-window -t {{session_name}} -n backend `shell echo $$SHELL`
    # Collect CLAUDE_* env vars (e.g. CLAUDE_AUTOCOMPACT_PCT_OVERRIDE) so they
    # reach the backend server and its claude child processes.  tmux send-keys
    # types text into a fresh shell that doesn't inherit the caller's env, so
    # we inject them explicitly in the `env` prefix.
    CLAUDE_ENV_VARS=""
    while IFS='=' read -r name value; do
        CLAUDE_ENV_VARS="$CLAUDE_ENV_VARS $name=$value"
    done < <(env | grep '^CLAUDE_')
    # Strip SCULPT_* vars leaked from an outer Sculptor session (when `just start`
    # is run from inside another Sculptor agent), and prepend the dev venv's bin
    # so the source-built `sculpt` shadows any packaged-app one on PATH.
    SCULPT_UNSETS="-u SCULPT_API_PORT -u SCULPT_WORKSPACE_ID -u SCULPT_PROJECT_ID -u SCULPT_AGENT_ID"
    DEV_PATH_PREFIX="{{justfile_directory()}}/.venv/bin"
    # Forward SCULPTOR_WORKSPACES_FOLDER if the caller set it (e.g. nested dev
    # instance redirecting workspaces to a flat path to avoid deep .dev_sculptor
    # nesting).  Same propagation pattern as CLAUDE_ENV_VARS above: tmux
    # send-keys runs in a fresh shell, so anything not embedded in the typed
    # command is lost.
    WORKSPACES_FOLDER_ARG="${SCULPTOR_WORKSPACES_FOLDER:+SCULPTOR_WORKSPACES_FOLDER=\"$SCULPTOR_WORKSPACES_FOLDER\"}"
    tmux send-keys -t {{session_name}}:frontend "cd '{{justfile_directory()}}' && env $SCULPT_UNSETS PATH=\"$DEV_PATH_PREFIX:\$PATH\" SCULPTOR_API_PORT={{SCULPTOR_API_PORT}} SCULPTOR_FRONTEND_PORT={{SCULPTOR_FRONTEND_PORT}} $WORKSPACES_FOLDER_ARG just frontend" Enter
    tmux send-keys -t {{session_name}}:backend "cd '{{justfile_directory()}}' && env $SCULPT_UNSETS PATH=\"$DEV_PATH_PREFIX:\$PATH\" SCULPTOR_API_PORT={{SCULPTOR_API_PORT}} SCULPTOR_FRONTEND_PORT={{SCULPTOR_FRONTEND_PORT}} SCULPTOR_CLAUDE_BINARY_DEFAULT_OVERRIDE=claude$CLAUDE_ENV_VARS $WORKSPACES_FOLDER_ARG just backend {{repo_path}}" Enter
    echo "Development servers started in tmux session '{{session_name}}'"
    echo "Backend serving repository: {{repo_path}}"
    echo "Use 'tmux attach -t {{session_name}}' to attach to the session"
    echo "Use 'just tmux-stop' to stop the session"
    tmux attach -t {{session_name}} || echo "Failed to attach to tmux session. You can attach manually using 'tmux attach -t {{session_name}}'"

# Start development servers without auto-creating a project (simulates first-run experience)
[group("dev")]
tmux-dev-no-project:
    just tmux-dev none

tmux-stop:
	tmux kill-session -t {{session_name}} 2>/dev/null && echo "Session '{{session_name}}' terminated" || echo "Session '{{session_name}}' did not exist"

# Rebuilds everything needed to successfully `just start` after changing commits
[group("dev")]
rebuild: clean install install-ratchets generate-api generate-sculpt-client

# Open the per-test runtime distribution visualization in a browser.
# Reads offload-history.jsonl from the repo root (tracked; updated by every `offload` run).
[group("dev")]
visualize-test-runtimes:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{justfile_directory()}}"
    PORT="$(uv run python -c 'import socket; s=socket.socket(); s.bind(("",0)); print(s.getsockname()[1]); s.close()')"
    URL="http://localhost:${PORT}/tools/offload-stats/test-runtime-distributions.html"
    echo "serving on http://localhost:${PORT}/  (Ctrl-C to stop)"
    echo "opening ${URL}"
    uv run python -m http.server "$PORT" >/dev/null 2>&1 &
    SERVER_PID=$!
    trap 'kill ${SERVER_PID} 2>/dev/null || true' EXIT
    sleep 0.3
    uv run python -m webbrowser "$URL" >/dev/null 2>&1 || true
    wait "$SERVER_PID"

# -------- Sculptor Build Commands --------

# Cleans up all files generated by the build process
[group("build")]
clean:
    #!/usr/bin/env bash
    cd "{{justfile_directory()}}/sculptor"
    echo "Cleaning up..."
    rm -rf frontend/node_modules
    rm -rf sculptor/web/frontend
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find . -name "*.pyc" -delete 2>/dev/null || true

    rm -r ./frontend-dist/* || true
    rm -r ./frontend/dist/* || true
    rm -r build/* || true
    rm -r _vendor/* || true
    rm -r _vendor/.lock || true
    rm sculptor/_version.py || true
    rm -rf frontend/src/api || true
    rm -rf frontend/out || true
    rm -rf frontend/.vite || true
    rm -rf ./dist/* || true
    rm -rf ../dist/* || true

# Installs build dependencies for a Mac
[group("install")]
[macos]
install-build-deps:
    #!/usr/bin/env bash
    set -euo pipefail
    {{ _quiet_by_default_fn }}
    _do_install_build_deps() {
      echo "Installing platform-specific build dependencies"
      # The uv python commands shouldn't be necessary most of the time,
      # but these need to be macOS x64 builds to function correctly -
      # we have a weird setup there where some workflows are run with arm mode and some with x64 mode.
      uv python install 3.13
      uv python update-shell
      brew install depot/tap/depot
      {{ nvm_use }}
    }
    quiet_by_default install-build-deps _do_install_build_deps

# Generates the frontend TypeScript client based on the API
[group("build")]
generate-api:
    #!/usr/bin/env bash
    set -euo pipefail
    {{ _quiet_by_default_fn }}
    _do_generate_api() {
      {{ nvm_use }}
      cd "{{justfile_directory()}}/sculptor/frontend"
      npm run generate-api
    }
    quiet_by_default generate-api _do_generate_api

# Installs all frontend libraries necessary
[group("install")]
install-frontend: && generate-api
    #!/usr/bin/env bash
    set -euo pipefail
    {{ _quiet_by_default_fn }}
    _do_install_frontend() {
      {{ nvm_use }}
      cd "{{justfile_directory()}}/sculptor/frontend"
      # Skip npm install when neither package.json nor package-lock.json has
      # changed since the last install. npm writes node_modules/.package-lock.json
      # on every successful install, so its mtime is a reliable stamp.
      stamp=node_modules/.package-lock.json
      if [ -f "$stamp" ] \
          && [ ! package.json -nt "$stamp" ] \
          && [ ! package-lock.json -nt "$stamp" ]; then
        echo "Frontend dependencies up to date, skipping npm install."
        return 0
      fi
      echo "Installing frontend dependencies..."
      npm ci
    }
    quiet_by_default install-frontend _do_install_frontend

# Installs all backend dependencies
[group("install")]
install-backend:
    # We don't actually have any pre-build installations for the backend now,
    # but leaving it as a no-op in case we need it in the future.

# Installs optional build dependencies for a Mac
[group("install")]
[macos]
install-build-deps-x86_64:
    bash "{{justfile_directory()}}/sculptor/builder/install-build-dependencies-x86_64.sh"

# Installs build dependencies
[group("install")]
[linux]
install-build-deps:
    #!/usr/bin/env bash
    set -euo pipefail
    {{ _quiet_by_default_fn }}
    _do_install_build_deps() {
      echo "Installing platform-specific build dependencies"
      uv python install 3.13
      uv python update-shell
      curl -L https://depot.dev/install-cli.sh | sh -s
      {{ nvm_use }}
    }
    quiet_by_default install-build-deps _do_install_build_deps

# Installs all dependencies.
# Set JUST_VERBOSE=1 in the environment for full output (used in CI).
[group("install")]
install:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ "${JUST_VERBOSE:-}" != "1" ] && [ -z "${JUST_LOG_FILE:-}" ]; then
      mkdir -p "{{ _logs_dir }}"
      export JUST_LOG_FILE="{{ _logs_dir }}/install-$(date +%Y%m%d-%H%M%S).log"
      echo "log: $JUST_LOG_FILE"
    fi
    just install-build-deps
    just install-backend
    just install-frontend
    # pi is not installed here: Sculptor provisions it in MANAGED mode (the
    # default). Run `just install-pi` only for a CUSTOM or real_pi dev setup.

# Installs the pinned, self-contained pi binary from GitHub Releases into
# .venv/pi (the whole release tree — the binary loads sibling files like
# package.json/wasm/theme relative to its real path) and symlinks it into
# .venv/bin, which `uv run` puts first on PATH so a CUSTOM `pi` resolves to it.
# We install the version PI_VERSION_RANGE pins. Sculptor provisions pi itself
# in MANAGED mode (the default), so this is NOT part of `just install`/`rebuild`.
# Opt-in dev helper: for a CUSTOM pi against .venv/bin/pi, or the real_pi suite.
[group("install")]
install-pi:
    #!/usr/bin/env bash
    set -euo pipefail
    {{ _quiet_by_default_fn }}
    _do_install_pi() {
      cd "{{justfile_directory()}}"
      venv="{{justfile_directory()}}/.venv"
      target="$venv/bin/pi"
      # Source of truth for the pinned version: PI_VERSION_RANGE. (uv run also
      # ensures the workspace venv exists, since we install into its bin.)
      version="$(uv run --project sculptor python -c 'from sculptor.services.dependency_management_service import PI_VERSION_RANGE; print(PI_VERSION_RANGE.recommended_version)')"
      if [ -x "$target" ] && [ "$("$target" --version 2>&1 | tr -dc '0-9.')" = "$version" ]; then
        echo "pi $version already installed."
        return 0
      fi
      case "$(uname -s)" in
        Darwin) os_part=darwin ;;
        Linux) os_part=linux ;;
        *) echo "install-pi: unsupported OS '$(uname -s)'" >&2; return 1 ;;
      esac
      case "$(uname -m)" in
        arm64|aarch64) arch_part=arm64 ;;
        x86_64|amd64) arch_part=x64 ;;
        *) echo "install-pi: unsupported arch '$(uname -m)'" >&2; return 1 ;;
      esac
      asset="pi-${os_part}-${arch_part}.tar.gz"
      url="https://github.com/earendil-works/pi/releases/download/v${version}/${asset}"
      echo "Downloading pi $version ($asset)..."
      tmp="$(mktemp -d)"
      trap 'rm -rf "$tmp"' RETURN
      curl -fsSL "$url" -o "$tmp/pi.tar.gz"
      rm -rf "$venv/pi"
      tar -xzf "$tmp/pi.tar.gz" -C "$venv"
      [ -x "$venv/pi/pi" ] || { echo "install-pi: pi binary missing in $asset" >&2; return 1; }
      ln -sf ../pi/pi "$target"
      echo "Installed pi $version -> $target"
    }
    quiet_by_default install-pi _do_install_pi

# Recompute pi's per-platform sha256 pin: download each supported-platform tarball,
# hash it, and print the platforms={...} block to paste into PI_PIN
# (sculptor/services/managed_tools.py). The one manual step at a pi version bump.
[group("install")]
compute-pi-pin version:
    uv run python "{{justfile_directory()}}/scripts/compute_pi_pin.py" "{{version}}"

# Installs additional dependencies for testing
[group("install")]
install-test:
	uv run --project sculptor -m playwright install --with-deps

# Install git hooks that delegate to just commands
[group("install")]
install-hooks:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{justfile_directory()}}"
    echo "Installing git hooks..."
    ln -sf ../../scripts/git-hooks/pre-commit .git/hooks/pre-commit
    echo "Git hooks installed successfully."
    echo "  pre-commit: runs 'just check' + 'just check-large-files'"

# Uninstall git hooks (restores to no hooks)
[group("install")]
uninstall-hooks:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{justfile_directory()}}"
    echo "Uninstalling git hooks..."
    rm -f .git/hooks/pre-commit .git/hooks/pre-push
    echo "Git hooks uninstalled."

# Creates a FE distribution for the backend to serve statically
[group("build")]
build-frontend: install-frontend
    #! /usr/bin/env bash
    {{ nvm_use }}
    cd "{{justfile_directory()}}/sculptor/frontend"
    # NOTE: intentionally not calling setup-build-vars here so test/dev builds don't pelt sentry
    npm run build --mode {{MODE}}
    mkdir -p ./frontend-dist
    cp -a dist/. ../frontend-dist/

[group("build")]
build-backend: install-backend
    #!/usr/bin/env bash
    cd "{{justfile_directory()}}/sculptor"
    echo "Creating an sdist for sculptor"
    uv run --project sculptor builder create-version-file

# Create _version.py with version and git SHA. Pass --annotate-dev for CI dev builds.
[group("build")]
create-version-file *args="":
    cd "{{justfile_directory()}}/sculptor" && uv run --project sculptor builder create-version-file {{ args }}

# Fail fast if pyproject version is inconsistent with the build context. Pass the
# tag (sculptor-v...) for tag builds; omit it for non-tag (dev) builds.
# The tag is a named parameter passed through quote() — NOT an unquoted variadic
# {{ args }} — because CI feeds github.ref_name through here and git refnames may
# contain shell metacharacters ($, ;, |, ...); unquoted interpolation would both
# drop an empty tag (the bug that failed every main build) and allow injection.
[group("build")]
verify-release-tag tag="":
    cd "{{justfile_directory()}}/sculptor" && uv run --project sculptor builder verify-release-tag --tag {{ quote(tag) }}

# Builds the Sculptor webapp in the default environment.
[group("build")]
build: (pyrefly-check) build-frontend build-backend

# run pyrefly type checking. can be skipped with by setting env var SKIP_PYREFLY_IN_SCULPTOR_BUILD=1
[private]
pyrefly-check:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{justfile_directory()}}"
    if [ -n "${SKIP_PYREFLY_IN_SCULPTOR_BUILD:-}" ]; then
        echo "Skipping pyrefly check (SKIP_PYREFLY_IN_SCULPTOR_BUILD is set)"
    else
        echo "Running pyrefly type check..."
        uv run --project sculptor pyrefly check
        echo "Pyrefly check passed!"
    fi

# Creates a production build of the Sculptor webapp and backend.
[group("build")]
dist:
    # The ENVIRONMENT variable gets eventually passed to sculptor/builder/cli.py,
    # where it's used to derive environment variables defining sentry DSN and release ID,
    # which then get picked up as Vite defines and affect the built JS files.
    @just ENVIRONMENT=production build-frontend build-backend

# Builds a "sidecar" of the Sculptor webapp backend.
[group("build")]
sidecar python_key="": dist
    /usr/bin/env bash "{{justfile_directory()}}/sculptor/builder/build-sidecar.sh" {{ python_key }}

# Builds a standalone binary for the sculpt CLI.
[group("build")]
sculpt-binary python_key="": generate-sculpt-client
    /usr/bin/env bash "{{justfile_directory()}}/sculptor/builder/build-sculpt.sh" {{ python_key }}

# Resizes and reformats icons for packaging based on an original
[group("build")]
icons:
    #! /usr/bin/env bash
    {{ nvm_use }}
    cd "{{justfile_directory()}}/sculptor/frontend"
    npm run generate-icons
    cp assets/desktop_icon.png assets/icons/icon.png


# Builds all the assets necessary for packaging into electron
[group("build")]
[macos]
electron-assets: icons

# Builds all the assets necessary for packaging into electron
[group("build")]
[linux]
electron-assets: icons

[doc("
The one-stop shop to clean, rebuild all intermediate targets from source, download all dependencies from remotes, and
prepare for a clean build. Prefix your electron build targets for ease of use, e.g. `just refresh app` or `just refresh pkg`")]
[group("build")]
refresh-assets: clean build-frontend sidecar sculpt-binary electron-assets

# Uses electron forge to create an executable application for MacOS on Arm64. This app will not be bundled into an installer.
[group("build")]
[macos]
build-desktop-app:
    #! /usr/bin/env bash
    {{ nvm_use }}
    cd "{{justfile_directory()}}/sculptor/frontend"
    # Set up the environment variables for the correct version. Defaults to
    # "dev" so `just refresh app` works locally without ceremony; CI sets
    # MODE=production explicitly when packaging release artifacts.
    eval $(uv run --project sculptor builder setup-build-vars "${MODE:-dev}") && npm run electron:package
    mkdir -p "{{justfile_directory()}}/dist/darwin-arm64"
    cp -r out/Sculptor-darwin-arm64/ "{{justfile_directory()}}/dist/darwin-arm64"

# Uses electron forge to create an executable application for MacOS on x86_64. This app will not be bundled into an installer.
[group("build")]
[macos]
build-desktop-app--x86_64:
    #!/usr/bin/env arch -x86_64 /usr/local/bin/bash -l
    {{ nvm_use }}
    set -e
    just refresh-assets
    just sidecar "cpython-3.13.7-macos-x86_64-none"
    cd "{{justfile_directory()}}/sculptor/frontend"
    npm ci
    eval $(uv run --project sculptor builder setup-build-vars "${MODE:-dev}") && npm run electron:package -- --  --platform=darwin --arch=x64
    mkdir -p "{{justfile_directory()}}/dist/Darwin-x86_64"
    cp -r out/Sculptor-darwin-x64/ "{{justfile_directory()}}/dist/darwin-x86_64"

# Uses electron forge to create an executable application for Linux. This app will not be bundled into an installer.
[group("build")]
[linux]
build-desktop-app:
    #! /usr/bin/env bash
    {{ nvm_use }}
    cd "{{justfile_directory()}}/sculptor/frontend"
    # Detect the host architecture (electron-forge builds for the host by default)
    case "$(uname -m)" in
      aarch64|arm64) ELECTRON_ARCH="arm64" ;;
      *)             ELECTRON_ARCH="x64" ;;
    esac
    # Set up the environment variables for the correct version. Defaults to
    # "dev" so `just refresh app` works locally without ceremony; CI sets
    # MODE=production explicitly when packaging release artifacts.
    eval $(uv run --project sculptor builder setup-build-vars "${MODE:-dev}") && npm run electron:package
    mkdir -p "{{justfile_directory()}}/dist/linux-${ELECTRON_ARCH}"
    cp -r "out/Sculptor-linux-${ELECTRON_ARCH}/" "{{justfile_directory()}}/dist/linux-${ELECTRON_ARCH}"

[doc("A simpler helper to unmount any Sculptor DMGs you might have mounted previously. This prevents the build step from
failing frustratingly after a long time generating artifacts but being unable to mount.")]
[group("build")]
[private]
[macos]
unmount-dmg:
    #! /usr/bin/env bash
    set +e
    hdiutil detach /Volumes/Sculptor || echo "No dmg mounted"
    set -e

[doc("""Uses electron forge to create an installable package (DMG) for MacOS (arm64).

You do NOT need to run `just app` before this, but might need to run `just refresh`.""")]
[group("build")]
[macos]
package-desktop-installer:
    #! /usr/bin/env bash
    just unmount-dmg
    {{ nvm_use }}
    cd "{{justfile_directory()}}/sculptor/frontend"
    # HACK: build with production vars so the shipped installer doesn't carry a dev/testing sentry dsn
    eval $(uv run --project sculptor builder setup-build-vars production) && npm run electron:make
    mkdir -p "{{justfile_directory()}}/dist"
    cp -r out/make/zip "{{justfile_directory()}}/dist"
    cp out/make/Sculptor.dmg "{{justfile_directory()}}/dist"
    cp out/make/Sculptor.dmg "{{justfile_directory()}}/dist/Sculptor-`uv run --project sculptor builder version | head -n 1 | cut -f2 -d" "`.dmg"
    bash "{{justfile_directory()}}/sculptor/builder/validate_sculptor_dmg.sh" "{{justfile_directory()}}/dist/Sculptor.dmg" arm64


[doc("""Build an unsigned dev DMG that can be installed alongside production Sculptor.

Syncs frontend/package.json to the .dev version from pyproject.toml so app.getVersion()
contains "-dev." (the convention that routes userData and the sculptor-data folder to
~/.dev-sculptor instead of ~/.sculptor — that split is what lets the dev build run
concurrently with a production install, since Electron's SingletonLock lives under
userData).

The version bump is reverted on exit (even on build failure) so package.json stays clean.
After this completes, run `just install-dev` to install + launch.""")]
[group("build")]
[macos]
pkg-dev:
    #! /usr/bin/env bash
    set -e
    ROOT="{{justfile_directory()}}"
    cd "$ROOT/sculptor"
    uv run --project sculptor builder sync-frontend-version
    trap '(cd "$ROOT/sculptor" && uv run --project sculptor builder sync-frontend-version --reverse)' EXIT
    {{ nvm_use }}
    cd "$ROOT/sculptor/frontend"
    # Use the "dev" sentry/posthog environment so daily-driver telemetry stays
    # out of the production buckets.
    eval $(uv run --project sculptor builder setup-build-vars dev) && \
        SKIP_NOTARIZE_AND_SIGN=1 npm run electron:make
    mkdir -p "$ROOT/dist"
    cp out/make/Sculptor.dmg "$ROOT/dist"
    echo "Built: $ROOT/dist/Sculptor.dmg"

[doc("""Install the dev DMG built by `just pkg-dev` to /Applications/Sculptor Dev.app.

If a dev instance was already running, kills it and relaunches the new build so
the colleague picks up their update. If dev wasn't running, just installs and
exits — no auto-launch, since a fresh install probably shouldn't take over the
foreground unprompted.""")]
[group("build")]
[macos]
install-dev:
    #! /usr/bin/env bash
    set -e
    DMG="{{justfile_directory()}}/dist/Sculptor.dmg"
    DEST="/Applications/Sculptor Dev.app"
    if [ ! -f "$DMG" ]; then
        echo "Error: $DMG not found. Run 'just pkg-dev' first." >&2
        exit 1
    fi
    # Track whether dev was already running. If yes, kill it now so the copy
    # doesn't clobber a live bundle, and relaunch at the end so the user picks
    # up the new build. If no, leave the launch decision to the user.
    WAS_RUNNING=0
    if pkill -f "/Applications/Sculptor Dev.app/Contents/MacOS/"; then
        WAS_RUNNING=1
        # Wait for the process tree to actually exit — the dev Electron's
        # before-quit handler can take up to ~30s if its backend child needs
        # SIGKILL. Launching `open -n` while the old SingletonLock is still
        # held makes the new instance silently exit on startup.
        for _ in $(seq 1 60); do
            pgrep -f "/Applications/Sculptor Dev.app/Contents/MacOS/" >/dev/null || break
            sleep 1
        done
    fi
    MOUNT=$(hdiutil attach -nobrowse -readonly "$DMG" | tail -n 1 | awk '{ for (i=3; i<=NF; i++) printf "%s%s", $i, (i<NF?OFS:ORS) }')
    trap 'hdiutil detach "$MOUNT" >/dev/null 2>&1 || true' EXIT
    SRC="$MOUNT/Sculptor.app"
    if [ ! -d "$SRC" ]; then
        echo "Error: $SRC not found in mounted DMG" >&2
        exit 1
    fi
    rm -rf "$DEST"
    cp -R "$SRC" "$DEST"
    # Unsigned build — strip quarantine so Gatekeeper doesn't refuse to launch.
    xattr -dr com.apple.quarantine "$DEST" || true
    echo "Installed: $DEST"
    if [ "$WAS_RUNNING" -eq 1 ]; then
        # Scrub Sculptor override env vars before launching. If the caller's
        # shell has any of these set (e.g. from a recent `just tmux-dev` or
        # integration test run), they leak into the GUI app via `open` and
        # quietly redirect the dev install at the wrong backend port /
        # userData / data folder. Most visible symptom: dev's renderer hits
        # prod's backend with dev's session token and bounces with
        # "Invalid or missing session token".
        env -u SCULPTOR_API_PORT \
            -u SCULPTOR_FRONTEND_PORT \
            -u SCULPTOR_SESSION_TOKEN \
            -u SCULPTOR_USER_DATA_DIR \
            -u SCULPTOR_FOLDER \
            -u SCULPTOR_FRONTEND_DIR \
            -u START_BACKEND_IN_DEV \
            open -n "$DEST"
    else
        echo "Launch with: open -n \"$DEST\""
    fi


[doc("""Uses electron forge to create an installable package (DMG) for MacOS (x86_64).

You do NOT need to run `just app` before this, but might need to run `just refresh`.""")]
[group("build")]
[macos]
package-desktop-installer-x86_64:
    #! /usr/bin/env bash
    just unmount-dmg
    {{ nvm_use }}
    cd "{{justfile_directory()}}/sculptor"
    bash builder/package-sculptor-x86_64.sh
    bash "builder/validate_sculptor_dmg.sh" ../dist/Sculptor-x86_64.dmg x86_64

[doc("""Uses electron forge to create an installable package (AppImage) for Linux.

You do NOT need to run `just app` before this, but might need to run `just refresh`.""")]
[group("build")]
[linux]
package-desktop-installer:
    #! /usr/bin/env bash
    {{ nvm_use }}
    cd "{{justfile_directory()}}/sculptor/frontend"
    # Detect the host architecture
    case "$(uname -m)" in
      aarch64|arm64) ELECTRON_ARCH="arm64" ;;
      *)             ELECTRON_ARCH="x64" ;;
    esac
    npm run electron:make

    # The AppImage maker includes the version in the filename.
    # Rename the file to remove the version for consistent filenames.
    mv "out/make/AppImage/${ELECTRON_ARCH}/Sculptor-"*.AppImage "out/make/AppImage/${ELECTRON_ARCH}/Sculptor.AppImage"

    mkdir -p "{{justfile_directory()}}/dist"
    # Note: This cp runs on Linux and the semantics are different than on Mac
    cp -r out/make/* "{{justfile_directory()}}/dist"

pkg_filename := if os() == "linux" { "AppImage/x64/Sculptor.AppImage" } else { "Sculptor.dmg" }

# -------- Sculptor Release Commands --------

# Generate an electron-updater auto-update manifest for the given platform and architecture.
[group("build")]
generate-autoupdate-manifest platform arch:
    #!/usr/bin/env bash
    cd "{{justfile_directory()}}/sculptor"
    uv run --project sculptor builder generate-autoupdate-manifest {{platform}} {{arch}}

# Uploads Snapshots of the artifacts for a given target to the BUILD s3 bucket and location.
[group("release")]
snapshot-build-artifacts platform arch:
    #!/usr/bin/env bash
    cd "{{justfile_directory()}}/sculptor"
    uv run --project sculptor builder snapshot-build-artifacts -p {{platform}} -a {{arch}}

# Pull down uploaded snapshots of the artifacts from the BUILD s3 bucket and location.
[group("release")]
retrieve-build-artifacts +args="":
    #!/usr/bin/env bash
    cd "{{justfile_directory()}}/sculptor"
    uv run --project sculptor builder retrieve-build-artifacts {{ args }}


[doc("""Publishes the artifacts for the given build to the public s3 buckets. This detects whether we're running in
release-candidate or not, and makes the appropriate copies.""")]
[group("release")]
publish-build-artifacts *args="":
    #!/usr/bin/env bash
    cd "{{justfile_directory()}}/sculptor"
    uv run --project sculptor builder publish-build-artifacts {{ args }}


# -------- Sculptor Testing Commands --------

# Run backend unit tests (excludes integration/acceptance tests)
# Pass a path to junitxml to output JUnit XML for CI
[group("test")]
test-unit-backend junitxml="":
    #!/usr/bin/env bash
    set -euo pipefail
    {{ _quiet_by_default_fn }}
    _do_test_unit_backend() {
      env -u SESSION_TOKEN uv run --project sculptor pytest -n "${SCULPTOR_TEST_WORKERS:-8}" "{{justfile_directory()}}/sculptor/sculptor/" "{{justfile_directory()}}/sculptor/builder/" --ignore=tests -m "not integration and not acceptance" {{ if junitxml != "" { "--junitxml=" + quote(junitxml) } else { "" } }}
    }
    quiet_by_default test-unit-backend _do_test_unit_backend

[group("test")]
test-unit-frontend:
    #!/usr/bin/env bash
    set -euo pipefail
    {{ _quiet_by_default_fn }}
    _do_test_unit_frontend() {
      {{ nvm_use }}
      cd "{{justfile_directory()}}/sculptor/frontend"
      stamp=node_modules/.package-lock.json
      if [ ! -f "$stamp" ] \
          || [ package.json -nt "$stamp" ] \
          || [ package-lock.json -nt "$stamp" ]; then
        npm ci
      else
        echo "Frontend dependencies up to date, skipping npm install."
      fi
      npm run generate-api
      npm test
    }
    quiet_by_default test-unit-frontend _do_test_unit_frontend

[group("test")]
test-build-artifacts:
	bash "{{justfile_directory()}}/sculptor/sculptor/scripts/test_build_artifacts.sh"

# Stops on first failure by default. Set RUN_ALL=1 to run all tests: RUN_ALL=1 just test-integration
# Set JUST_VERBOSE=1 in the environment for full output (used in CI).
# Uses pytest-xdist for parallel execution (-n auto, capped at 3 workers).
# Set XDIST_WORKERS to override (e.g. XDIST_WORKERS=1 for serial).
[group("test")]
test-integration tests="sculptor/tests/integration/" buildargs="": build-frontend generate-sculpt-client
    #!/usr/bin/env bash
    set -euo pipefail
    if [ "${JUST_VERBOSE:-}" != "1" ] && [ -z "${JUST_LOG_FILE:-}" ]; then
      mkdir -p "{{ _logs_dir }}"
      export JUST_LOG_FILE="{{ _logs_dir }}/test-integration-$(date +%Y%m%d-%H%M%S).log"
      echo "log: $JUST_LOG_FILE"
    fi
    if [ -n "${XDIST_WORKERS:-}" ]; then
      xdist_args="-n ${XDIST_WORKERS}"
    else
      xdist_args="-n auto --maxprocesses 3"
    fi
    # When SESSION_TIMEOUT_SECONDS is set, wrap pytest in timeout(1) --signal=INT
    # so that SIGINT goes directly to pytest (not through just). This lets pytest
    # handle KeyboardInterrupt and write JUnit XML before exiting.
    #
    # The conftest session budget guard (pytest_runtest_setup) uses
    # SESSION_TIMEOUT_SECONDS directly and fires between tests via pytest.fail().
    # The bash timeout is a safety net that only fires if the guard misses.
    # Its margin over the session budget must exceed PER_TEST_TIMEOUT because
    # the guard only checks between tests — a test that starts just before
    # the budget expires won't be interrupted until it finishes (or times out).
    # We add 120s on top for pytest teardown and JUnit XML writing.
    if [ -n "${SESSION_TIMEOUT_SECONDS:-}" ] && [ "${SESSION_TIMEOUT_SECONDS}" -gt 0 ] 2>/dev/null; then
      per_test_timeout="${PER_TEST_TIMEOUT:-180}"
      bash_timeout=$(( SESSION_TIMEOUT_SECONDS + per_test_timeout + 120 ))
      timeout_prefix="timeout --signal=INT --kill-after=60s ${bash_timeout}"
    else
      timeout_prefix=""
    fi
    {{ _quiet_by_default_fn }}
    _do_test_integration() {
      ${timeout_prefix} uv run --project sculptor pytest ${xdist_args} --ignore=sculptor/tests/integration/real_claude --ignore=sculptor/tests/integration/real_pi {{ if env("CI", "") != "" { "-o console_output_style=count --tb=short" } else { "--show-capture=all --capture=tee-sys -v -ra " + if env("RUN_ALL", "") != "" { "" } else { "-x" } } }} {{tests}} {{buildargs}}
    }
    quiet_by_default test-integration _do_test_integration

# Delegates to ``test-integration`` so it inherits the standard build,
# parallelism, and logging machinery — the only additions are a timestamped
# trace path and forced serial execution (one backend per trace path). The
# hardcoded scenario exercises frontend, backend, websocket, and the
# fake-Claude agent path, which is enough to produce events from every source
# the trace merge handles. See docs/development/tracing.md for trace contents.
# Run one integration test with backend tracing enabled and write the combined Chrome JSON trace under .just-logs/ for inspection in https://ui.perfetto.dev.
[group("test")]
test-tracing:
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p "{{ _logs_dir }}"
    trace_path="{{ _logs_dir }}/test-tracing-$(date +%Y%m%d-%H%M%S).json"
    # Always report the trace path on exit — even on test failure the lifespan
    # teardown may have written a partial file worth inspecting.
    report() {
      echo
      if [ -f "$trace_path" ]; then
        echo "trace written to: $trace_path"
        echo "drop the file at https://ui.perfetto.dev to view"
      else
        echo "no trace written (expected at $trace_path)"
      fi
    }
    trap report EXIT
    echo "trace will be written to: $trace_path"
    XDIST_WORKERS=1 just test-integration \
      "sculptor/tests/integration/frontend/test_home_page.py::test_recent_workspaces_shown_on_home_page" \
      "--sculptor-trace-to=$trace_path"

# Runs real Claude integration tests. Requires the `claude` CLI to be
# logged in (run `claude /login` once to write OAuth credentials to
# ~/.claude/). Hits real Claude usage and is excluded from CI. Run
# serially by default. Set XDIST_WORKERS to override (e.g.
# XDIST_WORKERS=2 for parallel).
[group("test")]
test-real-claude tests="sculptor/tests/integration/real_claude/" buildargs="": build-frontend generate-sculpt-client
    #!/usr/bin/env bash
    set -euo pipefail
    if [ "${JUST_VERBOSE:-}" != "1" ] && [ -z "${JUST_LOG_FILE:-}" ]; then
      mkdir -p "{{ _logs_dir }}"
      export JUST_LOG_FILE="{{ _logs_dir }}/test-real-claude-$(date +%Y%m%d-%H%M%S).log"
      echo "log: $JUST_LOG_FILE"
    fi
    if [ -n "${XDIST_WORKERS:-}" ]; then
      xdist_args="-n ${XDIST_WORKERS}"
    else
      xdist_args=""
    fi
    {{ _quiet_by_default_fn }}
    _do_test_real_claude() {
      uv run --project sculptor pytest ${xdist_args} -m real_claude --show-capture=all --capture=tee-sys -v -ra {{ if env("RUN_ALL", "") != "" { "" } else { "-x" } }} {{tests}} {{buildargs}}
    }
    quiet_by_default test-real-claude _do_test_real_claude

# Runs real pi integration tests (require ANTHROPIC_API_KEY). These tests hit
# the real upstream model through real pi and are excluded from CI. The
# `install-pi` dependency puts the pinned pi on PATH (.venv/bin/pi), which the
# real_pi resolver requires. Run serially by default.
# Set XDIST_WORKERS to override (e.g. XDIST_WORKERS=2 for parallel).
[group("test")]
test-real-pi tests="sculptor/tests/integration/real_pi/" buildargs="": install-pi build-frontend generate-sculpt-client
    #!/usr/bin/env bash
    set -euo pipefail
    if [ "${JUST_VERBOSE:-}" != "1" ] && [ -z "${JUST_LOG_FILE:-}" ]; then
      mkdir -p "{{ _logs_dir }}"
      export JUST_LOG_FILE="{{ _logs_dir }}/test-real-pi-$(date +%Y%m%d-%H%M%S).log"
      echo "log: $JUST_LOG_FILE"
    fi
    if [ -n "${XDIST_WORKERS:-}" ]; then
      xdist_args="-n ${XDIST_WORKERS}"
    else
      xdist_args=""
    fi
    {{ _quiet_by_default_fn }}
    _do_test_real_pi() {
      uv run --project sculptor pytest ${xdist_args} -m real_pi --show-capture=all --capture=tee-sys -v -ra {{ if env("RUN_ALL", "") != "" { "" } else { "-x" } }} {{tests}} {{buildargs}}
    }
    quiet_by_default test-real-pi _do_test_real_pi

# Runs Electron integration tests (marked @pytest.mark.electron or @pytest.mark.browser_and_electron).
# Same env var overrides as test-integration: RUN_ALL=1, XDIST_WORKERS=N, JUST_VERBOSE=1.
# Uses fewer parallel workers than test-integration (Electron is heavier than headless Chromium).
[group("test")]
test-integration-electron tests="sculptor/tests/integration/" buildargs="": build-frontend generate-sculpt-client
    #!/usr/bin/env bash
    set -euo pipefail
    if [ "${JUST_VERBOSE:-}" != "1" ] && [ -z "${JUST_LOG_FILE:-}" ]; then
      mkdir -p "{{ _logs_dir }}"
      export JUST_LOG_FILE="{{ _logs_dir }}/test-integration-electron-$(date +%Y%m%d-%H%M%S).log"
      echo "log: $JUST_LOG_FILE"
    fi
    if [ -n "${XDIST_WORKERS:-}" ]; then
      xdist_args="-n ${XDIST_WORKERS}"
    else
      xdist_args="-n auto --maxprocesses 2"
    fi
    # When SESSION_TIMEOUT_SECONDS is set, wrap pytest in timeout(1) --signal=INT.
    # Margin = PER_TEST_TIMEOUT + 120s teardown (see test-integration for rationale).
    if [ -n "${SESSION_TIMEOUT_SECONDS:-}" ] && [ "${SESSION_TIMEOUT_SECONDS}" -gt 0 ] 2>/dev/null; then
      per_test_timeout="${PER_TEST_TIMEOUT:-180}"
      bash_timeout=$(( SESSION_TIMEOUT_SECONDS + per_test_timeout + 120 ))
      timeout_prefix="timeout --signal=INT --kill-after=60s ${bash_timeout}"
    else
      timeout_prefix=""
    fi
    {{ _quiet_by_default_fn }}
    _do_test_integration_electron() {
      ${timeout_prefix} uv run --project sculptor pytest ${xdist_args} --ignore=sculptor/tests/integration/real_claude --ignore=sculptor/tests/integration/real_pi --sculptor-launch-mode=electron {{ if env("CI", "") != "" { "-o console_output_style=count --tb=short" } else { "--show-capture=all --capture=tee-sys -v -ra " + if env("RUN_ALL", "") != "" { "" } else { "-x" } } }} {{tests}} {{buildargs}}
    }
    quiet_by_default test-integration-electron _do_test_integration_electron

[group("test")]
benchmark tests="sculptor/tests/benchmark" buildargs="":
    uv run --project sculptor pytest --show-capture=all --capture=tee-sys -v -ra {{tests}} {{buildargs}}

# Run integration tests in parallel on Modal via Offload
[group("test")]
test-offload *args="":
    #!/bin/bash
    set -ueo pipefail
    {{ _require_offload }}
    ulimit -n 8192
    offload run --trace {{args}} || [ $? -eq 2 ]

# Run the @electron integration subset on Offload (Modal) in Electron launch
# mode; see offload-electron.toml. These are skipped by the browser-mode lane.
[group("test")]
test-offload-electron *args="":
    #!/bin/bash
    set -ueo pipefail
    {{ _require_offload }}
    ulimit -n 8192
    offload run -c offload-electron.toml --trace {{args}} || [ $? -eq 2 ]

# Run the backend unit suite on Offload (Modal); see offload-unit.toml.
# Alternative to `just test-unit-backend` (pytest -n 8).
[group("test")]
test-unit-offload *args="":
    #!/bin/bash
    set -ueo pipefail
    {{ _require_offload }}
    ulimit -n 8192
    offload run -c offload-unit.toml --trace --show-estimated-cost {{args}} || [ $? -eq 2 ]

# -------- Sculptor Release Commands --------

# Runs the dev command to create a branch bumping the version
[group("release")]
bump-version args="":
    #!/usr/bin/env bash
    cd "{{justfile_directory()}}/sculptor"
    uv run --project sculptor builder bump-version {{args}}

# Run the dev command to cut a release
[group("release")]
cut-release *args="":
    #!/usr/bin/env bash
    cd "{{justfile_directory()}}/sculptor"
    uv run --project sculptor builder cut-release {{args}}

# Run the dev command to update a release
[group("release")]
fixup-release args="":
    #!/usr/bin/env bash
    cd "{{justfile_directory()}}/sculptor"
    uv run --project sculptor builder fixup-release {{args}}

# Begins a hotfix branch for a release that was already published
[group("release")]
hotfix-release args="":
    #!/usr/bin/env bash
    cd "{{justfile_directory()}}/sculptor"
    uv run --project sculptor builder hotfix-release {{args}}


# Promote a release to the latest version
[group("release")]
promote-release args="":
    #!/usr/bin/env bash
    cd "{{justfile_directory()}}/sculptor"
    uv run --project sculptor builder promote-release {{args}}

# Trigger a dev build pipeline from the current branch
[group("release")]
trigger-dev-build:
    #!/usr/bin/env bash
    set -euo pipefail
    # Require clean working tree
    if ! git diff --quiet HEAD; then
        echo "Error: working tree is dirty. Commit or stash changes first."
        exit 1
    fi
    # Reject release versions — dev builds must use a .dev suffix in pyproject.toml
    VERSION=$(cd sculptor && python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")
    if [[ "$VERSION" != *".dev"* ]]; then
        echo "Error: pyproject.toml version '$VERSION' is a release version."
        echo "Dev builds require a .dev suffix (e.g. 0.15.0.dev0). Aborting."
        exit 1
    fi
    REF="$(git rev-parse --abbrev-ref HEAD)"
    if [ "$REF" = "HEAD" ]; then
        echo "Error: detached HEAD state. Check out a branch first."
        exit 1
    fi
    # Ensure branch is fully pushed to the remote
    git fetch origin "$REF" 2>/dev/null || true
    LOCAL_SHA="$(git rev-parse HEAD)"
    REMOTE_SHA="$(git rev-parse "origin/$REF" 2>/dev/null || echo "")"
    if [ -z "$REMOTE_SHA" ]; then
        echo "Error: branch '$REF' does not exist on origin. Push it first."
        exit 1
    fi
    if [ "$LOCAL_SHA" != "$REMOTE_SHA" ]; then
        echo "Error: local branch '$REF' ($LOCAL_SHA) differs from origin ($REMOTE_SHA)."
        echo "Push your changes first: git push origin $REF"
        exit 1
    fi
    echo "Triggering dev build on ref: $REF (sha: $LOCAL_SHA)"
    gh workflow run build-desktop.yml --ref "$REF"
