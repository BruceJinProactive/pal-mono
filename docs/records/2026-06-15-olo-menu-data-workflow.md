# Olo Menu Data Workflow

**Date**: 2026-06-15
**Status**: Implemented
**Related**: PAL-11481, PAL-11480, PAL-11479

## Context

The new pal-agents Olo provider is handle-backed. It reads compiled
`OloSpec.menu_data` from the project integration config and does not use the
legacy Olo vector-search fields `namespace` or `index_name`.

The existing pal-mono Olo knowledge-service pipeline is a legacy Pinecone
indexing path. It parses Olo menus into text and writes vector documents. That
pipeline is intentionally separate from the new handle-backed Olo ordering
provider.

## Source Of Truth

For `tool_name="olo_v1"`, the runtime source of truth is:

```json
{
  "tool_name": "olo_v1",
  "store_identifier": "259950",
  "config": {
    "menu_data": {
      "version": 1,
      "restaurant_id": "259950",
      "items": [],
      "modifier_groups_by_id": {},
      "modifier_options_by_id": {},
      "option_paths_by_product_id": {}
    }
  }
}
```

`store_identifier` is the Olo restaurant/vendor ID. pal-mono converts it to
`OloSpec.restaurant_id` when building the final pal-agents spec.

## Raw Input Shape

The compiler input is an Olo raw bundle:

```json
{
  "restaurant_id": "259950",
  "menu": {
    "categories": [
      {
        "id": 10,
        "name": "Burgers",
        "products": [
          {
            "id": 100,
            "name": "Cheeseburger"
          }
        ]
      }
    ]
  },
  "modifiers_by_product_id": {
    "100": {
      "optiongroups": []
    }
  }
}
```

This is not the legacy knowledge-service shape that groups products under a
`categories` object for Pinecone indexing.

## Compile Path

Use the pal-mono wrapper when backend code needs to compile Olo menu data:

```python
from services.knowledge_service.olo import compile_olo_menu_data

compiled_menu = compile_olo_menu_data(
    raw_bundle,
    selected_categories=["Burgers"],
    make_unique_categories=["Burgers"],
)
```

The wrapper delegates to `pal_agents.menu_assets.olo.compile_olo_menu`, so the
compiled output shape stays owned by pal-agents.

## Storage Path

For the first Olo setup path, store compiled JSON directly in
`ProjectIntegration.config.menu_data`.

That keeps the runtime simple:

1. Produce the raw Olo bundle.
2. Compile it with `compile_olo_menu_data`.
3. Save the compiled JSON in `ProjectIntegration.config.menu_data`.
4. Build runtime spec through the `olo_v1` ProjectIntegration path.

## Update Path

When the Olo menu changes, recompile the raw bundle and replace
`ProjectIntegration.config.menu_data`. Existing Olo item and selection handles
are menu-version scoped, so old handles should not be reused across a menu-data
replacement.

## Deferred Work

Backend `auto_fetch` is not included in this step. To add it safely, pal-mono
needs a raw-bundle Olo fetcher that returns the compiler input shape:

- raw `/restaurants/{restaurant_id}/menu` response under `menu`
- product modifiers under `modifiers_by_product_id`
- restaurant ID under `restaurant_id`

Do not feed the existing Pinecone-oriented Olo knowledge-service output into
`compile_olo_menu_data`.
