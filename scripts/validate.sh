#!/bin/bash

############################################################################
#
# Run this script to validate the workspace:
# 1. Format using black
# 2. Sort imports using isort
# 3. Lint using ruff
# 4. Type check using pyright
# Usage:
#   ./scripts/validate.sh
############################################################################

CURR_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname $CURR_DIR)"
source ${CURR_DIR}/_utils.sh

main() {
  print_heading "Validating workspace..."

  print_heading "Running: black ${REPO_ROOT}"
  black ${REPO_ROOT}

  print_heading "Running: ruff check ${REPO_ROOT}"
  ruff check ${REPO_ROOT} --fix

  print_heading "Running: isort ${REPO_ROOT}"
  isort ${REPO_ROOT}

  print_heading "Running: pyright ${REPO_ROOT}"
  export PYRIGHT_PYTHON_FORCE_VERSION=latest # ignore latest pyright version warning
  pyright ${REPO_ROOT}
}

main "$@"
