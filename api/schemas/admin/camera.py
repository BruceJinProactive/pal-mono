from pydantic import BaseModel, Field


class GetCamerasRequest(BaseModel):
    account_id: str = Field(..., description="Account ID")
    project_id: str = Field(..., description="Project ID")


class GetCamerasResponse(BaseModel):
    cameras: list[str] = Field(
        default=[], description="List of camera folder names/IDs under the project"
    )
