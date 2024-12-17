from fastapi import HTTPException, UploadFile

from api.schemas.asset.asset import AssetResponse, WriteAssetRequest
from api.schemas.error.error import ErrorResponse
from services.asset_service import write_asset
from utils.log import logger


async def upload_asset(asset: UploadFile, metadata: dict) -> AssetResponse:
    try:
        # Process the message
        logger.info(f"Received asset to upload: {asset.filename}")

        if not asset.filename:
            raise ValueError("File name is required to upload asset.")

        content = await asset.read()

        write_asset_req = WriteAssetRequest(
            name=asset.filename,
            content=content,
            metadata=metadata,
        )

        return write_asset(write_asset_req)

    except ValueError as ve:
        # Log and handle validation errors
        logger.error(f"Error validating asset: {ve}")
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error_code="VALIDATION_ERROR", error_message=str(ve)
            ).model_dump(),
        )
    except Exception as e:
        # Log the error
        logger.error(f"Error processing asset: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                error_code="INTERNAL_SERVER_ERROR",
                error_message="An unexpected error occurred while processing the message",
            ).model_dump(),
        )
