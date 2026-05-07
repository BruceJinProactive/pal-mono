"""
Folk CRM Integration for Mercury Bot

Provides company search functionality via the Folk API.
Used by Mercury's Create Client modal for typeahead company lookup.
"""

from typing import Any, Dict

import httpx

from utils.log import logger
from utils.secret import get_server_secret_with_fallback


def _get_folk_api_key() -> str:
    """Get Folk API key from AWS Secrets Manager with env var fallback."""
    try:
        return get_server_secret_with_fallback("FOLK_API_KEY")
    except ValueError:
        logger.warning("[Folk] FOLK_API_KEY not configured")
        return ""


async def search_companies(query: str) -> list[Dict[str, Any]]:
    """
    Search Folk companies by name and return Slack-compatible options.

    Args:
        query: Search string (minimum 2 characters)

    Returns:
        List of Slack option dicts (max 100) with text/value keys.
    """
    if not query or len(query) < 3:
        return []

    api_key = _get_folk_api_key()
    if not api_key:
        return []

    try:
        async with httpx.AsyncClient(timeout=5.0) as http_client:
            resp = await http_client.get(
                "https://api.folk.app/v1/companies",
                headers={"Authorization": f"Bearer {api_key}"},
                params={
                    "limit": "100",
                    "filter[name][like]": query,
                    "sort": "-createdAt",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        items = data.get("data", {}).get("items", [])
        options = []
        for item in items:
            name = item.get("name", "")
            if not name:
                continue

            # Skip companies that already have an Account Name (already onboarded)
            custom_fields = item.get("customFieldValues", {})
            has_account_name = any(
                isinstance(fields, dict) and fields.get("Account Name")
                for fields in custom_fields.values()
            )
            if has_account_name:
                continue

            # Encode name|email in value for pre-fill on selection
            emails = item.get("emails", [])
            email = emails[0] if emails else ""
            value = f"{name}|{email}"[:75]
            options.append(
                {
                    "text": {"type": "plain_text", "text": name[:75]},
                    "value": value,
                }
            )
        return options[:100]
    except Exception as e:
        logger.error("[Folk] Error searching companies: %s", e, exc_info=True)
        return []
