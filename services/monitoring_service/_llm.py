"""Monitoring Service LLM Integration.

LLM-specific functions for AI-based monitoring analysis using OpenAI Vision API.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import uuid
from datetime import datetime

import boto3
import openai
from ddtrace.trace import tracer
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from db.repositories import (
    MonitoringConfigRepositoryAsync,
    MonitoringRunRepositoryAsync,
)
from db.tables import MonitoringRun
from utils.log import logger

# OpenAI Configuration
OPENAI_MODEL = "gpt-4o"
OPENAI_MAX_TOKENS = 2000
OPENAI_RESPONSE_FORMAT = {"type": "json_object"}
OPENAI_IMAGE_DETAIL = "high"

# AWS Configuration
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
AWS_ASSET_BUCKET_NAME = os.getenv("AWS_ASSET_BUCKET_NAME")

# Validate required configuration at module import
if not AWS_ASSET_BUCKET_NAME:
    raise ValueError(
        "AWS_ASSET_BUCKET_NAME environment variable is required for monitoring service. "
        "Please set AWS_ASSET_BUCKET_NAME in your environment configuration."
    )


async def generate_monitoring_llm_prompt(
    session: AsyncSession,
    monitoring_config_id: uuid.UUID,
    image_url: str,
) -> dict:
    """
    Execute LLM analysis for a monitoring configuration.

    Retrieves the monitoring config, fetches reference images and camera image,
    and performs AI analysis using OpenAI Vision API.

    Args:
        session: Async database session
        monitoring_config_id: UUID of the monitoring configuration
        image_url: S3 key/path of the camera image to analyze

    Returns:
        dict: Contains both the prompt and analysis result:
            {
                "prompt_sent": {
                    "system_instruction": str,
                    "user_prompt": str,
                    "reference_images": [{"description": str}],
                    "camera_image_included": bool
                },
                "analysis_result": {
                    "result": "pass" or "fail" or "error",
                    "details": str
                }
            }

    Raises:
        HTTPException: If config not found or S3/OpenAI errors occur
    """
    # Get monitoring config
    config_repo = MonitoringConfigRepositoryAsync(session)
    config = await config_repo.get_by_id(monitoring_config_id)

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Monitoring config {monitoring_config_id} not found",
        )

    # Initialize S3 client
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

    # Fetch camera image from S3
    try:
        # Run blocking S3 operations in thread pool to avoid blocking event loop
        camera_response = await asyncio.to_thread(
            s3_client.get_object, Bucket=AWS_ASSET_BUCKET_NAME, Key=image_url
        )
        camera_image_content = await asyncio.to_thread(camera_response["Body"].read)
        camera_image_base64 = base64.b64encode(camera_image_content).decode("utf-8")
    except Exception as e:
        logger.error(f"Failed to retrieve camera image from S3: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve camera image from storage",
        ) from e

    # Build prompt from rules
    rules = config.rules or {}
    prompt = rules.get("prompt", "")
    reference_images_meta = rules.get("reference_images", [])
    structured_output = rules.get("structured_output")

    if not prompt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Monitoring config has no prompt in rules",
        )

    # Fetch reference images if specified
    reference_images_base64 = []
    for ref_img in reference_images_meta:
        ref_image_url = ref_img.get("url")
        description = ref_img.get("description", "Reference image")

        if not ref_image_url:
            logger.warning("Reference image missing 'url' field, skipping")
            continue

        try:
            # Run blocking S3 operations in thread pool to avoid blocking event loop
            ref_response = await asyncio.to_thread(
                s3_client.get_object, Bucket=AWS_ASSET_BUCKET_NAME, Key=ref_image_url
            )
            ref_content = await asyncio.to_thread(ref_response["Body"].read)
            ref_base64 = base64.b64encode(ref_content).decode("utf-8")
            reference_images_base64.append(
                {
                    "base64": ref_base64,
                    "description": description,
                }
            )
        except Exception as e:
            logger.warning(f"Failed to retrieve reference image {ref_image_url}: {e}")
            # Continue without this reference image

    # Build OpenAI messages with images - structured as a vision analysis prompt
    # Use custom structured output if provided, otherwise use default
    if structured_output:
        system_instruction = f"""You are a visual monitoring assistant. Your task is to analyze a camera image and compare it against reference images to detect any issues or anomalies.

First, verify that the camera image is valid and relevant to the analysis task. If the image has any of these issues, you should indicate an error in your response according to the schema below.

Image validation issues to check for:
- The image is completely black, white, or a solid color
- The image is corrupted, unreadable, or severely distorted
- The image content is completely unrelated to what should be monitored based on the reference images and task description
- The image quality is too poor to perform any meaningful analysis

Please analyze the images carefully and respond with a JSON object that follows this schema:

{json.dumps(structured_output, indent=2)}

Ensure your response strictly adheres to this schema structure."""
    else:
        system_instruction = """You are a visual monitoring assistant. Your task is to analyze a camera image and compare it against reference images to detect any issues or anomalies.

First, verify that the camera image is valid and relevant to the analysis task. If the image has any of these issues, return an error:
- The image is completely black, white, or a solid color
- The image is corrupted, unreadable, or severely distorted
- The image content is completely unrelated to what should be monitored based on the reference images and task description
- The image quality is too poor to perform any meaningful analysis

Please analyze the images carefully and respond with a JSON object in ONE of these formats:

For valid images:
{
  "result": "pass" or "fail",
  "details": "any relevant details about your analysis, why it passes/ failed"
}

For invalid/problematic images:
{
  "result": "error",
  "details": "specific description of what is wrong with the camera image"
}"""

    message_content: list[dict] = [
        {"type": "text", "text": system_instruction},
        {"type": "text", "text": f"\n**Analysis Task:**\n{prompt}\n"},
    ]

    # Add reference images with context
    if reference_images_base64:
        message_content.append(
            {"type": "text", "text": "\n**Reference Images (Expected State):**"}
        )
        for idx, ref_img in enumerate(reference_images_base64):
            message_content.append(
                {
                    "type": "text",
                    "text": f"\nReference {idx + 1}: {ref_img['description']}",
                }
            )
            message_content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{ref_img['base64']}",
                        "detail": OPENAI_IMAGE_DETAIL,
                    },
                }
            )

    # Add camera image to analyze
    message_content.append(
        {
            "type": "text",
            "text": "\n**Current Camera Image (To Be Analyzed):**\nPlease compare this image against the reference images above and evaluate based on the analysis task.",
        }
    )
    message_content.append(
        {
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{camera_image_base64}",
                "detail": OPENAI_IMAGE_DETAIL,
            },
        }
    )

    # Call OpenAI Vision API
    try:
        # Determine response format based on custom structured output
        if structured_output:
            # Use structured outputs with custom JSON schema
            openai_response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": "monitoring_analysis",
                    "strict": True,
                    "schema": structured_output,
                },
            }
        else:
            # Use default json_object format
            openai_response_format = OPENAI_RESPONSE_FORMAT

        # Create a wrapper function that runs OpenAI call in a new trace context
        # This breaks the trace inheritance from the parent request (e.g., voice interaction)
        # so monitoring analysis appears as a separate trace in Datadog
        def call_openai_with_new_trace():
            # Get the current context and clear it to start a fresh trace
            # This prevents inheriting the parent trace from voice/agent interactions
            current_context = tracer.current_trace_context()

            # Temporarily clear the trace context to create an independent trace
            tracer.context_provider.activate(None)

            try:
                # Start a completely new root trace
                with tracer.trace(
                    "monitoring.vision_analysis",
                    service="pal-mono-monitoring",
                    resource="openai.vision.analysis",
                ) as span:
                    span.set_tag("monitoring.config_id", str(monitoring_config_id))
                    span.set_tag("monitoring.model", OPENAI_MODEL)
                    span.set_tag("monitoring.image_url", image_url)
                    return openai.OpenAI().chat.completions.create(
                        model=OPENAI_MODEL,
                        messages=[{"role": "user", "content": message_content}],  # type: ignore[arg-type]
                        response_format=openai_response_format,  # type: ignore[arg-type]
                        max_tokens=OPENAI_MAX_TOKENS,
                    )
            finally:
                # Restore the original context after the call
                if current_context:
                    tracer.context_provider.activate(current_context)

        # Run blocking OpenAI call in thread pool with new trace context
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(None, call_openai_with_new_trace)

        analysis_result = json.loads(response.choices[0].message.content or "{}")

        logger.info(
            f"Monitoring LLM analysis completed for config {monitoring_config_id}",
            extra={
                "config_id": str(monitoring_config_id),
                "result": analysis_result.get("result", "unknown"),
            },
        )

        # Build prompt summary (excluding base64 data for readability)
        prompt_summary = {
            "system_instruction": system_instruction,
            "user_prompt": prompt,
            "reference_images": [
                {"description": ref_img["description"]}
                for ref_img in reference_images_base64
            ],
            "camera_image_included": True,
        }

        return {
            "prompt_sent": prompt_summary,
            "analysis_result": analysis_result,
        }

    except Exception as e:
        logger.error(f"OpenAI API call failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"LLM analysis failed: {str(e)}",
        )


async def create_monitoring_run_with_analysis(
    session: AsyncSession,
    monitoring_config_id: uuid.UUID,
    image_url: str,
    trigger_metadata: dict | None = None,
) -> tuple[MonitoringRun, dict]:
    """
    Create a monitoring run with LLM analysis and add to database session.

    This function:
    1. Validates the monitoring config exists
    2. Runs LLM analysis on the camera image
    3. Creates a MonitoringRun record with results and adds to session
    4. Returns both the run object and the prompt/analysis details

    Note: This function does NOT commit the transaction. The caller is responsible
    for committing or rolling back the session. This allows the caller to include
    this operation in a larger transaction if needed.

    Args:
        session: Async database session (caller manages commit/rollback)
        monitoring_config_id: UUID of the monitoring configuration
        image_url: S3 key/path of the camera image to analyze
        trigger_metadata: Optional metadata about what triggered this run

    Returns:
        tuple: (MonitoringRun object, analysis_details dict)
            analysis_details contains:
            {
                "prompt_sent": {...},
                "analysis_result": {...}
            }

    Raises:
        HTTPException: If config not found or analysis fails
    """
    config_repo = MonitoringConfigRepositoryAsync(session)
    run_repo = MonitoringRunRepositoryAsync(session)

    # Verify monitoring config exists before proceeding
    config = await config_repo.get_by_id(monitoring_config_id)
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Monitoring config {monitoring_config_id} not found",
        )

    # Set default trigger metadata
    if trigger_metadata is None:
        trigger_metadata = {
            "trigger_source": "internal_api",
            "triggered_at": datetime.utcnow().isoformat(),
            "image_url": image_url,
        }

    # Record start time
    started_at = datetime.utcnow()

    # Run LLM analysis
    try:
        analysis_details = await generate_monitoring_llm_prompt(
            session=session,
            monitoring_config_id=monitoring_config_id,
            image_url=image_url,
        )
    except HTTPException as e:
        # Re-raise config not found errors without creating a run
        if e.status_code == status.HTTP_404_NOT_FOUND:
            raise

        # For other HTTP errors (S3, OpenAI, etc.), create a run with error
        error_run = MonitoringRun(
            monitoring_config_id=monitoring_config_id,
            trigger_metadata=trigger_metadata,
            started_at=started_at,
            completed_at=datetime.utcnow(),
            evaluation_result={},
            error_message="LLM analysis failed",
        )
        created_run = await run_repo.create(error_run)
        # Note: Caller is responsible for committing/rolling back
        raise

    completed_at = datetime.utcnow()
    analysis_result = analysis_details.get("analysis_result", {})
    result_status = analysis_result.get("result")

    # Extract error message if result is "error"
    error_message = None
    if result_status == "error":
        error_message = analysis_result.get("details", "Image validation failed")

    # Create monitoring run and add to session
    run = MonitoringRun(
        monitoring_config_id=monitoring_config_id,
        trigger_metadata=trigger_metadata,
        started_at=started_at,
        completed_at=completed_at,
        evaluation_result=analysis_result,
        error_message=error_message,
    )

    created_run = await run_repo.create(run)

    logger.info(
        f"Created monitoring run {created_run.id} for config {monitoring_config_id}",
        extra={
            "run_id": str(created_run.id),
            "config_id": str(monitoring_config_id),
            "result": result_status,
            "error_message": error_message,
        },
    )

    # Note: Caller is responsible for committing the transaction
    return created_run, analysis_details
