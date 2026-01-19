"""Routine Submission Service LLM Integration.

LLM-specific functions for AI-based routine item verification using Azure OpenAI.
Supports vision-based analysis for photo routine items.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import uuid
from decimal import Decimal

import boto3
from ddtrace.trace import tracer
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from db.repositories import RoutineRepositoryAsync, RoutineSubmissionRepositoryAsync
from db.tables.routine_item_responses import RoutineItemResponse
from db.tables.types import ItemResponseStatus
from services.monitoring_service._providers import (
    MonitoringLLMConfig,
    MonitoringLLMProvider,
    create_monitoring_llm_provider,
)
from utils.log import logger

# AWS Configuration
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
AWS_ASSET_BUCKET_NAME = os.getenv("AWS_ASSET_BUCKET_NAME")

# Validate required configuration at module import
if not AWS_ASSET_BUCKET_NAME:
    raise ValueError(
        "AWS_ASSET_BUCKET_NAME environment variable is required for routine submission service. "
        "Please set AWS_ASSET_BUCKET_NAME in your environment configuration."
    )


async def analyze_routine_item_response(
    session: AsyncSession,
    response_id: uuid.UUID,
) -> dict:
    """
    Execute LLM analysis for a routine item response.

    Retrieves the routine item configuration, fetches reference images and submitted image,
    and performs AI analysis using Azure OpenAI or Google Gemini Vision API.

    Args:
        session: Async database session
        response_id: UUID of the routine item response to analyze

    Returns:
        dict: Analysis result with keys:
            {
                "result": "pass" or "fail" or "error",
                "details": str,
                "confidence": float (0.0-1.0),
                "findings": list[str] (optional)
            }

    Raises:
        HTTPException: If response not found or S3/LLM API errors occur
    """
    submission_repo = RoutineSubmissionRepositoryAsync(session)
    routine_repo = RoutineRepositoryAsync(session)

    # Get item response
    response = await submission_repo.get_item_response_by_id(response_id)

    if not response:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item response {response_id} not found",
        )

    # Get routine item configuration
    item = await routine_repo.get_routine_item_by_id(response.routine_item_id)

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Routine item {response.routine_item_id} not found",
        )

    if not item.ai_rules:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Routine item {item.id} has no AI rules configured",
        )

    if not response.image_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Item response {response_id} has no image to analyze",
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

    # Fetch submitted image from S3
    try:
        # Run blocking S3 operations in thread pool to avoid blocking event loop
        submitted_response = await asyncio.to_thread(
            s3_client.get_object, Bucket=AWS_ASSET_BUCKET_NAME, Key=response.image_url
        )
        submitted_image_content = await asyncio.to_thread(
            submitted_response["Body"].read
        )
        submitted_image_base64 = base64.b64encode(submitted_image_content).decode(
            "utf-8"
        )
    except Exception as e:
        logger.error(f"Failed to retrieve submitted image from S3: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve submitted image from storage",
        ) from e

    # Build prompt from ai_rules
    ai_rules = item.ai_rules
    prompt = ai_rules.get("prompt", "")
    reference_images_meta = item.reference_images or []
    structured_output = ai_rules.get("structured_output")

    # Get model configuration from ai_rules (optional)
    model_config = ai_rules.get("model", {})
    llm_provider = model_config.get("provider")  # e.g., "azure" or "google"
    llm_model = model_config.get("model")  # e.g., "gpt-4o" or "gemini-3-flash-preview"

    if not prompt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Routine item has no prompt in ai_rules",
        )

    # Fetch reference images if specified
    reference_images_base64 = []
    for ref_img in reference_images_meta:
        ref_image_url = ref_img.get("image_url")
        description = ref_img.get("description", "Reference image")

        if not ref_image_url:
            logger.warning("Reference image missing 'image_url' field, skipping")
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

    # Build LLM prompt with images - structured as a vision analysis prompt
    # Use custom structured output if provided, otherwise use default
    if structured_output:
        system_instruction = f"""You are a routine verification assistant. Your task is to analyze a submitted image and compare it against reference images to verify if the routine task was completed correctly.

First, verify that the submitted image is valid and relevant to the verification task. If the image has any of these issues, you should indicate an error in your response according to the schema below.

Image validation issues to check for:
- The image is completely black, white, or a solid color
- The image is corrupted, unreadable, or severely distorted
- The image content is completely unrelated to what should be verified based on the reference images and task description
- The image quality is too poor to perform any meaningful analysis

Please analyze the images carefully and respond with a JSON object that follows this schema:

{json.dumps(structured_output, indent=2)}

Ensure your response strictly adheres to this schema structure."""
    else:
        system_instruction = """You are a routine verification assistant. Your task is to analyze a submitted image and compare it against reference images to verify if the routine task was completed correctly.

First, verify that the submitted image is valid and relevant to the verification task. If the image has any of these issues, return an error:
- The image is completely black, white, or a solid color
- The image is corrupted, unreadable, or severely distorted
- The image content is completely unrelated to what should be verified based on the reference images and task description
- The image quality is too poor to perform any meaningful analysis

Please analyze the images carefully and respond with a JSON object in ONE of these formats:

For valid images:
{
  "result": "pass" or "fail",
  "details": "any relevant details about your analysis, why it passed/failed",
  "confidence": 0.0 to 1.0 (how confident you are in the result),
  "findings": ["list", "of", "specific", "observations"] (optional)
}

For invalid/problematic images:
{
  "result": "error",
  "details": "specific description of what is wrong with the submitted image",
  "confidence": 0.0
}"""

    # Prepare reference images data for provider
    reference_images_for_provider = [
        {"description": ref_img["description"], "base64_data": ref_img["base64"]}
        for ref_img in reference_images_base64
    ]

    # Determine response format based on custom structured output
    response_format = None
    if structured_output:
        # Use structured outputs with custom JSON schema
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "routine_verification",
                "strict": True,
                "schema": structured_output,
            },
        }

    # Call LLM Vision API using provider abstraction
    try:
        # Create a wrapper function that runs LLM call in a new trace context
        # This breaks the trace inheritance from the parent request
        # so routine verification appears as a separate trace in Datadog
        def call_llm_with_new_trace():
            # Get the current context and clear it to start a fresh trace
            # This prevents inheriting the parent trace from API requests
            current_context = tracer.current_trace_context()

            # Temporarily clear the trace context to create an independent trace
            tracer.context_provider.activate(None)

            try:
                # Initialize provider with config-specific model settings
                # Config-level settings override environment variables
                if llm_provider or llm_model:
                    logger.info(
                        f"[Routine Verification LLM] Using model config from ai_rules - Provider: {llm_provider or 'default'}, Model: {llm_model or 'default'}"
                    )
                    provider_enum = None
                    resolved_model = (
                        llm_model  # Use separate variable to avoid scope issues
                    )
                    if llm_provider:
                        try:
                            provider_enum = MonitoringLLMProvider(llm_provider.lower())
                        except ValueError:
                            logger.warning(
                                f"Invalid provider '{llm_provider}' in ai_rules, using default provider and clearing model"
                            )
                            # Clear the model when provider is invalid to prevent mismatch
                            # between provider and model (e.g., gemini model with azure provider)
                            resolved_model = None

                    custom_config = MonitoringLLMConfig(
                        provider=provider_enum, model=resolved_model
                    )
                    provider = create_monitoring_llm_provider(config=custom_config)
                else:
                    # Use default config from environment variables
                    logger.info(
                        "[Routine Verification LLM] Using model config from environment variables"
                    )
                    provider = create_monitoring_llm_provider()

                # Log the final resolved configuration
                logger.info(
                    f"[Routine Verification LLM] Provider initialized - Final config: Provider={provider.config.provider.value}, Model={provider.config.model}"
                )

                # Add tags to current span
                with tracer.trace(
                    "routine.verification.llm_call",
                    service="pal-mono-routine-verification",
                ) as span:
                    span.set_tag("routine.item_id", str(item.id))
                    span.set_tag("routine.response_id", str(response_id))
                    span.set_tag("routine.llm_provider", provider.config.provider.value)
                    span.set_tag("routine.llm_model", provider.config.model)

                    return provider.analyze_image(
                        system_instruction=system_instruction,
                        analysis_task=f"\n**Verification Task:**\n{prompt}\n",
                        reference_images=reference_images_for_provider,
                        camera_image_base64=submitted_image_base64,
                        response_format=response_format,
                    )
            finally:
                # Restore the original context after the call
                if current_context:
                    tracer.context_provider.activate(current_context)

        # Run blocking LLM call in thread pool with new trace context
        loop = asyncio.get_running_loop()
        analysis_result = await loop.run_in_executor(None, call_llm_with_new_trace)

        logger.info(
            f"Routine verification LLM analysis completed for response {response_id}",
            extra={
                "response_id": str(response_id),
                "item_id": str(item.id),
                "result": analysis_result.get("result", "unknown"),
            },
        )

        return analysis_result

    except Exception as e:
        logger.error(f"Routine verification LLM API call failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"LLM analysis failed: {str(e)}",
        ) from e


async def process_response_with_ai(
    session: AsyncSession,
    response_id: uuid.UUID,
) -> RoutineItemResponse:
    """
    Process AI verification for a routine item response and update the database.

    This function:
    1. Validates the item response exists and has AI rules
    2. Runs LLM analysis on the submitted image
    3. Updates the response record with AI results
    4. Returns the updated response object

    Note: This function does NOT commit the transaction. The caller is responsible
    for committing or rolling back the session. This allows the caller to include
    this operation in a larger transaction if needed.

    Args:
        session: Async database session (caller manages commit/rollback)
        response_id: UUID of the routine item response to process

    Returns:
        RoutineItemResponse: Updated response object with AI results

    Raises:
        HTTPException: If response not found or analysis fails
    """
    submission_repo = RoutineSubmissionRepositoryAsync(session)
    routine_repo = RoutineRepositoryAsync(session)

    # Get item response
    response = await submission_repo.get_item_response_by_id(response_id)

    if not response:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item response {response_id} not found",
        )

    # Get routine item to check AI rules
    item = await routine_repo.get_routine_item_by_id(response.routine_item_id)

    if not item or not item.ai_rules:
        logger.info(
            f"Skipping AI processing for response {response_id} - no AI rules configured"
        )
        return response

    if not response.image_url:
        logger.warning(
            f"Skipping AI processing for response {response_id} - no image provided"
        )
        return response

    # Run LLM analysis
    try:
        analysis_result = await analyze_routine_item_response(
            session=session,
            response_id=response_id,
        )
    except HTTPException as e:
        # For analysis errors, update response with error status
        logger.error(
            f"AI analysis failed for response {response_id}: {e.detail}",
            extra={
                "response_id": str(response_id),
                "item_id": str(response.routine_item_id),
            },
        )

        error_result = {
            "analysis_type": "ai_vision",
            "result": "error",
            "details": e.detail,
            "confidence": 0.0,
        }

        updated = await submission_repo.update_item_response(
            response_id=response_id,
            ai_result=error_result,
            ai_passed=None,
            ai_confidence=None,
            status=ItemResponseStatus.pending,  # Keep as pending for manual review
        )

        if not updated:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to update response {response_id} with error status",
            )

        logger.info(
            f"Updated response {response_id} with error status",
            extra={
                "response_id": str(response_id),
                "status": "error",
            },
        )

        # Note: Caller is responsible for committing the transaction
        return updated

    # Extract result fields
    result_status = analysis_result.get("result")
    details = analysis_result.get("details", "")
    confidence = analysis_result.get("confidence", 0.0)
    findings = analysis_result.get("findings", [])

    # Determine pass/fail status and item response status
    ai_passed = None
    item_status = ItemResponseStatus.pending

    if result_status == "pass":
        ai_passed = True
        item_status = ItemResponseStatus.passed
    elif result_status == "fail":
        ai_passed = False
        item_status = ItemResponseStatus.failed
    elif result_status == "error":
        ai_passed = None
        item_status = ItemResponseStatus.pending

    # Build full AI result
    full_ai_result = {
        "analysis_type": "ai_vision",
        "result": result_status,
        "details": details,
        "confidence": confidence,
        "findings": findings,
        "model": "azure_openai",  # Will be dynamic based on provider config
    }

    # Update response with AI results
    updated = await submission_repo.update_item_response(
        response_id=response_id,
        ai_result=full_ai_result,
        ai_passed=ai_passed,
        ai_confidence=Decimal(str(confidence)) if confidence else None,
        status=item_status,
    )

    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update response {response_id} with AI results",
        )

    logger.info(
        f"Updated response {response_id} with AI results",
        extra={
            "response_id": str(response_id),
            "result": result_status,
            "ai_passed": ai_passed,
            "confidence": confidence,
            "status": item_status,
        },
    )

    # Note: Caller is responsible for committing the transaction
    return updated
