#!/bin/bash

############################################################################
#
# Build and start Docker containers with automatic GITHUB_TOKEN loading
# Usage:
#   ./scripts/docker_build.sh          # Build and start in background
#   ./scripts/docker_build.sh --logs   # Build, start, and show logs
#
############################################################################

CURR_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "${CURR_DIR}")"

source "${CURR_DIR}/_utils.sh"

main() {
  cd "${REPO_ROOT}" || exit 1

  print_heading "Docker Build with Private Dependencies"

  # Check if local.env exists
  if [ ! -f local.env ]; then
    echo "❌ ERROR: local.env file not found"
    echo ""
    echo "Please create local.env from the example:"
    echo "  cp local.env.example local.env"
    echo ""
    echo "Then edit local.env and add your GITHUB_TOKEN"
    exit 1
  fi

  # Load GITHUB_TOKEN from local.env
  print_status "Loading GITHUB_TOKEN from local.env..."
  set -a  # Enable automatic export
  source local.env
  set +a  # Disable automatic export

  # Check if token was loaded
  if [ -z "$GITHUB_TOKEN" ]; then
    echo "❌ ERROR: GITHUB_TOKEN not found in local.env"
    echo ""
    echo "Please add GITHUB_TOKEN to your local.env file:"
    echo "  GITHUB_TOKEN=ghp_your_token_here"
    echo ""
    echo "Contact your team lead if you need a token"
    exit 1
  fi

  print_status "✅ GITHUB_TOKEN loaded successfully"

  # Enable Docker BuildKit for secrets support
  export COMPOSE_DOCKER_CLI_BUILD=1
  export DOCKER_BUILDKIT=1
  print_status "Docker BuildKit enabled"

  # Build and start containers
  print_heading "Building Docker images..."
  docker-compose build

  if [ $? -ne 0 ]; then
    echo "❌ ERROR: Docker build failed"
    exit 1
  fi

  print_heading "Starting containers..."

  # Check if user wants logs
  if [ "$1" = "--logs" ]; then
    docker-compose up
    start_status=$?
  else
    docker-compose up -d
    start_status=$?
  fi

  if [ ${start_status} -ne 0 ]; then
    echo "❌ ERROR: Docker container startup failed"
    exit ${start_status}
  fi

  if [ "$1" != "--logs" ]; then
    print_heading "✅ Build complete! Containers running in background"
    echo ""
    echo "View logs with:"
    echo "  docker-compose logs -f api"
    echo ""
    echo "Stop containers with:"
    echo "  docker-compose down"
  fi
}

main "$@"
