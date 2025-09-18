"""
Square API client for menu data retrieval.

This module talks directly to Square's Catalog API using the provided
access token and composes a location-aware menu structure suitable for
formatting and indexing.
"""

import re
from typing import Any, Dict, List, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from utils.log import logger


class SquareAPIError(ValueError):
    """Raised for non-successful Square API responses.

    Carries HTTP status, endpoint, and response text so callers/UI can
    surface clear diagnostics (e.g., invalid token, insufficient scopes).
    """

    def __init__(
        self,
        status_code: int,
        endpoint: str,
        response_text: str,
        request_id: str | None = None,
    ):
        self.status_code = status_code
        self.endpoint = endpoint
        self.response_text = response_text
        self.request_id = request_id
        rid = f" request_id={request_id}" if request_id else ""
        super().__init__(
            f"Square API {endpoint} failed: HTTP {status_code}{rid}. Body: {response_text[:500]}"
        )


SQUARE_API_BASE = "https://connect.squareup.com/v2"
SQUARE_API_VERSION = "2025-08-20"

# HTTP session with basic retries for transient errors
_session = requests.Session()
_session.mount(
    "https://",
    HTTPAdapter(
        max_retries=Retry(
            total=3,
            backoff_factor=1.0,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )
    ),
)


def download_menu(access_token: str, location_id: str) -> Dict[str, Any]:
    """Fetch and assemble Square catalog into extracted menu items.

    Items include resolved categories, location-aware modifiers, and
    variations pre-filtered for the requested location.
    """
    try:
        logger.debug(
            "[square._client.download_menu] Fetching Square catalog",
            extra={
                "location_id": location_id,
                "square_api_version": SQUARE_API_VERSION,
            },
        )

        # Pull required object types
        items_data = _fetch_all(access_token, ["ITEM"]) or {"objects": []}
        mods_data = _fetch_all(access_token, ["MODIFIER", "MODIFIER_LIST"]) or {
            "objects": []
        }
        cats_data = _fetch_all(access_token, ["CATEGORY"]) or {"objects": []}

        raw_counts = {
            "items_objects": len(items_data.get("objects", [])),
            "modifiers_objects": len(
                [o for o in mods_data.get("objects", []) if o.get("type") == "MODIFIER"]
            ),
            "modifier_lists_objects": len(
                [
                    o
                    for o in mods_data.get("objects", [])
                    if o.get("type") == "MODIFIER_LIST"
                ]
            ),
            "categories_objects": len(cats_data.get("objects", [])),
        }

        logger.debug(
            "[square._client.download_menu] Raw catalog counts",
            extra={
                "location_id": location_id,
                **raw_counts,
            },
        )

        extracted_items = _extract_items(items_data, mods_data, cats_data, location_id)

        result = {
            "location_id": location_id,
            "items": extracted_items,
            "item_count": len(extracted_items),
            "raw_counts": raw_counts,
        }

        if result["item_count"] == 0:
            logger.warning(
                "[square._client.download_menu] Extracted 0 items. Possible causes: empty catalog, token lacks catalog read scopes, or location mismatch.",
                extra={
                    "location_id": location_id,
                    **raw_counts,
                },
            )

        return result
    except SquareAPIError:
        # Propagate explicit API failures so the admin route can return 4xx with details
        raise
    except Exception as e:
        raise RuntimeError(f"Error downloading Square menu: {e}")


def _fetch_all(access_token: str, types: List[str]) -> Optional[Dict[str, Any]]:
    """List catalog objects for the given types with pagination."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Square-Version": SQUARE_API_VERSION,
    }
    params = {"types": ",".join(types)}
    cursor: Optional[str] = None
    all_objects: List[Dict[str, Any]] = []

    while True:
        if cursor:
            params["cursor"] = cursor
        resp = _session.get(
            f"{SQUARE_API_BASE}/catalog/list",
            headers=headers,
            params=params,
            timeout=30,
        )
        if resp.status_code != 200:
            request_id = resp.headers.get("x-request-id") or resp.headers.get(
                "X-Request-Id"
            )
            logger.error(
                "Square list_catalog failed",
                extra={
                    "status": resp.status_code,
                    "endpoint": "/v2/catalog/list",
                    "request_id": request_id,
                    "square_api_version": SQUARE_API_VERSION,
                    "response_excerpt": resp.text[:500],
                    "types": ",".join(types),
                    "cursor_present": bool(cursor),
                },
            )
            raise SquareAPIError(
                resp.status_code, "/v2/catalog/list", resp.text, request_id
            )

        data = resp.json()
        all_objects.extend(data.get("objects", []))
        cursor = data.get("cursor")
        if not cursor:
            break

    return {"objects": all_objects}


def _extract_items(
    item_data: Dict[str, Any],
    modifier_data: Dict[str, Any],
    category_data: Dict[str, Any],
    location_id: str,
) -> List[Dict[str, Any]]:
    """Compose location-aware items with variations, categories, and modifiers."""
    # Lookups
    modifier_lookup: Dict[str, Dict[str, Any]] = {}
    modifier_list_lookup: Dict[str, Dict[str, Any]] = {}
    category_lookup: Dict[str, Dict[str, Any]] = {}

    for obj in modifier_data.get("objects", []):
        if obj.get("type") == "MODIFIER" and _meets_location(obj, location_id):
            modifier_lookup[obj.get("id")] = obj
        elif obj.get("type") == "MODIFIER_LIST" and _meets_location(obj, location_id):
            modifier_list_lookup[obj.get("id")] = obj

    for obj in category_data.get("objects", []):
        if obj.get("type") == "CATEGORY" and _meets_location(obj, location_id):
            category_lookup[obj.get("id")] = obj

    results: List[Dict[str, Any]] = []
    for item_obj in item_data.get("objects", []):
        if item_obj.get("type") != "ITEM":
            continue

        item_id = item_obj.get("id")
        item_data_block = item_obj.get("item_data", {})
        item_name = item_data_block.get("name") or "Unnamed Item"

        # Skip items with names starting with T + digits (script behavior)
        if item_name and re.match(r"^T\s*\d+\b", item_name):
            continue

        # Collect valid variations (respect location overrides first)
        variations_out: List[Dict[str, Any]] = []
        for var in item_data_block.get("variations", []) or []:
            if not _variation_meets_location(var, item_obj, location_id):
                continue
            var_id = var.get("id")
            var_name = var.get("item_variation_data", {}).get("name") or ""
            price = _get_var_price_string(var, location_id)
            variations_out.append(
                {
                    "variation_id": var_id,
                    "variation_name": var_name,
                    "price": price,
                }
            )

        if not variations_out:
            continue

        # Categories with resolved names
        categories_out: List[Dict[str, Any]] = []
        for cat_ref in item_data_block.get("categories", []) or []:
            cat_id = cat_ref.get("id")
            cat_obj = category_lookup.get(cat_id)
            categories_out.append(
                {
                    "category_id": cat_id,
                    "category_name": (
                        (cat_obj or {}).get("category_data", {}).get("name")
                        or "Category None"
                    ),
                    "ordinal": cat_ref.get("ordinal", 0),
                }
            )

        # Modifier lists: include only modifiers available at location
        modifier_lists_out: List[Dict[str, Any]] = []
        for info in item_data_block.get("modifier_list_info", []) or []:
            mod_list_id = info.get("modifier_list_id")
            mod_list_obj = modifier_list_lookup.get(mod_list_id)
            if not mod_list_obj:
                continue
            mod_list_data = mod_list_obj.get("modifier_list_data", {})

            modifiers_out: List[Dict[str, Any]] = []
            for mod_ref in mod_list_data.get("modifiers", []) or []:
                mod_id = mod_ref.get("id")
                mod_obj = modifier_lookup.get(mod_id)
                if not mod_obj or not _meets_location(mod_obj, location_id):
                    continue
                mod_data = mod_obj.get("modifier_data", {})
                # Prefer location override price when available
                price_money = None
                for ov in mod_data.get("location_overrides", []) or []:
                    if ov.get("location_id") == location_id and ov.get("price_money"):
                        price_money = ov["price_money"]
                        break
                if price_money is None:
                    price_money = mod_data.get("price_money") or {}
                amount = int(price_money.get("amount", 0) or 0)
                currency = price_money.get("currency", "USD") or "USD"
                modifiers_out.append(
                    {
                        "modifier_id": mod_id,
                        "name": mod_data.get("name", ""),
                        "price_amount": amount,
                        "price_currency": currency,
                    }
                )

            if not modifiers_out:
                continue

            min_sel, max_sel = _resolve_selection_limits(info, mod_list_data)
            modifier_lists_out.append(
                {
                    "modifier_list_id": mod_list_id,
                    "name": mod_list_data.get("name", ""),
                    "selection_type": mod_list_data.get("selection_type", "SINGLE"),
                    "min_selected": min_sel,
                    "max_selected": max_sel,
                    "modifiers": modifiers_out,
                }
            )

        description = item_data_block.get(
            "description_plaintext"
        ) or item_data_block.get("description", "")

        results.append(
            {
                "item_id": item_id,
                "item_name": item_name,
                "description": description or "",
                "categories": categories_out,
                "variations": variations_out,
                "modifier_lists": modifier_lists_out,
                "is_taxable": item_data_block.get("is_taxable", True),
                "product_type": item_data_block.get("product_type", ""),
            }
        )

    return results


def _meets_location(obj: Dict[str, Any], location_id: str) -> bool:
    if obj.get("present_at_all_locations", False) and location_id not in (
        obj.get("absent_at_location_ids", []) or []
    ):
        return True
    return location_id in (obj.get("present_at_location_ids", []) or [])


def _variation_meets_location(
    variation: Dict[str, Any], item_obj: Dict[str, Any], location_id: str
) -> bool:
    # Respect explicit absences first
    if location_id in (variation.get("absent_at_location_ids", []) or []):
        return False
    if location_id in (item_obj.get("absent_at_location_ids", []) or []):
        return False

    overrides = (
        variation.get("item_variation_data", {}).get("location_overrides", []) or []
    )
    for ov in overrides:
        if ov.get("location_id") == location_id:
            return True

    if variation.get("present_at_all_locations", False):
        return True
    if location_id in (variation.get("present_at_location_ids", []) or []):
        return True

    if item_obj.get("present_at_all_locations", False):
        return True
    if location_id in (item_obj.get("present_at_location_ids", []) or []):
        return True
    return False


def _format_money(amount_minor: int, currency: str) -> str:
    """Format Square Money using ISO 4217 minor unit digits.

    Square's Money.amount is in minor units. Convert to major units using
    the currency's number of minor unit digits (default 2).
    """
    minor_unit_digits: Dict[str, int] = {
        # Common currencies
        "USD": 2,
        "EUR": 2,
        "GBP": 2,
        "CAD": 2,
        "AUD": 2,
        "NZD": 2,
        "JPY": 0,
        "KRW": 0,
        "VND": 0,
        "TND": 3,
        "BHD": 3,
        "KWD": 3,
        "OMR": 3,
    }
    code = (currency or "USD").upper()
    digits = minor_unit_digits.get(code, 2)
    if digits == 0:
        major = str(int(amount_minor))
    else:
        major = f"{amount_minor / (10 ** digits):.{digits}f}"
    if code == "USD":
        return f"${major}"
    return f"{major} {code}"


def _get_var_price_string(variation: Dict[str, Any], location_id: str) -> str:
    var_data = variation.get("item_variation_data", {})
    # location overrides first
    for ov in var_data.get("location_overrides", []) or []:
        if ov.get("location_id") == location_id and ov.get("price_money"):
            amt = int(ov["price_money"].get("amount", 0) or 0)
            cur = ov["price_money"].get("currency", "USD") or "USD"
            return _format_money(amt, cur)
    # fallback to default
    price_money = var_data.get("price_money") or {}
    amt = int(price_money.get("amount", 0) or 0)
    cur = price_money.get("currency", "USD") or "USD"
    return _format_money(amt, cur)


def _resolve_selection_limits(
    info: Dict[str, Any], mod_list_data: Dict[str, Any]
) -> Tuple[int, Optional[int]]:
    """Resolve min/max selection using Square modifier metadata."""
    info_min = info.get("min_selected_modifiers", -1)
    info_max = info.get("max_selected_modifiers", -1)
    list_min = mod_list_data.get("minimum_selected_modifiers", -1)
    list_max = mod_list_data.get("maximum_selected_modifiers", -1)

    # minimum
    if info_min == -1:
        min_selected = (
            0 if list_min in (-1, None) or list_min < -1 else max(0, list_min)
        )
    else:
        min_selected = 0 if info_min < -1 else max(0, info_min)

    # maximum: None means unbounded
    max_selected: Optional[int]
    if info_max == -1:
        if list_max in (-1, None) or list_max < -1:
            max_selected = 1
        elif list_max == 0:
            max_selected = None
        else:
            max_selected = int(list_max)
    else:
        if info_max == 0 or info_max < -1:
            max_selected = None
        else:
            max_selected = int(info_max)

    return int(min_selected), max_selected
