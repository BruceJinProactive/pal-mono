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

from typing import Any, Dict, Optional

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
        restaurant_name: str,
        pinecone_index_name: str,
        pinecone_namespace: str,
        location_name: Optional[str] = None,
        include_location_in_doc_name: bool = False,
    ) -> Dict[str, Any]:
        """Process Square menu and index it to Pinecone.

        Args:
            access_token: Square access token for API authentication
            location_id: Square location ID to process menu for
            restaurant_name: Name of the restaurant for indexing (required)
            pinecone_index_name: Name of the Pinecone index to use
            pinecone_namespace: Namespace to store the menu data in
            location_name: Optional human-readable location name
            include_location_in_doc_name: Whether to include location name in document names

        Returns:
            dict: Processing results including menu data and indexing information

        Raises:
            ValueError: If input parameters are invalid
            RuntimeError: If processing fails
        """
        try:
            if self.debug:
                logger.debug("Starting Square menu processing...")

            # Step 1: Validate credentials and parameters
            validation_result = validate_square_credentials(access_token, location_id)
            if not validation_result.get("valid", False):
                raise ValueError(
                    f"Invalid credentials: {validation_result.get('error')}"
                )

            if self.debug:
                logger.debug(f"Credentials validated for location {location_id}")

            # Step 2: Download menu data from Square API
            menu_data = download_menu(
                access_token=access_token,
                location_id=location_id,
                location_name=location_name,
            )

            if self.debug:
                logger.debug(f"Successfully downloaded menu for location {location_id}")
                logger.debug(f"Menu contains {menu_data.get('item_count', 0)} items")

            # Step 3: Parse and validate menu data
            parsed_menu = parse_menu_data(menu_data)

            if self.debug:
                validation_summary = parsed_menu.get("validation_summary", {})
                logger.debug(
                    f"Menu validation: {validation_summary.get('items_valid', 0)} valid items "
                    f"out of {validation_summary.get('items_processed', 0)} processed"
                )

            # Step 4: Generate individual item texts
            individual_items = []
            menu_items = parsed_menu.get("menu_items", [])

            for i, item in enumerate(menu_items):
                try:
                    item_text = generate_item_text(
                        item=item,
                        location_name=location_name or location_id,
                        include_location_in_text=True,
                    )
                    individual_items.append(
                        {
                            "name": item.get("name", f"Item_{i+1}"),
                            "text": item_text,
                            "metadata": {
                                "item_id": item.get("id"),
                                "variation_id": item.get("_variation_id"),
                                "location_id": location_id,
                                "location_name": location_name or location_id,
                            },
                        }
                    )
                except Exception as e:
                    logger.warning(f"Failed to generate text for item {i+1}: {e}")
                    continue

            if self.debug:
                logger.debug(f"Generated text for {len(individual_items)} menu items")

            # Step 5: Generate consolidated menu documents
            consolidated_documents = format_consolidated_menu(
                menu_data=parsed_menu,
                include_location_in_doc_name=include_location_in_doc_name,
            )

            if self.debug:
                logger.debug(
                    f"Generated {len(consolidated_documents)} consolidated documents"
                )

            # Step 6: Index individual items to Pinecone (following notebook pattern)
            indexing_result = index_individual_items_to_pinecone(
                menu_data=parsed_menu,
                pinecone_index_name=pinecone_index_name,
                pinecone_namespace=pinecone_namespace,
                location_id=location_id,
                location_name=location_name,
                restaurant_name=restaurant_name,
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

            if self.debug:
                logger.debug(f"Menu statistics calculated: {menu_stats}")

            # Return comprehensive results
            return {
                "success": indexing_result.get("success", False),
                "location_id": location_id,
                "location_name": location_name or location_id,
                "menu_data": parsed_menu,
                "individual_items": individual_items,
                "consolidated_documents": consolidated_documents,
                "indexing_result": indexing_result,
                "menu_statistics": menu_stats,
                "processing_summary": {
                    "total_catalog_objects": menu_data.get("total_objects", 0),
                    "menu_items_processed": len(menu_items),
                    "individual_texts_generated": len(individual_items),
                    "consolidated_documents_created": len(consolidated_documents),
                    "vectors_indexed": indexing_result.get("vectors_created", 0),
                },
            }

        except Exception as e:
            logger.error(f"Error processing Square menu: {e}")
            return {
                "success": False,
                "error": str(e),
                "location_id": location_id,
                "location_name": location_name or location_id,
                "processing_summary": {
                    "total_catalog_objects": 0,
                    "menu_items_processed": 0,
                    "individual_texts_generated": 0,
                    "consolidated_documents_created": 0,
                    "vectors_indexed": 0,
                },
            }

    def get_menu_data_only(
        self,
        access_token: str,
        location_id: str,
        location_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Download and process Square menu data without indexing.

        Args:
            access_token: Square access token for API authentication
            location_id: Square location ID to process menu for
            location_name: Optional human-readable location name

        Returns:
            dict: Processed menu data without indexing

        Raises:
            ValueError: If input parameters are invalid
            RuntimeError: If processing fails
        """
        try:
            if self.debug:
                logger.debug(
                    f"Downloading Square menu data only for location {location_id}"
                )

            # Validate credentials
            validation_result = validate_square_credentials(access_token, location_id)
            if not validation_result.get("valid", False):
                raise ValueError(
                    f"Invalid credentials: {validation_result.get('error')}"
                )

            # Download and parse menu data
            menu_data = download_menu(
                access_token=access_token,
                location_id=location_id,
                location_name=location_name,
            )

            parsed_menu = parse_menu_data(menu_data)
            menu_stats = calculate_menu_statistics(parsed_menu)

            return {
                "success": True,
                "location_id": location_id,
                "location_name": location_name or location_id,
                "menu_data": parsed_menu,
                "menu_statistics": menu_stats,
            }

        except Exception as e:
            logger.error(f"Error downloading Square menu data: {e}")
            return {
                "success": False,
                "error": str(e),
                "location_id": location_id,
                "location_name": location_name or location_id,
            }

    def generate_text_only(
        self,
        menu_data: Dict[str, Any],
        location_name: Optional[str] = None,
        include_location_in_doc_name: bool = False,
    ) -> Dict[str, Any]:
        """Generate text documents from existing menu data.

        Args:
            menu_data: Pre-processed menu data
            location_name: Optional location name for text generation
            include_location_in_doc_name: Whether to include location in document names

        Returns:
            dict: Generated text documents and individual items

        Raises:
            ValueError: If menu data is invalid
        """
        try:
            if self.debug:
                logger.debug("Generating text documents from menu data")

            # Parse menu data if needed
            if "menu_items" not in menu_data:
                parsed_menu = parse_menu_data(menu_data)
            else:
                parsed_menu = menu_data

            location_id = parsed_menu.get("location_id")
            if not location_name:
                location_name = parsed_menu.get("location_name", location_id)

            # Generate individual item texts
            individual_items = []
            menu_items = parsed_menu.get("menu_items", [])

            for i, item in enumerate(menu_items):
                try:
                    item_text = generate_item_text(
                        item=item,
                        location_name=location_name,
                        include_location_in_text=True,
                    )
                    individual_items.append(
                        {
                            "name": item.get("name", f"Item_{i+1}"),
                            "text": item_text,
                            "metadata": {
                                "item_id": item.get("id"),
                                "variation_id": item.get("_variation_id"),
                                "location_id": location_id,
                                "location_name": location_name,
                            },
                        }
                    )
                except Exception as e:
                    logger.warning(f"Failed to generate text for item {i+1}: {e}")
                    continue

            # Generate consolidated documents
            consolidated_documents = format_consolidated_menu(
                menu_data=parsed_menu,
                include_location_in_doc_name=include_location_in_doc_name,
            )

            return {
                "success": True,
                "location_id": location_id,
                "location_name": location_name,
                "individual_items": individual_items,
                "consolidated_documents": consolidated_documents,
                "text_generation_summary": {
                    "menu_items_processed": len(menu_items),
                    "individual_texts_generated": len(individual_items),
                    "consolidated_documents_created": len(consolidated_documents),
                },
            }

        except Exception as e:
            logger.error(f"Error generating text documents: {e}")
            return {
                "success": False,
                "error": str(e),
                "text_generation_summary": {
                    "menu_items_processed": 0,
                    "individual_texts_generated": 0,
                    "consolidated_documents_created": 0,
                },
            }
