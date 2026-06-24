# Account Catering Menu Import

## Summary

Added an account-scoped admin import endpoint for safely populating
`catering_menus` from a flat CSV upload.

## Changes

- Added `POST /admin/accounts/{account_name}/catering/menu-items/import`.
- Added `CateringMenuImportResponse` for reporting parsed rows, projects
  updated, inserted rows, and updated rows.
- The CSV parser accepts `item_name,item_price` columns, with `name,price`
  aliases for simpler hand-authored files.
- The import resolves the account server-side and applies rows to each project
  under that account, so callers do not provide project IDs.
- The write path only inserts or updates `catering_menus` rows.

## Notes

This keeps direct database writes out of operator workflows while preserving the
existing project-scoped catering menu read path used by internal catering
surfaces.
