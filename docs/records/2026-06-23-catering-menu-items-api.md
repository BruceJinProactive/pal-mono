# Catering Menu Items API

Date: 2026-06-23

## Summary

Added the API/service/repository path for reading and updating catering menu
items stored in `catering_menus`, so internal catering surfaces can display a
project's menu rows and persist item name or price corrections.

## Implementation Notes

- Added `GET /catering/projects/{project_id}/menu-items` to return all menu
  items for a project, ordered by item name.
- Added `PATCH /catering/projects/{project_id}/menu-items/{menu_item_id}` to
  update an existing catering menu item's `item_name` and/or `item_price`.
- Added `CateringMenuItem`, `CateringMenuItemListResponse`, and
  `UpdateCateringMenuItemRequest` schemas for the new endpoints.
- Added the async `CateringMenuRepository` and frozen `CateringMenuData` DTO to
  keep catering menu access behind the repository layer.
- Added route-level coverage for listing menu items, returning updated items,
  and surfacing a 404 when an update target is missing.

## Authorization

Listing requires `project.read` for the requested project. Updates require
`project.write`, and the repository scopes the update by both `project_id` and
`menu_item_id`.
