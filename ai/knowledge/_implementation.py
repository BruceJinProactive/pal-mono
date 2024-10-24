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

    # all_products: list[dict[str, Any]] = []
    catalog = shopify.Product.find()

    indexer = ShopifyImageIndexer()

    products_indexed, successes, failures = 0, 0, 0
    while catalog:
        logger.info(catalog)
        for product in catalog:
            metadata = product.attributes

            image_url = metadata["image"].attributes["src"] if metadata["image"] else ""

            ###
            # Create filtered metadata
            # Includes:
            # - product_type
            # - tags
            # - options (colors and sizes)
            # ###
            filtered_metadata = {}

            # Format product type in metadata
            if metadata.get("product_type"):
                filtered_metadata[metadata["product_type"].strip()] = True

            # Format tags in metadata
            if metadata.get("tags"):
                for tag in metadata["tags"].split(","):
                    filtered_metadata[tag.strip()] = True

            # Format options in metadata
            if metadata.get("options"):
                for option_object in metadata["options"]:
                    option = option_object.attributes
                    if option["name"] == "Color":
                        for color in option["values"]:
                            filtered_metadata[color.strip()] = True
                    elif option["name"] == "Size":
                        for size in option["values"]:
                            filtered_metadata[size.strip()] = True

            # Format image urls in metadata
            if metadata.get("images"):
                image_urls: list[str] = []
                for image in metadata["images"]:
                    image_urls.append(image.attributes["src"])
                filtered_metadata["image_urls"] = image_urls

            ###
            # Create embedding information
            # Includes:
            # - title
            # - description (if exists)
            # ###
            embedding_data = {
                "title": metadata["title"],
                "description": metadata["body_html"],
            }

            item_data = {
                "id": str(metadata["id"]),
                "image_url": image_url,
                "metadata": filtered_metadata,
                "embedding_data": embedding_data,
            }

            response = indexer.upsert(item_data)

            if response:
                successes += 1
            else:
                failures += 1

            products_indexed += 1

        if catalog.has_next_page():  # type: ignore
            catalog = catalog.next_page()  # type: ignore
        else:
            catalog = None

        # TODO: For testing purposes, we only sample a subset of the data
        if products_indexed >= 1000:
            break

    logger.info(f"Total number of products to upsert: {products_indexed}")

    shopify.ShopifyResource.clear_session()  # Clear the session

    return successes, failures
