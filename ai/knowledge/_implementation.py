from concurrent.futures import ThreadPoolExecutor, as_completed

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

    catalog = shopify.Product.find()

    indexer = ShopifyImageIndexer()

    MAX_WORKERS = 10
    products_indexed, successes, failures = 0, 0, 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        while catalog:
            logger.info(catalog)

            future_to_product = {
                executor.submit(indexer.process_product, product): product
                for product in catalog
            }

            for future in as_completed(future_to_product):
                product = future_to_product[future]
                products_indexed += 1

                try:
                    # Return True if product was indexed successfully
                    result = future.result()
                    if result:
                        successes += 1
                    else:
                        failures += 1
                except Exception as exc:
                    logger.error(
                        f"Product ID {product['id']} generated an exception: {exc}"
                    )
                    failures += 1

            # Move to the next page if available
            if catalog.has_next_page():  # type: ignore
                catalog = catalog.next_page()  # type: ignore
            else:
                break

            # TODO: Remove once inital test is working
            if products_indexed >= 1000:
                break

    logger.info(f"Total number of items upserted: {products_indexed}")

    shopify.ShopifyResource.clear_session()  # Clear the session

    return successes, failures
