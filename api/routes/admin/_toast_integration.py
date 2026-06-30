"""Toast-specific integration route handlers."""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

import db
from api.schemas.admin.pos_onboarding import DiningOption, ToastOptionsResponse
from services.integration_service._utils import _get_integration_credentials
from services.knowledge_service.toast._client import download_menu, get_dining_options
from tools.toast_tool._apis import get_toast_access_token
from utils.log import logger

from ._utils import UserContext

_TAKE_OUT_BEHAVIORS = {"TAKE_OUT", "TAKEOUT"}
_DELIVERY_BEHAVIORS = {"DELIVERY"}


def _extract_menu_names(raw_menu: dict[str, Any]) -> list[str]:
    return [
        m["name"]
        for m in raw_menu.get("menus", [])
        if isinstance(m, dict) and m.get("name")
    ]


def _parse_dining_options(dining_options_json: str) -> list[DiningOption]:
    try:
        options = json.loads(dining_options_json)
    except (json.JSONDecodeError, TypeError):
        return []
    result = []
    for opt in options:
        if not isinstance(opt, dict):
            continue
        guid = _string_or_empty(opt.get("guid"))
        name = _string_or_empty(opt.get("name"))
        behavior = _string_or_empty(opt.get("behavior"))
        if guid and name:
            result.append(DiningOption(guid=guid, name=name, behavior=behavior))
    return result


def _string_or_empty(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _suggest_guids(
    dining_options: list[DiningOption],
) -> tuple[str | None, str | None]:
    takeout = [o for o in dining_options if o.behavior.upper() in _TAKE_OUT_BEHAVIORS]
    delivery = [o for o in dining_options if o.behavior.upper() in _DELIVERY_BEHAVIORS]
    return (
        takeout[0].guid if len(takeout) == 1 else None,
        delivery[0].guid if len(delivery) == 1 else None,
    )


def get_toast_options(
    account_name: str,
    integration_id: uuid.UUID,
    restaurant_guid: str,
    context: UserContext,
    session: Session,
) -> ToastOptionsResponse:
    """Fetch available menus and dining options for a Toast restaurant.

    Reads credentials from the stored Integration — no secrets in the URL.
    No database writes.
    """
    account_repo = db.AccountRepository(session)
    account = account_repo.get_account(account_name)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {account_name!r} not found",
            headers={"Content-Type": "application/json"},
        )

    integration_repo = db.IntegrationRepository(session)
    integration = integration_repo.get_integration_by_id(account.id, integration_id)
    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration {integration_id} not found",
            headers={"Content-Type": "application/json"},
        )

    try:
        credentials = _get_integration_credentials(integration.secret_key)
    except (KeyError, ValueError) as exc:
        logger.error(
            "[ToastIntegration] Failed to read credentials",
            extra={"integration_id": str(integration_id), "error": str(exc)},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not read integration credentials",
            headers={"Content-Type": "application/json"},
        )

    client_id = credentials.get("client_id")
    client_secret = credentials.get("client_secret")
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Integration is missing client_id or client_secret",
            headers={"Content-Type": "application/json"},
        )

    bearer_token = get_toast_access_token(
        client_id=client_id,
        client_secret=client_secret,
    )
    if bearer_token is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Toast authentication failed — check integration credentials",
            headers={"Content-Type": "application/json"},
        )

    try:
        raw_menu = download_menu(bearer_token, restaurant_guid)
    except (RuntimeError, ValueError) as exc:
        logger.error(
            "[ToastIntegration] Failed to download menu",
            extra={"restaurant_guid": restaurant_guid, "error": str(exc)},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to download Toast menu",
            headers={"Content-Type": "application/json"},
        )

    try:
        dining_options_json = get_dining_options(bearer_token, restaurant_guid)
    except RuntimeError as exc:
        logger.error(
            "[ToastIntegration] Failed to fetch dining options",
            extra={"restaurant_guid": restaurant_guid, "error": str(exc)},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to fetch Toast dining options",
            headers={"Content-Type": "application/json"},
        )

    menu_names = _extract_menu_names(raw_menu)
    dining_options = _parse_dining_options(dining_options_json)
    suggested_takeout, suggested_delivery = _suggest_guids(dining_options)

    logger.info(
        "[ToastIntegration] Options fetched",
        extra={
            "account_name": account_name,
            "integration_id": str(integration_id),
            "restaurant_guid": restaurant_guid,
            "menu_count": len(menu_names),
            "dining_option_count": len(dining_options),
        },
    )

    return ToastOptionsResponse(
        available_menus=menu_names,
        dining_options=dining_options,
        suggested_takeout_guid=suggested_takeout,
        suggested_delivery_guid=suggested_delivery,
    )
