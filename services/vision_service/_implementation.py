from sqlalchemy.orm import Session

import db
from api.schemas.admin.camera import GetCamerasRequest, GetCamerasResponse
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
