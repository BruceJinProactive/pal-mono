import json

from fastapi import APIRouter, Depends, File, Form, Path, UploadFile

from api.routes.admin._auth import authenticate_user
from api.routes.endpoints import endpoints
from api.schemas.asset.asset import AssetResponse
from api.schemas.error.error import ErrorResponse
from services.auth_types import UserContext

from . import _implementation

asset_router = APIRouter(prefix=endpoints.ASSETS, tags=["Assets"])


@asset_router.post(
    "/",
    response_model=AssetResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def upload_asset(
    asset: UploadFile = File(...),
    path: str = Form("", description="The desired upload path"),
    metadata: str | None = Form(None),
    context: UserContext = Depends(authenticate_user),
) -> AssetResponse:
    from utils.log import logger

    try:
        if not metadata:
            metadata_dict = {}
        else:
            metadata_dict = json.loads(metadata)
    except json.JSONDecodeError:
        logger.error("Invalid metadata format")
        raise ValueError(f"Invalid metadata format: {metadata}")

    return await _implementation.upload_asset(asset, path, metadata_dict)


@asset_router.get(
    "/",
    response_model=AssetResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def get_asset_by_name(name: str) -> AssetResponse:
    return await _implementation.get_asset_by_name(name)
