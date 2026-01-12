from botocore.exceptions import ClientError, ParamValidationError

from api.schemas.asset.asset import AssetResponse, ReadAssetRequest, WriteAssetRequest
from utils.log import logger

from . import _constants, _utils

AWS_ASSET_BUCKET_NAME = _utils.AWS_ASSET_BUCKET_NAME
AWS_REGION = _constants.AWS_REGION


def write_asset(file: WriteAssetRequest) -> AssetResponse:
    try:
        if not file.name:
            raise ValueError("File name must be provided.")

        if not file.content:
            raise ValueError("File content must be provided.")

        _utils.check_region_name()
        s3_client = _utils.init_s3(AWS_REGION)

        logger.info(
            f"Uploading `{file.name}` to bucket `{AWS_ASSET_BUCKET_NAME}`"
            f"Metadata: {file.metadata}"
        )
        _utils.check_bucket_name()
        s3_client.put_object(
            Bucket=AWS_ASSET_BUCKET_NAME,
            Key=file.name,
            Body=file.content,
            Metadata=file.metadata,
        )
        # Return the S3 key instead of presigned URL
        # The API layer will convert to presigned URL when needed
        logger.info("Asset file uploaded successfully.")
        return AssetResponse(url=file.name)
    except (ClientError, ParamValidationError) as e:
        logger.error(f"S3 write operation failed: {e}")
        raise RuntimeError(f"S3 write operation failed: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred writing asset file: {e}")
        raise RuntimeError(f"An unexpected error occurred writing asset file: {e}")


## Read ##
@_utils.handle_s3_errors
def read_asset_by_name(request: ReadAssetRequest) -> AssetResponse:
    """Read single asset by name."""
    if not request.name:
        raise ValueError("Name of the asset not provided.")

    _utils.check_region_name()
    s3_client = _utils.init_s3(AWS_REGION)

    _utils.check_bucket_name()

    # Check if the object exists
    try:
        # Attempt to construct the URL only if the object exists
        s3_client.head_object(Bucket=AWS_ASSET_BUCKET_NAME, Key=request.name)
        url = _utils.generate_presigned_url(
            s3_client, AWS_ASSET_BUCKET_NAME, request.name
        )
        return AssetResponse(url=url)
    except ClientError as e:
        # Handle object not found
        error_code = e.response["Error"]["Code"]
        if error_code == "404":
            return AssetResponse(url="")  # Object doesn't exist
        raise  # Re-raise other exceptions


@_utils.handle_s3_errors
def read_assets(request: ReadAssetRequest) -> list[AssetResponse]:
    """Read assets using either the `name` or `metadata` filters."""

    if not request.name and not request.metadata:
        raise ValueError("At least one of `name` or `metadata` must be provided.")

    _utils.check_region_name()
    s3_client = _utils.init_s3(AWS_REGION)

    found_urls: list[AssetResponse] = []
    if request.name:
        # Find by file name
        _utils.check_bucket_name()
        head = s3_client.head_object(Bucket=AWS_ASSET_BUCKET_NAME, Key=request.name)
        url = _utils.generate_presigned_url(
            s3_client, AWS_ASSET_BUCKET_NAME, request.name
        )
        found_urls.append(AssetResponse(url=url))
    else:
        # Find by metadata filters

        # Set up the paginator for listing objects
        paginator = s3_client.get_paginator("list_objects_v2")

        _utils.check_bucket_name()
        # Paginate through all objects in the bucket
        for page in paginator.paginate(Bucket=AWS_ASSET_BUCKET_NAME):
            contents = page.get("Contents", [])

            for obj in contents:
                key = obj["Key"]

                try:
                    # Retrieve the object's metadata
                    head = s3_client.head_object(Bucket=AWS_ASSET_BUCKET_NAME, Key=key)
                    metadata = head.get("Metadata", {})

                    # Check if all metadata_filters match
                    if all(metadata.get(k) == v for k, v in request.metadata.items()):
                        url = _utils.generate_presigned_url(
                            s3_client, AWS_ASSET_BUCKET_NAME, key
                        )
                        found_urls.append(AssetResponse(url=url))

                except ClientError as e:
                    error_code = e.response["Error"]["Code"]
                    logger.error(
                        f"ClientError for object {key}: {error_code} - {e.response['Error']['Message']}"
                    )
                    continue  # Skip to the next object

    return found_urls


## Delete ##
def delete_asset(file_name: str) -> bool:
    """Delete an asset from S3 by file name.

    Args:
        file_name (str): The name/key of the file to delete from S3.

    Returns:
        bool: True if the file was deleted successfully, False if the file doesn't exist.

    Raises:
        RuntimeError: If the deletion operation fails.
    """
    try:
        if not file_name:
            raise ValueError("File name must be provided.")

        _utils.check_region_name()
        s3_client = _utils.init_s3(AWS_REGION)

        _utils.check_bucket_name()

        # Check if the object exists before attempting to delete
        try:
            s3_client.head_object(Bucket=AWS_ASSET_BUCKET_NAME, Key=file_name)
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "404":
                logger.warning(
                    f"Asset `{file_name}` does not exist in S3, skipping deletion."
                )
                return False
            raise

        # Delete the object
        logger.info(f"Deleting `{file_name}` from bucket `{AWS_ASSET_BUCKET_NAME}`")
        s3_client.delete_object(Bucket=AWS_ASSET_BUCKET_NAME, Key=file_name)
        logger.info(f"Asset file `{file_name}` deleted successfully.")
        return True

    except (ClientError, ParamValidationError) as e:
        logger.error(f"S3 delete operation failed: {e}")
        raise RuntimeError(f"S3 delete operation failed: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred deleting asset file: {e}")
        raise RuntimeError(f"An unexpected error occurred deleting asset file: {e}")
