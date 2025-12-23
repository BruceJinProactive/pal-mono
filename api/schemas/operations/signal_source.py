"""Signal Source API schemas.

Defines Pydantic models for signal source configuration validation
and API request/response schemas.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

from db.tables.types import (
    CameraSubtype,
    CloudCameraProvider,
    SignalSourceStatus,
    SignalType,
)

# ============================================================================
# CAMERA SUBTYPE CONFIGS
# ============================================================================


class RTSPCameraConfig(BaseModel):
    """Configuration for RTSP/IP cameras."""

    subtype: Literal[CameraSubtype.rtsp] = CameraSubtype.rtsp

    rtsp_url: str = Field(..., description="RTSP stream URL")
    username: str | None = Field(None, description="Authentication username")
    password: str | None = Field(None, description="Authentication password")
    snapshot_url: str | None = Field(
        None, description="HTTP URL for still image capture"
    )
    snapshot_interval: int = Field(
        300, ge=10, le=3600, description="Seconds between captures"
    )


class CloudCameraConfig(BaseModel):
    """Configuration for cloud camera APIs."""

    subtype: Literal[CameraSubtype.cloud] = CameraSubtype.cloud

    provider: CloudCameraProvider = Field(..., description="Cloud camera provider")
    api_key: str = Field(..., description="Provider API key/token")
    device_id: str = Field(..., description="Camera identifier in provider system")
    location_id: str | None = Field(
        None, description="Location/site ID if required by provider"
    )


class S3RecordingConfig(BaseModel):
    """Configuration for S3 uploaded recordings."""

    subtype: Literal[CameraSubtype.s3] = CameraSubtype.s3


# Discriminated union for camera subtypes
CameraConfigDetails = Annotated[
    Union[RTSPCameraConfig, CloudCameraConfig, S3RecordingConfig],
    Field(discriminator="subtype"),
]


# ============================================================================
# SIGNAL SOURCE CONFIG (V1: Camera only)
# ============================================================================


class CameraSignalConfig(BaseModel):
    """Configuration for camera signal sources."""

    signal_type: Literal[SignalType.camera] = SignalType.camera
    camera: CameraConfigDetails
    camera_id: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Unique camera identifier within the project. Used for upload/lookup.",
    )


# V1: Only camera supported
# Future: SignalSourceConfig = Union[CameraSignalConfig, WeatherSignalConfig, ...]
SignalSourceConfig = CameraSignalConfig


# ============================================================================
# API REQUEST/RESPONSE SCHEMAS
# ============================================================================


class CreateSignalSourceRequest(BaseModel):
    """Request to create a new signal source."""

    name: str = Field(..., min_length=1, max_length=255, description="Source name")
    config: SignalSourceConfig = Field(..., description="Type-specific configuration")
    description: str | None = Field(None, description="Optional description")


class UpdateSignalSourceRequest(BaseModel):
    """Request to update a signal source."""

    name: str | None = Field(None, min_length=1, max_length=255, description="New name")
    config: SignalSourceConfig | None = Field(None, description="Updated configuration")
    description: str | None = Field(None, description="Updated description")
    status: SignalSourceStatus | None = Field(None, description="Updated status")


class SignalSourceResponse(BaseModel):
    """Response model for a signal source."""

    id: uuid.UUID
    account_id: uuid.UUID
    project_id: uuid.UUID | None
    name: str
    signal_type: SignalType
    status: SignalSourceStatus
    status_message: str | None
    config: dict
    description: str | None
    last_capture_at: datetime | None = Field(
        None, description="Last capture time from associated feed"
    )
    created_at: datetime
    updated_at: datetime | None


class ListSignalSourcesResponse(BaseModel):
    """Response for listing signal sources."""

    items: list[SignalSourceResponse]
    total: int
    page: int = 1
    page_size: int = 20
