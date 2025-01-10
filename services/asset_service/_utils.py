import functools
import os

import boto3
import botocore
import botocore.client
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

from utils.log import logger

from . import _constants

AWS_ASSET_BUCKET_NAME = _constants.AWS_ASSET_BUCKET_NAME
AWS_REGION = _constants.AWS_REGION
LOCAL_BUCKET = _constants.LOCAL_BUCKET


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

        except NoCredentialsError as e:
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


def construct_s3_url(bucket_name: str, region_name: str, file_name: str) -> str:
    return f"https://{bucket_name}.s3.{region_name}.amazonaws.com/{file_name}"


def init_s3(region_name: str) -> botocore.client.BaseClient:
    try:
        if AWS_ASSET_BUCKET_NAME == LOCAL_BUCKET:
            logger.info("Using local aws credentials.")
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
    except NoCredentialsError as e:
        raise RuntimeError(f"AWS credentials invalid or not found: {e}")
    except BotoCoreError as e:
        raise RuntimeError(f"Issue with boto3: {e}")
    except Exception as e:
        raise RuntimeError(f"An unexpected error occurred: {e}")
