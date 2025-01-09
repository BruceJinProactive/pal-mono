from uuid import uuid4

from pydantic import BaseModel, Field


class WriteAssetRequest(BaseModel):
    name: str = Field(
        default_factory=lambda: uuid4().hex, description="Name of the file."
    )
    content: bytes = Field(..., description="File content in bytes.")
    metadata: dict[str, str] = Field(default={}, description="File metadata.")


class ReadAssetRequest(BaseModel):
    name: str | None = Field(
        default=None, description="Name of file to read from S3 bucket."
    )
    metadata: dict[str, str] = Field(
        default={},
        description="Metadata filters. Used only if file name is empty.",
    )


class AssetResponse(BaseModel):
    url: str = Field(..., description="S3 URL of the written file.")
