"""
Features service schemas for managing feature flags.
"""

from pydantic import BaseModel, Field, field_validator

from db.tables.types import IdentifierType


class CheckFeatureRequest(BaseModel):
    """Check Feature Request"""

    feature: str = Field(..., min_length=1, max_length=255, description="Feature name")
    identifier_type: IdentifierType = Field(
        ..., description="Type of identifier (agent, account, project, user)"
    )
    identifier: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Identifier value (UUID or string ID)",
    )

    @field_validator("feature")
    def validate_feature(cls, v):
        """Ensure feature name is not empty."""
        if not v or not v.strip():
            raise ValueError("Feature name cannot be empty")
        return v.strip()

    @field_validator("identifier")
    def validate_identifier(cls, v):
        """Ensure identifier is not empty."""
        if not v or not v.strip():
            raise ValueError("Identifier cannot be empty")
        return v.strip()


class UpsertFeatureRequest(BaseModel):
    """Upsert Feature Request"""

    feature: str = Field(..., min_length=1, max_length=255, description="Feature name")
    identifier_type: IdentifierType = Field(
        ..., description="Type of identifier (agent, account, project, user)"
    )
    identifier: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Identifier value (UUID or string ID)",
    )
    enabled: bool = Field(..., description="Whether the feature should be enabled")

    @field_validator("feature")
    def validate_feature(cls, v):
        """Ensure feature name is not empty."""
        if not v or not v.strip():
            raise ValueError("Feature name cannot be empty")
        return v.strip()

    @field_validator("identifier")
    def validate_identifier(cls, v):
        """Ensure identifier is not empty."""
        if not v or not v.strip():
            raise ValueError("Identifier cannot be empty")
        return v.strip()


class CheckFeatureResponse(BaseModel):
    """Check Feature Response"""

    feature: str = Field(..., description="Feature name")
    identifier_type: IdentifierType = Field(..., description="Type of identifier")
    identifier: str = Field(..., description="Identifier value")
    enabled: bool = Field(..., description="Whether the feature is enabled")


class UpsertFeatureResponse(BaseModel):
    """Upsert Feature Response"""

    feature: str = Field(..., description="Feature name")
    identifier_type: IdentifierType = Field(..., description="Type of identifier")
    identifier: str = Field(..., description="Identifier value")
    enabled: bool = Field(..., description="Whether the feature is enabled")
    message: str = Field(..., description="Success message")
