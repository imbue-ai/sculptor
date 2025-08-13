.PHONY: dev start frontend backend rm-state clean install install-frontend install-backend install-test build build-frontend build-backend help tmux-dev tmux-stop test-integration test-integration-dist
.ONESHELL:
.SHELLFLAGS := -eu -o pipefail -c

# We keep track of the user's shell so we can start tmux environments in the
# language they are accustomed.
_ENV_SHELL := $(shell echo $$SHELL)

# But we MUST force all our scripts to use bash so they are consistent
# machine-to-machine.
SHELL := /bin/bash

# Variables
SESSION_NAME := sculptor-session
REPO_PATH ?= $(error REPO_PATH is required. Usage: make dev REPO_PATH=/path/to/repo)
DEV_MODE ?= false
ENABLED_FRONTEND_ARTIFACT_VIEWS ?= ""


# Force SHELL to /bin/bash for users of more esoteric shells
ifeq ($(filter %bash %zsh,$(notdir $(SHELL))),)
    SHELL := /bin/bash
endif


# Environment controls which environment that the test is running in.
# It is dev by default, but can be one of {dev|production|testing}
ENVIRONMENT ?= dev


dev: tmux-dev ## Run both frontend and backend in tmux session (requires REPO_PATH=/path/to/repo)
              ## Note that this supports hot-reloading for frontend assets.

start: tmux-dev

sos: install
	echo "Starting tmux development session..."
	echo "Using repository path: $(REPO_PATH)"
	echo "Killing existing session if present..."
	tmux kill-session -t $(SESSION_NAME) 2>/dev/null || true
	echo "Creating new tmux session..."
	tmux new-session -d -s $(SESSION_NAME) -n dev-frontend -c "$(PWD)/frontend" $(_ENV_SHELL)
	tmux new-window -t $(SESSION_NAME) -n dev-backend $(_ENV_SHELL)
	tmux new-window -t $(SESSION_NAME) -n dist $(_ENV_SHELL)
	tmux new-window -t $(SESSION_NAME) -n test-project $(_ENV_SHELL)
	tmux send-keys -t $(SESSION_NAME):dev-frontend "npm run dev -- --open" Enter
	tmux send-keys -t $(SESSION_NAME):dev-backend "DEV_MODE=true USE_PROD_POSTHOG=0 ENABLED_FRONTEND_ARTIFACT_VIEWS=$(ENABLED_FRONTEND_ARTIFACT_VIEWS) uv run python -m sculptor.cli.main  --no-open-browser $(REPO_PATH)" Enter
	tmux send-keys -t $(SESSION_NAME):dist "SCULPTOR_API_PORT=1224 uvx --with https://imbue-sculptor-latest.s3.us-west-2.amazonaws.com/internal/sculptor.tar.gz --refresh sculptor .." Enter
	tmux send-keys -t $(SESSION_NAME):test-project "cd $(REPO_PATH)" Enter
	echo "Development servers started in tmux session '$(SESSION_NAME)'"
	echo "Backend serving repository: $(REPO_PATH)"
	echo "Use 'tmux attach -t $(SESSION_NAME)' to attach to the session"
	echo "Use 'make tmux-stop' to stop the session"
	tmux attach -t $(SESSION_NAME) || echo "Failed to attach to tmux session. You can attach manually using 'tmux attach -t $(SESSION_NAME)'"


tmux-dev: install ## Start tmux session with frontend and backend windows (requires REPO_PATH=/path/to/repo)
	echo "Starting tmux development session..."
	echo "Using repository path: $(REPO_PATH)"
	echo "Killing existing session if present..."
	tmux kill-session -t $(SESSION_NAME) 2>/dev/null || true
	echo "Creating new tmux session..."
	tmux new-session -d -s $(SESSION_NAME) -n frontend $(_ENV_SHELL)
	tmux new-window -t $(SESSION_NAME) -n backend $(_ENV_SHELL)
	tmux send-keys -t $(SESSION_NAME):frontend "cd \"$(PWD)/frontend\" && DEV_MODE=$(DEV_MODE) npm run dev" Enter
	tmux send-keys -t $(SESSION_NAME):backend "cd \"$(PWD)\" && DEV_MODE=$(DEV_MODE) ENABLED_FRONTEND_ARTIFACT_VIEWS=$(ENABLED_FRONTEND_ARTIFACT_VIEWS) uv run python -m sculptor.cli.main --serve-static $(REPO_PATH)" Enter
	echo "Development servers started in tmux session '$(SESSION_NAME)'"
	echo "Backend serving repository: $(REPO_PATH)"
	echo "Use 'tmux attach -t $(SESSION_NAME)' to attach to the session"
	echo "Use 'make tmux-stop' to stop the session"
	tmux attach -t $(SESSION_NAME) || echo "Failed to attach to tmux session. You can attach manually using 'tmux attach -t $(SESSION_NAME)'"

tmux-stop: ## Stop tmux development session
	echo "Stopping tmux session..."
	tmux kill-session -t $(SESSION_NAME) 2>/dev/null || echo "Session '$(SESSION_NAME)' not found"

frontend: install ## Run the frontend development server
	echo "Starting frontend server..."
	cd frontend && npm run dev

backend: ## Run the backend server (requires REPO_PATH=/path/to/repo)
	echo "Starting backend server..."
	echo "Using repository path: $(REPO_PATH)"
	uv run python -m sculptor.cli.main $(REPO_PATH)

rm-state: ## Clear sculptor application state
	echo "Clearing sculptor database..."
	rm -f ~/.sculptor/database.db
	rm -f ~/.sculptor/database.db-shm
	rm -f ~/.sculptor/database.db-wal

# Build commands follow

clean: ## Clean node_modules and Python cache
	echo "Cleaning up..."
	rm -rf frontend/node_modules
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm ../dist/* claude-container/*.whl || true
	rm -r ./frontend-dist/* || true
	rm -r build/* || true
	rm -r _vendor/* || true
	rm sculptor/_version.py || true
	rm -rf frontend/src/api || true

install-frontend:
	# Only installs the frontend dependencies, for local iteration. Will not set
	# up a FE dist to enable the sculptor backend to serve statically.
	echo "Installing frontend dependencies..."
	( cd frontend && npm install --force )
	( cd frontend && npm run build )

build-frontend: install-frontend
	# Creates a FE distribution for the sculptor backend to serve statically.
    # This next line will set up the correct sentry variables and then runs npm build
	echo $(ENVIRONMENT)
	( eval $$(uv run sculptor/scripts/dev.py setup-build-vars $(ENVIRONMENT)) && cd frontend && npm run build )
	# Necessary to pre-create the target so the following command behaves the
	# same on Mac and Linux.
	mkdir -p ./frontend-dist
	# These /. s are necessary to ensure the correct data gets copied into place
	cp -R frontend/dist/. ./frontend-dist/.

install-backend:
	echo "Installing backend dependencies..."
	# We cannot install imbue_core's dependencies at this time, because that
	# would bake in platform-specific .so files and other binaries into our
	# build, which we want to be platform agnostic.
	uv pip install ../imbue_core --no-deps --target _vendor

build-backend: install-backend
	echo "Building the Docker image and creating a sdist for sculptor"
	uv run sculptor/scripts/dev.py images
	uv run sculptor/scripts/dev.py create-version-file
	uv build --wheel --sdist

install: build-frontend install-backend ## Install dependencies for both frontend and backend

install-test:
	# Override the environment completed and ensure we are getting a testing build
	$(MAKE) ENVIRONMENT=testing install
	uv run -m playwright install --with-deps

build: build-frontend build-backend ## build the artifacts

dist: install
	$(MAKE) build-frontend build-backend ENVIRONMENT=production

dist-test: install-test
	$(MAKE) ENVIRONMENT=testing build

sidecar: install
	# Creates a bundled executable sidecar of the Sculptor application that we
	# can use for the Desktop app.
	#
	# TODO(danver): I don't want to have to collect These things by hand. Figure
	# out a better way.
	uv run --project sculptor pyinstaller --onefile --name sculptor_main \
  --collect-all coolname \
  --copy-metadata coolname \
	sculptor/cli/main.py

# Release and operational commands follow

bump-version: ## Convenience shortcut for creating a branch bumping the version.
	uv run sculptor/scripts/dev.py bump-version $(ARGS)

cut-release: ## Convenience shortcut for running dev command to cut a release
	# No dependencies because it's a shortcut
	uv run sculptor/scripts/dev.py cut-release $(RELEASE_ARGS)

fixup-release: ## Convenience shortcut for running dev command to update a release
	# No dependencies because it's a shortcut
	uv run sculptor/scripts/dev.py fixup-release $(RELEASE_ARGS)

promote: ## Promote a release to the latest version
	# No dependencies because it's a shortcut
	uv run sculptor/scripts/dev.py promote $(RELEASE_ARGS)

generate-release-notes: ## Convenience shortcut for running dev command to update a release
	# No dependencies because it's a shortcut
	uv run sculptor/scripts/dev.py generate-release-notes $(RELEASE_ARGS)


# Help command

help: ## Show this help message
	echo "Available targets:"
	grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-12s %s\n", $$1, $$2}'


# Tests below
test-integration: # Run integration tests for Sculptor
	# Sculptors integration tests will run the makefile targets it needs to run, so no dependencies
	uv run pytest -n 8 -k "v1" -m "integration" --show-capture=all --capture=tee-sys -v -ra $(or $(TEST_ARGS), "tests/integration/")

test-integration-no-build: # Run integration tests for Sculptor
	# Sculptors integration tests will run the makefile targets it needs to run, so no dependencies
	uv run pytest -n 8 -k "v1" -m "integration" --show-capture=all --capture=tee-sys -v -ra --skip-build-artifacts $(or $(TEST_ARGS), "tests/integration/")

test-integration-dist: # Run integration tests for Sculptor on the dist
	# Sculptors integration tests will run the makefile targets it needs to run, so no dependencies here.
	uv run pytest -n 8 -k "dist" -m "integration" --show-capture=all --capture=tee-sys -v -ra $(or $(TEST_ARGS), "tests/integration/")

test-acceptance: # Run acceptance tests for Sculptor on the dist
	# Sculptors acceptance tests will run the makefile targets it needs to run, so no dependencies here.
	# We only ever run the acceptance tests on the dist.
	# TODO: Add the Acceptance Testing Folder
	uv run pytest -n 8 -k "dist" -m "acceptance" --show-capture=all --capture=tee-sys -v -ra $(or $(TEST_ARGS), "tests/integration/")

test-unit: ## Run unit tests for Sculptor
	uv run pytest -n 8 -sv $(or $(TEST_ARGS), "sculptor/")

test-build-artifacts: ## Test the build script and verify that the artifacts can run
	bash sculptor/scripts/test_build_artifacts.sh
