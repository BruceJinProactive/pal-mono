import os
from typing import Any

import jwt
import requests
from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

import db
from api.schemas.admin.user import User
from services.account_service import get_account
from services.auth_types import UserContext, UserRole
from utils.log import logger

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
AWS_MANAGE_APP_USER_POOL_ID = os.environ.get("AWS_MANAGE_APP_USER_POOL_ID")
AWS_MANAGE_APP_APP_CLIENT_ID = os.environ.get("AWS_MANAGE_APP_APP_CLIENT_ID")


def get_jwks(user_pool_id: str):
    """
    Fetches the JSON Web Key Set (JWKS) from the AWS Cognito endpoint.

    The JWKS contains the public keys used to verify the signatures of JWT tokens issued by AWS Cognito.

    Args:
        user_pool_id (str): The ID of the cognito user pool.

    Returns:
        dict: A dictionary representing the JWKS.

    Raises:
        requests.exceptions.HTTPError: If the HTTP request to fetch the JWKS fails.
    """
    jwks_url = f"https://cognito-idp.{AWS_REGION}.amazonaws.com/{user_pool_id}/.well-known/jwks.json"
    response = requests.get(jwks_url)
    response.raise_for_status()
    return response.json()


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


def decode_verify_jwt(token, jwks, app_client_id) -> dict[str, Any]:
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


def parse_cognito_token(id_token, user_pool_id, app_client_id: str) -> dict[str, Any]:
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
        user_pool_id (str): ID of the cognito user pool.
        app_client_id (str): ID of the app client for the given user pool.

    Returns:
        dict: The claims contained in the verified ID token.

    Raises:
        ValueError: If the token is expired, the audience is invalid, or the token verification fails for any other reason.
    """
    jwks = get_jwks(user_pool_id)
    claims = decode_verify_jwt(id_token, jwks, app_client_id)

    return claims


def parse_admin_console_cognito_token(id_token: str) -> dict:
    return parse_cognito_token(
        id_token,
        AWS_ADMIN_CONSOLE_USER_POOL_ID,
        AWS_ADMIN_CONSOLE_APP_CLIENT_ID,
    )


def parse_manage_app_cognito_token(id_token: str) -> dict:
    return parse_cognito_token(
        id_token,
        AWS_MANAGE_APP_USER_POOL_ID or "",
        AWS_MANAGE_APP_APP_CLIENT_ID or "",
    )


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
        claims = parse_admin_console_cognito_token(id_token)
        return claims["custom:account_name"]
    except Exception as e:
        logger.error(f"Error parsing ID token: {e}")
        return None


def decrypt_id_token(request: Request) -> dict[str, Any]:
    """
    Decrypts the ID token from the request headers.

    This function retrieves the 'Authorization' header from the request,
    decrypts the ID token, and returns the decrypted token as a dictionary.
    It tries authenticating against the admin console pool first, and if that fails,
    it tries the manage app pool.

    Args:
        request (Request): The FastAPI request object containing the headers with the authorization token.

    Returns:
        dict: The decrypted ID token.

    Raises:
        HTTPException: If the ID token is invalid or missing, or if authentication fails against both pools.
    """
    auth_token = request.headers.get("Authorization")
    if not auth_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header is missing",
            headers={"Content-Type": "application/json"},
        )

    try:
        return parse_admin_console_cognito_token(auth_token)
    except ValueError as admin_error:
        if AWS_MANAGE_APP_USER_POOL_ID and AWS_MANAGE_APP_APP_CLIENT_ID:
            try:
                return parse_manage_app_cognito_token(auth_token)
            except ValueError as manage_error:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"Authentication failed: {str(manage_error)}",
                    headers={"Content-Type": "application/json"},
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Authentication failed: {str(admin_error)}",
                headers={"Content-Type": "application/json"},
            )


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
        decrypted_id_token = decrypt_id_token(request)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )

    # Get Account from ID Token
    account = get_account(
        session, account_name=decrypted_id_token["custom:account_name"]
    )

    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found.",
            headers={"Content-Type": "application/json"},
        )

    return account


def authenticate_user(request: Request) -> UserContext:
    """
    Authenticates the user from the request. Returns a user context object
    that contains useful information about the user if they are authenticated.
    Otherwise, a 401 HTTPException is raised.

    Args:
        request: incoming HTTP request

    Returns:
        UserContext: An object that contains various useful information about the user.
    Raises:
        HTTPException: If the auth token is invalid or missing.
    """
    token = decrypt_id_token(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,  # 500 because this is never expected
            detail=str("token is empty!"),
            headers={"Content-Type": "application/json"},
        )

    # Combine both custom:account_name and custom:account_names
    account_names = []

    account_name = token.get("custom:account_name", "")
    if account_name:
        account_names.extend(account_name.split(","))

    account_names_str = token.get("custom:account_names", "")
    if account_names_str:
        account_names.extend(account_names_str.split(","))

    seen = set()
    unique_account_names = []
    for name in account_names:
        name = name.strip()
        if name and name not in seen:
            seen.add(name)
            unique_account_names.append(name)

    user_role = get_user_role(token)
    return UserContext(
        username=token.get("cognito:username", ""),
        email=token.get("email", ""),
        groups=token.get("cognito:groups", []),
        display_name=token.get("name", ""),
        account_names=unique_account_names,
        role=user_role,
    )


def get_user_role(token: dict[str, Any]) -> UserRole:
    email = token.get("email", "").lower()
    if email.endswith("@proactiveailab.com") or email.endswith("@palona.ai"):
        return UserRole.Admin
    else:
        return UserRole.AccountManager


def authorize_user_account(context: UserContext, account_name: str):
    """
    Authorize a user's access to a specific account. This function checks if the
    provided account name matches the account name in the user's context. If the
    account names match or the user's role is Admin, the function allows access.
    Otherwise, an HTTPException is raised with a 403 Forbidden status, indicating
    insufficient permissions.

    Args:
        context: A UserContext object containing the user's account name and role.
        account_name: The name of the account that the user is attempting to access.

    Returns:
        None if the user is authorized to access the account.
    Raises:
        HTTPException: If the user does not have the required permissions to access
        the provided account name.
    """
    if account_name in context.account_names:
        return
    if context.role == UserRole.Admin:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="User does not have permission for the requested account",
        headers={"Content-Type": "application/json"},
    )


def authorize_admin(context: UserContext):
    if context.role != UserRole.Admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have permission for the requested resource",
            headers={"Content-Type": "application/json"},
        )


def get_user_info(context: UserContext) -> User:
    return User(
        id=context.username,
        email=context.email,
        display_name=context.display_name,
        account_name=context.account_names[0] if context.account_names else "",
    )
