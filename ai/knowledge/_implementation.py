from typing import Any

import shopify
from phi.knowledge.base import AssistantKnowledge
from phi.knowledge.combined import CombinedKnowledgeBase
from phi.vectordb.pgvector.pgvector2 import PgVector2

from ai.llm import get_embedder
from db.session import db_url
from utils.log import logger
from utils.secret import get_client_secret

from .image_indexer import ShopifyImageIndexer


def get_knowledge(account_name: str) -> AssistantKnowledge:
    knowledge_table_name = f"{account_name}_knowledge"
    get_knowledge = CombinedKnowledgeBase(
        sources=[],
        vector_db=PgVector2(
            db_url=db_url,
            collection=knowledge_table_name,
            embedder=get_embedder(),
        ),
        # 2 references are added to the prompt
        num_documents=10,
    )

    return get_knowledge


def index_data_from_shopify() -> tuple[int, int]:
    logger.info("Running data indexing from Shopify")

    windsor_shopify_url: str = "windsor-us.myshopify.com"
    api_version: str = "2024-07"

    shopify_access_token = get_client_secret("WINDSOR_SHOPIFY_ACCESS_TOKEN")

    session = shopify.Session(windsor_shopify_url, api_version, shopify_access_token)
    shopify.ShopifyResource.activate_session(session)

    all_products: list[dict[str, Any]] = []
    catalog = shopify.Product.find()

    products_indexed = 0
    while catalog:
        for product in catalog:
            metadata = product.attributes

            image_url = metadata["image"].attributes["src"] if metadata["image"] else ""

            # Format tags in metadata
            for tag in metadata["tags"].split(","):
                metadata[tag.strip()] = True

            filtered_metadata = {
                k: v
                for k, v in metadata.items()
                if k not in ["variants", "options", "images", "image"] and v is not None
            }

            if not filtered_metadata["body_html"]:
                filtered_metadata["body_html"] = ""

            data = {
                "id": str(metadata["id"]),
                "image_url": image_url,
                "metadata": filtered_metadata,
            }
            all_products.append(data)

            products_indexed += 1

            if catalog.has_next_page():  # type: ignore
                catalog = catalog.next_page()  # type: ignore

        # TODO: For testing purposes, we only sample a subset of the data
        if products_indexed >= 100:
            break

    indexer = ShopifyImageIndexer()

    logger.info(f"Total number of products to upsert: {len(all_products)}")
    successes, failures = indexer.batch_upsert(all_products)

    shopify.ShopifyResource.clear_session()  # Clear the session

    return successes, failures
