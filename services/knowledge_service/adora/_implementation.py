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

from typing import Any, Dict, List

from utils.log import logger

from ._client import download_menu, get_bearer_token
from ._formatter import format_consolidated_menu, generate_item_text
from ._indexer import index_to_pinecone
from ._utils import parse_item_data


class AdoraMenuProcessor:
    """Processes Adora menu data and indexes it to Pinecone.

    This class orchestrates the entire menu processing pipeline:
    1. Authentication with Adora API
    2. Menu data download
    3. Text generation and formatting
    4. Pinecone indexing
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
    ) -> Dict[str, Any]:
        """Process Adora menu and index it to Pinecone.

        Args:
            store_id: The store ID to process menu for
            client_id: The client ID for authentication
            client_secret: The client secret for authentication
            pinecone_index_name: The name of the Pinecone index to use
            pinecone_namespace: The namespace to store the menu data in
            token_api_endpoint: The complete URL for the token endpoint
            general_api_endpoint: The complete URL for the general API endpoint

        Returns:
            dict: Processing results including menu data and indexing information
        """
        try:
            if self.debug:
                logger.debug("Starting Adora menu processing...")

            # Step 1: Get authentication token
            if not self.token:
                self.token = get_bearer_token(
                    client_id=client_id,
                    client_secret=client_secret,
                    token_api_endpoint=token_api_endpoint,
                )
                if self.debug:
                    logger.debug(
                        f"[adora._implementation.process_and_index_menu] Successfully got authentication token for store {store_id}"
                    )

            # Step 2: Download menu data
            menu_data = download_menu(
                store_id=store_id,
                token=self.token,
                general_api_endpoint=general_api_endpoint,
            )

            if self.debug:
                logger.debug(
                    f"[adora._implementation.process_and_index_menu] Successfully downloaded menu for store {store_id}"
                )
                logger.debug(
                    f"[adora._implementation.process_and_index_menu] Menu contains {len(menu_data.get('items', []))} items"
                )

            # Step 3: Generate individual item texts
            individual_items = []
            for item in menu_data.get("items", []):
                item_text = generate_item_text(
                    item=item,
                    menu_data=menu_data,
                    with_ids=True,
                )
                individual_items.append(item_text)
            # Step 4: Generate consolidated menu
            consolidated_menu = self._generate_consolidated_menu(
                individual_items=individual_items
            )
            # Step 5: Index to Pinecone
            final_namespace = index_to_pinecone(
                individual_items=individual_items,
                pinecone_index_name=pinecone_index_name,
                pinecone_namespace=pinecone_namespace,
                debug=self.debug,
            )
            if self.debug:
                logger.debug(
                    f"[adora._implementation.process_and_index_menu] Processing complete. Total items: {len(individual_items)}"
                )

            return {
                "system_prompt_menu": consolidated_menu,
                "pinecone_namespace": final_namespace,
                "pinecone_index_name": pinecone_index_name,
                "processed_items": len(individual_items),
                "store_id": store_id,
            }

        except Exception as e:
            logger.error(f"Error processing Adora menu: {e}")
            raise

    def _generate_consolidated_menu(self, individual_items: List[str]) -> str:
        """Generate consolidated menu text from individual items.

        Args:
            individual_items: List of formatted individual item strings

        Returns:
            str: Consolidated menu text
        """
        # Parse items for consolidated format
        menu_items = []
        for item_text in individual_items:
            item_data = parse_item_data(item_text)
            if item_data:
                menu_items.append(item_data)

        # Sort and format consolidated menu
        menu_items.sort(key=lambda x: (x["category"], x["name"]))
        return format_consolidated_menu(menu_items)
