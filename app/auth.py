import json
import os

import jwt
import requests
import streamlit as st
from jwt.algorithms import RSAAlgorithm
from streamlit_cognito_auth import CognitoAuthenticator

AWS_REGION = os.environ["AWS_REGION"]
AWS_USER_POOL_ID = os.environ["AWS_USER_POOL_ID"]
AWS_APP_CLIENT_ID = os.environ["AWS_APP_CLIENT_ID"]
AWS_APP_CLIENT_SECRET = os.environ["AWS_APP_CLIENT_SECRET"]

AWS_COGNITO_JWKS_URL = f"https://cognito-idp.{AWS_REGION}.amazonaws.com/{AWS_USER_POOL_ID}/.well-known/jwks.json"


# Auth helper methods
def get_jwks():
    response = requests.get(AWS_COGNITO_JWKS_URL)
    response.raise_for_status()
    return response.json()


def get_public_key(jwks, kid):
    for key in jwks["keys"]:
        if key["kid"] == kid:
            return RSAAlgorithm.from_jwk(json.dumps(key))
    raise ValueError("Public key not found.")


def decode_verify_jwt(token, jwks, app_client_id):
    headers = jwt.get_unverified_header(token)
    kid = headers["kid"]
    public_key = get_public_key(jwks, kid)
    try:
        claims = jwt.decode(
            token, public_key, algorithms=["RS256"], audience=app_client_id
        )
    except jwt.ExpiredSignatureError:
        raise ValueError("Token is expired")
    except jwt.InvalidAudienceError:
        raise ValueError("Token was not issued for this audience")
    except jwt.PyJWTError as e:
        raise ValueError(f"Token verification failed: {e}")
    return claims


def parse_id_token(id_token):
    jwks = get_jwks()
    claims = decode_verify_jwt(id_token, jwks, AWS_APP_CLIENT_ID)
    return claims


def get_account_name(authenticator: CognitoAuthenticator):
    credentials = authenticator.get_credentials()
    if credentials is not None:
        id_token = credentials.id_token
    else:
        id_token = None
    try:
        claims = parse_id_token(id_token)
        return claims["custom:account_name"]
    except Exception as e:
        st.write(f"Error parsing ID token: {e}")


class User:

    def __init__(self):
        self.is_logged_in = False
        self.username = ""
        self.email = ""
        self.account_name = ""

    def update(self, authenticator: CognitoAuthenticator):
        self.is_logged_in = authenticator.is_logged_in()
        self.username = authenticator.get_username()
        self.email = authenticator.get_email()
        self.account_name = get_account_name(authenticator)

    def logout(self):
        self.is_logged_in = False
        self.username = ""
        self.email = ""
        self.account_name = ""


user = User()
