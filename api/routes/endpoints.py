from dataclasses import dataclass


@dataclass
class ApiEndpoints:
    ADMIN: str = "/admin"
    CHAT: str = "/chat"
    HEALTH: str = "/health"
    PING: str = "/ping"
    ASSETS: str = "/assets"
    INTEGRATIONS: str = "/integrations"
    OPERATION: str = "/operation"
    CATERING: str = "/catering"
    ADMIN_ACCOUNT_CATERING_MENU_IMPORT: str = (
        "/accounts/{account_name}/catering/menu-items/import"
    )
    CATERING_PROJECT_MENU_ITEMS: str = "/projects/{project_id}/menu-items"
    CATERING_PROJECT_MENU_ITEM: str = "/projects/{project_id}/menu-items/{menu_item_id}"
    TELEPHONY: str = "/telephony"
    EVAL: str = "/eval"
    SNAPSHOTS: str = "/snapshots"


endpoints = ApiEndpoints()
