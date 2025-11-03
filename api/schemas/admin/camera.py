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


class UploadBaseImageResponse(BaseModel):
    message: str = Field(..., description="Success message")
    conversation_id: str = Field(
        ..., description="Unique conversation ID for this camera"
    )
    base_image_url: str = Field(..., description="S3 URL of the uploaded base image")
    gpt_response: str = Field(..., description="GPT's acknowledgment of the base image")


class AnalyzeImageRequest(BaseModel):
    prompt: str = Field(
        ...,
        description="Custom analysis prompt to send with the image",
        min_length=1,
    )


class AnalyzeImageResponse(BaseModel):
    conversation_id: str = Field(..., description="Conversation ID used for analysis")
    analysis: str = Field(..., description="GPT's analysis response")
    image_analyzed: str = Field(
        ..., description="Filename of the image that was analyzed"
    )
    timestamp: str = Field(
        ..., description="ISO 8601 timestamp of when the analysis was performed"
    )
