"""
Square menu processing orchestrator for knowledge base integration.

Removes tool dependencies, uses direct Square API, resolves real categories,
and aligns outputs with Adora/Toast: per-item docs and a consolidated menu.
"""

import re
from typing import Any, Dict, List

from utils.log import logger

from ._client import download_menu
from ._formatter import format_consolidated_menu, generate_item_text
from ._indexer import index_to_pinecone


class SquareMenuProcessor:
    def __init__(self, debug: bool = False):
        self.debug = debug

    def process_and_index_menu(
        self,
        access_token: str,
        location_id: str,
        pinecone_index_name: str,
        pinecone_namespace: str,
        include_location_in_doc_name: bool = False,
    ) -> Dict[str, Any]:
        try:
            logger.debug("[square._implementation] Starting Square menu processing...")

            if not access_token or not access_token.strip():
                raise ValueError("Square access token is required")
            if not location_id or not location_id.strip():
                raise ValueError("Square location_id is required")

            # 1) Fetch items directly from Square
            menu = download_menu(access_token=access_token, location_id=location_id)
            items: List[Dict[str, Any]] = menu.get("items", [])
            raw_counts = menu.get("raw_counts", {})
            logger.debug(
                "[square._implementation] Downloaded %s items for location %s",
                len(items),
                location_id,
            )
            if raw_counts:
                logger.debug(
                    "[square._implementation] Catalog object counts",
                    extra={
                        "location_id": location_id,
                        **raw_counts,
                    },
                )

            # 2) Build per-item documents
            individual_items: List[Dict[str, str]] = []
            for i, item in enumerate(items):
                try:
                    item_text, item_name = generate_item_text(item, with_ids=True)
                except Exception as e:
                    logger.warning(
                        "[square._implementation] Failed to format item %s: %s", i, e
                    )
                    continue

                # Sanitize filename
                safe_name = re.sub(r"[^\w\s-]", "", item_name).strip()
                safe_name = re.sub(r"\s+", "_", safe_name)
                doc_name = f"item_{i}_{safe_name}"
                if include_location_in_doc_name:
                    doc_name = f"{location_id}_{doc_name}"
                individual_items.append({doc_name: item_text})

            # 3) Consolidated menu text for system prompt
            system_prompt_menu = format_consolidated_menu(items)

            # 4) Index to Pinecone (per-item path, like Adora/Toast)
            doc_count = index_to_pinecone(
                individual_items=individual_items,
                pinecone_index_name=pinecone_index_name,
                pinecone_namespace=pinecone_namespace,
            )

            logger.debug(
                "[square._implementation] Indexed %s docs to namespace %s",
                doc_count,
                pinecone_namespace,
            )

            return {
                "system_prompt_menu": system_prompt_menu,
                "pinecone_namespace": pinecone_namespace,
                "pinecone_index_name": pinecone_index_name,
                "processed_items": doc_count,
                "store_id": location_id,
                "raw_counts": raw_counts,
            }

        except Exception as e:
            logger.error(f"Error processing Square menu: {e}")
            raise
