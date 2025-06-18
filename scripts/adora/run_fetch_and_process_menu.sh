#!/bin/bash

# This script is a wrapper to run the fetch_and_process_menu.py python script.
# It provides an example of how to call the script with all possible arguments.
#
# Usage:
# 1. Fill in the configuration variables in scripts/adora/config.yml.
# 2. Make the script executable: chmod +x scripts/adora/run_fetch_and_process_menu.sh
# 3. Run the script: ./scripts/adora/run_fetch_and_process_menu.sh

# --- Configuration Loading ---
CONFIG_FILE="scripts/adora/config.yml"
TEMPLATE_FILE="scripts/adora/config.yml.template"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "Error: Configuration file not found at $CONFIG_FILE"
    echo "Please create it by copying the template: cp $TEMPLATE_FILE $CONFIG_FILE"
    exit 1
fi

# --- Execution ---
echo "Running python script with config file: $CONFIG_FILE"
python scripts/adora/src/fetch_and_process_menu.py --config "$CONFIG_FILE"

echo "Script finished." 