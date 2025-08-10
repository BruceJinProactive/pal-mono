import json
import os
import re
import uuid
from datetime import datetime, timezone

from fastapi import Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from vapi import AsyncVapi

import db
from api.schemas.chat.message import (
    AuthorType,
    Extras,
    Message,
    Metadata,
    TextObject,
    Type,
)
from db.tables.agents import SpeechRate
from db.tables.types import Channel
from services import agent_service, project_service, user_service
from utils.dd import dd_histogram_duration
from utils.log import logger

from ._squad import create_multilingual_squad
from ._utils import get_transcriber_and_voice_config, validate_vapi_request


def send_dd_latency(
    log_message: str, call_id: str, customer_number: str, phone_number: str
) -> None:
    """
    Extract latency metrics from VAPI log message and send to DataDog.

    Args:
        log_message: Log message containing latency data
        call_id: Call ID for tagging
        customer_number: Customer phone number for tagging
        phone_number: Business phone number for tagging
    """
    # Extract turn latency
    turn_latency_match = re.search(r"Turn latency: (\d+)ms", log_message)
    turn_latency = int(turn_latency_match.group(1)) if turn_latency_match else None

    # Extract transcriber latency
    transcriber_match = re.search(r"transcriber: (\d+)ms", log_message)
    transcriber_latency = int(transcriber_match.group(1)) if transcriber_match else None

    # Extract model latency
    model_match = re.search(r"model: (\d+)ms", log_message)
    model_latency = int(model_match.group(1)) if model_match else None

    # Extract voice latency
    voice_match = re.search(r"voice: (\d+)ms", log_message)
    voice_latency = int(voice_match.group(1)) if voice_match else None

    logger.debug(
        f"Extracted latencies for call {call_id} (from {customer_number} to {phone_number}): turn={turn_latency}ms, transcriber={transcriber_latency}ms, model={model_latency}ms, voice={voice_latency}ms"
    )

    # Send individual metrics to DataDog
    base_tags = [
        f"call_id:{call_id}",
        f"customer_number:{customer_number}",
        f"phone_number:{phone_number}",
    ]

    if turn_latency is not None:
        dd_histogram_duration(
            name="vapi.turn_latency",
            duration_ms=turn_latency,
            tags=base_tags + ["component:total"],
        )
    else:
        logger.debug(f"Turn latency not found in log message for call {call_id}")

    if transcriber_latency is not None:
        dd_histogram_duration(
            name="vapi.transcriber_latency",
            duration_ms=transcriber_latency,
            tags=base_tags + ["component:transcriber"],
        )
    else:
        logger.debug(f"Transcriber latency not found in log message for call {call_id}")

    if model_latency is not None:
        dd_histogram_duration(
            name="vapi.model_latency",
            duration_ms=model_latency,
            tags=base_tags + ["component:model"],
        )
    else:
        logger.debug(f"Model latency not found in log message for call {call_id}")

    if voice_latency is not None:
        dd_histogram_duration(
            name="vapi.voice_latency",
            duration_ms=voice_latency,
            tags=base_tags + ["component:voice"],
        )
    else:
        logger.debug(f"Voice latency not found in log message for call {call_id}")


async def _measure_voice_to_voice_latency(message_data: dict) -> None:
    """
    Measure conversation turn-taking latency for a completed call and send metrics to DataDog.
    Distinguishes between user-to-agent and agent-to-user response latencies.

    Args:
        message_data: Message data sent from VAPI webhook
    """
    call_data = message_data.get("call", {})
    call_id = call_data.get("id")

    # Extract caller information
    customer_data = message_data.get("customer", {})
    customer_number = customer_data.get("number", "")

    # Extract business information
    phone_number_data = message_data.get("phoneNumber", {})
    phone_number = phone_number_data.get("number", "")

    # Initialize VAPI client
    vapi_token = os.environ.get("VAPI_API_KEY")
    if not vapi_token:
        logger.error("VAPI_API_KEY environment variable not set")
        return

    vapi_client = AsyncVapi(token=vapi_token)

    # Get logs for this call
    try:
        logs_pager = await vapi_client.logs.get(call_id=call_id, type="Call")

        # Collect and filter logs from the pager
        async for log in logs_pager:
            # Filter for turn latency logs
            log_level = getattr(log, "level", None)
            log_message = getattr(log, "log", None)
            if log_level == "INFO" and log_message and "Turn latency:" in log_message:
                send_dd_latency(log_message, call_id, customer_number, phone_number)

    except Exception as e:
        logger.error(f"Failed to retrieve logs for call {call_id}: {str(e)}")
        return


async def api_vapi_server(request: Request, session: AsyncSession) -> JSONResponse:
    """
    Process incoming requests from VAPI service.

    Args:
        request: The FastAPI request object
        session: The database session

    Returns:
        JSONResponse: The response to send back to VAPI

    Raises:
        HTTPException: If there's an error processing the request
    """
    try:
        # Extract body from request
        body = await request.json()

        # Validate request format
        if not isinstance(body, dict):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"error": "Invalid request format"},
            )

        # Log the incoming request for debugging
        logger.debug(
            "VAPI request received",
            extra={
                "message_type": body.get("message", {}).get("type"),
                # drop / hash phone numbers & transcripts
            },
        )
        # Validate that the request is coming from VAPI
        if not validate_vapi_request(request):
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"error": "Unauthorized request"},
            )

        # Extract information from VAPI request structure
        message_data = body.get("message", {})
        message_type = message_data.get("type")

        # Handle different message types from VAPI
        match message_type:
            case "assistant-request":
                response_data = await handle_assistant_request(message_data, session)
            case "status-update":
                response_data = await handle_status_update(message_data, session)
            case "function-call":
                response_data = handle_function_call(message_data)
            case "transcript-update":
                response_data = handle_transcript_update(message_data)
            case "end-of-call-report":
                response_data = await handle_session_closure(message_data, session)
            case _:
                logger.warning(f"Received unknown VAPI message type: {message_type}")
                response_data = {"status": "acknowledged"}
        return JSONResponse(content=response_data)

    except json.JSONDecodeError:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Invalid JSON in request body"},
        )
    except Exception as e:
        logger.error(f"Error processing VAPI request: {str(e)}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": f"Error processing request: {str(e)}"},
        )


async def handle_assistant_request(message_data, session: AsyncSession):
    """
    Handle assistant-request message type.
    This is sent when a call starts and is waiting for initial instructions.

    Args:
        message_data: The message data from the request
        session: The database session

    Returns:
        dict: Response for VAPI with either an assistantId, a transient assistant configuration, or a workflow configuration
    """
    try:
        # Extract call information
        call_data = message_data.get("call", {})
        call_id = call_data.get("id")

        # Extract phone number information
        phone_number_data = message_data.get("phoneNumber", {})
        phone_number = phone_number_data.get("number", "")

        # Extract customer information
        customer_data = message_data.get("customer", {})
        customer_number = customer_data.get("number", "")

        logger.debug(
            f"Handling assistant request for call {call_id} from {customer_number} to {phone_number}"
        )

        # Create a Message object for this call request
        message = Message(
            id=str(uuid.uuid4()),
            author_type=AuthorType.SYSTEM,
            # Channel information
            sender_identifier=customer_number,
            recipient_identifier=phone_number,
            channel=Channel.VOICE,
            broker=None,  # Could be set if known
            # Content
            type=Type.TEXT,
            text=TextObject(body="[Call initiated]"),
            context="",
            # Extras
            extras=Extras(),
            # Metadata
            metadata=Metadata(),
            timestamp=datetime.now(timezone.utc),
        )

        # Log the created message
        logger.debug(f"Created message: {message.id} for call {call_id}")

        # ==== Step 1: Get project, user, and save request message ====
        project = await project_service.get_project_async(session, message)
        if not project:
            raise ValueError("Project not found for this message")

        # Get user_id by sender channel/number with user_service
        user, _ = await user_service.get_user_async(session, project, message)
        if not user:
            # Create new user record
            user = await user_service.create_user_async(session, project, message)

        # Save request message to database
        message_repo = db.MessageRepositoryAsync(session)
        request_message = await message_repo.create_message(
            user_id=user.id, project_id=project.id, message_body=message.to_dict()
        )
        await session.refresh(user, attribute_names=["id"])

        if not request_message:
            raise ValueError("Failed to create request message")

        await session.refresh(project, attribute_names=["account"])

        account_display_name = project.account.display_name
        # Fallback to account name if display name is not set
        if not account_display_name:
            account_display_name = project.account.name

        # ================= Step 2: Construct agent and generate output =================
        agent_id = project.agent_id
        if not agent_id:
            raise ValueError("Agent ID not found")

        # Construct agent config
        config = await agent_service.construct_agent_config(
            session=session,
            agent_id=agent_id,
            user_id=user.id,
            project_id=project.id,
            conversation_id=request_message.conversation_id,
            channel=message.channel,
        )

        # Create caller_info with required fields for message routing
        caller_info = {
            "sender_identifier": customer_number,
            "recipient_identifier": phone_number,
            "call_id": call_id,  # Adding call_id for future reference
        }

        # ================= Step 3: Construct assistant(s) =================

        #########################################################
        # Check if multilingual squad should be used
        #########################################################

        if config.multiling_squad_config and config.voice_config.enabled:
            logger.debug(f"Creating multilingual squad for call {call_id}")
            return create_multilingual_squad(
                agent_config=config,
                account_display_name=account_display_name,
                caller_info=caller_info,
                call_id=call_id,
            )

        #########################################################
        # Continue with existing single-language assistant configuration
        #########################################################

        dynamic_vapi_config = config.voice_config.enabled

        greeting = f"Hi this is {config.persona.name} from {account_display_name}. How can I help you today?"

        if dynamic_vapi_config and config.voice_config.greeting_message:
            greeting = config.voice_config.greeting_message

        # Get voice_id from config
        if dynamic_vapi_config and config.voice_config.voice_id:
            voice_id = config.voice_config.voice_id
        else:
            voice_id = config.persona.voice_id

        # Get speech rate from config
        if dynamic_vapi_config and config.voice_config.speech_rate:
            speech_rate = config.voice_config.speech_rate
        else:
            # Default to normal if not configured
            speech_rate = SpeechRate.normal

        # Get transcriber and voice configuration
        transcriber, voice = get_transcriber_and_voice_config(
            config, voice_id, speech_rate
        )

        if dynamic_vapi_config:
            background_sound = config.voice_config.background_noise
        else:
            background_sound = "off"

        # Return a transient assistant configuration
        api_url = os.environ.get("PAL_API_URL", "https://lat-api.palona.ai")
        # Document the expected format using a comment
        # Model field format: {sender_identifier: string, recipient_identifier: string, call_id?: string}

        # Prepare assistant configuration
        assistant_config = {
            "firstMessage": greeting,
            "transcriber": transcriber,
            "model": {
                "provider": "custom-llm",
                "url": f"{api_url}/v1",
                "model": json.dumps(caller_info),
                "messages": [{"role": "system", "content": config.persona.description}],
            },
            "voice": voice,
            "backgroundSound": background_sound,
            "silenceTimeoutSeconds": 60,
            "backgroundDenoisingEnabled": True,
        }

        # Add background speech denoising configuration if available
        if dynamic_vapi_config and config.voice_config.background_speech_denoising_plan:
            assistant_config["backgroundSpeechDenoisingPlan"] = (
                config.voice_config.background_speech_denoising_plan.model_dump(
                    exclude_none=True
                )
            )

        # Add start speaking plan configuration if available
        if dynamic_vapi_config and config.voice_config.start_speaking_plan:
            assistant_config["startSpeakingPlan"] = (
                config.voice_config.start_speaking_plan.model_dump(
                    exclude_none=True, by_alias=True
                )
            )

        return {"assistant": assistant_config}
    except Exception as e:
        logger.error(f"Error in handle_assistant_request: {str(e)}")
        return {"error": str(e)}


async def handle_status_update(message_data, session: AsyncSession):
    """
    Handle status-update message type.
    This is sent when a call's status changes (e.g., started, ended).
    Extracts and persists the control URL when available.

    Args:
        message_data: The message data from the request
        session: The database session

    Returns:
        dict: Response for VAPI
    """
    try:
        status = message_data.get("status")
        call_data = message_data.get("call", {})
        call_id = call_data.get("id")

        logger.debug(f"Call {call_id} status updated to: {status}")

        assistant_data = call_data.get("assistant", {})
        model_block = assistant_data.get("model")

        raw_model_data = None
        if isinstance(model_block, dict):
            raw_model_data = model_block.get("model")

        try:
            model_data = json.loads(raw_model_data) if raw_model_data else {}
        except (TypeError, json.JSONDecodeError):
            logger.warning("Unable to decode model_data from VAPI payload")
            model_data = {}

        # Extract control URL from monitor data if available
        monitor_data = call_data.get("monitor", {})
        control_url = monitor_data.get("controlUrl")

        if control_url and model_data:
            customer_number = model_data.get("sender_identifier", "")
            phone_number = model_data.get("recipient_identifier", "")

            if customer_number and phone_number:
                # Find the conversation using the same logic as handle_session_closure
                channel_identifier = f"voice:{customer_number}"
                project_channel_identifier = f"voice:{phone_number}"

                project_repo = db.ProjectRepositoryAsync(session)
                project = await project_repo.get_project_by_channel_identifier(
                    project_channel_identifier
                )
                if not project:
                    raise ValueError(
                        f"Project not found for this message: {project_channel_identifier}"
                    )
                user = await user_service.get_user_by_channel_identifier_async(
                    session=session,
                    account_id=project.account_id,
                    channel_identifier=channel_identifier,
                )
                if not user:
                    raise ValueError(
                        f"User not found for this message: account_id: {project.account_id}, channel_identifier:{channel_identifier}"
                    )
                conversation_repo = db.ConversationRepositoryAsync(session)
                conversations = (
                    await conversation_repo.get_open_conversations_by_user_id(user.id)
                )
                if not conversations:
                    logger.warning(
                        f"No matching active conversation found for call {call_id}"
                    )
                else:

                    if len(conversations) > 1:
                        logger.warning(
                            f"There are more than one open conversations for user:{user.id}"
                        )
                    conversation = sorted(
                        conversations, key=lambda c: c.created_at, reverse=True
                    )[0]

                    logger.debug(
                        f"Found conversation: {conversation.id} with url: {conversation.vapi_control_url} for call {call_id}"
                    )
                    if not conversation.vapi_control_url:
                        conversation.vapi_control_url = control_url
            else:
                logger.warning(
                    f"Missing phone number data for customer_number: {customer_number} and phone_number: {phone_number}"
                )
        else:
            logger.debug(
                f"No control URL: {control_url} or model: {model_data} available for call {call_id}"
            )

        # Acknowledge status updates
        return {"status": "acknowledged"}
    except Exception as e:
        call_data = message_data.get("call", {})
        call_id = call_data.get("id")
        logger.error(f"Error in handle_status_update: {str(e)}, call: {call_id}")
        return {"error": str(e)}


def handle_function_call(message_data):
    """
    Handle function-call message type.
    This is sent when the Assistant wants to call a function.

    Args:
        message_data: The message data from the request

    Returns:
        dict: Response for VAPI
    """
    try:
        function_call = message_data.get("functionCall", {})
        function_name = function_call.get("name")
        function_args = function_call.get("arguments", {})
        call_data = message_data.get("call", {})
        call_id = call_data.get("id")

        logger.debug(
            f"Function call received for call {call_id}: {function_name} with args: {json.dumps(function_args)}"
        )

        # Handle different function types
        if function_name == "record_message":
            return handle_record_message(function_args, call_data, message_data)
        else:
            # Unknown function
            logger.warning(f"Unknown function call: {function_name}")
            return {
                "type": "function-call-response",
                "functionCall": {
                    "name": function_name,
                    "response": {"error": f"Unknown function: {function_name}"},
                },
            }
    except Exception as e:
        logger.error(f"Error in handle_function_call: {str(e)}")
        return {"error": str(e)}


def handle_record_message(args, call_data, message_data):
    """
    Handle the record_message function call.

    Args:
        args: The function arguments
        call_data: Information about the call
        message_data: The full message data

    Returns:
        dict: Response for VAPI
    """
    try:
        # Extract message details
        caller_name = args.get("caller_name", "Unknown")
        message_content = args.get("message", "")
        callback_number = args.get("callback_number", "")

        # Use the caller's number from the call data if callback_number wasn't provided
        if not callback_number:
            customer_data = message_data.get("customer", {})
            callback_number = customer_data.get("number", "Unknown")

        # Extract business information
        phone_number_data = message_data.get("phoneNumber", {})
        phone_number_name = phone_number_data.get("name", "")
        business_name = "default"
        if phone_number_name and ":" in phone_number_name:
            business_name = phone_number_name.split(":", 1)[1]

        # Log the message (in a real implementation, you'd store this in a database)
        logger.debug(
            f"Message recorded for {business_name}: Name: {caller_name}, Message: {message_content}, Callback: {callback_number}"
        )

        # Return success response
        return {
            "type": "function-call-response",
            "functionCall": {
                "name": "record_message",
                "response": {
                    "success": True,
                    "message": "Message recorded successfully",
                    "reference_id": call_data.get("id", "unknown_call"),
                },
            },
        }
    except Exception as e:
        logger.error(f"Error recording message: {str(e)}")
        return {
            "type": "function-call-response",
            "functionCall": {
                "name": "record_message",
                "response": {"success": False, "error": str(e)},
            },
        }


def handle_transcript_update(message_data):
    """
    Handle transcript-update message type.
    This is sent when new transcripts are available.

    Args:
        message_data: The message data from the request

    Returns:
        dict: Response for VAPI
    """
    try:
        transcript = message_data.get("transcript", {})
        call_data = message_data.get("call", {})
        call_id = call_data.get("id")

        logger.debug(f"Transcript update for call {call_id}: {transcript}")

        # Just acknowledge transcript updates
        return {"status": "acknowledged"}
    except Exception as e:
        logger.error(f"Error in handle_transcript_update: {str(e)}")
        return {"error": str(e)}


async def handle_session_closure(message_data, session: AsyncSession):
    """
    Handle end-of-call-report message type.
    This is sent when a call has ended and the conversation should be closed.

    Args:
        message_data: The message data from the request

    Returns:
        dict: Response for VAPI
    """
    try:
        # Extract call information
        call_data = message_data.get("call", {})
        call_id = call_data.get("id")

        # Extract caller information
        customer_data = message_data.get("customer", {})
        customer_number = customer_data.get("number", "")

        # Extract business information
        phone_number_data = message_data.get("phoneNumber", {})
        phone_number = phone_number_data.get("number", "")

        logger.debug(
            f"Session closure request for call {call_id} from {customer_number} to {phone_number}"
        )

        # Find the conversation by caller information and update its status
        channel_identifier = f"voice:{customer_number}"
        project_channel_identifier = f"voice:{phone_number}"

        project_repo = db.ProjectRepositoryAsync(session)
        project = await project_repo.get_project_by_channel_identifier(
            project_channel_identifier
        )
        if not project:
            raise ValueError(
                f"Project not found for this message: {project_channel_identifier}"
            )

        user = await user_service.get_user_by_channel_identifier_async(
            session=session,
            account_id=project.account_id,
            channel_identifier=channel_identifier,
        )
        if not user:
            raise ValueError(
                f"User not found for this message: account_id: {project.account_id}, channel_identifier:{channel_identifier}"
            )

        conversation_repo = db.ConversationRepositoryAsync(session)
        conversations = await conversation_repo.get_open_conversations_by_user_id(
            user.id
        )

        if not conversations:
            logger.warning(f"No matching active conversation found for call {call_id}")
        else:
            if len(conversations) > 1:
                logger.warning(
                    f"There are {len(conversations)} open conversations exist for user: {user.id}"
                )
            for conversation in conversations:
                conversation.status = db.ConversationStatus.CLOSING

            await session.commit()

        # Measure and record voice-to-voice latency metrics
        await _measure_voice_to_voice_latency(message_data)

        return {
            "status": "session closed",
        }

    except Exception as e:
        logger.error(f"Error in handle_session_closure: {str(e)}")
        return {"error": str(e)}
