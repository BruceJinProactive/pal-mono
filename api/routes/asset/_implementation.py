import os

from fastapi import HTTPException, UploadFile, status

from api.schemas.asset.asset import AssetResponse, ReadAssetRequest, WriteAssetRequest
from api.schemas.error.error import ErrorResponse
from services.asset_service import read_asset_by_name, write_asset
from utils.log import logger


async def upload_asset(asset: UploadFile, path: str, metadata: dict) -> AssetResponse:
    try:
        # Process the message
        logger.info(f"Received asset to upload: {asset.filename} and path")

        if not asset.filename:
            raise ValueError("File name is required to upload asset.")

        content = await asset.read()

        file_path = os.path.join(path, asset.filename)
        write_asset_req = WriteAssetRequest(
            name=file_path,
            content=content,
            metadata=metadata,
        )

        return write_asset(write_asset_req)

    except ValueError as ve:
        # Log and handle validation errors
        logger.error(f"Error validating asset: {ve}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorResponse(
                error_code="VALIDATION_ERROR", error_message=str(ve)
            ).model_dump(),
        )
    except Exception as e:
        # Log the error
        logger.error(f"Error processing asset: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse(
                error_code="INTERNAL_SERVER_ERROR",
                error_message="An unexpected error occurred while processing the message",
            ).model_dump(),
        )


async def get_asset_by_name(name: str) -> AssetResponse:
    try:
        logger.info(f"Get asset `{name}` from s3 bucket")

        if not name:
            raise ValueError("File name is required to get asset.")

        read_asset_req = ReadAssetRequest(name=name)
        return read_asset_by_name(read_asset_req)

    except ValueError as ve:
        # Log and handle validation errors
        logger.error(f"Error validating asset: {ve}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorResponse(
                error_code="VALIDATION_ERROR", error_message=str(ve)
            ).model_dump(),
        )
    except Exception as e:
        # Log the error
        logger.error(f"Error processing asset: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse(
                error_code="INTERNAL_SERVER_ERROR",
                error_message="An unexpected error occurred while processing the message",
            ).model_dump(),
        )
