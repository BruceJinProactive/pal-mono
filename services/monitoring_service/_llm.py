"""Monitoring Service LLM Integration.

LLM-specific functions for AI-based monitoring analysis using multiple LLM providers.
Supports Azure OpenAI and Google Gemini for vision-based monitoring analysis.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import uuid
from datetime import datetime, timezone

import boto3
from ddtrace.trace import tracer
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from db.repositories import (
    MonitoringConfigRepositoryAsync,
    MonitoringRunRepositoryAsync,
    ProjectRepositoryAsync,
)
from db.tables import MonitoringRun
from services.monitoring_service._business_hours import (
    is_within_business_hours,
    parse_captured_at,
)
from services.monitoring_service._providers import (
    create_monitoring_llm_provider,
    supports_native_video,
)
from services.monitoring_service._time_window import should_skip_monitoring
from services.monitoring_service._video import (
    download_video_bytes,
    extract_video_frames,
)
from utils.log import logger

# AWS Configuration
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
AWS_ASSET_BUCKET_NAME = os.getenv("AWS_ASSET_BUCKET_NAME")


async def generate_monitoring_llm_prompt(
    session: AsyncSession,
    monitoring_config_id: uuid.UUID,
    image_url: str,
) -> dict:
    """
    Execute LLM analysis for a monitoring configuration.

    Retrieves the monitoring config, fetches reference images and camera image,
    and performs AI analysis using Azure OpenAI or Google Gemini Vision API.

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
        HTTPException: If config not found or S3/LLM API errors occur
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

    # Get model configuration from rules (optional)
    model_config = rules.get("model", {})
    llm_provider = model_config.get("provider")  # e.g., "azure" or "google"
    llm_model = model_config.get("model")  # e.g., "gpt-4o" or "gemini-3-flash-preview"

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

    # Build LLM prompt with images - structured as a vision analysis prompt
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
                "name": "monitoring_analysis",
                "strict": True,
                "schema": structured_output,
            },
        }

    # Call LLM Vision API using provider abstraction
    try:
        # Initialize provider with config-specific model settings
        # Config-level settings override environment variables
        from services.monitoring_service._providers import (
            MonitoringLLMConfig,
            MonitoringLLMProvider,
        )

        # Create custom config if model settings are specified in the monitoring config
        if llm_provider or llm_model:
            logger.info(
                f"[Monitoring LLM] Using model config from database rules - Provider: {llm_provider or 'default'}, Model: {llm_model or 'default'}"
            )
            provider_enum = None
            resolved_model = llm_model  # Use separate variable to avoid scope issues
            if llm_provider:
                try:
                    provider_enum = MonitoringLLMProvider(llm_provider.lower())
                except ValueError:
                    logger.warning(
                        f"Invalid provider '{llm_provider}' in monitoring config, using default provider and clearing model"
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
                "[Monitoring LLM] Using model config from environment variables"
            )
            provider = create_monitoring_llm_provider()

        # Log the final resolved configuration
        logger.info(
            f"[Monitoring LLM] Provider initialized - Final config: Provider={provider.config.provider.value}, Model={provider.config.model}"
        )

        # Create a wrapper that isolates the LLM call into its own trace.
        # This breaks trace inheritance from the parent voice-agent request
        # so monitoring LLM spans appear as a separate root trace in Datadog.
        def call_llm_with_isolated_trace() -> dict:
            current_context = tracer.current_trace_context()
            tracer.context_provider.activate(None)

            try:
                with tracer.trace(
                    "monitoring.llm.analyze_image",
                    service="pal-mono-monitoring",
                ) as span:
                    span.set_tag("monitoring.config_id", str(monitoring_config_id))
                    span.set_tag(
                        "monitoring.llm_provider", provider.config.provider.value
                    )
                    span.set_tag("monitoring.llm_model", provider.config.model)
                    span.set_tag("monitoring.media_type", "image")

                    return provider.analyze_image(
                        system_instruction=system_instruction,
                        analysis_task=f"\n**Analysis Task:**\n{prompt}\n",
                        reference_images=reference_images_for_provider,
                        camera_image_base64=camera_image_base64,
                        response_format=response_format,
                    )
            finally:
                if current_context:
                    tracer.context_provider.activate(current_context)

        # Run blocking LLM call in thread pool with isolated trace context
        loop = asyncio.get_running_loop()
        analysis_result = await loop.run_in_executor(None, call_llm_with_isolated_trace)

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
        logger.error(f"Monitoring LLM API call failed: {e}")
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
    project_repo = ProjectRepositoryAsync(session)

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
            "triggered_at": datetime.now(timezone.utc).isoformat(),
            "image_url": image_url,
        }

    # Check business hours if enabled
    rules = config.rules or {}
    skip_outside_hours = rules.get("skip_outside_business_hours", False)

    if skip_outside_hours:
        captured_at = parse_captured_at(trigger_metadata)
        if captured_at:
            project = await project_repo.get_project(config.project_id)
            if project:
                hours_check = is_within_business_hours(
                    captured_at=captured_at,
                    business_hours=project.business_hours,
                    timezone_str=project.timezone,
                )

                if not hours_check.is_open:
                    logger.info(
                        f"Skipping monitoring run - outside business hours: {hours_check.reason}",
                        extra={
                            "config_id": str(monitoring_config_id),
                            "captured_at": captured_at.isoformat(),
                            "reason": hours_check.reason,
                            "period_info": hours_check.period_info,
                        },
                    )

                    # Create run record with skipped status
                    skipped_result = {
                        "result": "skipped",
                        "reason": "outside_business_hours",
                        "details": hours_check.reason,
                        "business_hours_check": {
                            "is_open": hours_check.is_open,
                            "reason": hours_check.reason,
                            "period_info": hours_check.period_info,
                        },
                    }

                    skipped_run = MonitoringRun(
                        monitoring_config_id=monitoring_config_id,
                        trigger_metadata=trigger_metadata,
                        started_at=datetime.now(timezone.utc),
                        completed_at=datetime.now(timezone.utc),
                        evaluation_result=skipped_result,
                        error_message=None,
                    )

                    created_run = await run_repo.create(skipped_run)

                    return created_run, {
                        "prompt_sent": {},
                        "analysis_result": skipped_result,
                        "skipped": True,
                    }

    # Check time window if configured
    time_window_config = rules.get("monitoring_time_window")
    if time_window_config:
        should_skip, skip_reason = await should_skip_monitoring(
            session=session,
            project_id=config.project_id,
            time_window_config=time_window_config,
        )

        if should_skip:
            logger.info(
                f"Skipping monitoring run - {skip_reason}",
                extra={
                    "config_id": str(monitoring_config_id),
                    "reason": skip_reason,
                },
            )

            # Create run record with skipped status
            skipped_result = {
                "result": "skipped",
                "reason": "outside_time_window",
                "details": skip_reason,
            }

            skipped_run = MonitoringRun(
                monitoring_config_id=monitoring_config_id,
                trigger_metadata=trigger_metadata,
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
                evaluation_result=skipped_result,
                error_message=None,
            )

            created_run = await run_repo.create(skipped_run)

            return created_run, {
                "prompt_sent": {},
                "analysis_result": skipped_result,
                "skipped": True,
            }

    # Record start time
    started_at = datetime.now(timezone.utc)

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

        # For other HTTP errors (S3, LLM API, etc.), create a run with error
        error_run = MonitoringRun(
            monitoring_config_id=monitoring_config_id,
            trigger_metadata=trigger_metadata,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            evaluation_result={},
            error_message="LLM analysis failed",
        )
        created_run = await run_repo.create(error_run)
        # Note: Caller is responsible for committing/rolling back
        raise

    completed_at = datetime.now(timezone.utc)
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


async def generate_monitoring_video_llm_prompt(
    session: AsyncSession,
    monitoring_config_id: uuid.UUID,
    video_url: str,
) -> dict:
    """
    Execute LLM analysis on video frames for a monitoring configuration.

    Retrieves the monitoring config, fetches reference images, extracts frames
    from the video at regular intervals, and performs AI analysis using the
    configured LLM provider's video analysis capability.

    Args:
        session: Async database session
        monitoring_config_id: UUID of the monitoring configuration
        video_url: S3 key/path of the video file to analyze

    Returns:
        dict: Contains both the prompt and analysis result:
            {
                "prompt_sent": {
                    "system_instruction": str,
                    "user_prompt": str,
                    "reference_images": [{"description": str}],
                    "video_frames_count": int
                },
                "analysis_result": {
                    "result": "pass" or "fail" or "error",
                    "details": str
                }
            }

    Raises:
        HTTPException: If config not found or S3/LLM API errors occur
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

    # Build prompt from rules
    rules = config.rules or {}
    prompt = rules.get("prompt", "")
    reference_images_meta = rules.get("reference_images", [])
    structured_output = rules.get("structured_output")

    # Get model configuration from rules (optional)
    model_config = rules.get("model", {})
    llm_provider = model_config.get("provider")
    llm_model = model_config.get("model")

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

    # Build system instruction adapted for video analysis
    if structured_output:
        system_instruction = f"""You are a visual monitoring assistant. Your task is to analyze video frames captured at regular intervals from a monitoring camera and compare them against reference images to detect any issues or anomalies.

First, verify that the video frames are valid and relevant to the analysis task. If the frames have any of these issues, you should indicate an error in your response according to the schema below.

Frame validation issues to check for:
- The frames are completely black, white, or a solid color
- The frames are corrupted, unreadable, or severely distorted
- The frame content is completely unrelated to what should be monitored based on the reference images and task description
- The frame quality is too poor to perform any meaningful analysis

Please analyze all the video frames carefully, noting any changes over time, and respond with a JSON object that follows this schema:

{json.dumps(structured_output, indent=2)}

Ensure your response strictly adheres to this schema structure."""
    else:
        system_instruction = """You are a visual monitoring assistant. Your task is to analyze video frames captured at regular intervals from a monitoring camera and compare them against reference images to detect any issues or anomalies.

First, verify that the video frames are valid and relevant to the analysis task. If the frames have any of these issues, return an error:
- The frames are completely black, white, or a solid color
- The frames are corrupted, unreadable, or severely distorted
- The frame content is completely unrelated to what should be monitored based on the reference images and task description
- The frame quality is too poor to perform any meaningful analysis

Please analyze all the video frames carefully, noting any changes over time, and respond with a JSON object in ONE of these formats:

For valid frames:
{
  "result": "pass" or "fail",
  "details": "any relevant details about your analysis, why it passes/failed"
}

For invalid/problematic frames:
{
  "result": "error",
  "details": "specific description of what is wrong with the video frames"
}"""

    # Prepare reference images data for provider
    reference_images_for_provider = [
        {"description": ref_img["description"], "base64_data": ref_img["base64"]}
        for ref_img in reference_images_base64
    ]

    # Determine response format based on custom structured output
    response_format = None
    if structured_output:
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "monitoring_analysis",
                "strict": True,
                "schema": structured_output,
            },
        }

    # Call LLM Vision API using provider abstraction
    try:
        from services.monitoring_service._providers import (
            GoogleMonitoringProvider,
            MonitoringLLMConfig,
            MonitoringLLMProvider,
        )

        if llm_provider or llm_model:
            logger.info(
                f"[Monitoring LLM] Using model config from database rules (video) - Provider: {llm_provider or 'default'}, Model: {llm_model or 'default'}"
            )
            provider_enum = None
            resolved_model = llm_model
            if llm_provider:
                try:
                    provider_enum = MonitoringLLMProvider(llm_provider.lower())
                except ValueError:
                    logger.warning(
                        f"Invalid provider '{llm_provider}' in monitoring config, using default provider and clearing model"
                    )
                    resolved_model = None

            custom_config = MonitoringLLMConfig(
                provider=provider_enum, model=resolved_model
            )
            provider = create_monitoring_llm_provider(config=custom_config)
        else:
            logger.info(
                "[Monitoring LLM] Using model config from environment variables (video)"
            )
            provider = create_monitoring_llm_provider()

        logger.info(
            f"[Monitoring LLM] Provider initialized (video) - Final config: Provider={provider.config.provider.value}, Model={provider.config.model}"
        )

        # Check if this model supports native video input
        use_native_video = supports_native_video(
            provider.config.provider, provider.config.model
        )

        if use_native_video and isinstance(provider, GoogleMonitoringProvider):
            # Native video path: download raw bytes and pass entire video to Gemini
            logger.info(
                f"[Monitoring LLM] Model {provider.config.model} supports native video, downloading raw video"
            )
            video_bytes, video_mime_type = await download_video_bytes(video_url)

            def call_native_video_llm_with_isolated_trace() -> dict:
                current_context = tracer.current_trace_context()
                tracer.context_provider.activate(None)

                try:
                    with tracer.trace(
                        "monitoring.llm.analyze_native_video",
                        service="pal-mono-monitoring",
                    ) as span:
                        span.set_tag("monitoring.config_id", str(monitoring_config_id))
                        span.set_tag(
                            "monitoring.llm_provider", provider.config.provider.value
                        )
                        span.set_tag("monitoring.llm_model", provider.config.model)
                        span.set_tag("monitoring.media_type", "native_video")
                        span.set_tag(
                            "monitoring.video_size_bytes", str(len(video_bytes))
                        )
                        span.set_tag("monitoring.video_mime_type", video_mime_type)

                        return provider.analyze_native_video(
                            system_instruction=system_instruction,
                            analysis_task=f"\n**Analysis Task:**\n{prompt}\n",
                            reference_images=reference_images_for_provider,
                            video_bytes=video_bytes,
                            video_mime_type=video_mime_type,
                            response_format=response_format,
                        )
                finally:
                    if current_context:
                        tracer.context_provider.activate(current_context)

            loop = asyncio.get_running_loop()
            analysis_result = await loop.run_in_executor(
                None, call_native_video_llm_with_isolated_trace
            )

            prompt_summary = {
                "system_instruction": system_instruction,
                "user_prompt": prompt,
                "reference_images": [
                    {"description": ref_img["description"]}
                    for ref_img in reference_images_base64
                ],
                "native_video": True,
                "video_size_bytes": len(video_bytes),
            }
        else:
            # Frame extraction path: extract frames and send as images
            video_frames = await extract_video_frames(video_url)

            def call_video_llm_with_isolated_trace() -> dict:
                current_context = tracer.current_trace_context()
                tracer.context_provider.activate(None)

                try:
                    with tracer.trace(
                        "monitoring.llm.analyze_video_frames",
                        service="pal-mono-monitoring",
                    ) as span:
                        span.set_tag("monitoring.config_id", str(monitoring_config_id))
                        span.set_tag(
                            "monitoring.llm_provider", provider.config.provider.value
                        )
                        span.set_tag("monitoring.llm_model", provider.config.model)
                        span.set_tag("monitoring.media_type", "video")
                        span.set_tag(
                            "monitoring.video_frames_count", str(len(video_frames))
                        )

                        return provider.analyze_video_frames(
                            system_instruction=system_instruction,
                            analysis_task=f"\n**Analysis Task:**\n{prompt}\n",
                            reference_images=reference_images_for_provider,
                            video_frames=video_frames,
                            response_format=response_format,
                        )
                finally:
                    if current_context:
                        tracer.context_provider.activate(current_context)

            loop = asyncio.get_running_loop()
            analysis_result = await loop.run_in_executor(
                None, call_video_llm_with_isolated_trace
            )

            prompt_summary = {
                "system_instruction": system_instruction,
                "user_prompt": prompt,
                "reference_images": [
                    {"description": ref_img["description"]}
                    for ref_img in reference_images_base64
                ],
                "video_frames_count": len(video_frames),
            }

        logger.info(
            f"Monitoring LLM video analysis completed for config {monitoring_config_id}",
            extra={
                "config_id": str(monitoring_config_id),
                "result": analysis_result.get("result", "unknown"),
                "native_video": use_native_video,
            },
        )

        return {
            "prompt_sent": prompt_summary,
            "analysis_result": analysis_result,
        }

    except Exception as e:
        logger.error(f"Monitoring LLM video API call failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"LLM video analysis failed: {str(e)}",
        )


async def create_monitoring_video_run_with_analysis(
    session: AsyncSession,
    monitoring_config_id: uuid.UUID,
    video_url: str,
    trigger_metadata: dict | None = None,
) -> tuple[MonitoringRun, dict]:
    """
    Create a monitoring run with video LLM analysis and add to database session.

    This function:
    1. Validates the monitoring config exists
    2. Runs LLM analysis on extracted video frames
    3. Creates a MonitoringRun record with results and adds to session
    4. Returns both the run object and the prompt/analysis details

    Note: This function does NOT commit the transaction. The caller is responsible
    for committing or rolling back the session.

    Args:
        session: Async database session (caller manages commit/rollback)
        monitoring_config_id: UUID of the monitoring configuration
        video_url: S3 key/path of the video file to analyze
        trigger_metadata: Optional metadata about what triggered this run

    Returns:
        tuple: (MonitoringRun object, analysis_details dict)

    Raises:
        HTTPException: If config not found or analysis fails
    """
    config_repo = MonitoringConfigRepositoryAsync(session)
    run_repo = MonitoringRunRepositoryAsync(session)
    project_repo = ProjectRepositoryAsync(session)

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
            "triggered_at": datetime.now(timezone.utc).isoformat(),
            "video_url": video_url,
        }

    # Check business hours if enabled
    rules = config.rules or {}
    skip_outside_hours = rules.get("skip_outside_business_hours", False)

    if skip_outside_hours:
        captured_at = parse_captured_at(trigger_metadata)
        if captured_at:
            project = await project_repo.get_project(config.project_id)
            if project:
                hours_check = is_within_business_hours(
                    captured_at=captured_at,
                    business_hours=project.business_hours,
                    timezone_str=project.timezone,
                )

                if not hours_check.is_open:
                    logger.info(
                        f"Skipping monitoring video run - outside business hours: {hours_check.reason}",
                        extra={
                            "config_id": str(monitoring_config_id),
                            "captured_at": captured_at.isoformat(),
                            "reason": hours_check.reason,
                            "period_info": hours_check.period_info,
                        },
                    )

                    skipped_result = {
                        "result": "skipped",
                        "reason": "outside_business_hours",
                        "details": hours_check.reason,
                        "business_hours_check": {
                            "is_open": hours_check.is_open,
                            "reason": hours_check.reason,
                            "period_info": hours_check.period_info,
                        },
                    }

                    skipped_run = MonitoringRun(
                        monitoring_config_id=monitoring_config_id,
                        trigger_metadata=trigger_metadata,
                        started_at=datetime.now(timezone.utc),
                        completed_at=datetime.now(timezone.utc),
                        evaluation_result=skipped_result,
                        error_message=None,
                    )

                    created_run = await run_repo.create(skipped_run)

                    return created_run, {
                        "prompt_sent": {},
                        "analysis_result": skipped_result,
                        "skipped": True,
                    }

    # Check time window if configured
    time_window_config = rules.get("monitoring_time_window")
    if time_window_config:
        should_skip, skip_reason = await should_skip_monitoring(
            session=session,
            project_id=config.project_id,
            time_window_config=time_window_config,
        )

        if should_skip:
            logger.info(
                f"Skipping monitoring video run - {skip_reason}",
                extra={
                    "config_id": str(monitoring_config_id),
                    "reason": skip_reason,
                },
            )

            skipped_result = {
                "result": "skipped",
                "reason": "outside_time_window",
                "details": skip_reason,
            }

            skipped_run = MonitoringRun(
                monitoring_config_id=monitoring_config_id,
                trigger_metadata=trigger_metadata,
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
                evaluation_result=skipped_result,
                error_message=None,
            )

            created_run = await run_repo.create(skipped_run)

            return created_run, {
                "prompt_sent": {},
                "analysis_result": skipped_result,
                "skipped": True,
            }

    # Record start time
    started_at = datetime.now(timezone.utc)

    # Run LLM video analysis
    try:
        analysis_details = await generate_monitoring_video_llm_prompt(
            session=session,
            monitoring_config_id=monitoring_config_id,
            video_url=video_url,
        )
    except HTTPException as e:
        if e.status_code == status.HTTP_404_NOT_FOUND:
            raise

        error_run = MonitoringRun(
            monitoring_config_id=monitoring_config_id,
            trigger_metadata=trigger_metadata,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            evaluation_result={},
            error_message="LLM video analysis failed",
        )
        await run_repo.create(error_run)
        raise

    completed_at = datetime.now(timezone.utc)
    analysis_result = analysis_details.get("analysis_result", {})
    result_status = analysis_result.get("result")

    error_message = None
    if result_status == "error":
        error_message = analysis_result.get("details", "Video validation failed")

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
        f"Created monitoring video run {created_run.id} for config {monitoring_config_id}",
        extra={
            "run_id": str(created_run.id),
            "config_id": str(monitoring_config_id),
            "result": result_status,
            "error_message": error_message,
        },
    )

    return created_run, analysis_details
