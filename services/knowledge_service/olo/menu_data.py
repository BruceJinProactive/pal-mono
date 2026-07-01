"""Compile Olo raw menu bundles for handle-backed ProjectIntegration config."""

from __future__ import annotations

from typing import Any

from pal_agents.menu_assets.olo import compile_olo_menu

from ._client import get_restaurant_menu_bundle


def compile_olo_menu_data(
    raw_bundle: dict[str, Any],
    *,
    selected_categories: list[str] | None = None,
    make_unique_categories: list[str] | None = None,
    max_depth: int = 8,
) -> dict[str, Any]:
    """Return compiled Olo menu_data for ProjectIntegration.config."""
    return compile_olo_menu(
        raw_bundle,
        selected_categories=selected_categories,
        make_unique_categories=make_unique_categories,
        max_depth=max_depth,
    )


def fetch_and_compile_olo_menu_data(
    *,
    restaurant_id: str,
    client_id: str,
    client_secret: str,
    general_api_endpoint: str,
    selected_categories: list[str] | None = None,
    make_unique_categories: list[str] | None = None,
    max_depth: int = 8,
) -> dict[str, Any]:
    """Fetch an Olo menu with the existing Olo API client and compile it for config."""
    raw_bundle = get_restaurant_menu_bundle(
        restaurant_id,
        client_id,
        client_secret,
        general_api_endpoint,
    )
    if not raw_bundle:
        raise ValueError(f"Failed to fetch menu for restaurant {restaurant_id}")

    return compile_olo_menu_data(
        raw_bundle,
        selected_categories=selected_categories,
        make_unique_categories=make_unique_categories,
        max_depth=max_depth,
    )
