#!/bin/bash
#
# Publish a recipe directory as a GitHub gist.
#
# Resolves symlinks so the gist contains real file contents (gists are flat
# and don't support symlinks or subdirectories).
#
# Usage:
#   ./publish-gist.sh <recipe-dir> [--public] [--update <gist-id>]
#
# Examples:
#   ./publish-gist.sh recipes/docker                     # Create secret gist
#   ./publish-gist.sh recipes/docker --public             # Create public gist
#   ./publish-gist.sh recipes/docker --update abc123def   # Update existing gist
#   ./publish-gist.sh recipes/docker --dry-run            # Stage files without publishing
#
# Requires: gh (GitHub CLI), authenticated (unless --dry-run)

set -euo pipefail

log() { echo "[publish-gist] $*" >&2; }

usage() {
    echo "Usage: $0 <recipe-dir> [--public] [--update <gist-id>] [--dry-run]" >&2
    exit 1
}

if [ $# -lt 1 ]; then
    usage
fi

RECIPE_DIR="$1"
shift

if [ ! -d "$RECIPE_DIR" ]; then
    log "ERROR: $RECIPE_DIR is not a directory"
    exit 1
fi

PUBLIC_FLAG=""
UPDATE_GIST=""
DRY_RUN=false

while [ $# -gt 0 ]; do
    case "$1" in
        --public)
            PUBLIC_FLAG="--public"
            shift
            ;;
        --update)
            UPDATE_GIST="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        *)
            usage
            ;;
    esac
done

if [ "$DRY_RUN" = false ]; then
    # Check that gh is installed
    if ! command -v gh > /dev/null 2>&1; then
        log "ERROR: gh (GitHub CLI) is not installed."
        log "Install it from https://cli.github.com/ and try again."
        exit 1
    fi

    # Check that gh is authenticated
    if ! gh auth status > /dev/null 2>&1; then
        log "ERROR: gh is not authenticated."
        log "Run 'gh auth login' to authenticate and try again."
        exit 1
    fi
fi

# Create a temp dir with resolved symlinks
TEMP_DIR=$(mktemp -d)
if [ "$DRY_RUN" = false ]; then
    trap 'rm -rf "$TEMP_DIR"' EXIT
fi

log "Preparing files from $RECIPE_DIR"

for file in "$RECIPE_DIR"/*; do
    [ -f "$file" ] || continue
    basename=$(basename "$file")

    # Skip hidden files and __pycache__
    case "$basename" in
        .*|__pycache__) continue ;;
    esac

    if [ -L "$file" ]; then
        # Resolve symlink — copy the actual file content
        resolved=$(readlink -f "$file")
        log "  $basename (resolved from symlink -> $resolved)"
        cp "$resolved" "$TEMP_DIR/$basename"
    else
        log "  $basename"
        cp "$file" "$TEMP_DIR/$basename"
    fi
done

# Build the file list for gh gist create
FILE_LIST=()
for file in "$TEMP_DIR"/*; do
    [ -f "$file" ] || continue
    FILE_LIST+=("$file")
done

if [ ${#FILE_LIST[@]} -eq 0 ]; then
    log "ERROR: No files found in $RECIPE_DIR"
    exit 1
fi

RECIPE_NAME=$(basename "$RECIPE_DIR")
DESCRIPTION="Sculptor backend: $RECIPE_NAME recipe"

if [ "$DRY_RUN" = true ]; then
    log "Dry run — ${#FILE_LIST[@]} files staged in $TEMP_DIR"
    log "Files that would be published:"
    for file in "${FILE_LIST[@]}"; do
        basename=$(basename "$file")
        size=$(wc -c < "$file" | tr -d ' ')
        log "  $basename ($size bytes)"
    done
    log ""
    log "Inspect with: ls -la $TEMP_DIR"
    exit 0
fi

log "Publishing ${#FILE_LIST[@]} files"

if [ -n "$UPDATE_GIST" ]; then
    # Update an existing gist. gh gist edit replaces files one at a time,
    # so we use the API directly for a clean update.
    log "Updating gist $UPDATE_GIST"
    for file in "${FILE_LIST[@]}"; do
        gh gist edit "$UPDATE_GIST" -a "$file"
    done
    log "Updated: https://gist.github.com/$UPDATE_GIST"
else
    # Create a new gist
    gh gist create $PUBLIC_FLAG --desc "$DESCRIPTION" "${FILE_LIST[@]}"
fi
