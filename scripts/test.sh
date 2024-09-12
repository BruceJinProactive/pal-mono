#!/bin/bash

############################################################################
#
# Run this script to run pytest tests
# Usage:
#   ./scripts/test.sh
############################################################################

CURR_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source ${CURR_DIR}/_utils.sh

main() {
  print_heading "Running pytest..."
  docker exec -it pal-mono-api pytest
}

main "$@"
