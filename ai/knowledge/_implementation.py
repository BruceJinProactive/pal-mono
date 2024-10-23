from os import getenv
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

    try:
        shopify_access_token = get_client_secret("WINDSOR_SHOPIFY_ACCESS_TOKEN")
    except Exception as e:
        shopify_access_token = getenv("SHOPIFY_ACCESS_TOKEN")  # Use local env variable

    session = shopify.Session(windsor_shopify_url, api_version, shopify_access_token)
    shopify.ShopifyResource.activate_session(session)

    all_products: list[dict[str, Any]] = []
    erroneous_products: list[str] = []
    catalog = shopify.Product.find()
    while catalog:
        # TODO: For testing purposes, we only sample a subset of the data
        for product in catalog[:3]:
            attributes = product.attributes

            if not attributes["image"]:
                # If there is no image, skip the product for now
                logger.error(f"Product {attributes['id']} has no image")
                erroneous_products.append(attributes["id"])
                continue

            # NOTE: Assumption - only index single image for shopify item
            # We can also modify the filter logic to include different metadata
            # for embedding
            metadata = {
                "id": str(attributes["id"]),
                "title": str(attributes["title"]),
                "description": str(attributes["body_html"]),
                "tags": str(attributes["tags"]),
                "product_type": str(attributes["product_type"]),
                "image_url": attributes["image"].attributes["src"],
            }

            data = {
                "id": str(attributes["id"]),
                "image_url": attributes["image"].attributes["src"],
                "metadata": metadata,
            }
            all_products.append(data)

            if catalog.has_next_page():  # type: ignore
                catalog = catalog.next_page()  # type: ignore

        break

    indexer = ShopifyImageIndexer()

    logger.info(f"Total number of products: {len(all_products)}")
    successes, failures = indexer.batch_upsert(all_products)

    shopify.ShopifyResource.clear_session()  # Clear the session

    logger.info(f"The following products are missing images: {erroneous_products}")

    return successes, failures + len(erroneous_products)
