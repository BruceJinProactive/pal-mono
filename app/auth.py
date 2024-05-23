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


class User:

    def __init__(self):
        self.username = ""
        self.email = ""
        self.account_name = ""


class Auth:
    username = None

    def __init__(self):
        self.authenticator = CognitoAuthenticator(
            pool_id=AWS_USER_POOL_ID,
            app_client_id=AWS_APP_CLIENT_ID,
            app_client_secret=AWS_APP_CLIENT_SECRET,
            use_cookies=True,
        )

    def auth(self):
        is_logged_in = self.authenticator.login()
        if not is_logged_in:
            st.stop()

        self.__update_user()
        self.__update_ui()

        return is_logged_in

    def logout(self):
        self.authenticator.logout()

    def __update_user(self):
        user.username = self.authenticator.get_username()
        user.email = self.authenticator.get_email()

        credentials = self.authenticator.get_credentials()
        if credentials is not None:
            id_token = credentials.id_token
        else:
            id_token = None
        try:
            claims = self.parse_id_token(id_token)
            user.account_name = claims["custom:account_name"]
        except Exception as e:
            st.write(f"Error parsing ID token: {e}")

    def __update_ui(self):
        with st.sidebar:
            st.sidebar.info(f":office: Account: {user.account_name}")
            st.sidebar.info(f":technologist: User: {user.email}")
            st.button("Logout", "logout_btn", on_click=auth.logout)

    # Private instance helper methods
    def get_jwks(self):
        response = requests.get(AWS_COGNITO_JWKS_URL)
        response.raise_for_status()
        return response.json()

    def get_public_key(self, jwks, kid):
        for key in jwks["keys"]:
            if key["kid"] == kid:
                return RSAAlgorithm.from_jwk(json.dumps(key))
        raise ValueError("Public key not found.")

    def decode_verify_jwt(self, token, jwks, app_client_id):
        headers = jwt.get_unverified_header(token)
        kid = headers["kid"]
        public_key = self.get_public_key(jwks, kid)
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

    def parse_id_token(self, id_token):
        jwks = self.get_jwks()
        claims = self.decode_verify_jwt(id_token, jwks, AWS_APP_CLIENT_ID)
        return claims


# The singleton instance
user = User()
auth = Auth()

# Only expose the singleton instance
__all__ = ["user", "auth"]
