# Adora Menu Fetch & Process Pipeline

This document outlines the steps for using the Adora menu fetching and processing pipeline. The pipeline downloads menu data from the Adora API, processes it into structured text files, and provides an option to index the data into a Pinecone vector store.

## Configuration

The pipeline is configured using a YAML file.

1.  **Create `config.yml`**: This project uses a `config.yml` file for all settings. A template is provided. If `config.yml` does not exist in `scripts/adora/`, create it by copying the template:
    ```bash
    cp scripts/adora/config.yml.template scripts/adora/config.yml
    ```

2.  **Edit `config.yml`**: Open `scripts/adora/config.yml` and fill in the required values:
    *   `store_id`: The unique identifier for the Adora store.
    *   `store_menu_dir`: The name of the directory where the menu files will be saved (e.g., `my_restaurant`). This will be created inside the top-level `menu/` directory.
    *   `use_qa_store`: (Optional) Set to `true` to use Adora's QA environment. Leave empty or set to `false` for production.
    *   `token_api_endpoint`: (Optional) The base URL for the Adora token endpoint. Leave empty if you are using either Adora's QA or production environment.
    *   `general_api_endpoint`: (Optional) The base URL for the Adora menu API endpoint. Leave empty if you are using either Adora's QA or production environment.
    *   `client_id`: Your Adora client ID.
    *   `client_secret`: Your Adora client secret.

## Execution

1.  Access the Docker environment:
    ```bash
    docker exec -it PAL_MONO_API_CONTAINER_ID /bin/bash
    ```
2.  Make the execution script runnable:
    ```bash
    chmod +x scripts/adora/run_fetch_and_process_menu.sh
    ```
3.  Run the script:
    ```bash
    ./scripts/adora/run_fetch_and_process_menu.sh
    ```

## What to Expect

The script will perform the following actions:
1.  Read the configuration from `scripts/adora/config.yml`.
2.  Fetch the menu from the Adora API.
3.  Create a directory at `menu/<store_menu_dir>/`.
4.  Save the raw JSON menu data in this new directory.
5.  Generate individual `.txt` files for each menu item in two subdirectories: `output_<store_id>_with_ids` and `output_<store_id>_no_ids`.
6.  Create a concatenated `menu_formatted.txt` file containing the entire menu.
7.  Finally, it will ask if you want to index the menu items to Pinecone. If you agree, it will prompt for a namespace and then begin the upsert process. 