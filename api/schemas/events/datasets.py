import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DatasetActionItem(BaseModel):
    """
    Individual dataset action item.
    Represents a single dataset to be created, updated, or deleted.
    """

    name: str = Field(..., description="Name of the dataset")
    integrated_tool: str = Field(
        ..., description="Name of the integrated tool (e.g., 'waitlist', 'reservation')"
    )
    metric: str = Field(
        ..., description="Evaluation metric (e.g., 'Waitlist Evaluation')"
    )
    updated_at: datetime | None = Field(
        default=None, description="Timestamp of last update (for update actions)"
    )


class DatasetActions(BaseModel):
    """
    Dataset actions to be performed.
    Groups datasets by the action type to be taken on them.
    """

    create: list[DatasetActionItem] = Field(
        default_factory=list, description="Datasets to create"
    )
    update: list[DatasetActionItem] = Field(
        default_factory=list, description="Datasets to update"
    )
    delete: list[DatasetActionItem] = Field(
        default_factory=list, description="Datasets to delete"
    )
    noop: list[Any] = Field(
        default_factory=list,
        description="No operation items (should be empty for phase 3)",
    )


class CreateDatasetRequest(BaseModel):
    """
    Request schema for creating a dataset generation job.
    This is sent from the orchestrator to trigger dataset generation.
    """

    agent_id: uuid.UUID = Field(..., description="Agent UUID")
    project: str = Field(..., description="Project name")
    account_name: str = Field(..., description="Account identifier")
    actions: DatasetActions = Field(..., description="Actions to perform on datasets")


class DatasetGenerationResponse(BaseModel):
    """
    Response schema for successful dataset generation request.
    Returns 202 Accepted with job tracking information.
    """

    job_id: str = Field(..., description="Event ID assigned by PAL-MONO")
    status: str = Field(default="pending", description="Job status")
    actions: DatasetActions = Field(..., description="Actions that will be performed")


class DatasetErrorResponse(BaseModel):
    """
    Error response schema for dataset generation failures.
    Returns 400 Bad Request when validation fails.
    """

    error: str = Field(..., description="Error message describing the failure")
