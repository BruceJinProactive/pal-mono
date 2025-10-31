from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

import db
from api.schemas.admin.camera import (
    GetCameraImagesRequest,
    GetCameraImagesResponse,
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
def get_camera_images(request: GetCameraImagesRequest) -> GetCameraImagesResponse:
    """Get all images from a camera within the last X seconds.

    Args:
        request: GetCameraImagesRequest containing account_id, project_id, camera_name, and seconds

    Returns:
        GetCameraImagesResponse containing list of images with metadata and total count
    """
    if not request.account_id:
        raise ValueError("Account ID must be provided.")
    if not request.project_id:
        raise ValueError("Project ID must be provided.")
    if not request.camera_name:
        raise ValueError("Camera name must be provided.")
    if request.seconds <= 0:
        raise ValueError("Seconds must be greater than 0.")

    # Construct the S3 prefix path
    prefix = f"security/cameras/{request.account_id}/{request.project_id}/{request.camera_name}/"

    _utils.check_region_name()
    s3_client = _utils.init_s3(AWS_REGION)
    _utils.check_bucket_name()

    # Calculate the cutoff time
    cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=request.seconds)

    # Images are named: {camera_name}_{YYYYMMDD}_{HHMMSS}.ext
    # We can use StartAfter to skip objects older than the cutoff time
    # Format the cutoff time to match the naming convention
    cutoff_timestamp = cutoff_time.strftime("%Y%m%d_%H%M%S")
    start_after_key = f"{prefix}{request.camera_name}_{cutoff_timestamp}"

    logger.info(f"Using StartAfter key: {start_after_key}")

    # List objects starting from the cutoff timestamp
    images = []
    continuation_token = None

    while True:
        # Prepare list_objects_v2 parameters
        list_params = {
            "Bucket": AWS_ASSET_BUCKET_NAME,
            "Prefix": prefix,
            "StartAfter": start_after_key,
        }
        if continuation_token:
            list_params["ContinuationToken"] = continuation_token

        response = s3_client.list_objects_v2(**list_params)

        # Process the objects (all should be within time range due to StartAfter)
        for obj in response.get("Contents", []):
            # Extract filename from the key
            file_name = obj["Key"].split("/")[-1]

            # Skip if it's a "folder" (ends with /)
            if not file_name:
                continue

            # Get last_modified from S3 metadata
            last_modified = obj["LastModified"]

            # Ensure last_modified is timezone-aware
            if last_modified.tzinfo is None:
                last_modified = last_modified.replace(tzinfo=timezone.utc)

            # Generate presigned URL for the image
            url = s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": AWS_ASSET_BUCKET_NAME, "Key": obj["Key"]},
                ExpiresIn=3600,  # URL valid for 1 hour
            )

            image_metadata = ImageMetadata(
                file_name=file_name,
                url=url,
                last_modified=last_modified.isoformat(),
                size=obj["Size"],
            )
            images.append(image_metadata)

        # Check if there are more results
        if response.get("IsTruncated"):
            continuation_token = response.get("NextContinuationToken")
        else:
            break

    # Sort images by last_modified (newest first)
    images.sort(key=lambda x: x.last_modified, reverse=True)

    logger.info(f"Found {len(images)} images within the last {request.seconds} seconds")

    return GetCameraImagesResponse(images=images, total_count=len(images))
