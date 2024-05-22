import json
import os

import jwt
import requests
import streamlit as st
from jwt.algorithms import RSAAlgorithm
from streamlit_cognito_auth import CognitoAuthenticator

from db.repositories.account_repository import AccountRepository
from db.session import get_db

st.set_page_config(
    page_title="Account Test",
    page_icon=":key:",
)
st.title("Account Test")

AWS_DEFAULT_REGION = os.environ["AWS_DEFAULT_REGION"]
AWS_USER_POOL_ID = os.environ["AWS_USER_POOL_ID"]
AWS_APP_CLIENT_ID = os.environ["AWS_APP_CLIENT_ID"]
AWS_APP_CLIENT_SECRET = os.environ["AWS_APP_CLIENT_SECRET"]

# Cognito JWKS URL
JWKS_URL = f"https://cognito-idp.{AWS_DEFAULT_REGION}.amazonaws.com/{AWS_USER_POOL_ID}/.well-known/jwks.json"

authenticator = CognitoAuthenticator(
    pool_id=AWS_USER_POOL_ID,
    app_client_id=AWS_APP_CLIENT_ID,
    app_client_secret=AWS_APP_CLIENT_SECRET,
    use_cookies=False,
)


def logout():
    print("Logout in example")
    authenticator.logout()


def get_jwks():
    response = requests.get(JWKS_URL)
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


is_logged_in = authenticator.login()
if not is_logged_in:
    st.stop()
else:
    st.write("---")
    st.write("## Account info from Cognito")

    st.write("- username: ", authenticator.get_username())
    st.write("- email: ", authenticator.get_email())

    # Example usage
    credentials = authenticator.get_credentials()
    if credentials is not None:
        id_token = credentials.id_token
    else:
        id_token = None
    try:
        claims = parse_id_token(id_token)
        st.write("- claims: ", json.dumps(claims, indent=4))
        st.write("- account_name: ", claims["custom:account_name"])

        st.write("---")
        st.write("## Account details from RDS")

        db = next(get_db())
        account_repository = AccountRepository(db)

        account_id = int(st.number_input("Enter Account ID", step=1))
        account_name = st.text_input("Enter Account Name")
        if st.button("Get Accounts"):
            accounts = account_repository.get_accounts()
            for account in accounts:
                st.write(account)
        if st.button("Get Account"):
            account = account_repository.get_account(account_id, account_name)
            st.write(account)
        if st.button("Create Account"):
            account = account_repository.create_account(account_name)
            st.write(account)
        if st.button("Update Account"):
            account = account_repository.update_account(account_id, account_name)
            st.write(account)
        if st.button("Delete Account"):
            account = account_repository.delete_account(account_id)
            st.write(account)

    except Exception as e:
        st.write(f"Error parsing ID token: {e}")


with st.sidebar:
    st.text(f"Welcome,\n{authenticator.get_email()}")
    st.button("Logout", "logout_btn", on_click=logout)
