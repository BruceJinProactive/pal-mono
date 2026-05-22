"""Schemas for POS onboarding endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DiningOption(BaseModel):
    """A dining option returned by the Toast options endpoint."""

    guid: str = Field(..., description="Toast dining option GUID")
    name: str = Field(..., description="Display name of the dining option")
    behavior: str = Field(..., description="Behavior type, e.g. TAKE_OUT or DELIVERY")


class ToastOptionsResponse(BaseModel):
    """Response from GET /accounts/{account_name}/integrations/{integration_id}/toast/options."""

    available_menus: list[str] = Field(
        ..., description="Top-level menu names from the raw Toast menu"
    )
    dining_options: list[DiningOption] = Field(
        ..., description="All dining options for the restaurant"
    )
    suggested_takeout_guid: str | None = Field(
        default=None,
        description="Suggested takeout GUID when exactly one TAKE_OUT option exists",
    )
    suggested_delivery_guid: str | None = Field(
        default=None,
        description="Suggested delivery GUID when exactly one DELIVERY option exists",
    )
