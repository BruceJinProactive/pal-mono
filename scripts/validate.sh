#!/bin/bash

############################################################################
#
# Run this script to validate the workspace:
# 1. Format using black
# 2. Sort imports using isort
# 3. Lint using ruff
# 4. Type check using pyright
# 5. Sort pyproject.toml with toml-sort
# Usage:
#   ./scripts/validate.sh
############################################################################

set -e          # Exit immediately if a command exits with a non-zero status
set -u          # Treat unset variables as an error
set -o pipefail # Fail if any command in a pipeline fails

CURR_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "${CURR_DIR}")"

source "${CURR_DIR}/_utils.sh"

# Check if --check flag is provided
CHECK_MODE=false
# Detect --check anywhere in the argument list
if [[ " $* " == *" --check "* ]]; then
  CHECK_MODE=true
fi
main() {
  print_heading "Validating workspace..."

  if [[ "$CHECK_MODE" == "true" ]]; then
    print_heading "Running: uv run black ${REPO_ROOT} --check --diff"
    uv run black "${REPO_ROOT}" --check --diff

    print_heading "Running: uv run ruff check ${REPO_ROOT} --diff"
    uv run ruff check "${REPO_ROOT}" --diff

    print_heading "Running: uv run isort ${REPO_ROOT} --check-only"
    uv run isort "${REPO_ROOT}" --check-only

    print_heading "Running: uv run pyright ${REPO_ROOT}"
    export PYRIGHT_PYTHON_FORCE_VERSION=latest # ignore latest pyright version warning
    uv run pyright "${REPO_ROOT}"

    print_heading "Running: uv run toml-sort ${REPO_ROOT}/pyproject.toml --sort-inline-arrays --check"
    uv run toml-sort "${REPO_ROOT}/pyproject.toml" --sort-inline-arrays --check
  else
    print_heading "Running: uv run black ${REPO_ROOT}"
    uv run black "${REPO_ROOT}"

    print_heading "Running: uv run ruff check ${REPO_ROOT} --fix"
    uv run ruff check "${REPO_ROOT}" --fix

    print_heading "Running: uv run isort ${REPO_ROOT}"
    uv run isort "${REPO_ROOT}"

    print_heading "Running: uv run pyright ${REPO_ROOT}"
    export PYRIGHT_PYTHON_FORCE_VERSION=latest # ignore latest pyright version warning
    uv run pyright "${REPO_ROOT}"

    print_heading "Running: uv run toml-sort ${REPO_ROOT}/pyproject.toml --sort-inline-arrays --in-place"
    uv run toml-sort "${REPO_ROOT}/pyproject.toml" --sort-inline-arrays --in-place
  fi
}

main "$@"
