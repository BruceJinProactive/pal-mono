import asyncio
from typing import Any, Optional

from firecrawl import Firecrawl

from utils.log import logger
from utils.secret import get_client_secret_with_fallback


class MenuBuilder:
    """Menu builder for restaurant websites and delivery platforms"""

    def __init__(self):
        # Try to get API key from AWS Secrets Manager with fallback to environment variable
        try:
            api_key = get_client_secret_with_fallback("FIRECRAWL_API_KEY")
        except ValueError as e:
            raise ValueError("Firecrawl API key required.") from e

        self.firecrawl = Firecrawl(api_key=api_key)

    def _get_default_extract_prompt(self):
        """Get the comprehensive default extraction prompt for menu data"""
        return """
        You are analyzing content from a restaurant menu webpage. Extract and organize ALL menu information comprehensively.

        EXTRACTION RULES:
        - Extract ALL menu content including items with and without prices
        - Include ALL categories: appetizers, salads, soups, entrees, mains, sides, desserts, beverages, drinks, cocktails, wine, beer, coffee, tea, specials, kids menu, lunch menu, dinner menu, breakfast, brunch, etc.
        - Look for items in tables, lists, sections, and any formatted content
        - Don't miss any categories due to formatting, pricing, or presentation issues
        - Include items with various price formats: $X.XX, $X, X.XX, "Market Price", "MP", "Ask server", ranges like "$12-15"
        - If same item appears in multiple sections, keep all instances
        - Preserve actual descriptions and prices exactly as shown (when available)
        - Clean prices and descriptions by removing any trailing ratings, percentages, loading indicators, or review counts
        - Capture complete descriptions - include full sentences and all continuation text that belongs to each item
        - Don't truncate descriptions mid-sentence or miss follow-up sentences that describe the same item
        - It's perfectly acceptable for items to have NO description - include these items anyway
        - Include size variations (Small/Large, 8oz/16oz, etc.) as separate items
        - Maintain all occurrences of items across different categories
        - Include category sections even if some items don't have clear prices
        - Look for items in sidebars, bottom sections, or separate menu areas
        - Include seasonal items, daily specials, and limited-time offers
        - Don't make up any items - only extract what's actually present
        - Be extremely thorough - scan entire content multiple times for menu items

        IMPORTANT: Do NOT remove duplicates. If the same item appears in multiple sections 
        (like Featured Items, Most Ordered, and category sections), include ALL instances.
        Each appearance may have different context, pricing, or section-specific information.

        ORDERING RULES:
        - PRESERVE THE ORIGINAL ORDER of categories as they appear on the menu
        - PRESERVE THE ORIGINAL ORDER of items within each category
        - Do NOT alphabetize or reorganize categories
        - Do NOT alphabetize or reorganize items within categories
        - Keep the exact sequence as presented on the original menu

        FORMATTING RULES:
        Return the data as a JSON object with the following structure:
        {
          "menu": [
            {
              "category": "Category Name",
              "items": [
                {
                  "name": "Item Name",
                  "price": "$X.XX" (or empty string if no price),
                  "description": "Full item description" (or empty string if no description)
                }
              ]
            }
          ]
        }
        
        Focus on food and beverage items from the official menu sections only.
        Ignore promotional content, navigation, technical elements, user reviews, and customer comments.
        Only extract items that appear in actual menu sections with official pricing and descriptions.
        """

    def build(self, url: str, proxy_type: str = "auto") -> Optional[dict[str, Any]]:
        """Build menu data from a URL using LLM extraction"""
        try:
            extract_prompt = self._get_default_extract_prompt()
            formats = [{"type": "json", "prompt": extract_prompt}]

            scrape_options = {
                "formats": formats,
                "timeout": 120000,
                "location": {"country": "US", "languages": ["en"]},
                "actions": [
                    {"type": "wait", "milliseconds": 3000},
                    {"type": "scroll", "direction": "down"},
                    {"type": "wait", "milliseconds": 5000},
                    {"type": "scroll", "direction": "up"},
                    {"type": "wait", "milliseconds": 2000},
                ],
                "proxy": proxy_type,
            }

            result = self.firecrawl.scrape(url, **scrape_options)
            # Normalize common return shapes (dict, Response-like with .json())
            if isinstance(result, dict):
                return result
            json_attr = getattr(result, "json", None)
            if callable(json_attr):
                json_result = json_attr()
                return json_result if isinstance(json_result, dict) else None
            return json_attr if isinstance(json_attr, dict) else None

        except Exception as e:
            # Preserve original stack/type; message for logs only
            raise RuntimeError("Menu building failed") from e

    def output_content_as_markdown(self, menu_data: dict[str, Any]) -> Optional[str]:
        """Convert menu data to markdown format"""
        if not menu_data or not isinstance(menu_data, dict) or "menu" not in menu_data:
            return None

        menu_list = menu_data["menu"]
        if not menu_list:
            return None

        return self._convert_menu_to_markdown(menu_list)

    def _convert_menu_to_markdown(self, menu_data: list[dict[str, Any]]) -> str:
        """Convert structured menu data to markdown format"""
        markdown_lines = []

        for category in menu_data:
            category_name = category.get("category", "Unknown Category")
            markdown_lines.append(f"## {category_name}")
            markdown_lines.append("")

            items = category.get("items", [])
            for item in items:
                item_name = item.get("name", "Unknown Item")
                price = item.get("price", "")
                description = item.get("description", "")

                # Add item header
                if price:
                    markdown_lines.append(f"### {item_name}")
                    markdown_lines.append(f"**Price:** {price}")
                else:
                    markdown_lines.append(f"### {item_name}")

                # Add description if available
                if description:
                    markdown_lines.append(f"{description}")

                markdown_lines.append("")

            markdown_lines.append("")

        return "\n".join(markdown_lines)


async def build_menu_from_url(
    url: str,
    use_stealth_proxy: bool = False,
) -> str:
    """
    Build menu data from a restaurant URL using Firecrawl.

    Args:
        url (str): The URL to build menu from
        use_stealth_proxy (bool): Whether to use stealth proxy for protected sites

    Returns:
        str: Menu data formatted as markdown

    Raises:
        ValueError: If there's an error building the menu
    """
    try:
        logger.info(f"Starting menu building for URL: {url}")

        builder = MenuBuilder()
        proxy_type = "stealth" if use_stealth_proxy else "auto"

        # Offload blocking work to thread to avoid blocking event loop
        menu_data = await asyncio.wait_for(
            asyncio.to_thread(builder.build, url, proxy_type=proxy_type), timeout=150
        )

        # Validate the returned menu data
        if not menu_data:
            raise ValueError("No menu data could be extracted from the URL")

        # Convert to markdown format
        menu_markdown = builder.output_content_as_markdown(menu_data)
        if not menu_markdown:
            raise ValueError("No menu categories found in the extracted data")

        logger.info(
            f"Successfully built menu markdown: {len(menu_markdown)} characters"
        )
        return menu_markdown

    except ValueError:
        # Client/content issues (no menu data, no categories) → 400 at route layer
        raise
    except asyncio.TimeoutError as e:
        # Timeout is a client issue (site too slow) → 400 at route layer
        raise ValueError(
            "Menu building timed out after 150 seconds - site may be too slow or unresponsive"
        ) from e
    except Exception as e:
        # Internal/server issues (API key, imports, network) → 500 at route layer
        logger.exception("Menu building service error for URL: %s", url)
        raise RuntimeError("Menu building service error") from e
