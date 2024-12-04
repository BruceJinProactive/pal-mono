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

BUCKET_NAME = os.getenv("AWS_ASSET_BUCKET_NAME", "pal-mono-assets-bucket")
REGION_NAME = os.getenv("AWS_ASSET_REGION_NAME", "us-west-1")


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
        s3_client = _init_s3(REGION_NAME)

        logger.info(
            f"Uploading `{file.name}` to bucket `{BUCKET_NAME}`"
            f"Metadata: {file.metadata}"
        )
        s3_client.put_object(
            Bucket=BUCKET_NAME,
            Key=file.name,
            Body=file.content,
            Metadata=file.metadata,
        )
        url = _construct_s3_url(BUCKET_NAME, REGION_NAME, file.name)

        logger.info("Asset file uploaded successfully.")
        return AssetResponse(url=url)
    except (ClientError, ParamValidationError) as e:
        logger.error(f"S3 write operation failed: {e}")
        raise RuntimeError(f"S3 write operation failed: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred writing asset file: {e}")
        raise RuntimeError(f"An unexpected error occurred writing asset file: {e}")


## Read ##
def read_asset(file: ReadAssetRequest) -> list[AssetResponse]:
    try:
        s3_client = _init_s3(REGION_NAME)

        found_urls: list[AssetResponse] = []
        if file.name:
            head = s3_client.head_object(Bucket=BUCKET_NAME, Key=file.name)
            url = _construct_s3_url(BUCKET_NAME, REGION_NAME, file.name)
            found_urls.append(AssetResponse(url=url))
        else:
            # Set up the paginator for listing objects
            paginator = s3_client.get_paginator("list_objects_v2")

            # Paginate through all objects in the bucket
            for page in paginator.paginate(Bucket=BUCKET_NAME):
                contents = page.get("Contents", [])

                for obj in contents:
                    key = obj["Key"]

                    try:
                        # Retrieve the object's metadata
                        head = s3_client.head_object(Bucket=BUCKET_NAME, Key=key)
                        metadata = head.get("Metadata", {})

                        # Check if all metadata_filters match
                        if all(metadata.get(k) == v for k, v in file.metadata.items()):
                            url = _construct_s3_url(BUCKET_NAME, REGION_NAME, key)
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
            logger.error(f"The bucket {BUCKET_NAME} does not exist.")
            raise RuntimeError(f"The bucket {BUCKET_NAME} does not exist.")
        elif error_code == "NoSuchKey":
            logger.error(
                f"The file {file.name} does not exist in bucket {BUCKET_NAME}."
            )
            raise RuntimeError(
                f"The file {file.name} does not exist in bucket {BUCKET_NAME}."
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
