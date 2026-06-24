from pydantic import BaseModel, Field


class CateringMenuImportResponse(BaseModel):
    """Response returned after importing account catering menu items from CSV."""

    account_name: str = Field(
        ..., description="Name of the account that received the catering menu import."
    )
    inserted_items: int = Field(
        ..., description="Number of catering menu rows inserted."
    )
    projects_updated: int = Field(
        ..., description="Number of account projects updated by the import."
    )
    rows_received: int = Field(..., description="Number of valid CSV rows parsed.")
    updated_items: int = Field(
        ..., description="Number of existing catering menu rows updated."
    )
