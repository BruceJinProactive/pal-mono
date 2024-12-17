from fastapi import APIRouter, File, UploadFile

from api.routes.endpoints import endpoints
from api.schemas.asset.asset import AssetResponse
from api.schemas.error.error import ErrorResponse

from . import _implementation

asset_router = APIRouter(prefix=endpoints.ASSETS, tags=["Assets"])


@asset_router.post(
    "/",
    response_model=AssetResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def upload_asset(
    asset: UploadFile = File(...), metadata: dict = {}
) -> AssetResponse:
    return await _implementation.upload_asset(asset, metadata)
