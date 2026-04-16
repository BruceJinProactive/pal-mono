"""Contact service — coordinates Contact and ProjectContact repositories."""

from services.contact_service._implementation import (
    create_for_project,
    delete_from_project,
    get_by_id,
    list_by_project,
    update_for_project,
)

__all__ = [
    "create_for_project",
    "delete_from_project",
    "get_by_id",
    "list_by_project",
    "update_for_project",
]
