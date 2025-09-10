"""
Square menu processing orchestrator for knowledge base integration.

This module provides the main orchestration class that coordinates all
Square menu processing operations from API retrieval to vector indexing.

Key responsibilities:
- Coordinate the complete menu processing pipeline
- Manage the workflow from Square API to knowledge base
- Handle error management and debug logging
- Provide the main interface for knowledge service integration

Processing pipeline:
1. Authenticate and download menu data from Square Catalog API
2. Process and format menu items into readable text
3. Index processed items into Pinecone vector store
4. Return processing results and metadata


Dependencies:
- _client: API communication with Square
- _formatter: Text generation and formatting
- _indexer: Vector store operations
- _utils: Data validation and processing utilities
"""

from typing import Any, Dict

from utils.log import logger

from ._client import download_menu
from ._formatter import format_consolidated_menu, generate_item_text
from ._indexer import index_individual_items_to_pinecone
from ._utils import (
    calculate_menu_statistics,
    parse_menu_data,
    validate_square_credentials,
)


class SquareMenuProcessor:
    """Processes Square menu data and indexes it to Pinecone.

    This class orchestrates the entire menu processing pipeline:
    1. Authentication and validation with Square API
    2. Menu data download and location filtering
    3. Text generation and formatting
    4. Pinecone indexing with proper metadata
    """

    def __init__(self, debug: bool = False):
        """Initialize processor.

        Args:
            debug: Whether to enable debug logging
        """
        self.debug = debug

    def process_and_index_menu(
        self,
        access_token: str,
        location_id: str,
        pinecone_index_name: str,
        pinecone_namespace: str,
        include_location_in_doc_name: bool = False,
    ) -> Dict[str, Any]:
        """Process Square menu and index it to Pinecone.

        Args:
            access_token: Square access token for API authentication
            location_id: Square location ID to process menu for
            pinecone_index_name: Name of the Pinecone index to use
            pinecone_namespace: Namespace to store the menu data in
            include_location_in_doc_name: Whether to include location name in document names

        Returns:
            dict: Processing results including menu data and indexing information

        Raises:
            ValueError: If input parameters are invalid
            RuntimeError: If processing fails
        """
        try:
            logger.debug("Starting Square menu processing...")

            # Step 1: Validate credentials and parameters
            validation_result = validate_square_credentials(access_token, location_id)
            if not validation_result.get("valid", False):
                raise ValueError(
                    f"Invalid credentials: {validation_result.get('error')}"
                )

            logger.debug("Credentials validated for location %s", location_id)

            # Step 2: Download menu data from Square API
            menu_data = download_menu(
                access_token=access_token,
                location_id=location_id,
            )

            logger.debug("Successfully downloaded menu for location %s", location_id)
            logger.debug("Menu contains %s items", menu_data.get("item_count", 0))

            # Step 3: Parse and validate menu data
            parsed_menu = parse_menu_data(menu_data)

            validation_summary = parsed_menu.get("validation_summary", {})
            logger.debug(
                "Menu validation: %s valid items out of %s processed",
                validation_summary.get("items_valid", 0),
                validation_summary.get("items_processed", 0),
            )

            # Step 4: Generate individual item texts
            individual_items = []
            menu_items = parsed_menu.get("menu_items", [])

            for i, item in enumerate(menu_items):
                try:
                    item_text = generate_item_text(
                        item=item,
                    )
                    individual_items.append(
                        {
                            "name": item.get("name", f"Item_{i+1}"),
                            "text": item_text,
                            "metadata": {
                                "item_id": item.get("id"),
                                "variation_id": item.get("_variation_id"),
                                "location_id": location_id,
                            },
                        }
                    )
                except Exception as e:
                    logger.warning(f"Failed to generate text for item {i+1}: {e}")
                    continue

            logger.debug("Generated text for %s menu items", len(individual_items))

            # Step 5: Generate consolidated menu documents
            consolidated_documents = format_consolidated_menu(
                menu_data=parsed_menu,
            )

            logger.debug(
                "Generated %s consolidated documents", len(consolidated_documents)
            )

            # Step 6: Index individual items to Pinecone
            indexing_result = index_individual_items_to_pinecone(
                menu_data=parsed_menu,
                pinecone_index_name=pinecone_index_name,
                pinecone_namespace=pinecone_namespace,
                location_id=location_id,
            )

            if self.debug:
                if indexing_result.get("success"):
                    logger.debug(
                        f"Successfully indexed {indexing_result.get('vectors_created', 0)} vectors"
                    )
                else:
                    logger.error(f"Indexing failed: {indexing_result.get('error')}")

            # Step 7: Calculate statistics
            menu_stats = calculate_menu_statistics(parsed_menu)

            logger.debug("Menu statistics calculated: %s", menu_stats)

            # Extract consolidated menu text for system prompt
            consolidated_menu = ""
            if consolidated_documents:
                # consolidated_documents is a dict, get the first value (the menu text)
                consolidated_menu = next(iter(consolidated_documents.values()), "")

            return {
                "system_prompt_menu": consolidated_menu,
                "pinecone_namespace": pinecone_namespace,
                "pinecone_index_name": pinecone_index_name,
                "processed_items": len(menu_items),
                "store_id": location_id,
            }

        except Exception as e:
            logger.error(f"Error processing Square menu: {e}")
            return {
                "system_prompt_menu": "",
                "pinecone_namespace": pinecone_namespace,
                "pinecone_index_name": pinecone_index_name,
                "processed_items": 0,
                "store_id": location_id,
            }
