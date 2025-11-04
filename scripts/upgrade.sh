#!/bin/bash

############################################################################
#
# Upgrade python dependencies using uv.
# Usage:
# 1. Update lock file with any new dependencies added to pyproject.toml:
#     ./scripts/upgrade.sh
# 2. Upgrade all python modules to latest compatible version:
#     ./scripts/upgrade.sh all
############################################################################

CURR_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "${CURR_DIR}")"

source "${CURR_DIR}/_utils.sh"

main() {
  UPGRADE_ALL=0

  if [[ "$#" -eq 1 ]] && [[ "$1" = "all" ]]; then
    UPGRADE_ALL=1
  fi

  print_heading "Upgrading dependencies for workspace: ${REPO_ROOT}"

  cd "${REPO_ROOT}" || exit
  if [[ $UPGRADE_ALL -eq 1 ]]; then
    print_heading "Upgrading all dependencies to latest version"
    uv lock --upgrade
    print_horizontal_line
  else
    print_heading "Updating uv.lock"
    uv lock
    print_horizontal_line
  fi
}

main "$@"
