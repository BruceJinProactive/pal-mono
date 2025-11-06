import functools
import os

import boto3
import botocore
import botocore.client
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    NoCredentialsError,
    PartialCredentialsError,
)

from utils.log import logger

from . import _constants

AWS_ASSET_BUCKET_NAME = _constants.AWS_ASSET_BUCKET_NAME
AWS_REGION = _constants.AWS_REGION


def handle_s3_errors(func):
    """Decorator to handle AWS S3 related errors."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            error_message = e.response["Error"]["Message"]

            logger.error(f"AWS ClientError: {error_code}, Message: {error_message}")
            raise RuntimeError(
                f"AWS ClientError: {error_code}, Message: {error_message}"
            ) from e

        except (NoCredentialsError, PartialCredentialsError) as e:
            logger.error(f"AWS credentials invalid or not found: {e}")
            raise RuntimeError(f"AWS credentials invalid or not found: {e}") from e

        except BotoCoreError as e:
            logger.error(f"Issue with boto3: {e}")
            raise RuntimeError(f"Issue with boto3: {e}") from e

        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}")
            raise RuntimeError(f"An unexpected error occurred: {e}") from e

    return wrapper


def check_bucket_name() -> None:
    if not AWS_ASSET_BUCKET_NAME:
        raise ValueError("AWS_ASSET_BUCKET_NAME not found in environment variables")


def check_region_name() -> None:
    if not AWS_REGION:
        raise ValueError("AWS_REGION not found in environment variables")


def generate_presigned_url(
    s3_client: botocore.client.BaseClient,
    bucket_name: str,
    object_key: str,
    expiration: int = 86400,  # 24 hours
) -> str:
    try:
        response = s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket_name, "Key": object_key},
            ExpiresIn=expiration,
        )
    except (NoCredentialsError, PartialCredentialsError) as e:
        logger.error("Credentials not available:", e)
        return ""
    except Exception as e:
        logger.error("Error generating presigned URL:", e)
        return ""

    return response


def init_s3(region_name: str) -> botocore.client.BaseClient:
    try:
        if os.getenv("LOCAL_AWS_ACCESS_KEY_ID"):
            logger.debug("Using local aws credentials.")
            s3_client = boto3.client(
                "s3",
                region_name=region_name,
                aws_access_key_id=os.getenv("LOCAL_AWS_ACCESS_KEY_ID"),
                aws_secret_access_key=os.getenv("LOCAL_AWS_SECRET_ACCESS_KEY"),
                aws_session_token=os.getenv("LOCAL_AWS_SESSION_TOKEN"),
            )
        else:
            s3_client = boto3.client("s3", region_name=region_name)
        return s3_client
    except (NoCredentialsError, PartialCredentialsError) as e:
        raise RuntimeError(f"AWS credentials invalid or not found: {e}")
    except BotoCoreError as e:
        raise RuntimeError(f"Issue with boto3: {e}")
    except Exception as e:
        raise RuntimeError(f"An unexpected error occurred: {e}")


def map_uri_to_s3_url(uri: str | None) -> str:
    """
    Maps a URI to an S3 URL by retrieving the asset through the asset service.

    Args:
        uri (str | None): The URI to map to an S3 URL.

    Returns:
        str: The S3 URL of the asset, or an empty string if the URI is None
             or no asset is found.
    """
    if uri:
        try:
            from api.schemas.asset.asset import ReadAssetRequest

            from . import _implementation

            s3_files = _implementation.read_assets(request=ReadAssetRequest(name=uri))
            if s3_files:
                return s3_files[0].url
        except Exception as e:
            logger.error(f"Error reading assets for URI {uri}: {e}")
    return ""
