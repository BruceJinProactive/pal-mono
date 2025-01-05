import os

import jwt
import requests
from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

import db
from services.account_service import get_account

"""
This module provides authentication and authorization utilities for the admin console using AWS Cognito.

The functions are ordered by responsibility:
1. Fetching and caching the JSON Web Key Set (JWKS) from AWS Cognito.
2. Decoding and verifying JSON Web Tokens (JWT) using the JWKS.
3. Parsing ID tokens issued by AWS Cognito for the admin console.
4. Extracting account information from ID tokens.
5. Retrieving account details from the database based on the ID token.
"""

AWS_REGION = os.environ["AWS_REGION"]
AWS_ADMIN_CONSOLE_USER_POOL_ID = os.environ["AWS_ADMIN_CONSOLE_USER_POOL_ID"]
AWS_ADMIN_CONSOLE_APP_CLIENT_ID = os.environ["AWS_ADMIN_CONSOLE_APP_CLIENT_ID"]

AWS_COGNITO_JWKS_URL = f"https://cognito-idp.{AWS_REGION}.amazonaws.com/{AWS_ADMIN_CONSOLE_USER_POOL_ID}/.well-known/jwks.json"


def get_jwks():
    """
    Fetches the JSON Web Key Set (JWKS) from the AWS Cognito endpoint.

    The JWKS contains the public keys used to verify the signatures of JWT tokens issued by AWS Cognito.

    Returns:
        dict: A dictionary representing the JWKS.

    Raises:
        requests.exceptions.HTTPError: If the HTTP request to fetch the JWKS fails.
    """
    response = requests.get(AWS_COGNITO_JWKS_URL)
    response.raise_for_status()
    return response.json()


# Saving the JWKS in a variable to prevent excessive requests to the AWS Cognito endpoint
jwks = get_jwks()


def get_public_key(jwks, kid):
    """
    Retrieves the public key from the JSON Web Key Set (JWKS) for a given key ID (kid).

    Args:
        jwks (dict): The JSON Web Key Set containing the public keys.
        kid (str): The key ID for which the public key is to be retrieved.

    Returns:
        RSAAlgorithm: The RSA public key corresponding to the given key ID.

    Raises:
        ValueError: If the public key with the specified key ID is not found in the JWKS.
    """
    for key in jwks["keys"]:
        if key["kid"] == kid:
            jwk_obj = jwt.PyJWK.from_dict(key)
            return jwk_obj.key
    raise ValueError("Public key not found.")


def decode_verify_jwt(token, jwks, app_client_id):
    """
    Decodes and verifies a JSON Web Token (JWT) using the provided JSON Web Key Set (JWKS) and application client ID.

    Args:
        token (str): The JWT to be decoded and verified.
        jwks (dict): The JSON Web Key Set containing the public keys.
        app_client_id (str): The application client ID to verify the token's audience.

    Returns:
        dict: The claims contained in the verified JWT.

    Raises:
        ValueError: If the token is expired, the audience is invalid, or the token verification fails for any other reason.
    """
    headers = jwt.get_unverified_header(token)
    kid = headers["kid"]
    public_key = get_public_key(jwks, kid)

    try:
        claims = jwt.decode(
            token, key=public_key, algorithms=["RS256"], audience=app_client_id
        )
    except jwt.ExpiredSignatureError:
        raise ValueError("Token is expired")
    except jwt.InvalidAudienceError:
        raise ValueError("Token was not issued for this audience")
    except jwt.PyJWTError as e:
        raise ValueError(f"Token verification failed: {e}")
    return claims


def parse_admin_console_id_token(id_token):
    """
    Parses and verifies an ID token issued by AWS Cognito for the admin console.

    The function decodes and verifies the ID token using the JSON Web Key Set (JWKS) and the application client ID.
    It returns the claims contained in the verified ID token.

    Example of decrypted ID token:
    {
        "sub": "<UUID = cognito:username>",                        # Same as 'cognito:username'
        "cognito:groups": ["<organization>-admins"],               # User group for administrative or marketing privileges
        "custom:account_name": "<organization-name>",              # User's immutable organization identifier
        "custom:account_display_name": "<organization-name>",      # User's public facing organization name
        "iss": "<URL of Issuer>",
        "cognito:username": "<UUID = sub>",                        # Same as 'sub'
        "origin_jti": "<UUID>",
        "aud": "<Audience Claim String>",
        "event_id": "<UUID>",
        "token_use": "id",
        "auth_time": <Unix Timestamp>,
        "exp": <Unix Timestamp>,
        "iat": <Unix Timestamp>,
        "jti": "<UUID>",
        "email": "<name>@<organization-domain>.com",
    }

    Args:
        id_token (str): The ID token to be parsed and verified.

    Returns:
        dict: The claims contained in the verified ID token.

    Raises:
        ValueError: If the token is expired, the audience is invalid, or the token verification fails for any other reason.
    """
    claims = decode_verify_jwt(id_token, jwks, AWS_ADMIN_CONSOLE_APP_CLIENT_ID)
    return claims


def get_account_name(id_token):
    """
    Extracts the account name from an AWS Cognito ID token.

    This function parses and verifies the provided ID token to extract the custom account name claim.
    If the token is invalid or the account name cannot be extracted, it returns None.

    Args:
        id_token (str): The ID token to be parsed and verified.

    Returns:
        str: The account name extracted from the ID token, or None if an error occurs.

    Raises:
        Exception: If there is an error parsing or verifying the ID token.
    """
    try:
        claims = parse_admin_console_id_token(id_token)
        return claims["custom:account_name"]
    except Exception as e:
        print(f"Error parsing ID token: {e}")
        return None


def decrypt_id_token(request: Request) -> dict:
    """
    Decrypts the ID token from the request headers.

    This function retrieves the 'Authorization' header from the request,
    decrypts the ID token, and returns the decrypted token as a dictionary.

    Args:
        request (Request): The FastAPI request object containing the headers with the authorization token.

    Returns:
        dict: The decrypted ID token.

    Raises:
        HTTPException: If the ID token is invalid or missing.
    """
    try:
        decrypted_id_token = parse_admin_console_id_token(
            request.headers.get("Authorization")
        )
    except ValueError as e:
        raise HTTPException(
            status_code=401,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )
    return decrypted_id_token


def get_account_from_id_token(request: Request, session: Session) -> db.Account:
    """
    Retrieves the account associated with the ID token from the request headers.

    This function decrypts the ID token from the 'Authorization' header,
    retrieves the account information from the database using the account name
    in the decrypted token, and returns the account.

    Args:
        request (Request): The FastAPI request object containing the headers with the authorization token.
        session (Session): The SQLAlchemy session for database access.

    Returns:
        db.Account: The account associated with the ID token.

    Raises:
        HTTPException: If the ID token is invalid or missing, or if the account is not found.
    """
    try:
        decrypted_id_token = parse_admin_console_id_token(
            request.headers.get("Authorization")
        )
    except ValueError as e:
        raise HTTPException(
            status_code=401,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )

    # Get Account from ID Token
    account = get_account(
        session, account_name=decrypted_id_token["custom:account_name"]
    )

    if account is None:
        raise HTTPException(
            status_code=500,
            detail="Account not found.",
            headers={"Content-Type": "application/json"},
        )

    return account
