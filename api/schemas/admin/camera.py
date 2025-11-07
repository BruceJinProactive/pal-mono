from pydantic import BaseModel, Field


class GetCamerasRequest(BaseModel):
    account_id: str = Field(..., description="Account ID")
    project_id: str = Field(..., description="Project ID")


class GetCamerasResponse(BaseModel):
    cameras: list[str] = Field(
        default=[], description="List of camera folder names/IDs under the project"
    )


class ImageMetadata(BaseModel):
    file_name: str = Field(..., description="Name of the image file")
    url: str = Field(..., description="S3 URL or presigned URL to the image")
    last_modified: str = Field(
        ..., description="ISO 8601 timestamp of when the image was last modified"
    )
    size: int = Field(..., description="Size of the image in bytes")


class GetCameraImagesRequest(BaseModel):
    account_id: str = Field(..., description="Account ID")
    project_id: str = Field(..., description="Project ID")
    camera_name: str = Field(..., description="Camera name/ID")
    seconds: int = Field(
        ..., description="Time range in seconds to retrieve images from", gt=0
    )


class GetCameraImagesResponse(BaseModel):
    images: list[ImageMetadata] = Field(
        default=[], description="List of images within the specified time range"
    )
    total_count: int = Field(default=0, description="Total number of images found")


class GetCameraImageUrlsResponse(BaseModel):
    urls: list[str] = Field(
        default=[], description="List of presigned S3 URLs (valid for 1 hour)"
    )


class CompareCameraCheckpointResponse(BaseModel):
    checkpoint_run_ids: list[str] = Field(
        default=[],
        description="List of checkpoint run IDs created for comparison",
    )
    submission_id: str | None = Field(
        None, description="Batch submission ID for all runs"
    )
    checkpoint_id: str = Field(..., description="ID of the checkpoint used")
    images_to_compare: int = Field(
        default=0, description="Number of images being compared"
    )
    status: str = Field(
        default="processing",
        description="Status of the comparison batch (processing, completed)",
    )
