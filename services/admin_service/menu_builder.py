import asyncio
import io
import json
from typing import Any, Optional, cast

from firecrawl import Firecrawl
from openai import OpenAI
from openai.types.responses import ResponseInputMessageContentList, ResponseInputParam

from utils.log import logger
from utils.secret import get_client_secret_with_fallback

# Shared extraction prompt for both web scraping and file uploads
MENU_EXTRACTION_PROMPT = """
You are analyzing content to determine if it contains restaurant menu information and extract that data.

STEP 1 - VALIDATION:
First, examine the content to verify it contains a restaurant menu with food/beverage pricing.

IF NOT A MENU, return this exact JSON:
{
  "error": "not_a_menu",
  "message": "This does not appear to contain a restaurant menu. Please provide a menu with food and beverage items and pricing."
}

STEP 2 - MENU EXTRACTION (only if content IS a menu):
Extract and organize ALL menu information comprehensively.

EXTRACTION RULES:
- Extract ALL menu content including items with and without prices
- Include ALL categories: appetizers, salads, soups, entrees, mains, sides, desserts, beverages, drinks, cocktails, wine, beer, coffee, tea, specials, kids menu, lunch menu, dinner menu, breakfast, brunch, etc.
- Look for items in tables, lists, sections, and any formatted content
- Include items with various price formats: $X.XX, $X, X.XX, "Market Price", "MP", "Ask server", ranges like "$12-15"
- If same item appears in multiple sections, keep all instances
- Preserve actual descriptions and prices exactly as shown (when available)
- Clean prices and descriptions by removing trailing ratings, percentages, loading indicators, or review counts
- Capture complete descriptions - include full sentences and all continuation text
- It's acceptable for items to have NO description - include these items anyway
- Include size variations (Small/Large, 8oz/16oz, etc.) as separate items
- Include category sections even if some items don't have clear prices
- Include seasonal items, daily specials, and limited-time offers
- Don't make up any items - only extract what's actually present
- Be extremely thorough - scan entire content multiple times

IMPORTANT: Do NOT remove duplicates. Include ALL instances of items that appear multiple times.

ORDERING RULES:
- PRESERVE THE ORIGINAL ORDER of categories as they appear
- PRESERVE THE ORIGINAL ORDER of items within each category
- Do NOT alphabetize or reorganize
- Keep the exact sequence as presented

FORMATTING RULES:
Return as JSON with this structure:
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

Focus on food and beverage items from official menu sections only.
Ignore promotional content, navigation, technical elements, user reviews, and customer comments.
"""


def convert_menu_to_markdown(menu_data: list[dict[str, Any]]) -> str:
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


class MenuBuilder:
    """Menu builder for restaurant websites and delivery platforms"""

    def __init__(self):
        try:
            api_key = get_client_secret_with_fallback("FIRECRAWL_API_KEY")
        except ValueError as e:
            raise ValueError("Firecrawl API key required.") from e

        self.firecrawl = Firecrawl(api_key=api_key)

    def build(self, url: str, proxy_type: str = "auto") -> Optional[dict[str, Any]]:
        """Build menu data from a URL using LLM extraction"""
        try:
            formats = [{"type": "json", "prompt": MENU_EXTRACTION_PROMPT}]

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
            raise RuntimeError("Menu building failed") from e

    def output_content_as_markdown(self, menu_data: dict[str, Any]) -> Optional[str]:
        """Convert menu data to markdown format"""
        if not menu_data or not isinstance(menu_data, dict) or "menu" not in menu_data:
            return None

        menu_list = menu_data["menu"]
        if not menu_list:
            return None

        return convert_menu_to_markdown(menu_list)


class MenuUploader:
    """Menu builder that processes uploaded files using OpenAI Responses API"""

    def __init__(self):
        try:
            openai_api_key = get_client_secret_with_fallback("OPENAI_API_KEY")
            if not openai_api_key:
                raise ValueError("OpenAI API key not found")
        except Exception as e:
            raise ValueError("OpenAI API key required for file processing.") from e

        self.openai = OpenAI(api_key=openai_api_key)

    @staticmethod
    def _get_file_config(
        content_type: str | None, filename: str | None
    ) -> tuple[str, str, str]:
        """
        Determine file configuration based on content type.

        Returns:
            tuple: (purpose, file_type, default_filename)
        """
        is_pdf = content_type == "application/pdf"

        if is_pdf:
            purpose = "user_data"
            file_type = "input_file"
            default_filename = filename or "menu.pdf"
        else:
            purpose = "user_data"
            file_type = "input_image"
            default_filename = filename or "menu.jpg"

        return purpose, file_type, default_filename

    def _upload_file(self, file_bytes: bytes, purpose: str, filename: str) -> str:
        """Upload file to OpenAI and return file_id"""
        file_obj = io.BytesIO(file_bytes)
        file_obj.name = filename

        uploaded_file = self.openai.files.create(file=file_obj, purpose=purpose)  # type: ignore[arg-type]
        return uploaded_file.id

    def _parse_response_content(self, content: str) -> Optional[dict[str, Any]]:
        """Parse JSON from response content"""
        # Look for JSON in the response
        start_idx = content.find("{")
        end_idx = content.rfind("}") + 1

        if start_idx == -1 or end_idx <= start_idx:
            logger.error("No JSON found in OpenAI response")
            return None

        try:
            json_str = content[start_idx:end_idx]
            parsed_json = json.loads(json_str)

            # Check if OpenAI detected this is not a menu
            if (
                isinstance(parsed_json, dict)
                and parsed_json.get("error") == "not_a_menu"
            ):
                error_message = parsed_json.get(
                    "message",
                    "This file does not appear to contain a restaurant menu.",
                )
                raise ValueError(error_message)

            return parsed_json
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from OpenAI response: {e}")
            return None

    def build_from_bytes(
        self,
        file_bytes: bytes,
        content_type: str | None = None,
        filename: str | None = None,
    ) -> Optional[dict[str, Any]]:
        """Build menu data from file bytes (image or PDF) using OpenAI Responses API"""
        try:
            # Get file configuration
            purpose, file_type, default_filename = self._get_file_config(
                content_type, filename
            )

            # Upload file to OpenAI
            file_id = self._upload_file(file_bytes, purpose, default_filename)

            try:
                # Call Responses API
                # Build content parts with appropriate type based on file
                content_parts_raw = [
                    {"type": "input_text", "text": MENU_EXTRACTION_PROMPT}
                ]

                if file_type == "input_image":
                    content_parts_raw.append(
                        {"type": "input_image", "file_id": file_id, "detail": "auto"}
                    )
                else:  # input_file (PDF)
                    content_parts_raw.append({"type": "input_file", "file_id": file_id})

                # Cast content parts to proper type
                content_parts = cast(
                    ResponseInputMessageContentList,
                    content_parts_raw,
                )

                # Cast input payload to proper type
                input_payload = cast(
                    ResponseInputParam,
                    [{"type": "message", "role": "user", "content": content_parts}],
                )

                response = self.openai.responses.create(
                    model="gpt-4o-mini",
                    input=input_payload,
                )

                # Extract and parse content
                content = response.output_text
                if not content:
                    logger.error(f"No content in response: {response}")
                    return None

                return self._parse_response_content(content)

            finally:
                # Always clean up uploaded file
                try:
                    self.openai.files.delete(file_id)
                except Exception as cleanup_error:
                    logger.warning(
                        f"Failed to delete uploaded file {file_id}: {cleanup_error}"
                    )

        except ValueError:
            # Re-raise ValueError (including our "not_a_menu" errors)
            raise
        except Exception as e:
            logger.exception(f"Error processing file bytes: {e}")
            raise RuntimeError("Menu building from file failed") from e

    def output_content_as_markdown(self, menu_data: dict[str, Any]) -> Optional[str]:
        """Convert menu data to markdown format"""
        if not menu_data or not isinstance(menu_data, dict) or "menu" not in menu_data:
            return None

        menu_list = menu_data["menu"]
        if not menu_list:
            return None

        return convert_menu_to_markdown(menu_list)


async def build_menu_from_url(
    url: str,
    use_stealth_proxy: bool = False,
) -> str:
    """
    Build menu data from a restaurant URL using Firecrawl.

    Args:
        url: The URL to build menu from
        use_stealth_proxy: Whether to use stealth proxy for protected sites

    Returns:
        Menu data formatted as markdown

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
        raise
    except asyncio.TimeoutError as e:
        raise ValueError(
            "Menu building timed out after 150 seconds - site may be too slow or unresponsive"
        ) from e
    except Exception as e:
        logger.exception("Menu building service error for URL: %s", url)
        raise RuntimeError("Menu building service error") from e


async def build_menu_from_upload(
    upload_files,
) -> str:
    """
    Build menu data from uploaded file(s) using OpenAI API.
    Processes all files together in a single API call for better performance.

    Args:
        upload_files: FastAPI UploadFile object or list of UploadFile objects

    Returns:
        Combined menu data formatted as markdown

    Raises:
        ValueError: If there's an error building the menu from the file(s)
    """
    try:
        # Handle both single file and multiple files
        files = upload_files if isinstance(upload_files, list) else [upload_files]
        logger.info(
            f"Starting menu building from {len(files)} uploaded file(s) together"
        )

        uploader = MenuUploader()

        # Step 1: Upload all files and collect file_ids
        file_info_list = []

        async def upload_single_file(upload_file):
            """Upload a single file and return its info"""
            # Validate file type
            if not upload_file.content_type:
                raise ValueError(
                    f"File type could not be determined for {upload_file.filename}"
                )

            is_image = upload_file.content_type.startswith("image/")
            is_pdf = upload_file.content_type == "application/pdf"

            if not (is_image or is_pdf):
                raise ValueError(
                    f"Invalid file type. Expected image or PDF, got: {upload_file.content_type} for {upload_file.filename}"
                )

            # Read file content
            file_bytes = await upload_file.read()
            if not file_bytes:
                raise ValueError(f"Empty file uploaded: {upload_file.filename}")

            # Get file configuration
            purpose, file_type, default_filename = MenuUploader._get_file_config(
                upload_file.content_type, upload_file.filename
            )

            # Upload file
            file_id = await asyncio.to_thread(
                uploader._upload_file, file_bytes, purpose, default_filename
            )

            return {
                "file_id": file_id,
                "file_type": file_type,
                "filename": upload_file.filename,
            }

        # Upload all files concurrently
        file_info_list = await asyncio.gather(
            *[upload_single_file(file) for file in files]
        )

        try:
            # Step 2: Build content parts
            content_parts_raw = [{"type": "input_text", "text": MENU_EXTRACTION_PROMPT}]

            # Add all file references with appropriate type
            for file_info in file_info_list:
                if file_info["file_type"] == "input_image":
                    content_parts_raw.append(
                        {
                            "type": "input_image",
                            "file_id": file_info["file_id"],
                            "detail": "auto",
                        }
                    )
                else:  # input_file (PDF)
                    content_parts_raw.append(
                        {"type": "input_file", "file_id": file_info["file_id"]}
                    )

            # Cast content parts to proper type
            content_parts = cast(
                ResponseInputMessageContentList,
                content_parts_raw,
            )

            # Step 3: Make single API call with all files
            logger.info(f"Processing {len(files)} file(s) together in single API call")

            # Cast input payload to proper type
            input_payload = cast(
                ResponseInputParam,
                [{"type": "message", "role": "user", "content": content_parts}],
            )

            response = await asyncio.to_thread(
                lambda: uploader.openai.responses.create(
                    model="gpt-4o-mini",
                    input=input_payload,
                )
            )

            # Extract and parse content
            content = response.output_text
            if not content:
                logger.error(f"No content in response: {response}")
                raise ValueError("No menu data could be extracted from the files")

            menu_data = uploader._parse_response_content(content)
            if not menu_data or "menu" not in menu_data:
                raise ValueError("No menu categories found in the uploaded files")

            # Convert to markdown
            menu_markdown = convert_menu_to_markdown(menu_data["menu"])
            if not menu_markdown:
                raise ValueError("Failed to convert menu data to markdown format")

            logger.info(
                f"Successfully built combined menu markdown from {len(files)} file(s): {len(menu_markdown)} characters"
            )
            return menu_markdown

        finally:
            # Clean up all uploaded files
            for file_info in file_info_list:
                try:
                    uploader.openai.files.delete(file_info["file_id"])
                except Exception as cleanup_error:
                    logger.warning(
                        f"Failed to delete uploaded file {file_info['file_id']}: {cleanup_error}"
                    )

    except ValueError:
        raise
    except asyncio.TimeoutError as e:
        raise ValueError(
            "Menu building timed out after 300 seconds - files may be too complex or unreadable"
        ) from e
    except Exception as e:
        logger.exception("Menu building service error for uploaded files")
        raise RuntimeError("Menu building service error") from e
