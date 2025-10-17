import asyncio
import base64
import json
import os
from uuid import UUID

import boto3
import openai
from sqlalchemy.orm import Session

import db
from db.repositories import checkpoint_repository
from db.tables.types import CheckStatus
from services.asset_service._constants import AWS_ASSET_BUCKET_NAME, AWS_REGION
from utils.log import logger


def create_checkpoint(session: Session, checkpoint: db.CheckPoint) -> db.CheckPoint:
    return checkpoint_repository.create_checkpoint(session, checkpoint)


def list_checkpoints(session: Session, project_id: UUID) -> list[db.CheckPoint]:
    return checkpoint_repository.list_checkpoints(session, project_id)


def get_checkpoint(session: Session, checkpoint_id: UUID) -> db.CheckPoint | None:
    return checkpoint_repository.get_checkpoint(session, checkpoint_id)


def update_checkpoint(
    session: Session, checkpoint_id: UUID, updates: dict
) -> db.CheckPoint | None:
    return checkpoint_repository.update_checkpoint(session, checkpoint_id, updates)


def delete_checkpoint(session: Session, checkpoint_id: UUID) -> bool:
    return checkpoint_repository.delete_checkpoint(session, checkpoint_id)


async def compare_checkpoint_images_async(
    checkpoint: db.CheckPoint,
    uploaded_image_base64: str,
) -> dict:
    """
    Async version: Compare an uploaded image with a checkpoint's reference image using OpenAI Vision API.

    Args:
        checkpoint: The checkpoint database object with image_url and rules
        uploaded_image_base64: Base64 encoded string of the uploaded image

    Returns:
        Dictionary containing comparison results with structured JSON

    Raises:
        Exception: If S3 retrieval or OpenAI API call fails
    """
    # Run the blocking comparison in a thread pool to avoid blocking the event loop
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, compare_checkpoint_images, checkpoint, uploaded_image_base64
    )


def compare_checkpoint_images(
    checkpoint: db.CheckPoint,
    uploaded_image_base64: str,
) -> dict:
    """
    Compare an uploaded image with a checkpoint's reference image using OpenAI Vision API.

    Args:
        checkpoint: The checkpoint database object with image_url and rules
        uploaded_image_base64: Base64 encoded string of the uploaded image

    Returns:
        Dictionary containing comparison results with structured JSON

    Raises:
        Exception: If S3 retrieval or OpenAI API call fails
    """
    # Get the checkpoint's image from S3
    s3_client = (
        boto3.client(
            "s3",
            region_name=AWS_REGION,
            aws_access_key_id=os.getenv("LOCAL_AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("LOCAL_AWS_SECRET_ACCESS_KEY"),
            aws_session_token=os.getenv("LOCAL_AWS_SESSION_TOKEN"),
        )
        if os.getenv("LOCAL_AWS_ACCESS_KEY_ID")
        else boto3.client("s3", region_name=AWS_REGION)
    )

    try:
        s3_response = s3_client.get_object(
            Bucket=AWS_ASSET_BUCKET_NAME, Key=checkpoint.image_url
        )
        checkpoint_image_content = s3_response["Body"].read()
    except Exception as e:
        logger.error(f"Failed to retrieve checkpoint image from S3: {e}")
        raise Exception("Failed to retrieve checkpoint image from storage.")

    checkpoint_image_base64 = base64.b64encode(checkpoint_image_content).decode("utf-8")

    # Build the comparison prompt - FOCUS ON CLEANLINESS AND SAFETY ONLY
    # The prompt explicitly requires OpenAI to evaluate EVERY rule and return
    # each rule's status (PASS/FAIL) in the response JSON.
    checkpoint_rules = checkpoint.rules if checkpoint.rules else []

    rules_count = len(checkpoint_rules)
    rules_section = ""
    rules_example = ""

    if checkpoint_rules:
        rules_text = "\n".join(
            f"{i+1}. {rule}" for i, rule in enumerate(checkpoint_rules)
        )
        rules_section = f"""**Inspection Rules ({rules_count} total - Cleanliness & Safety Only):**
{rules_text}

"""
        # Add example showing the expected format to ensure ALL rules are processed
        rules_example = f"""
**EXAMPLE - If there are {rules_count} rules, your "rules" array should look like:**
[
  {{"rule_number": 1, "rule_text": "...", "status": "PASS", "details": "...", "location": "..."}},
  {{"rule_number": 2, "rule_text": "...", "status": "FAIL", "details": "...", "location": "..."}},
  ... (continue for all {rules_count} rules)
]
"""

    prompt = f"""You are a restaurant safety and cleanliness inspection AI comparing two images.

**CHECKPOINT**: {checkpoint.name}
**DESCRIPTION**: {checkpoint.description or "N/A"}

**REFERENCE IMAGE (First Image)**: This is the CLEAN/SAFE standard that inspections should match.

**TEST IMAGE (Second Image)**: This is the image being inspected.

**IMPORTANT**: Focus ONLY on the rules provided below, please do NOT consider any other factors.

{rules_section}**Your Task:**
FIRST, verify that the TEST image is related to the checkpoint area/subject (e.g., if checkpoint is "Kitchen Sink", the test image should show a kitchen sink).
- If the TEST image is UNRELATED or shows a completely different area/subject, immediately return FAIL with error.
- If the TEST image is related, proceed to compare it against the REFERENCE image for cleanliness and safety standards.
{rules_example}
**Return your analysis as a valid JSON object with this structure:**

{{
  "overall_result": "PASS" or "FAIL",
  "summary": "Brief explanation of why it passed or failed",
  "error": "Set this if TEST image is unrelated to checkpoint (e.g., 'Image shows [X] but checkpoint expects [Y]'), otherwise omit or set to null",
  "rules": [
    {{
      "rule_number": 1,
      "rule_text": "Copy the exact rule text from above",
      "status": "PASS" or "FAIL",
      "details": "Specific details about compliance or violation",
      "location": "Where in the image this applies",
    }}
  ],
}}

**CRITICAL INSTRUCTIONS**:
- You MUST evaluate ALL {rules_count} rules listed above
- For PASSING rules: Set status="PASS", provide confirmation in details
- For FAILING rules: Set status="FAIL", provide specific violation in details
- DO NOT skip any rules - all {rules_count} rules must be evaluated
- Return ONLY valid JSON, no markdown formatting or extra text


**VALIDATION CHECK**: Before returning, verify your "rules" array has exactly {rules_count} entries."""

    # Call OpenAI Vision API with JSON response format
    client = openai.OpenAI()
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{checkpoint_image_base64}",
                            "detail": "high",
                        },
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{uploaded_image_base64}",
                            "detail": "high",
                        },
                    },
                ],
            }
        ],
        response_format={"type": "json_object"},
        max_tokens=2000,
    )

    comparison_result_json = json.loads(response.choices[0].message.content or "{}")

    logger.info(
        f"Checkpoint comparison completed for checkpoint {checkpoint.id}. "
        f"Result: {comparison_result_json.get('overall_result', 'UNKNOWN')}, "
        f"Confidence: {comparison_result_json.get('confidence_score', 0)}%"
    )

    return comparison_result_json


def create_checkpoint_result_processing(
    session: Session,
    checkpoint_id: UUID,
    submission_id: UUID,
) -> db.CheckpointResult:
    """
    Create a checkpoint result with 'processing' status immediately.
    This is called BEFORE OpenAI starts processing.

    Args:
        session: Database session
        checkpoint_id: UUID of the checkpoint
        submission_id: UUID of the submission being checked

    Returns:
        db.CheckpointResult: The created checkpoint result record with processing status
    """
    return checkpoint_repository.create_checkpoint_result_processing(
        session, checkpoint_id, submission_id
    )


def list_checkpoint_results(
    session: Session,
    checkpoint_id: UUID | None = None,
    submission_id: UUID | None = None,
    status: CheckStatus | None = None,
    project_id: UUID | None = None,
) -> list[db.CheckpointResult]:
    """
    List checkpoint results with optional filters.

    Args:
        session: Database session
        checkpoint_id: Optional filter by checkpoint ID
        submission_id: Optional filter by submission ID
        status: Optional filter by status
        project_id: Optional filter by project ID (via checkpoint)

    Returns:
        list[db.CheckpointResult]: List of checkpoint results
    """
    return checkpoint_repository.list_checkpoint_results(
        session, checkpoint_id, submission_id, status, project_id
    )


def get_checkpoint_result(
    session: Session,
    result_id: UUID,
) -> db.CheckpointResult | None:
    """
    Get a single checkpoint result by ID.

    Args:
        session: Database session
        result_id: UUID of the checkpoint result

    Returns:
        db.CheckpointResult | None: The checkpoint result or None if not found
    """
    return checkpoint_repository.get_checkpoint_result(session, result_id)


def update_checkpoint_result(
    session: Session,
    result_id: UUID,
    result: dict,
    status: CheckStatus,
) -> db.CheckpointResult:
    """
    Update a checkpoint result with the final comparison result.
    This is called AFTER OpenAI finishes processing.

    Args:
        session: Database session
        result_id: UUID of the checkpoint result to update
        result: Dictionary containing the comparison result (JSON)
        status: Final status (active or failed)

    Returns:
        db.CheckpointResult: The updated checkpoint result record
    """
    return checkpoint_repository.update_checkpoint_result(
        session, result_id, result, status
    )


def save_checkpoint_result(
    session: Session,
    checkpoint_id: UUID,
    submission_id: UUID,
    result: dict,
    status: CheckStatus = CheckStatus.active,
) -> db.CheckpointResult:
    """
    Save a checkpoint comparison result to the database.
    (Legacy function - prefer using create + update pattern)

    Args:
        session: Database session
        checkpoint_id: UUID of the checkpoint
        submission_id: UUID of the submission being checked
        result: Dictionary containing the comparison result (JSON)
        status: Status of the check (default: active)

    Returns:
        db.CheckpointResult: The created checkpoint result record
    """
    return checkpoint_repository.save_checkpoint_result(
        session, checkpoint_id, submission_id, result, status
    )


async def compare_and_save_checkpoint_async(
    session: Session,
    checkpoint: db.CheckPoint,
    submission_id: UUID,
    uploaded_image_base64: str,
) -> db.CheckpointResult:
    """
    Async function to compare checkpoint images and save the result.

    LEGACY VERSION: Creates and saves result after comparison completes.
    For immediate response, use compare_and_update_checkpoint_background() instead.

    Args:
        session: Database session
        checkpoint: The checkpoint to compare against
        submission_id: UUID of the submission being checked
        uploaded_image_base64: Base64 encoded uploaded image

    Returns:
        db.CheckpointResult: The saved checkpoint result
    """
    try:
        # Run comparison asynchronously
        comparison_result = await compare_checkpoint_images_async(
            checkpoint=checkpoint,
            uploaded_image_base64=uploaded_image_base64,
        )

        # Save to database
        checkpoint_result = save_checkpoint_result(
            session=session,
            checkpoint_id=checkpoint.id,
            submission_id=submission_id,
            result=comparison_result,
            status=CheckStatus.active,
        )

        return checkpoint_result

    except Exception as e:
        logger.error(
            f"Error comparing and saving checkpoint {checkpoint.id}: {e}",
            exc_info=True,
        )

        # Save failed result
        error_result = {
            "overall_result": "FAIL",
            "error": str(e),
            "confidence_score": 0,
        }

        checkpoint_result = save_checkpoint_result(
            session=session,
            checkpoint_id=checkpoint.id,
            submission_id=submission_id,
            result=error_result,
            status=CheckStatus.failed,
        )

        return checkpoint_result


async def compare_and_update_checkpoint_background(
    checkpoint_result_id: UUID,
    checkpoint: db.CheckPoint,
    uploaded_image_base64: str,
) -> None:
    """
    Background task: Compare images and update existing checkpoint result.

    This function is meant to run in the background AFTER returning response to frontend.
    It updates the checkpoint_result from 'processing' to 'active' or 'failed'.

    This function creates a new short-lived Session using SyncSessionLocal to avoid
    reusing the request-scoped Session which may have been closed.

    Args:
        checkpoint_result_id: UUID of the checkpoint result to update
        checkpoint: The checkpoint to compare against
        uploaded_image_base64: Base64 encoded uploaded image

    Returns:
        None (updates database directly)
    """

    def _update_result_sync(
        result_id: UUID,
        result: dict,
        status: CheckStatus,
    ) -> None:
        """
        Synchronous helper to update checkpoint result with proper session management.

        Args:
            result_id: UUID of the checkpoint result to update
            result: Dictionary containing the comparison result (JSON)
            status: Final status (active or failed)
        """
        # Import SyncSessionLocal from db.session
        from db.session import SyncSessionLocal

        # Create a new short-lived Session
        session = SyncSessionLocal()

        try:
            # Update database with result
            update_checkpoint_result(
                session=session,
                result_id=result_id,
                result=result,
                status=status,
            )
        except Exception as e:
            logger.error(f"Error updating checkpoint result {result_id}: {e}")
            raise
        finally:
            # Always close the session
            session.close()

    try:
        logger.info(
            f"Starting background comparison for checkpoint {checkpoint.id}, "
            f"result_id {checkpoint_result_id}"
        )

        # Run comparison asynchronously (this uses run_in_executor internally)
        comparison_result = await compare_checkpoint_images_async(
            checkpoint=checkpoint,
            uploaded_image_base64=uploaded_image_base64,
        )

        # Run the synchronous DB update in a thread pool to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            _update_result_sync,
            checkpoint_result_id,
            comparison_result,
            CheckStatus.active,
        )

        logger.info(
            f"Background comparison completed for result_id {checkpoint_result_id}, "
            f"overall_result: {comparison_result.get('overall_result', 'N/A')}"
        )

    except Exception as e:
        logger.error(
            f"Error in background comparison for checkpoint {checkpoint.id}: {e}",
            exc_info=True,
        )

        # Update with failed status
        error_result = {
            "overall_result": "FAIL",
            "error": str(e),
            "confidence_score": 0,
        }

        try:
            # Run the synchronous DB update in a thread pool
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                _update_result_sync,
                checkpoint_result_id,
                error_result,
                CheckStatus.failed,
            )
        except Exception as db_error:
            logger.error(
                f"Failed to save error result for checkpoint_result {checkpoint_result_id}: {db_error}",
                exc_info=True,
            )
