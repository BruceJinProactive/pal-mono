import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

import db
from api.schemas.admin.camera import (
    GetCameraImageUrlsResponse,
    GetCamerasRequest,
    GetCamerasResponse,
    ImageMetadata,
)
from services.asset_service import _constants, _utils
from utils.log import logger

AWS_ASSET_BUCKET_NAME = _utils.AWS_ASSET_BUCKET_NAME
AWS_REGION = _constants.AWS_REGION


def create_checkpoint(session: Session, checkpoint: db.CheckPoint) -> db.CheckPoint:
    """Create a new checkpoint.

    Args:
        session: Database session
        checkpoint: Checkpoint object to create

    Returns:
        db.CheckPoint: Created checkpoint
    """
    checkpoint_repository = db.CheckpointRepository(session)
    return checkpoint_repository.create_checkpoint(checkpoint)


## List Folders ##
@_utils.handle_s3_errors
def list_folders(prefix: str) -> list[str]:
    """List all 'folders' under a given prefix in S3.

    Args:
        prefix: The S3 path prefix (e.g., "security/cameras/acctid/projid/")

    Returns:
        List of folder names with the full path (e.g., ["security/cameras/acctid/projid/folder1/"])
    """
    if not prefix:
        raise ValueError("Prefix must be provided.")

    _utils.check_region_name()
    s3_client = _utils.init_s3(AWS_REGION)
    _utils.check_bucket_name()

    # Ensure prefix ends with / if not empty
    if not prefix.endswith("/"):
        prefix += "/"

    logger.info(f"Listing folders under prefix: {prefix}")

    response = s3_client.list_objects_v2(
        Bucket=AWS_ASSET_BUCKET_NAME, Prefix=prefix, Delimiter="/"
    )

    # CommonPrefixes contains the "folder" names
    folders = []
    for common_prefix in response.get("CommonPrefixes", []):
        folders.append(common_prefix.get("Prefix"))

    logger.info(f"Found {len(folders)} folders under prefix {prefix}")
    return folders


@_utils.handle_s3_errors
def get_cameras_under_project(request: GetCamerasRequest) -> GetCamerasResponse:
    """Get all cameras under a specific project.

    Args:
        request: GetCamerasRequest containing account_id and project_id

    Returns:
        GetCamerasResponse containing list of camera names/IDs
    """
    if not request.account_id:
        raise ValueError("Account ID must be provided.")
    if not request.project_id:
        raise ValueError("Project ID must be provided.")

    # Construct the S3 prefix path
    prefix = f"security/cameras/{request.account_id}/{request.project_id}"

    logger.info(
        f"Getting cameras for account {request.account_id}, project {request.project_id}"
    )

    # Get all folders under this prefix
    folder_paths = list_folders(prefix)

    # Extract just the camera names from the full paths
    # e.g., "security/acct123/proj456/camera1/" -> "camera1"
    cameras = []
    for folder_path in folder_paths:
        # Remove trailing slash and split by /
        parts = folder_path.rstrip("/").split("/")
        # Get the last part which is the camera name
        if parts:
            camera_name = parts[-1]
            cameras.append(camera_name)

    logger.info(f"Found {len(cameras)} cameras: {cameras}")

    return GetCamerasResponse(cameras=cameras)


@_utils.handle_s3_errors
def get_camera_image(
    account_id: str, project_id: str, camera_name: str
) -> ImageMetadata:
    """Get the single camera image named {camera_name}.png.

    Args:
        account_id: Account ID
        project_id: Project ID
        camera_name: Camera name (the image will be {camera_name}.png)

    Returns:
        ImageMetadata containing the image information

    Raises:
        ValueError: If required parameters are missing
        FileNotFoundError: If the image doesn't exist
    """
    if not account_id:
        raise ValueError("Account ID must be provided.")
    if not project_id:
        raise ValueError("Project ID must be provided.")
    if not camera_name:
        raise ValueError("Camera name must be provided.")

    # Construct the S3 key path for the specific image
    key = f"security/cameras/{account_id}/{project_id}/{camera_name}/{camera_name}.png"

    logger.info(
        f"Getting image for account {account_id}, project {project_id}, "
        f"camera {camera_name} at key {key}"
    )

    _utils.check_region_name()
    s3_client = _utils.init_s3(AWS_REGION)
    _utils.check_bucket_name()

    try:
        # Get object metadata using head_object (doesn't download the file)
        response = s3_client.head_object(Bucket=AWS_ASSET_BUCKET_NAME, Key=key)

        # Get last_modified from S3 metadata
        last_modified = response["LastModified"]

        # Ensure last_modified is timezone-aware
        if last_modified.tzinfo is None:
            last_modified = last_modified.replace(tzinfo=timezone.utc)

        # Generate presigned URL for the image
        url = s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": AWS_ASSET_BUCKET_NAME, "Key": key},
            ExpiresIn=3600,  # URL valid for 1 hour
        )

        image_metadata = ImageMetadata(
            file_name=f"{camera_name}.png",
            url=url,
            last_modified=last_modified.isoformat(),
            size=response["ContentLength"],
        )

        logger.info(f"Found image: {camera_name}.png")
        return image_metadata

    except s3_client.exceptions.NoSuchKey:
        logger.error(f"Image not found: {key}")
        raise FileNotFoundError(f"Image {camera_name}.png not found")
    except Exception as e:
        logger.error(f"Error retrieving image: {str(e)}")
        raise


def _fetch_image_urls_with_prefix(
    s3_client,
    prefix: str,
    start_filename: str,
    end_filename: str,
) -> list[str]:
    """Helper function to fetch image URLs with a specific S3 prefix.

    Args:
        s3_client: Boto3 S3 client
        prefix: S3 prefix (e.g., "security/cameras/acc/proj/cam/20251104_")
        start_filename: Start filename (e.g., "20251104_220000")
        end_filename: End filename (e.g., "20251104_235959")

    Returns:
        List of presigned URLs
    """
    urls = []
    paginator = s3_client.get_paginator("list_objects_v2")

    logger.debug(f"Fetching images with prefix: {prefix}")

    for page in paginator.paginate(Bucket=AWS_ASSET_BUCKET_NAME, Prefix=prefix):
        contents = page.get("Contents", [])

        for obj in contents:
            key = obj["Key"]
            file_name = key.split("/")[-1]

            # Extract timestamp from filename (without extension)
            try:
                file_timestamp_str = file_name.rsplit(".", 1)[0]

                # Validate format: YYYYMMDD_HHMMSS (15 characters)
                if (
                    len(file_timestamp_str) != 15
                    or file_timestamp_str[8] != "_"
                    or not file_timestamp_str[:8].isdigit()
                    or not file_timestamp_str[9:].isdigit()
                ):
                    logger.debug(f"Skipping file with invalid format: {file_name}")
                    continue

            except (IndexError, ValueError) as e:
                logger.warning(f"Error processing filename {file_name}: {e}")
                continue

            # Early exit: if we've passed end_filename, stop
            if file_timestamp_str > end_filename:
                logger.debug(f"Reached end of range at {file_name}")
                return urls

            # Filter: only include files within range
            if start_filename <= file_timestamp_str <= end_filename:
                # Generate presigned URL
                url = s3_client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": AWS_ASSET_BUCKET_NAME, "Key": key},
                    ExpiresIn=3600,  # 1 hour
                )
                urls.append(url)

    return urls


@_utils.handle_s3_errors
def get_images_by_time_interval(
    session: Session,
    project_id: str,
    camera_name: str,
    start_time: datetime,
    end_time: datetime,
) -> GetCameraImageUrlsResponse:
    """Get camera image URLs within a time interval (optimized for < 24 hour ranges).

    Uses date-specific S3 prefixes for optimal performance when query spans multiple dates.

    Args:
        session: Database session
        project_id: Project UUID (as string)
        camera_name: Camera identifier
        start_time: Start of time range (timezone-aware datetime)
        end_time: End of time range (timezone-aware datetime)

    Returns:
        GetCameraImageUrlsResponse with urls

    Raises:
        ValueError: If required parameters are missing or invalid
        RuntimeError: If there are S3 or database errors
    """
    # Validation
    if not project_id:
        raise ValueError("Project ID must be provided.")
    if not camera_name:
        raise ValueError("Camera name must be provided.")
    if not start_time or not end_time:
        raise ValueError("Both start_time and end_time must be provided.")
    if start_time >= end_time:
        raise ValueError("start_time must be before end_time.")

    # Validate camera name format
    if "/" in camera_name or camera_name.startswith(".."):
        raise ValueError(
            "Invalid camera_name. Must not contain '/', '..' or start with '.'"
        )

    # Ensure timezone-aware
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)
    if end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=timezone.utc)

    # Validate time range (< 24 hours)
    duration = end_time - start_time
    if duration > timedelta(hours=24):
        raise ValueError(
            f"Time range must be less than 24 hours. "
            f"Requested: {duration.total_seconds() / 3600:.1f} hours"
        )

    # Get account_id from project_id
    project_repo = db.ProjectRepository(session)
    try:
        project_uuid = uuid.UUID(project_id)
    except ValueError:
        raise ValueError(f"Invalid project_id format: {project_id}")

    project = project_repo.get_project(project_uuid)
    if not project:
        raise ValueError(f"Project {project_id} not found.")

    account_id = str(project.account_id)

    # Extract dates
    start_date = start_time.strftime("%Y%m%d")  # e.g., "20251104"
    end_date = end_time.strftime("%Y%m%d")  # e.g., "20251105"

    start_filename = start_time.strftime("%Y%m%d_%H%M%S")  # e.g., "20251104_220000"
    end_filename = end_time.strftime("%Y%m%d_%H%M%S")  # e.g., "20251105_020000"

    logger.info(
        f"Getting images for camera {camera_name} "
        f"from {start_filename} to {end_filename}"
    )

    _utils.check_region_name()
    s3_client = _utils.init_s3(AWS_REGION)
    _utils.check_bucket_name()

    base_prefix = f"security/cameras/{account_id}/{project_id}/{camera_name}/"

    urls = []

    # Strategy: Check if query spans single day or multiple days
    if start_date == end_date:
        # CASE 1: Same day - single query with date prefix
        logger.info(f"Single day query: {start_date}")

        date_prefix = f"{base_prefix}{start_date}_"

        urls = _fetch_image_urls_with_prefix(
            s3_client=s3_client,
            prefix=date_prefix,
            start_filename=start_filename,
            end_filename=end_filename,
        )

    else:
        # CASE 2: Spans multiple days - query each day separately
        logger.info(f"Multi-day query: {start_date} to {end_date}")

        # Query 1: Get images from start_date >= start_time
        prefix_start_date = f"{base_prefix}{start_date}_"
        urls_day1 = _fetch_image_urls_with_prefix(
            s3_client=s3_client,
            prefix=prefix_start_date,
            start_filename=start_filename,
            end_filename=f"{start_date}_235959",  # End of start day
        )

        # Query 2: Get images from end_date <= end_time
        prefix_end_date = f"{base_prefix}{end_date}_"
        urls_day2 = _fetch_image_urls_with_prefix(
            s3_client=s3_client,
            prefix=prefix_end_date,
            start_filename=f"{end_date}_000000",  # Start of end day
            end_filename=end_filename,
        )

        # Combine results
        urls = urls_day1 + urls_day2

        logger.info(
            f"Found {len(urls_day1)} images on {start_date}, "
            f"{len(urls_day2)} images on {end_date}"
        )

    logger.info(f"Total: {len(urls)} image URLs found")

    return GetCameraImageUrlsResponse(urls=urls)
