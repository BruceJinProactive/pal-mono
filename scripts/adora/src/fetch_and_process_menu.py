# python scripts/adora/fetch_and_process_menu.py UGDX4 pizza_guys
import argparse
import json
import os
import sys
import time
from typing import Optional

import requests
import yaml

from scripts.adora.src.adora_json_to_txt import generate_text_files_from_json
from scripts.adora.src.concatenate_menu_old import concatenate_menu_files


def get_bearer_token(
    client_id, client_secret, qa_store: bool = False, base_url: Optional[str] = None
):
    """Gets bearer token from Adora."""
    if base_url:
        token_url = f"https://{base_url}/connect/token"
    elif qa_store:
        token_url = "https://identityqa.adorapos.com/connect/token"
    else:
        token_url = "https://identity.adorapos.net/connect/token"

    payload = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }

    try:
        response = requests.post(token_url, data=payload)
        response.raise_for_status()  # Raises an exception for 4XX or 5XX status codes
        return response.json().get("access_token")
    except requests.exceptions.HTTPError as err:
        print(f"Error getting token: {err.response.status_code} {err.response.reason}")
        print(f"Response body: {err.response.text}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"An unexpected error occurred: {e}")
        return None


def download_menu(
    token, store_id, qa_store: bool = False, base_url: Optional[str] = None
):
    """Downloads menu for a given store ID."""
    if base_url:
        menu_url = f"https://{base_url}/api/v1/OrderHub/menu"
    elif qa_store:
        menu_url = "https://adora-qa-api-public.azurewebsites.net/api/v1/OrderHub/menu"
    else:
        menu_url = "https://public.api.adorapos.net/api/v1/OrderHub/menu"

    headers = {"Authorization": f"Bearer {token}"}
    params = {"sid": store_id}

    try:
        response = requests.get(menu_url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as err:
        print(
            f"Error downloading menu: {err.response.status_code} {err.response.reason}"
        )
        print(f"Response body: {err.response.text}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"An unexpected error occurred: {e}")
        return None


def main():
    """Main function to fetch and process menu."""
    # Include a breif description of the pipeline in the help message
    parser = argparse.ArgumentParser(
        description="Fetch and process Adora menu for a given store. This pipeline will: 1. Download the menu data from the Adora API, and save it to a json file, 2. Generate individual txt files for each menu item, 3. Concatenate the individual txt files into a single file that can be used for for use in the agent's raw_config knowledge content, 4. Upsert the menu items with IDs to Pinecone if the user wants to."
    )
    parser.add_argument(
        "--config",
        type=str,
        required=True,
        help="Path to the configuration YAML file.",
    )
    args = parser.parse_args()

    # Load config from YAML
    try:
        with open(args.config, "r") as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"Error: Configuration file not found at {args.config}")
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"Error parsing YAML file: {e}")
        sys.exit(1)

    store_id = config.get("store_id")  # type: ignore
    store_menu_dir = config.get("store_menu_dir")  # type: ignore
    use_qa_store = config.get("use_qa_store", False)  # type: ignore
    token_base_url = config.get("token_api_endpoint")  # type: ignore
    general_base_url = config.get("general_api_endpoint")  # type: ignore
    client_id = config.get("client_id")  # type: ignore
    client_secret = config.get("client_secret")  # type: ignore

    if not all([store_id, store_menu_dir, client_id, client_secret]):
        print(
            "Error: store_id, store_menu_dir, client_id, and client_secret must be set in the config file."
        )
        sys.exit(1)

    print("Getting bearer token...")
    token = get_bearer_token(
        client_id,
        client_secret,
        qa_store=use_qa_store,
        base_url=token_base_url,
    )
    if not token:
        sys.exit(1)
    print("Successfully got bearer token.")
    print(f"Token: {token[:5]}...{token[-5:]}")

    print(f"Downloading menu for store {store_id}...")
    menu_data = download_menu(
        token, store_id, qa_store=use_qa_store, base_url=general_base_url
    )
    if not menu_data:
        sys.exit(1)
    if menu_data.get("latitude", 0.0) == 0.0 and menu_data.get("longitude", 0.0) == 0.0:
        print(
            "There are some issues with the menu data, please check if the provided store id and key are correct."
        )
        print(f"Menu data: {menu_data}")
        sys.exit(0)

    print("Successfully downloaded menu data.")

    # Define paths
    menu_root_dir = os.path.join("menu", store_menu_dir)
    json_file_path = os.path.join(menu_root_dir, f"{store_id}.json")
    individual_files_dir_no_ids = os.path.join(
        menu_root_dir, f"output_{store_id}_no_ids"
    )
    individual_files_dir_with_ids = os.path.join(
        menu_root_dir, f"output_{store_id}_with_ids"
    )
    concatenated_file_path = os.path.join(menu_root_dir, "menu_formatted.txt")

    # Create directories if they don't exist
    os.makedirs(menu_root_dir, exist_ok=True)
    os.makedirs(individual_files_dir_no_ids, exist_ok=True)
    os.makedirs(individual_files_dir_with_ids, exist_ok=True)

    # Save original menu JSON
    with open(json_file_path, "w", encoding="utf-8") as f:
        json.dump(menu_data, f, indent=4)
    print(f"Saved menu JSON to {json_file_path}")

    # Generate individual txt files
    print(f"Generating individual menu files in {individual_files_dir_no_ids}...")
    generate_text_files_from_json(
        menu_data, individual_files_dir_no_ids, with_ids=False
    )
    print(f"Generating individual menu files in {individual_files_dir_with_ids}...")
    generate_text_files_from_json(
        menu_data, individual_files_dir_with_ids, with_ids=True
    )
    print("Finished generating individual files.")

    # Generate concatenated menu file
    print(f"Generating concatenated menu file at {concatenated_file_path}...")
    concatenate_menu_files(individual_files_dir_with_ids, concatenated_file_path)
    print("All done!")

    print("\n--- Pinecone Indexing ---")
    user_input = input(
        "Do you want to upsert the menu items with IDs to Pinecone? (yes/no): "
    )

    if user_input.lower() in ["yes", "y"]:
        namespace = input(
            "Please provide a Pinecone namespace with no timestamp (e.g., myrestaurant_menus), we will use the current date as the timestamp: "
        )
        if not namespace:
            print("Namespace cannot be empty. Aborting Pinecone indexing.")
            sys.exit(1)

        print(f"Starting Pinecone indexing with namespace: {namespace}")

        # Check for API keys
        if "PINECONE_API_KEY" not in os.environ or "COHERE_API_KEY" not in os.environ:
            print(
                "Error: PINECONE_API_KEY and COHERE_API_KEY environment variables must be set for indexing."
            )
            sys.exit(1)

        try:
            from llama_index.core import (
                Settings,
                SimpleDirectoryReader,
                StorageContext,
                VectorStoreIndex,
            )
            from llama_index.embeddings.cohere import CohereEmbedding
            from llama_index.vector_stores.pinecone import PineconeVectorStore
            from pinecone import Pinecone
        except ImportError:
            print("Error: Required libraries for Pinecone indexing are not installed.")
            print(
                "Please run: pip install llama-index-core llama-index-embeddings-cohere llama-index-vector-stores-pinecone pinecone-client"
            )
            sys.exit(1)

        # --- Indexing Logic ---
        pinecone_index_name = "agents"

        print(f"Loading documents from: {individual_files_dir_with_ids}")
        documents = SimpleDirectoryReader(individual_files_dir_with_ids).load_data()

        for doc in documents:
            doc.metadata["include_ids"] = "True"

        print("Initializing Pinecone and embeddings...")
        pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
        pinecone_index = pc.Index(pinecone_index_name)
        namespace += "_" + time.strftime("%Y-%m-%d")
        print(f"namespace: {namespace}")
        vector_store = PineconeVectorStore(
            pinecone_index=pinecone_index, namespace=namespace
        )

        Settings.embed_model = CohereEmbedding(
            api_key=os.environ["COHERE_API_KEY"],
            model_name="embed-english-v3.0",
        )

        storage_context = StorageContext.from_defaults(vector_store=vector_store)

        print("Indexing documents to Pinecone... This may take a moment.")
        _ = VectorStoreIndex.from_documents(
            documents,
            storage_context=storage_context,
            embed_model=Settings.embed_model,
        )
        print("Successfully indexed documents to Pinecone.")

    else:
        print("Skipping Pinecone indexing.")


if __name__ == "__main__":
    main()
