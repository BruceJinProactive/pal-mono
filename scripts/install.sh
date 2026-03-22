#!/bin/bash

############################################################################
#
# Install python dependencies. Run this inside a virtual env.
# Usage:
# 1. Create + activate virtual env using:
#     python3 -m venv aienv
#     source aienv/bin/activate
# 2. Install workspace and dependencies:
#     ./scripts/install.sh
############################################################################

CURR_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "${CURR_DIR}")"

source "${CURR_DIR}/_utils.sh"

init_submodules() {
  print_heading "Initializing submodules"

  # Initialize pal-skills submodule with sparse checkout
  # Only materializes .claude/skills/ from the repo (skips .github/, docs/, etc.)
  git -C "${REPO_ROOT}" submodule update --init .pal-skills

  if [ -d "${REPO_ROOT}/.pal-skills" ]; then
    git -C "${REPO_ROOT}/.pal-skills" sparse-checkout init --cone
    git -C "${REPO_ROOT}/.pal-skills" sparse-checkout set .claude/skills
  fi
}

main() {
  print_heading "Installing workspace: ${REPO_ROOT}"

  init_submodules

  # Install all dependencies including dev dependencies using uv
  # uv sync reads pyproject.toml and uv.lock to install exact versions
  # --all-extras: Install all optional dependencies including dev extras
  print_heading "Installing dependencies with uv"
  uv sync --all-extras

  print_heading "Installation complete"
}

main "$@"
