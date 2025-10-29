"""
OLO menu processing orchestrator for knowledge base integration.

This module provides the main orchestration class that coordinates all
OLO menu processing operations from raw menu data to vector indexing.

Key responsibilities:
- Coordinate the complete menu processing pipeline
- Manage the workflow from JSON data to knowledge base
- Handle error management and debug logging
- Provide the main interface for knowledge service integration

Processing pipeline:
1. Accept raw OLO menu JSON data
2. Process and format menu items into readable text
3. Index processed items into Pinecone vector store
4. Return processing results and metadata

Usage:
    processor = OloMenuProcessor(debug=True)
    result = processor.process_and_index_menu(
        menu_json=raw_menu_data,
        pinecone_index_name="olo-menu",
        pinecone_namespace="restaurant_123",
        ...
    )

Dependencies:
- _formatter: Text generation
- _indexer: Vector store operations
- _utils: OLO-specific utilities
"""

import datetime
import os
from typing import Any, Dict, List, Optional

from utils.log import logger

from ._indexer import index_to_pinecone
from ._utils import _sanitize_filename, parse_menu


class OloMenuProcessor:
    """Processes OLO menu data and indexes it to Pinecone.

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
        restaurant_id: str,
        save_debug_files: bool = False,
        debug_output_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Process OLO menu and index it to Pinecone.

        Args:
            menu_json: Raw OLO menu JSON data (products_with_modifiers format)
            pinecone_index_name: Pinecone index name
            pinecone_namespace: Pinecone namespace for menu data
            restaurant_id: Restaurant ID for metadata
            save_debug_files: Whether to save debug files to disk
            debug_output_dir: Directory to save debug files (optional)

        Returns:
            dict: Processing results with menu data and indexing information
        """
        try:
            logger.debug(
                "[olo._implementation.process_and_index_menu] Starting OLO menu processing..."
            )

            # Step 1: Parse menu JSON
            individual_items, system_prompt_menu = parse_menu(menu_json)

            logger.debug(
                "[olo._implementation.process_and_index_menu] Successfully parsed menu"
            )
            logger.debug(
                "[olo._implementation.process_and_index_menu] Menu contains %s items",
                len(individual_items),
            )

            # Step 2: Save debug files if requested
            if save_debug_files:
                self._save_debug_files(
                    individual_items,
                    system_prompt_menu,
                    debug_output_dir,
                    restaurant_id,
                )

            # Step 3: Index to Pinecone
            document_count = index_to_pinecone(
                individual_items=individual_items,
                pinecone_index_name=pinecone_index_name,
                pinecone_namespace=pinecone_namespace,
                debug=self.debug,
            )

            logger.debug(
                "[olo._implementation.process_and_index_menu] Processing complete. Total items: %s",
                len(individual_items),
            )
            logger.debug(
                "[olo._implementation.process_and_index_menu] Indexed %s documents to namespace: %s",
                document_count,
                pinecone_namespace,
            )

            return {
                "system_prompt_menu": system_prompt_menu,
                "pinecone_namespace": pinecone_namespace,
                "pinecone_index_name": pinecone_index_name,
                "processed_items": document_count,
                "restaurant_id": restaurant_id,
            }

        except Exception as e:
            logger.error(
                f"[olo._implementation.process_and_index_menu] Error processing OLO menu: {e}"
            )
            raise

    def _save_debug_files(
        self,
        individual_items: List[Dict[str, str]],
        system_prompt_menu: str,
        debug_output_dir: Optional[str],
        restaurant_id: str,
    ) -> None:
        """Save debug files to disk.

        Args:
            individual_items: List of menu item dictionaries
            system_prompt_menu: System prompt menu text
            debug_output_dir: Directory to save files (optional)
            restaurant_id: Restaurant ID for directory naming
        """
        # Use provided directory or create default one
        if debug_output_dir is None:
            dirname = f"olo_menu_debug_{restaurant_id}_{datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
        else:
            dirname = debug_output_dir

        # Create directories
        os.makedirs(dirname, exist_ok=True)
        os.makedirs(os.path.join(dirname, "menu_items"), exist_ok=True)

        # Save each item in a separate file
        for menu_item in individual_items:
            for filename, information in menu_item.items():
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

        logger.debug(
            "[olo._implementation._save_debug_files] Debug files saved to: %s",
            dirname,
        )

    def process_and_index_menu_from_api(
        self,
        store_id: str,
        client_id: str,
        client_secret: str,
        pinecone_index_name: str,
        pinecone_namespace: str,
        general_api_endpoint: str,
    ) -> Dict[str, Any]:
        """Process OLO menu from API and index it to Pinecone.

        This method fetches the menu from the OLO API, processes it,
        and indexes it to Pinecone.

        Unlike Adora/Toast which use OAuth token endpoints, OLO uses
        signed HMAC requests for authentication, so only the general
        API endpoint is needed.

        Args:
            store_id: OLO restaurant ID
            client_id: OLO API client ID
            client_secret: OLO API client secret
            pinecone_index_name: Pinecone index name
            pinecone_namespace: Pinecone namespace for menu data
            general_api_endpoint: OLO general API endpoint

        Returns:
            dict: Processing results with menu data and indexing information
        """
        try:
            logger.debug(
                "[olo._implementation.process_and_index_menu_from_api] Starting OLO menu processing from API..."
            )

            # Import OLO client functions
            from ._client import get_restaurant_menu

            # Fetch menu from OLO API
            logger.debug(
                "[olo._implementation.process_and_index_menu_from_api] Fetching menu for restaurant %s",
                store_id,
            )

            menu_json = get_restaurant_menu(
                store_id, client_id, client_secret, general_api_endpoint
            )
            if not menu_json:
                raise ValueError(f"Failed to fetch menu for restaurant {store_id}")

            logger.debug(
                "[olo._implementation.process_and_index_menu_from_api] Successfully fetched menu data"
            )

            # Process and index the menu
            result = self.process_and_index_menu(
                menu_json=menu_json,
                pinecone_index_name=pinecone_index_name,
                pinecone_namespace=pinecone_namespace,
                restaurant_id=store_id,
                save_debug_files=False,
                debug_output_dir=None,
            )

            logger.debug(
                "[olo._implementation.process_and_index_menu_from_api] Successfully processed and indexed menu"
            )

            return result

        except Exception as e:
            logger.error(
                f"[olo._implementation.process_and_index_menu_from_api] Error processing OLO menu from API: {e}"
            )
            raise
