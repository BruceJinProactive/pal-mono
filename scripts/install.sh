#!/bin/bash

############################################################################
#
# Install python dependencies. Skips work when nothing has changed.
# Usage:
#     ./scripts/install.sh          # Smart install (skips if up-to-date)
#     ./scripts/install.sh --force  # Force reinstall
############################################################################

CURR_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "${CURR_DIR}")"
STAMP_FILE="${REPO_ROOT}/.install-stamp"

source "${CURR_DIR}/_utils.sh"

compute_fingerprint() {
  # Hash dependency-related files to detect when install is needed
  local files=("${REPO_ROOT}/pyproject.toml" "${REPO_ROOT}/uv.lock" "${REPO_ROOT}/.gitmodules")
  local hash_input=""
  for f in "${files[@]}"; do
    if [ -f "$f" ]; then
      hash_input+="$(cat "$f")"
    fi
  done
  echo -n "$hash_input" | shasum -a 256 | cut -d' ' -f1
}

is_up_to_date() {
  [ -f "${STAMP_FILE}" ] && [ "$(cat "${STAMP_FILE}")" = "$(compute_fingerprint)" ]
}

save_stamp() {
  compute_fingerprint > "${STAMP_FILE}"
}

setup_git_hooks() {
  # Point git to tracked hooks so they work across clones and worktrees
  git -C "${REPO_ROOT}" config core.hooksPath scripts/githooks
}

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
  local force=false
  if [ "${1:-}" = "--force" ]; then
    force=true
  fi

  if [ "$force" = false ] && is_up_to_date; then
    print_status "Dependencies up-to-date, skipping install (use --force to override)"
    return 0
  fi

  print_heading "Installing workspace: ${REPO_ROOT}"

  setup_git_hooks
  init_submodules

  # Install all dependencies including dev dependencies using uv
  # uv sync reads pyproject.toml and uv.lock to install exact versions
  # --all-extras: Install all optional dependencies including dev extras
  print_heading "Installing dependencies with uv"
  uv sync --all-extras

  save_stamp
  print_heading "Installation complete"
}

main "$@"
