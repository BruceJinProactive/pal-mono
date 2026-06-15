"""Compile Olo raw menu bundles for handle-backed ProjectIntegration config."""

from __future__ import annotations

from typing import Any

from pal_agents.menu_assets.olo import compile_olo_menu


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
