from urllib.parse import urlparse

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
        url = _utils.construct_s3_url(AWS_ASSET_BUCKET_NAME, AWS_REGION, file.name)

        logger.info("Asset file uploaded successfully.")
        return AssetResponse(url=url)
    except (ClientError, ParamValidationError) as e:
        logger.error(f"S3 write operation failed: {e}")
        raise RuntimeError(f"S3 write operation failed: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred writing asset file: {e}")
        raise RuntimeError(f"An unexpected error occurred writing asset file: {e}")


## Read ##
@_utils.handle_s3_errors
def read_asset_response(asset_response: AssetResponse) -> bytes:
    _utils.check_region_name()
    s3_client = _utils.init_s3(AWS_REGION)

    _utils.check_bucket_name()

    parsed_url = urlparse(asset_response.url)
    bucket_name = parsed_url.netloc.split(".")[0]
    object_key = parsed_url.path.lstrip("/")

    response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
    content = response["Body"].read()  # Read the object content
    return content


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
        url = _utils.construct_s3_url(AWS_ASSET_BUCKET_NAME, AWS_REGION, request.name)
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
        url = _utils.construct_s3_url(AWS_ASSET_BUCKET_NAME, AWS_REGION, request.name)
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
                        url = _utils.construct_s3_url(
                            AWS_ASSET_BUCKET_NAME, AWS_REGION, key
                        )
                        found_urls.append(AssetResponse(url=url))

                except ClientError as e:
                    error_code = e.response["Error"]["Code"]
                    logger.error(
                        f"ClientError for object {key}: {error_code} - {e.response['Error']['Message']}"
                    )
                    continue  # Skip to the next object

    return found_urls
