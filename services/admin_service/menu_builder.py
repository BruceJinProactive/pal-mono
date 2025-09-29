import asyncio
import base64
import json
from typing import Any, Optional

from firecrawl import Firecrawl
from openai import OpenAI

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


# Menu Uploader for admin console which supports menu update for clients
class MenuUploader:
    """Menu builder that processes uploaded files using OpenAI"""

    def __init__(self):
        try:
            openai_api_key = get_client_secret_with_fallback("OPENAI_API_KEY")
            if not openai_api_key:
                raise ValueError("OpenAI API key not found")
        except Exception as e:
            raise ValueError("OpenAI API key required for file processing.") from e

        self.openai = OpenAI(api_key=openai_api_key)
        # Create MenuBuilder instance to reuse its markdown conversion method
        self.menu_builder = MenuBuilder()

    def _get_mime_type_from_content_type(self, content_type: str | None) -> str:
        """Get MIME type from content type header"""
        if content_type and content_type.startswith("image/"):
            return content_type
        return "image/jpeg"  # Default fallback

    def _get_extract_prompt(self) -> str:
        """Get the extraction prompt for image analysis"""
        return """
        You are analyzing an image to determine if it contains restaurant menu information and extract that data.

        STEP 1 - IMAGE VALIDATION:
        First, carefully examine the image to determine if it actually contains a restaurant menu or food/beverage pricing information.

        IF THE IMAGE IS NOT A MENU (examples of non-menu images):
        - Random photos (selfies, landscapes, animals, objects, etc.)
        - Business documents, receipts, invoices, or contracts
        - Screenshots of apps/websites that aren't menus
        - Text documents, letters, or forms
        - Business cards or flyers
        - Images with no food/beverage items or pricing
        - Blurry, corrupted, or unreadable images

        Return this exact JSON structure for non-menu images:
        {
          "error": "not_a_menu",
          "message": "This image does not appear to contain a restaurant menu. Please upload a clear image of a menu with food and beverage items and pricing."
        }

        STEP 2 - MENU EXTRACTION (only if image IS a menu):
        If the image clearly contains a restaurant menu with food/beverage items, extract and organize ALL menu information comprehensively.

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
        - Be extremely thorough - scan entire image multiple times for menu items

        IMPORTANT: Do NOT remove duplicates. If the same item appears in multiple sections 
        (like Featured Items, Most Ordered, and category sections), include ALL instances.
        Each appearance may have different context, pricing, or section-specific information.

        ORDERING RULES:
        - PRESERVE THE ORIGINAL ORDER of categories as they appear on the menu
        - PRESERVE THE ORIGINAL ORDER of items within each category
        - Do NOT alphabetize or reorganize categories
        - Do NOT alphabetize or reorganize items within categories
        - Keep the exact sequence as presented on the original menu

        FORMATTING RULES FOR VALID MENUS:
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

    def build_from_bytes(
        self, image_bytes: bytes, content_type: str | None = None
    ) -> Optional[dict[str, Any]]:
        """Build menu data from image bytes using OpenAI Vision"""
        try:
            # Get MIME type from content type or default
            mime_type = self._get_mime_type_from_content_type(content_type)

            # Encode image bytes to base64
            base64_image = base64.b64encode(image_bytes).decode("utf-8")

            # Prepare the prompt
            extract_prompt = self._get_extract_prompt()

            # Make API call to OpenAI Vision
            response = self.openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": extract_prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{base64_image}",
                                },
                            },
                        ],
                    }
                ],
                max_tokens=4000,
                temperature=0.1,
            )

            # Extract and parse the response
            content = response.choices[0].message.content
            if not content:
                return None

            # Try to parse JSON from the response
            try:
                # Look for JSON in the response
                start_idx = content.find("{")
                end_idx = content.rfind("}") + 1
                if start_idx != -1 and end_idx > start_idx:
                    json_str = content[start_idx:end_idx]
                    parsed_json = json.loads(json_str)

                    # Check if OpenAI detected this is not a menu
                    if (
                        isinstance(parsed_json, dict)
                        and parsed_json.get("error") == "not_a_menu"
                    ):
                        # Raise a specific ValueError with the AI's message
                        error_message = parsed_json.get(
                            "message",
                            "This image does not appear to contain a restaurant menu.",
                        )
                        raise ValueError(error_message)

                    return parsed_json
                else:
                    logger.error("No JSON found in OpenAI response")
                    return None
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON from OpenAI response: {e}")
                return None

        except ValueError:
            # Re-raise ValueError (including our "not_a_menu" errors) without modification
            raise
        except Exception as e:
            logger.exception(f"Error processing image bytes: {e}")
            raise RuntimeError("Menu building from image failed") from e

    def output_content_as_markdown(self, menu_data: dict[str, Any]) -> Optional[str]:
        """Convert menu data to markdown format"""
        if not menu_data or not isinstance(menu_data, dict) or "menu" not in menu_data:
            return None

        menu_list = menu_data["menu"]
        if not menu_list:
            return None

        # Reuse MenuBuilder's markdown conversion method
        return self.menu_builder._convert_menu_to_markdown(menu_list)


async def build_menu_from_upload(
    upload_files,  # UploadFile or list[UploadFile] - avoiding import here for flexibility
) -> str:
    """
    Build menu data from uploaded image file(s) using OpenAI Vision.
    Handles FastAPI UploadFile objects directly without saving to disk.
    Supports both single file and multiple files.

    Args:
        upload_files: FastAPI UploadFile object or list of UploadFile objects containing images

    Returns:
        str: Combined menu data formatted as markdown

    Raises:
        ValueError: If there's an error building the menu from the image(s)
    """
    try:
        # Handle both single file and multiple files
        files = upload_files if isinstance(upload_files, list) else [upload_files]

        logger.info(f"Starting menu building from {len(files)} uploaded file(s)")

        async def process_single_file(upload_file):
            """Process a single uploaded file"""
            # Validate file type
            if not upload_file.content_type or not upload_file.content_type.startswith(
                "image/"
            ):
                raise ValueError(
                    f"Invalid file type. Expected image, got: {upload_file.content_type}"
                )

            # Read file content
            image_bytes = await upload_file.read()

            if not image_bytes:
                raise ValueError(f"Empty file uploaded: {upload_file.filename}")

            uploader = MenuUploader()

            # Offload blocking work to thread to avoid blocking event loop
            menu_data = await asyncio.wait_for(
                asyncio.to_thread(
                    uploader.build_from_bytes, image_bytes, upload_file.content_type
                ),
                timeout=300,
            )

            # Validate the returned menu data
            if not menu_data:
                raise ValueError(
                    f"No menu data could be extracted from {upload_file.filename}"
                )

            return menu_data, upload_file.filename, uploader

        # Process all files concurrently
        results = await asyncio.gather(*[process_single_file(file) for file in files])

        # Combine all menu data
        combined_menu = []
        last_uploader = None

        for menu_data, filename, uploader in results:
            last_uploader = uploader  # Keep reference to reuse
            if menu_data and "menu" in menu_data:
                # Add filename as a section header for multiple files
                if len(files) > 1:
                    combined_menu.append(
                        {"category": f"Menu from {filename}", "items": []}
                    )
                combined_menu.extend(menu_data["menu"])

        if not combined_menu:
            raise ValueError("No menu categories found in any of the uploaded files")

        # Convert combined data to markdown - reuse existing uploader instance
        if not last_uploader:
            # Fallback: create new uploader if none available (shouldn't happen with valid files)
            last_uploader = MenuUploader()
        menu_markdown = last_uploader.menu_builder._convert_menu_to_markdown(
            combined_menu
        )

        if not menu_markdown:
            raise ValueError("Failed to convert menu data to markdown format")

        logger.info(
            f"Successfully built combined menu markdown from {len(files)} file(s): {len(menu_markdown)} characters"
        )
        return menu_markdown

    except ValueError:
        # Client/content issues (no menu data, no categories, invalid file) → 400 at route layer
        raise
    except asyncio.TimeoutError as e:
        # Timeout is a client issue (processing too slow) → 400 at route layer
        raise ValueError(
            "Menu building timed out after 300 seconds - one or more images may be too complex or unreadable"
        ) from e
    except Exception as e:
        # Internal/server issues (API key, OpenAI errors, file access) → 500 at route layer
        logger.exception("Menu building service error for uploaded files")
        raise RuntimeError("Menu building service error") from e
