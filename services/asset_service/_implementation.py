import os

import boto3
import botocore
import botocore.client
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    NoCredentialsError,
    ParamValidationError,
)

from api.schemas.asset.asset import AssetResponse, ReadAssetRequest, WriteAssetRequest
from utils.log import logger

AWS_ASSET_BUCKET_NAME = os.getenv("AWS_ASSET_BUCKET_NAME", default="DEFAULT_BUCKET")
AWS_REGION = os.environ["AWS_REGION"]


def _check_bucket_name() -> None:
    if not AWS_ASSET_BUCKET_NAME:
        raise ValueError("AWS_ASSET_BUCKET_NAME not found in environment variables")


def _check_region_name() -> None:
    if not AWS_REGION:
        raise ValueError("AWS_REGION not found in environment variables")


def _init_s3(region_name: str) -> botocore.client.BaseClient:
    try:
        s3_client = boto3.client("s3", region_name=region_name)
        return s3_client
    except NoCredentialsError as e:
        raise RuntimeError(f"AWS credentials invalid or not found: {e}")
    except BotoCoreError as e:
        raise RuntimeError(f"Issue with boto3: {e}")
    except Exception as e:
        raise RuntimeError(f"An unexpected error occurred: {e}")


def _construct_s3_url(bucket_name: str, region_name: str, file_name: str) -> str:
    return f"https://{bucket_name}.s3.{region_name}.amazonaws.com/{file_name}"


def write_asset(file: WriteAssetRequest) -> AssetResponse:
    try:
        if not file.name:
            raise ValueError("File name must be provided.")

        if not file.content:
            raise ValueError("File content must be provided.")

        _check_region_name()
        s3_client = _init_s3(AWS_REGION)

        logger.info(
            f"Uploading `{file.name}` to bucket `{AWS_ASSET_BUCKET_NAME}`"
            f"Metadata: {file.metadata}"
        )
        _check_bucket_name()
        s3_client.put_object(
            Bucket=AWS_ASSET_BUCKET_NAME,
            Key=file.name,
            Body=file.content,
            Metadata=file.metadata,
        )
        url = _construct_s3_url(AWS_ASSET_BUCKET_NAME, AWS_REGION, file.name)

        logger.info("Asset file uploaded successfully.")
        return AssetResponse(url=url)
    except (ClientError, ParamValidationError) as e:
        logger.error(f"S3 write operation failed: {e}")
        raise RuntimeError(f"S3 write operation failed: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred writing asset file: {e}")
        raise RuntimeError(f"An unexpected error occurred writing asset file: {e}")


## Read ##
def read_assets(request: ReadAssetRequest) -> list[AssetResponse]:
    try:
        if not request.name and not request.metadata:
            raise ValueError("At least one of `name` or `metadata` must be provided.")

        _check_region_name()
        s3_client = _init_s3(AWS_REGION)

        found_urls: list[AssetResponse] = []
        if request.name:
            _check_bucket_name()
            head = s3_client.head_object(Bucket=AWS_ASSET_BUCKET_NAME, Key=request.name)
            url = _construct_s3_url(AWS_ASSET_BUCKET_NAME, AWS_REGION, request.name)
            found_urls.append(AssetResponse(url=url))
        else:
            # Set up the paginator for listing objects
            paginator = s3_client.get_paginator("list_objects_v2")

            _check_bucket_name()
            # Paginate through all objects in the bucket
            for page in paginator.paginate(Bucket=AWS_ASSET_BUCKET_NAME):
                contents = page.get("Contents", [])

                for obj in contents:
                    key = obj["Key"]

                    try:
                        # Retrieve the object's metadata
                        head = s3_client.head_object(
                            Bucket=AWS_ASSET_BUCKET_NAME, Key=key
                        )
                        metadata = head.get("Metadata", {})

                        # Check if all metadata_filters match
                        if all(
                            metadata.get(k) == v for k, v in request.metadata.items()
                        ):
                            url = _construct_s3_url(
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

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        error_message = e.response["Error"]["Message"]
        if error_code == "NoSuchBucket":
            logger.error(f"The bucket {AWS_ASSET_BUCKET_NAME} does not exist.")
            raise RuntimeError(f"The bucket {AWS_ASSET_BUCKET_NAME} does not exist.")
        elif error_code == "NoSuchKey":
            logger.error(
                f"The file {request.name} does not exist in bucket {AWS_ASSET_BUCKET_NAME}."
            )
            raise RuntimeError(
                f"The file {request.name} does not exist in bucket {AWS_ASSET_BUCKET_NAME}."
            )
        else:
            logger.error(f"AWS ClientError: {error_code}, Message: {error_message}")
            raise RuntimeError(
                f"AWS ClientError: {error_code}, Message: {error_message}"
            )
    except NoCredentialsError as e:
        logger.error(f"AWS credentials invalid or not found: {e}")
        raise RuntimeError(f"AWS credentials invalid or not found: {e}")
    except BotoCoreError as e:
        logger.error(f"Issue with boto3: {e}")
        raise RuntimeError(f"Issue with boto3: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred reading asset file: {e}")
        raise RuntimeError(f"An unexpected error occurred reading asset file: {e}")
