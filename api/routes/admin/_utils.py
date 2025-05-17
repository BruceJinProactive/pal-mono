import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from enum import Enum
from typing import List

from fastapi import HTTPException, Request, status

import db
from db.tables.agents import AgentType
from utils import secret
from utils.log import logger


class UserRole(str, Enum):
    AccountManager = "AccountManager"
    Admin = "Admin"


@dataclass
class UserContext:
    username: str
    email: str
    groups: List[str]
    display_name: str
    account_names: List[str]
    role: UserRole


class SortOrder(str, Enum):
    asc = "asc"
    desc = "desc"


async def retrieve_body_message(request: Request) -> str:
    """
    Retrieves the 'message' field to be injected into a Message object.

    Args:
        request (Request): The FastAPI request object containing the JSON body to validate.

    Returns:
        str: The validated 'message' field from the request body.

    Raises:
        HTTPException: If the 'message' field is missing or not a string, or if there is
                       an error in processing the request body.
    """
    body = await request.json()
    try:
        body_message = body["message"]
        if not isinstance(body_message, str):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Validation error: 'message' must be a string",
            )
        return body_message
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Validation error: 'message' field is required\n\nInvalid request body: {body}",
        )
    except (ValueError, TypeError) as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,  # Unprocessable Entity
            detail=f"Validation error: {e}\n\nInvalid request body: {body}",
        )


def not_found_error(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=message,
        headers={"Content-Type": "application/json"},
    )


def verify_instagram_deauthorize_signature(
    encoded_payload: str, encoded_signature: str
):
    try:
        # Decode and parse the payload
        # Need to pad with '=' before decoding
        encoded_payload_padding = "=" * (-len(encoded_payload) % 4)
        payload_json = json.loads(
            base64.urlsafe_b64decode(encoded_payload + encoded_payload_padding)
        )

        if not isinstance(payload_json, dict) or "user_id" not in payload_json:
            raise ValueError("Invalid payload")

        app_secret = secret.get_client_secret("INSTAGRAM_APP_SECRET")

        # Verify the signature using app secret
        expected_signature_bytes = hmac.new(
            bytes(app_secret, "utf-8"),
            bytes(encoded_payload, "utf-8"),
            hashlib.sha256,
        ).digest()

        # Compare the expected and actual signatures
        # Need to pad with '=' before decoding
        encoded_signature_padding = "=" * (-len(encoded_signature) % 4)
        if not hmac.compare_digest(
            expected_signature_bytes,
            base64.urlsafe_b64decode(encoded_signature + encoded_signature_padding),
        ):
            raise ValueError("Invalid signature")

        return payload_json
    except Exception as e:
        raise ValueError(f"Error during signature verification: {e}")


def get_agent_type(agent: db.Agent) -> AgentType:
    # The agent_type defined in raw_config takes higher priority than
    # the dedicated agent_type column.
    agent_type_str = agent.agent_type_legacy
    if agent.agent_type_legacy:
        try:
            return AgentType(agent_type_str)
        except ValueError:
            logger.warn(
                f"Unrecognized agent type value in raw_config: {agent_type_str}"
            )

    return agent.agent_type
