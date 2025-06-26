.PHONY: dev start frontend backend rm-state clean install help tmux-dev tmux-stop test-integration
.SILENT:
.ONESHELL:

# Variables
SESSION_NAME := sculptor-session
REPO_PATH ?= $(error REPO_PATH is required. Usage: make dev REPO_PATH=/path/to/repo)
DEV_MODE ?= false
# Force SHELL to /bin/bash for users of more esoteric shells
ifeq ($(filter %bash %zsh,$(SHELL)),)
    SHELL := /bin/bash
endif

dev: tmux-dev ## Run both frontend and backend in tmux session (requires REPO_PATH=/path/to/repo)

start: install tmux-dev

tmux-dev: ## Start tmux session with frontend and backend windows (requires REPO_PATH=/path/to/repo)
	echo "Starting tmux development session..."
	echo "Using repository path: $(REPO_PATH)"
	echo "Killing existing session if present..."
	tmux kill-session -t $(SESSION_NAME) 2>/dev/null || true
	echo "Creating new tmux session..."
	tmux new-session -d -s $(SESSION_NAME) -n frontend $(SHELL)
	tmux new-window -t $(SESSION_NAME) -n backend $(SHELL)
	tmux send-keys -t $(SESSION_NAME):frontend "cd $(PWD)/../sculptor_v0/frontend && DEV_MODE=$(DEV_MODE) npm run dev" Enter
	tmux send-keys -t $(SESSION_NAME):backend "cd $(PWD) && DEV_MODE=$(DEV_MODE) uv run python -m sculptor.cli.main $(REPO_PATH)" Enter
	echo "Development servers started in tmux session '$(SESSION_NAME)'"
	echo "Backend serving repository: $(REPO_PATH)"
	echo "Use 'tmux attach -t $(SESSION_NAME)' to attach to the session"
	echo "Use 'make tmux-stop' to stop the session"
	tmux attach -t $(SESSION_NAME) || echo "Failed to attach to tmux session. You can attach manually using 'tmux attach -t $(SESSION_NAME)'"

tmux-stop: ## Stop tmux development session
	echo "Stopping tmux session..."
	tmux kill-session -t $(SESSION_NAME) 2>/dev/null || echo "Session '$(SESSION_NAME)' not found"

frontend: ## Run the frontend development server
	echo "Starting frontend server..."
	cd ../sculptor_v0/frontend && npm run dev

backend: ## Run the backend server (requires REPO_PATH=/path/to/repo)
	echo "Starting backend server..."
	echo "Using repository path: $(REPO_PATH)"
	uv run python -m sculptor.cli.main $(REPO_PATH)

rm-state: ## Clear sculptor application state
	echo "Clearing sculptor database..."
	rm /tmp/sculptor.db

# Build commands follow

clean: ## Clean node_modules and Python cache
	echo "Cleaning up..."
	rm -rf ../sculptor_v0/frontend/node_modules
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm ../dist/* claude-container/*.whl || true
	rm -r ./frontend-dist/* || true
	rm -r build/* || true
	rm -r _vendor/* || true
	rm -r sculptor/_version.py || true


install: ## Install dependencies for both frontend and backend
	echo "Installing frontend dependencies..."
	( cd ../sculptor_v0/frontend && npm install --force )
	echo "Installing backend dependencies..."
	uv sync --dev
	# We cannot install imbue_core's dependencies at this time, because that
	# would bake in platform-specific .so files and other binaries into our
	# build, which we want to be platform agnostic.
	uv pip install ../imbue_core --no-deps --target _vendor
	echo "Building the docker image."
	uv run sculptor/scripts/dev.py images


dist: clean install  ## Build a distribution for sculptor

    # We have a dependency on sculptor_v0 for the frontend artifacts
	cd ../sculptor_v0/frontend && npm run build
	cp -R ../sculptor_v0/frontend/dist/ ./frontend-dist

	uv run sculptor/scripts/dev.py create-version-file

	uv build --wheel --sdist


help: ## Show this help message
	echo "Available targets:"
	grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-12s %s\n", $$1, $$2}'

# Tests below
test-integration: ## Run integration tests for Sculptor
	uv run sculptor/scripts/dev.py images
	uv run --project ../sculptor pytest ../sculptor/tests/integration --no-headless -kv1 -sv -ra $(TEST_ARGS)

test-unit: ## Run unit tests for Sculptor
	uv run pytest sculptor/ -n 8 $(TEST_ARGS)
