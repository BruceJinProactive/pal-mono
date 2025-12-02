"""
Toast menu processing orchestrator for knowledge base integration.

This module provides the main orchestration class that coordinates all
Toast menu processing operations from raw menu data to vector indexing.

Key responsibilities:
- Coordinate the complete menu processing pipeline
- Manage the workflow from JSON data to knowledge base
- Handle error management and debug logging
- Provide the main interface for knowledge service integration

Processing pipeline:
1. Accept raw Toast menu JSON data
2. Process and format menu items into readable text
3. Index processed items into Pinecone vector store
4. Return processing results and metadata

Usage:
    processor = ToastMenuProcessor(debug=True)
    result = processor.process_and_index_menu(
        menu_json=raw_menu_data,
        pinecone_index_name="toast-menu",
        pinecone_namespace="store_123",
        ...
    )

Dependencies:
- _formatter: Text generation
- _indexer: Vector store operations
- _utils: Toast-specific utilities
"""

import datetime
import os
from typing import Any, Dict, List, Optional

from tools.toast_tool._apis import get_toast_access_token
from tools.toast_tool.classes import ToastAccessToken
from utils.log import logger

from ._client import download_menu, get_dining_options, get_menu_metadata
from ._indexer import index_dining_options_to_pinecone, index_to_pinecone
from ._utils import _sanitize_filename, parse_menu


class ToastMenuProcessor:
    """Processes Toast menu data and indexes it to Pinecone.

    Controls the complete menu processing pipeline from JSON parsing
    to vector store indexing.
    """

    def __init__(self, debug: bool = False):
        """Initialize processor.

        Args:
            debug: Whether to enable debug logging
        """
        self.debug = debug

    def process_and_index_menu(
        self,
        menu_json: Dict[str, Any],
        pinecone_index_name: str,
        pinecone_namespace: str,
        store_id: str,
        save_debug_files: bool = False,
        debug_output_dir: Optional[str] = None,
        selected_menus: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Process Toast menu and index it to Pinecone.

        Args:
            menu_json: Raw Toast menu JSON data
            pinecone_index_name: Pinecone index name
            pinecone_namespace: Pinecone namespace for menu data
            store_id: Store ID for metadata
            save_debug_files: Whether to save debug files to disk
            debug_output_dir: Directory to save debug files (optional)
            selected_menus: Optional list of menu names to process

        Returns:
            dict: Processing results with menu data and indexing information
        """
        try:
            logger.debug(
                "[toast._implementation.process_and_index_menu] Starting Toast menu processing..."
            )

            # Step 1: Parse menu JSON using migrated logic
            individual_items, system_prompt_menu, infinite_loop_items = parse_menu(
                menu_json, selected_menus
            )

            logger.debug(
                "[toast._implementation.process_and_index_menu] Successfully parsed menu"
            )
            logger.debug(
                "[toast._implementation.process_and_index_menu] Menu contains %s items",
                len(individual_items),
            )
            if infinite_loop_items:
                logger.debug(
                    "[toast._implementation.process_and_index_menu] Found %s items with infinite loops (excluded from indexing)",
                    len(infinite_loop_items),
                )

            # Step 2: Save debug files if requested (like dummy_menu.py)
            if save_debug_files:
                self._save_debug_files(
                    individual_items,
                    system_prompt_menu,
                    infinite_loop_items,
                    debug_output_dir,
                )

            # Step 3: Index to Pinecone
            document_count = index_to_pinecone(
                individual_items=individual_items,
                pinecone_index_name=pinecone_index_name,
                pinecone_namespace=pinecone_namespace,
                debug=self.debug,
            )

            logger.debug(
                "[toast._implementation.process_and_index_menu] Processing complete. Total items: %s",
                len(individual_items),
            )
            logger.debug(
                "[toast._implementation.process_and_index_menu] Indexed %s documents to namespace: %s",
                document_count,
                pinecone_namespace,
            )

            return {
                "system_prompt_menu": system_prompt_menu,
                "pinecone_namespace": pinecone_namespace,
                "pinecone_index_name": pinecone_index_name,
                "processed_items": document_count,
                "store_id": store_id,
                "infinite_loop_items_count": len(infinite_loop_items),
            }

        except Exception as e:
            logger.error(
                f"[toast._implementation.process_and_index_menu] Error processing Toast menu: {e}"
            )
            raise

    def _save_debug_files(
        self,
        individual_items: List[Dict[str, str]],
        system_prompt_menu: str,
        infinite_loop_items: List[Dict[str, str]],
        debug_output_dir: Optional[str] = None,
        dining_options_json: Optional[str] = None,
    ) -> None:
        """Save debug files to disk (similar to dummy_menu.py logic).

        Args:
            individual_items: List of menu item dictionaries
            system_prompt_menu: System prompt menu text
            infinite_loop_items: Items with infinite loops
            debug_output_dir: Directory to save files (optional)
            dining_options_json: Raw JSON string of dining options (optional)
        """
        # Use provided directory or create default one
        if debug_output_dir is None:
            dirname = f"toast_menu_debug_{datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
        else:
            dirname = debug_output_dir

        # Create directories
        os.makedirs(dirname, exist_ok=True)
        os.makedirs(os.path.join(dirname, "menu_items"), exist_ok=True)

        # Save each item in a separate file
        for menu_item in individual_items:
            for filename, information in menu_item.items():
                # Sanitize the filename to avoid filesystem issues
                safe_filename = _sanitize_filename(filename)
                with open(
                    os.path.join(dirname, "menu_items", f"{safe_filename}.txt"),
                    "w",
                    encoding="utf-8",
                ) as f:
                    f.write(information)

        # Save system prompt menu to a file
        with open(
            os.path.join(dirname, "system_prompt_menu.md"), "w", encoding="utf-8"
        ) as f:
            f.write(system_prompt_menu)

        # Save dining options if provided
        if dining_options_json:
            dining_options_dirname = os.path.join(dirname, "dining_options")
            os.makedirs(dining_options_dirname, exist_ok=True)

            with open(
                os.path.join(dining_options_dirname, "dining_options.txt"),
                "w",
                encoding="utf-8",
            ) as f:
                f.write(dining_options_json)

            logger.debug(
                "[toast._implementation._save_debug_files] Saved dining options to: %s",
                dining_options_dirname,
            )

        # Save infinite loop items to separate directory
        if infinite_loop_items:
            infinite_loop_dirname = os.path.join(dirname, "infinite_loops")
            os.makedirs(infinite_loop_dirname, exist_ok=True)

            logger.debug(
                "[toast._implementation._save_debug_files] Saving %s infinite loop items to: %s",
                len(infinite_loop_items),
                infinite_loop_dirname,
            )

            for menu_item in infinite_loop_items:
                for filename, information in menu_item.items():
                    # Sanitize the filename to avoid filesystem issues
                    safe_filename = _sanitize_filename(filename)
                    with open(
                        os.path.join(infinite_loop_dirname, f"{safe_filename}.txt"),
                        "w",
                        encoding="utf-8",
                    ) as f:
                        f.write(information)
        else:
            logger.debug(
                "[toast._implementation._save_debug_files] No infinite loop items found"
            )

        logger.debug(
            "[toast._implementation._save_debug_files] Debug files saved to: %s",
            dirname,
        )

    def _should_update_menu(
        self, menu_last_updated: str, metadata: Dict[str, Any]
    ) -> bool:
        """Determine if menu should be updated based on timestamps.

        Args:
            menu_last_updated: When we last processed the menu (from our database)
            metadata: Menu metadata from Toast API containing their lastUpdated timestamp

        Returns:
            bool: True if menu should be updated (Toast has newer data), False otherwise
        """
        from_api_menu_last_updated = metadata.get("lastUpdated")

        if from_api_menu_last_updated is None:
            logger.debug(
                "[toast._implementation._should_update_menu] No previous menu timestamp found. Menu will be updated."
            )
            return True
        # Only check if the two timestamps is the same, if not, then update
        should_update = menu_last_updated != from_api_menu_last_updated

        action = "will be updated" if should_update else "is up to date"
        logger.debug(
            "[toast._implementation._should_update_menu] Menu %s based on timestamp comparison.",
            action,
        )
        return should_update

    def _authenticate_with_toast(
        self,
        client_id: str,
        client_secret: str,
        token_api_endpoint: Optional[str] = None,
    ) -> ToastAccessToken:
        """Authenticate with Toast API and return access token.

        Args:
            client_id: Toast API client ID
            client_secret: Toast API client secret
            token_api_endpoint: Optional custom token API endpoint

        Returns:
            ToastAccessToken: Access token

        Raises:
            RuntimeError: If authentication fails
        """
        logger.debug(
            "[toast._implementation._authenticate_with_toast] Authenticating with Toast API..."
        )

        access_token = get_toast_access_token(
            client_id=client_id,
            client_secret=client_secret,
            token_api_endpoint=token_api_endpoint,
        )

        if not access_token:
            raise RuntimeError("Failed to obtain Toast access token")

        logger.debug(
            "[toast._implementation._authenticate_with_toast] Successfully authenticated with Toast API"
        )
        return access_token

    def _get_menu_metadata(
        self,
        bearer_token: ToastAccessToken,
        restaurant_external_id: str,
        general_api_endpoint: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get menu metadata from Toast API.

        Args:
            bearer_token: Bearer token for API authentication
            restaurant_external_id: Restaurant external ID
            general_api_endpoint: Optional custom API endpoint

        Returns:
            dict: Menu metadata
        """
        logger.debug(
            "[toast._implementation._get_menu_metadata] Getting menu metadata..."
        )

        metadata = get_menu_metadata(
            bearer_token=bearer_token,
            restaurant_external_id=restaurant_external_id,
            general_api_endpoint=general_api_endpoint,
        )

        logger.debug(
            "[toast._implementation._get_menu_metadata] Retrieved metadata for restaurant %s",
            metadata.get("restaurantGuid"),
        )
        return metadata

    def _download_and_process_menu(
        self,
        bearer_token: ToastAccessToken,
        restaurant_external_id: str,
        general_api_endpoint: Optional[str] = None,
        selected_menus: Optional[List[str]] = None,
    ) -> tuple[list[Dict[str, str]], str, list[Dict[str, str]]]:
        """Download menu data from Toast API and process it.

        Args:
            bearer_token: Bearer token for API authentication
            restaurant_external_id: Restaurant external ID
            general_api_endpoint: Optional custom API endpoint
            selected_menus: Optional list of menu names to process

        Returns:
            tuple: (individual_items, system_prompt_menu, infinite_loop_items)
        """
        logger.debug(
            "[toast._implementation._download_and_process_menu] Downloading menu data..."
        )

        menu_json = download_menu(
            bearer_token=bearer_token,
            restaurant_external_id=restaurant_external_id,
            general_api_endpoint=general_api_endpoint,
        )

        logger.debug(
            "[toast._implementation._download_and_process_menu] Successfully downloaded menu with %s menus",
            len(menu_json.get("menus", [])),
        )

        # Process menu using the existing logic
        individual_items, system_prompt_menu, infinite_loop_items = parse_menu(
            menu_json, selected_menus
        )

        logger.debug(
            "[toast._implementation._download_and_process_menu] Parsed menu: %s items, %s infinite loop items",
            len(individual_items),
            len(infinite_loop_items),
        )

        return individual_items, system_prompt_menu, infinite_loop_items

    def _index_menu_to_pinecone(
        self,
        individual_items: list[Dict[str, str]],
        pinecone_index_name: str,
        pinecone_namespace: str,
    ) -> int:
        """Index processed menu items to Pinecone.

        Args:
            individual_items: List of processed menu items
            pinecone_index_name: Pinecone index name
            pinecone_namespace: Pinecone namespace

        Returns:
            int: Number of documents indexed
        """
        document_count = index_to_pinecone(
            individual_items=individual_items,
            pinecone_index_name=pinecone_index_name,
            pinecone_namespace=pinecone_namespace,
            debug=self.debug,
        )

        logger.debug(
            "[toast._implementation._index_menu_to_pinecone] Successfully indexed %s documents to Pinecone",
            document_count,
        )
        return document_count

    def _get_and_index_dining_options(
        self,
        bearer_token: ToastAccessToken,
        store_id: str,
        pinecone_index_name: str,
        pinecone_namespace: str,
        general_api_endpoint: Optional[str] = None,
    ) -> tuple[int, str]:
        """Get dining options from Toast API and index to Pinecone.

        Args:
            bearer_token: Bearer token for API authentication
            store_id: Store ID
            pinecone_index_name: Pinecone index name
            pinecone_namespace: Pinecone namespace
            general_api_endpoint: Optional custom API endpoint

        Returns:
            tuple: (Number of documents indexed, raw JSON string)
        """
        logger.debug(
            "[toast._implementation._get_and_index_dining_options] Getting dining options..."
        )

        # Get raw JSON string from API
        dining_options_json = get_dining_options(
            bearer_token=bearer_token,
            store_id=store_id,
            general_api_endpoint=general_api_endpoint,
        )

        # Index to Pinecone
        document_count = index_dining_options_to_pinecone(
            dining_options_json=dining_options_json,
            pinecone_index_name=pinecone_index_name,
            pinecone_namespace=pinecone_namespace,
            store_id=store_id,
            debug=self.debug,
        )

        logger.debug(
            "[toast._implementation._get_and_index_dining_options] Successfully indexed dining options to Pinecone"
        )
        return document_count, dining_options_json

    def process_and_index_menu_from_api(
        self,
        client_id: str,
        client_secret: str,
        restaurant_external_id: str,
        pinecone_index_name: str,
        pinecone_namespace: str,
        token_api_endpoint: Optional[str] = None,
        general_api_endpoint: Optional[str] = None,
        save_debug_files: bool = False,
        debug_output_dir: Optional[str] = None,
        menu_last_updated: Optional[str] = None,
        selected_menus: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Process Toast menu from API and index it to Pinecone.

        This method handles the complete workflow:
        1. Authenticate with Toast API
        2. Get menu metadata
        3. Download menu data
        4. Process and format menu items
        5. Index to Pinecone

        Args:
            client_id: Toast API client ID
            client_secret: Toast API client secret
            restaurant_external_id: Restaurant external ID for Toast-Restaurant-External-ID header
            pinecone_index_name: Pinecone index name
            pinecone_namespace: Pinecone namespace for menu data
            token_api_endpoint: Optional custom token API endpoint
            general_api_endpoint: Optional custom API endpoint for menu calls
            save_debug_files: Whether to save debug files to disk
            debug_output_dir: Directory to save debug files (optional)
            menu_last_updated: Optional timestamp of when menu was last updated
            selected_menus: Optional list of menu names to process

        Returns:
            dict: Processing results with menu data and indexing information
        """
        try:
            logger.debug(
                "[toast._implementation.process_and_index_menu_from_api] Starting Toast menu processing from API..."
            )

            # Step 1: Get authentication token
            access_token = self._authenticate_with_toast(
                client_id, client_secret, token_api_endpoint
            )

            logger.debug("Menu last updated: %s", menu_last_updated)

            # Step 2: Get menu metadata
            metadata = self._get_menu_metadata(
                access_token, restaurant_external_id, general_api_endpoint
            )

            logger.debug("Menu metadata: %s", metadata)

            # Step 2.5: Check if menu needs updating
            if menu_last_updated and not self._should_update_menu(
                menu_last_updated, metadata
            ):
                logger.debug(
                    "[toast._implementation.process_and_index_menu_from_api] Skipping indexing — menu is up to date."
                )
                return {"message": "Menu is up to date. Skipping indexing."}

            # Step 3: Download and process menu data
            individual_items, system_prompt_menu, infinite_loop_items = (
                self._download_and_process_menu(
                    access_token,
                    restaurant_external_id,
                    general_api_endpoint,
                    selected_menus,
                )
            )

            # Step 4: Index menu to Pinecone
            document_count = self._index_menu_to_pinecone(
                individual_items, pinecone_index_name, pinecone_namespace
            )

            # Step 5: Get and index dining options
            dining_options_count = 0
            dining_options_json = None
            try:
                dining_options_count, dining_options_json = (
                    self._get_and_index_dining_options(
                        access_token,
                        restaurant_external_id,
                        pinecone_index_name,
                        pinecone_namespace,
                        general_api_endpoint,
                    )
                )
                logger.debug(
                    "[toast._implementation.process_and_index_menu_from_api] Successfully indexed %s dining options",
                    dining_options_count,
                )
            except Exception as e:
                logger.warning(
                    f"[toast._implementation.process_and_index_menu_from_api] Failed to index dining options: {e}. Continuing with menu indexing."
                )

            # Step 6: Save debug files if requested (including dining options)
            if save_debug_files:
                self._save_debug_files(
                    individual_items,
                    system_prompt_menu,
                    infinite_loop_items,
                    debug_output_dir,
                    dining_options_json,
                )

            return {
                "system_prompt_menu": system_prompt_menu,
                "pinecone_namespace": pinecone_namespace,
                "pinecone_index_name": pinecone_index_name,
                "processed_items": document_count,
                "dining_options_indexed": dining_options_count,
                "restaurant_external_id": restaurant_external_id,
                "restaurant_guid": metadata.get("restaurantGuid"),
                "menu_last_updated": metadata.get("lastUpdated"),
                "infinite_loop_items_count": len(infinite_loop_items),
                "token_api_endpoint": token_api_endpoint,
                "general_api_endpoint": general_api_endpoint,
            }

        except Exception as e:
            logger.error(
                f"[toast._implementation.process_and_index_menu_from_api] Error processing Toast menu from API: {e}"
            )
            raise
