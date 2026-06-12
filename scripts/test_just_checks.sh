#!/usr/bin/env bash
# Test script to verify that just check commands catch the issues they should catch
#
# Usage: ./scripts/test_just_checks.sh
#
# This script creates temporary test files to verify each check command works correctly,
# then cleans them up. It does not leave any artifacts in the repo.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

# Track results
PASSED=0
FAILED=0

test_passed() {
    echo -e "${GREEN}✓ PASSED${NC}: $1"
    PASSED=$((PASSED + 1))
}

test_failed() {
    echo -e "${RED}✗ FAILED${NC}: $1"
    FAILED=$((FAILED + 1))
}

# Cleanup function to ensure test files are removed
cleanup() {
    git reset sculptor/test_file.txt sculptor/test_file.yaml sculptor/test_script.sh >/dev/null 2>&1 || true
    rm -f sculptor/test_file.txt sculptor/test_file.yaml sculptor/test_script.sh
}
trap cleanup EXIT

echo "========================================"
echo "Testing just check commands"
echo "========================================"

#
# check-file-hygiene tests
#
echo ""
echo "=== Test 1: check-file-hygiene catches trailing whitespace ==="
echo "hello world   " > sculptor/test_file.txt
git add sculptor/test_file.txt
OUTPUT=$(just check-file-hygiene 2>&1 || true)
if echo "$OUTPUT" | grep -q "trailing whitespace"; then
    test_passed "Detected trailing whitespace"
else
    test_failed "Should detect trailing whitespace"
fi
git reset -q sculptor/test_file.txt 2>/dev/null || true
rm -f sculptor/test_file.txt

echo ""
echo "=== Test 2: check-file-hygiene catches missing trailing newline ==="
printf "hello world" > sculptor/test_file.txt
git add sculptor/test_file.txt
OUTPUT=$(just check-file-hygiene 2>&1 || true)
if echo "$OUTPUT" | grep -q "missing trailing newline"; then
    test_passed "Detected missing trailing newline"
else
    test_failed "Should detect missing trailing newline"
fi
git reset -q sculptor/test_file.txt 2>/dev/null || true
rm -f sculptor/test_file.txt

echo ""
echo "=== Test 3: check-file-hygiene catches multiple trailing newlines ==="
printf "hello world\n\n\n" > sculptor/test_file.txt
git add sculptor/test_file.txt
OUTPUT=$(just check-file-hygiene 2>&1 || true)
if echo "$OUTPUT" | grep -q "multiple trailing newlines"; then
    test_passed "Detected multiple trailing newlines"
else
    test_failed "Should detect multiple trailing newlines"
fi
git reset -q sculptor/test_file.txt 2>/dev/null || true
rm -f sculptor/test_file.txt

echo ""
echo "=== Test 4: check-file-hygiene passes on clean file ==="
echo "hello world" > sculptor/test_file.txt
git add sculptor/test_file.txt
OUTPUT=$(just check-file-hygiene 2>&1 || true)
if echo "$OUTPUT" | grep -q "All files pass hygiene checks"; then
    test_passed "Passes on clean file"
else
    test_failed "Should pass on clean file"
fi
git reset -q sculptor/test_file.txt 2>/dev/null || true
rm -f sculptor/test_file.txt

#
# check-yaml tests
#
echo ""
echo "=== Test 5: check-yaml catches invalid YAML ==="
echo "invalid: yaml: syntax: [unclosed" > sculptor/test_file.yaml
git add sculptor/test_file.yaml
OUTPUT=$(just check-yaml 2>&1 || true)
if echo "$OUTPUT" | grep -q "Invalid YAML"; then
    test_passed "Detected invalid YAML"
else
    test_failed "Should detect invalid YAML"
fi
git reset -q sculptor/test_file.yaml 2>/dev/null || true
rm -f sculptor/test_file.yaml

echo ""
echo "=== Test 6: check-yaml passes on valid YAML ==="
cat > sculptor/test_file.yaml << 'EOF'
name: test
version: 1.0
items:
  - one
  - two
EOF
git add sculptor/test_file.yaml
OUTPUT=$(just check-yaml 2>&1 || true)
if echo "$OUTPUT" | grep -q "All YAML files are valid"; then
    test_passed "Passes on valid YAML"
else
    test_failed "Should pass on valid YAML"
fi
git reset -q sculptor/test_file.yaml 2>/dev/null || true
rm -f sculptor/test_file.yaml

#
# check-large-files tests
#
echo ""
echo "=== Test 7: check-large-files catches large staged files ==="
# Create a 600KB file (over the 500KB default)
dd if=/dev/zero of=sculptor/test_file.txt bs=1024 count=600 2>/dev/null
git add sculptor/test_file.txt
OUTPUT=$(just check-large-files 2>&1 || true)
if echo "$OUTPUT" | grep -q "Large files detected"; then
    test_passed "Detected large staged file"
else
    test_failed "Should detect large staged file"
fi
git reset -q sculptor/test_file.txt 2>/dev/null || true
rm -f sculptor/test_file.txt

echo ""
echo "=== Test 8: check-large-files passes when no large files staged ==="
echo "small content" > sculptor/test_file.txt
git add sculptor/test_file.txt
OUTPUT=$(just check-large-files 2>&1 || true)
if echo "$OUTPUT" | grep -q "No large staged files found"; then
    test_passed "Passes with small staged file"
else
    test_failed "Should pass with small staged file"
fi
git reset -q sculptor/test_file.txt 2>/dev/null || true
rm -f sculptor/test_file.txt

#
# check-shellcheck tests
#
echo ""
echo "=== Test 9: check-shellcheck catches warning-level issues ==="
# SC2034 (warning): VAR appears unused
cat > sculptor/test_script.sh << 'SCRIPT'
#!/bin/bash
UNUSED_VAR="hello"
SCRIPT
git add sculptor/test_script.sh
OUTPUT=$(just check-shellcheck 2>&1 || true)
if echo "$OUTPUT" | grep -qE "SC2034|appears unused"; then
    test_passed "Detected shellcheck warning (unused variable)"
else
    test_failed "Should detect shellcheck warning"
fi
git reset -q sculptor/test_script.sh 2>/dev/null || true
rm -f sculptor/test_script.sh

echo ""
echo "=== Test 10: check-shellcheck passes on clean scripts ==="
OUTPUT=$(just check-shellcheck 2>&1 || true)
if echo "$OUTPUT" | grep -q "Shellcheck passed"; then
    test_passed "Passes on clean shell scripts"
else
    test_failed "Should pass on clean shell scripts"
fi

#
# check-uv-lock tests
#
echo ""
echo "=== Test 11: check-uv-lock passes when lock files are up to date ==="
OUTPUT=$(just check-uv-lock 2>&1 || true)
if echo "$OUTPUT" | grep -q "All uv.lock files are up to date"; then
    test_passed "Passes when lock files are current"
else
    test_failed "Should pass when lock files are current"
fi

#
# Summary
#
echo ""
echo "========================================"
echo "Results Summary"
echo "========================================"
echo -e "${GREEN}Passed${NC}: $PASSED"
echo -e "${RED}Failed${NC}: $FAILED"
echo ""

if [ "$FAILED" -eq 0 ]; then
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed!${NC}"
    exit 1
fi
