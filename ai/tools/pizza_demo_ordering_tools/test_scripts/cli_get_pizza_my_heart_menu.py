import json
import os
from datetime import datetime

from ai.tools.pizza_demo_ordering_tools.adapters.integrations.pos.adora_pos_apis import (
    AdoraApiKeyAndSecret,
    _get_adora_pos_auth_token,
    _get_adora_pos_store_menu,
)

# Get the path to the secrets file
yaml_file_path = os.path.join("workspace", "secrets", "dev_app_secrets.yml")

# Initialize the api_key variable
api_key = None
api_secret = None

# Find the ADORA_POS_API_KEY and ADORA_POS_API_SECRET
with open(yaml_file_path, "r") as file:
    for line in file:
        # Strip any leading/trailing whitespace
        line = line.strip()
        # Check if the line contains the key
        if line.startswith("ADORA_POS_API_KEY:"):
            # Extract the value after the colon and any whitespace
            api_key = line.split(":", 1)[1].strip()[1:-1]
        elif line.startswith("ADORA_POS_API_SECRET:"):
            # Extract the value after the colon and any whitespace
            api_secret = line.split(":", 1)[1].strip()[1:-1]

if api_key and api_secret:
    adora_key_and_secret = AdoraApiKeyAndSecret(
        api_key=api_key,
        api_secret=api_secret,
    )

    store_id = "9WHCV"  # NOTE: this is the PizzaMyHeart Test Store ID
    bearer_token = _get_adora_pos_auth_token(adora_key_and_secret)

    menu_json_string = _get_adora_pos_store_menu(
        store_id, bearer_token, log_request=True
    )

    menu = json.loads(menu_json_string)

    # Write the menu to file with current date
    current_date = datetime.now()
    formatted_date = current_date.strftime("%Y%m%d")
    file_path = f"{formatted_date}_adora_pizza_my_heart_menu.json"

    try:
        with open(file_path, "w") as file:
            json.dump(menu, file, indent=4)
        print(f"Menu successfully written to {file_path}")
    except Exception as e:
        print(f"An error occurred while writing the menu to file: {e}")

else:
    print("missing ADORA_POS_API_KEY or ADORA_POS_API_SECRET in environment")
