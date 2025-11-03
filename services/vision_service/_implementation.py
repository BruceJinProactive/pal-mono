import base64
import json
from datetime import datetime, timezone

from fastapi import UploadFile
from sqlalchemy.orm import Session

import db
from api.schemas.admin.camera import (
    AnalyzeImageResponse,
    GetCamerasRequest,
    GetCamerasResponse,
    ImageMetadata,
    UploadBaseImageResponse,
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


## GPT Vision Conversation Functions ##


def _get_conversation_key(account_id: str, project_id: str, camera_name: str) -> str:
    """Generate S3 key for storing conversation state."""
    return f"security/cameras/{account_id}/{project_id}/{camera_name}/conversation.json"


def _get_base_image_key(account_id: str, project_id: str, camera_name: str) -> str:
    """Generate S3 key for storing base image."""
    return f"security/cameras/{account_id}/{project_id}/{camera_name}/{camera_name}_base.png"


@_utils.handle_s3_errors
def _save_conversation_state(
    account_id: str, project_id: str, camera_name: str, conversation_data: dict
) -> None:
    """Save conversation state to S3."""
    _utils.check_region_name()
    s3_client = _utils.init_s3(AWS_REGION)
    _utils.check_bucket_name()

    key = _get_conversation_key(account_id, project_id, camera_name)
    conversation_json = json.dumps(conversation_data, indent=2)

    s3_client.put_object(
        Bucket=AWS_ASSET_BUCKET_NAME,
        Key=key,
        Body=conversation_json.encode("utf-8"),
        ContentType="application/json",
    )

    logger.info(f"Saved conversation state to {key}")


@_utils.handle_s3_errors
def _load_conversation_state(
    account_id: str, project_id: str, camera_name: str
) -> dict:
    """Load conversation state from S3."""
    _utils.check_region_name()
    s3_client = _utils.init_s3(AWS_REGION)
    _utils.check_bucket_name()

    key = _get_conversation_key(account_id, project_id, camera_name)

    try:
        response = s3_client.get_object(Bucket=AWS_ASSET_BUCKET_NAME, Key=key)
        conversation_json = response["Body"].read().decode("utf-8")
        return json.loads(conversation_json)
    except s3_client.exceptions.NoSuchKey:
        logger.error(f"Conversation state not found: {key}")
        raise FileNotFoundError(
            f"No conversation initialized for camera {camera_name}. "
            "Please upload a base image first."
        )


@_utils.handle_s3_errors
def _upload_image_to_s3(
    account_id: str, project_id: str, camera_name: str, image: UploadFile, suffix: str
) -> str:
    """Upload an image to S3 and return its key."""
    _utils.check_region_name()
    s3_client = _utils.init_s3(AWS_REGION)
    _utils.check_bucket_name()

    # Read image content
    image_content = image.file.read()

    # Determine file extension
    content_type = image.content_type or "image/png"
    extension = content_type.split("/")[-1]
    if extension not in ["png", "jpg", "jpeg"]:
        extension = "png"

    # Generate S3 key
    key = f"security/cameras/{account_id}/{project_id}/{camera_name}/{camera_name}_{suffix}.{extension}"

    logger.info(f"Uploading to bucket: {AWS_ASSET_BUCKET_NAME}, key: {key}")

    # Upload to S3
    s3_client.put_object(
        Bucket=AWS_ASSET_BUCKET_NAME,
        Key=key,
        Body=image_content,
        ContentType=content_type,
    )

    logger.info(f"Uploaded image to {key}")
    return key


def _call_openai_vision(messages: list[dict]) -> str:
    """Call OpenAI vision API with messages containing images.

    Returns JSON-formatted response from GPT.
    """
    import os

    from openai import AzureOpenAI

    # Get Azure OpenAI credentials from environment
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    if not api_key:
        raise ValueError("AZURE_OPENAI_API_KEY environment variable not set")

    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    if not azure_endpoint:
        raise ValueError("AZURE_OPENAI_ENDPOINT environment variable not set")

    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2025-01-01-preview")

    # Get deployment name for GPT-4o (which supports vision)
    deployment_name = os.getenv("AZURE_OPENAI_DEPLOYMENT_GPT4O")
    if not deployment_name:
        raise ValueError("AZURE_OPENAI_DEPLOYMENT_GPT4O environment variable not set")

    # Initialize client
    client = AzureOpenAI(
        api_key=api_key,
        azure_endpoint=azure_endpoint,
        api_version=api_version,
    )

    # Ensure the last user message contains "json" for Azure OpenAI requirement
    # when using response_format=json_object
    modified_messages = messages.copy()
    for i in range(len(modified_messages) - 1, -1, -1):
        if modified_messages[i]["role"] == "user":
            content = modified_messages[i]["content"]
            # Check if content is a list (multimodal) or string
            if isinstance(content, list):
                # Find the text content and append JSON instruction
                for item in content:
                    if item["type"] == "text":
                        if "json" not in item["text"].lower():
                            item["text"] += " Respond in JSON format."
                        break
            elif isinstance(content, str):
                if "json" not in content.lower():
                    modified_messages[i]["content"] = (
                        content + " Respond in JSON format."
                    )
            break

    logger.info(
        f"Calling Azure OpenAI vision API with {len(modified_messages)} messages"
    )

    # Make the API call with JSON response format
    # Type ignore for messages as OpenAI SDK accepts dict format
    response = client.chat.completions.create(
        model=deployment_name,
        messages=modified_messages,  # type: ignore
        max_tokens=1000,
        response_format={"type": "json_object"},
    )

    # Handle potential None response
    if not response.choices or not response.choices[0].message.content:
        raise ValueError("Empty response from OpenAI API")

    assistant_message = response.choices[0].message.content
    logger.info(f"Received response from OpenAI: {assistant_message[:100]}...")

    return assistant_message


async def upload_base_image(
    account_id: str,
    project_id: str,
    camera_name: str,
    image: UploadFile,
    prompt: str,
) -> UploadBaseImageResponse:
    """
    Upload a base reference image and initialize GPT conversation.

    Args:
        account_id: Account ID
        project_id: Project ID
        camera_name: Camera name
        image: Uploaded image file
        prompt: Initialization prompt to send with the base image

    Returns:
        UploadBaseImageResponse with conversation details
    """
    try:
        logger.info(
            f"Initializing base image for account {account_id}, "
            f"project {project_id}, camera {camera_name}"
        )

        # Upload image to S3
        image_key = _upload_image_to_s3(
            account_id, project_id, camera_name, image, "base"
        )

        # Get the uploaded image URL
        _utils.check_region_name()
        s3_client = _utils.init_s3(AWS_REGION)
        _utils.check_bucket_name()

        base_image_url = s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": AWS_ASSET_BUCKET_NAME, "Key": image_key},
            ExpiresIn=3600,
        )

        # Read the image and encode it to base64 for OpenAI
        image.file.seek(0)  # Reset file pointer
        image_content = image.file.read()
        image_base64 = base64.b64encode(image_content).decode("utf-8")

        # Determine image format
        content_type = image.content_type or "image/png"
        image_format = content_type.split("/")[-1]

        # Create initial conversation with the base image
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/{image_format};base64,{image_base64}"
                        },
                    },
                ],
            }
        ]

        # Call OpenAI vision API
        gpt_response = _call_openai_vision(messages)

        # Add GPT's response to conversation history
        messages.append({"role": "assistant", "content": gpt_response})

        # Generate conversation ID
        conversation_id = f"{account_id}_{project_id}_{camera_name}"

        # Save conversation state to S3
        conversation_data = {
            "conversation_id": conversation_id,
            "account_id": account_id,
            "project_id": project_id,
            "camera_name": camera_name,
            "base_image_key": image_key,
            "messages": messages,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        _save_conversation_state(account_id, project_id, camera_name, conversation_data)

        return UploadBaseImageResponse(
            message="Base image uploaded and conversation initialized successfully",
            conversation_id=conversation_id,
            base_image_url=base_image_url,
            gpt_response=gpt_response,
        )

    except Exception as e:
        logger.error(f"Error uploading base image: {str(e)}")
        raise


async def analyze_camera_image(
    account_id: str, project_id: str, camera_name: str, prompt: str
) -> AnalyzeImageResponse:
    """
    Analyze the current camera image against the base reference image.

    Args:
        account_id: Account ID
        project_id: Project ID
        camera_name: Camera name
        prompt: Analysis prompt to send with the current image

    Returns:
        AnalyzeImageResponse with analysis results
    """
    try:
        logger.info(
            f"Analyzing camera image for account {account_id}, "
            f"project {project_id}, camera {camera_name}"
        )

        # Load existing conversation state
        conversation_data = _load_conversation_state(
            account_id, project_id, camera_name
        )
        messages = conversation_data["messages"]

        # Get the current camera image
        image_metadata = get_camera_image(account_id, project_id, camera_name)

        # Download the image from S3
        _utils.check_region_name()
        s3_client = _utils.init_s3(AWS_REGION)
        _utils.check_bucket_name()

        image_key = f"security/cameras/{account_id}/{project_id}/{camera_name}/{camera_name}.png"
        response = s3_client.get_object(Bucket=AWS_ASSET_BUCKET_NAME, Key=image_key)
        image_content = response["Body"].read()

        # Encode image to base64
        image_base64 = base64.b64encode(image_content).decode("utf-8")

        # Add new user message with the current image
        new_message = {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{image_base64}"},
                },
            ],
        }

        messages.append(new_message)

        # Call OpenAI vision API
        gpt_response = _call_openai_vision(messages)

        # Add GPT's response to conversation history
        messages.append({"role": "assistant", "content": gpt_response})

        # Update conversation state
        conversation_data["messages"] = messages
        conversation_data["updated_at"] = datetime.now(timezone.utc).isoformat()

        _save_conversation_state(account_id, project_id, camera_name, conversation_data)

        return AnalyzeImageResponse(
            conversation_id=conversation_data["conversation_id"],
            analysis=gpt_response,
            image_analyzed=image_metadata.file_name,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    except FileNotFoundError:
        # Re-raise FileNotFoundError as-is for proper 404 handling
        raise
    except Exception as e:
        logger.error(f"Error analyzing camera image: {str(e)}")
        raise
