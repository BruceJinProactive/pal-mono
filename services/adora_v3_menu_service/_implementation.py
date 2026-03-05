from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pal_agents.providers.adora._implementation import AdoraCompiledMenuV1

from ._compile_adora_menu_v2 import compile_menu_v2
from ._generate_menu_v9 import (
    WarningTracker,
    build_llm_menu_v9,
    render_markdown,
    verify_llm_menu_v9,
)


@dataclass(frozen=True)
class AdoraV3MenuAssets:
    english_menu_prompt: str
    menu_data: dict[str, Any]


def build_menu_assets(raw_menu: dict[str, Any]) -> AdoraV3MenuAssets:
    """Build both prompt-facing and tool-facing menu assets from raw Adora JSON."""
    source_menu = dict(raw_menu)
    store_id = source_menu.get("store_id")
    if not isinstance(store_id, str) or not store_id.strip():
        raise ValueError("Raw Adora menu must contain a non-empty store_id")

    warning_tracker = WarningTracker()
    llm_menu_model = build_llm_menu_v9(source_menu, warnings=warning_tracker)
    verify_llm_menu_v9(llm_menu_model)
    english_menu_prompt = render_markdown(llm_menu_model)

    compiled_menu = compile_menu_v2(source_menu)
    validated_menu_data = AdoraCompiledMenuV1.model_validate(compiled_menu).model_dump(
        mode="python"
    )

    return AdoraV3MenuAssets(
        english_menu_prompt=english_menu_prompt,
        menu_data=validated_menu_data,
    )
