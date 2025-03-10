import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import List

from fastapi import HTTPException, Request, status

from utils import secret


@dataclass
class UserContext:
    username: str
    email: str
    groups: List[str]
    display_name: str
    account_name: str
    account_display_name: str


async def retrieve_body_brand(request: Request) -> tuple[str, str]:
    """
    Retrieves the 'brandKey' and 'brandValue' fields from the request body.

    Args:
        request (Request): The FastAPI request object containing the JSON body to validate.

    Returns:
        tuple[str, str]: A tuple containing the validated 'brandKey' and 'brandValue' fields from the request body.

    Raises:
        HTTPException: If the 'brandKey' or 'brandValue' field is missing or not a string, or if there is
                       an error in processing the request body.
    """
    body = await request.json()
    try:
        brand_key = body["brandKey"]
        brand_value = body["brandValue"]
        if not isinstance(brand_key, str) or not isinstance(brand_value, str):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Validation error: 'brandKey' and 'brandValue' must be strings. Received types: {type(brand_key)}, {type(brand_value)}",
            )
        return (brand_key, brand_value)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Validation error: missing 'brandKey' or 'brandValue'\n\n"
            f"Invalid request body: {body}",
        )
    except (ValueError, TypeError) as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,  # Unprocessable Entity
            detail=f"Validation error: {e}\n\nInvalid request body: {body}",
        )


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
