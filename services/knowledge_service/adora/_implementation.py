"""
Adora menu processing orchestrator for knowledge base integration.

This module provides the main orchestration class that coordinates all
Adora menu processing operations from API retrieval to vector indexing.

Key responsibilities:
- Coordinate the complete menu processing pipeline
- Manage the workflow from API to knowledge base
- Handle error management and debug logging
- Provide the main interface for knowledge service integration

Processing pipeline:
1. Authenticate and download menu data from Adora API
2. Process and format menu items into readable text
3. Index processed items into Pinecone vector store
4. Return processing results and metadata

Usage:
    processor = AdoraMenuProcessor(debug=True)
    result = processor.process_and_index_menu(
        store_id="123",
        client_id="client",
        client_secret="secret",
        ...
    )

Dependencies:
- _client: API communication
- _formatter: Text generation
- _indexer: Vector store operations
"""

import re
from typing import Any, Dict, List

from utils.log import logger

from ._client import download_menu, get_bearer_token
from ._formatter import format_consolidated_menu, generate_item_text
from ._indexer import index_to_pinecone
from ._utils import parse_item_data


class AdoraMenuProcessor:
    """Processes Adora menu data and indexes it to Pinecone.

    Controls the complete menu processing pipeline from API authentication
    to vector store indexing.
    """

    def __init__(self, debug: bool = False):
        """Initialize processor.

        Args:
            debug: Whether to enable debug logging
        """
        self.debug = debug
        self.token = None

    def process_and_index_menu(
        self,
        store_id: str,
        client_id: str,
        client_secret: str,
        pinecone_index_name: str,
        pinecone_namespace: str,
        token_api_endpoint: str,
        general_api_endpoint: str,
        include_category_in_doc_name: bool = False,
    ) -> Dict[str, Any]:
        """Process Adora menu and index it to Pinecone.

        Args:
            store_id: Store ID to process menu for
            client_id: Client ID for authentication
            client_secret: Client secret for authentication
            pinecone_index_name: Pinecone index name
            pinecone_namespace: Pinecone namespace for menu data
            token_api_endpoint: Complete URL for token endpoint
            general_api_endpoint: Complete URL for general API endpoint
            include_category_in_doc_name: Whether to include category in document names

        Returns:
            dict: Processing results with menu data and indexing information
        """
        try:
            logger.debug("Starting Adora menu processing...")

            # Step 1: Get authentication token
            if not self.token:
                self.token = get_bearer_token(
                    client_id=client_id,
                    client_secret=client_secret,
                    token_api_endpoint=token_api_endpoint,
                )
                logger.debug(
                    "[adora._implementation.process_and_index_menu] Successfully got authentication token for store %s",
                    store_id,
                )

            # Step 2: Download menu data
            menu_data = download_menu(
                store_id=store_id,
                token=self.token,
                general_api_endpoint=general_api_endpoint,
            )

            logger.debug(
                "[adora._implementation.process_and_index_menu] Successfully downloaded menu for store %s",
                store_id,
            )
            logger.debug(
                "[adora._implementation.process_and_index_menu] Menu contains %s items",
                len(menu_data.get("items", [])),
            )

            # Step 3: Generate individual item texts
            individual_items = []
            for i, item in enumerate(menu_data.get("items", [])):
                item_text, item_name, category_name = generate_item_text(
                    item=item,
                    menu_data=menu_data,
                    with_ids=True,
                )

                # Sanitize item_name and category_name
                item_name_sanitized = re.sub(r"[^\w\s]", "", item_name)
                category_name_sanitized = re.sub(r"[^\w\s]", "", category_name)

                # Generate document name based on include_category_in_doc_name setting
                if include_category_in_doc_name:
                    # Check if category name is already in item name (case insensitive)
                    if category_name.lower() in item_name.lower():
                        document_name = f"item_{i}_{item_name_sanitized}"
                    else:
                        document_name = (
                            f"item_{i}_{item_name_sanitized} {category_name_sanitized}"
                        )
                else:
                    # Don't include category name in document name
                    document_name = f"item_{i}_{item_name_sanitized}"

                individual_items.append({document_name: item_text})
            # Step 4: Generate consolidated menu
            consolidated_menu = self._generate_consolidated_menu(
                individual_items=individual_items
            )
            # Step 5: Index to Pinecone
            document_count = index_to_pinecone(
                individual_items=individual_items,
                pinecone_index_name=pinecone_index_name,
                pinecone_namespace=pinecone_namespace,
                debug=self.debug,
            )
            logger.debug(
                "[adora._implementation.process_and_index_menu] Processing complete. Total items: %s",
                len(individual_items),
            )
            logger.debug(
                "[adora._implementation.process_and_index_menu] Indexed %s documents to namespace: %s",
                document_count,
                pinecone_namespace,
            )

            return {
                "system_prompt_menu": consolidated_menu,
                "pinecone_namespace": pinecone_namespace,
                "pinecone_index_name": pinecone_index_name,
                "processed_items": document_count,
                "store_id": store_id,
            }

        except Exception as e:
            logger.error(f"Error processing Adora menu: {e}")
            raise

    def _generate_consolidated_menu(
        self,
        individual_items: List[Dict[str, str]],
    ) -> str:
        """Generate consolidated menu text from individual items.

        Args:
            individual_items: List of dictionaries where each dict contains one key-value pair.
                            Key format depends on include_category_in_doc_name setting:
                            - If True: "item_{index}_{item_name}" if category is already in item name,
                              or "item_{index}_{item_name} {category_name}" if category is not in item name.
                            - If False: "item_{index}_{item_name}" (category name never included).
                            Value: The formatted item text.

        Returns:
            str: Consolidated menu text
        """
        # Parse items for consolidated format
        menu_items = []
        for item_dict in individual_items:
            # Each item_dict has one key-value pair
            for _, item_text in item_dict.items():
                item_data = parse_item_data(item_text)
                if item_data:
                    menu_items.append(item_data)

        # Sort and format consolidated menu
        menu_items.sort(key=lambda x: (x["category"], x["name"]))
        return format_consolidated_menu(menu_items)
