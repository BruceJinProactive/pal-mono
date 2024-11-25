import json
import os

from boto3.session import Session
from botocore.exceptions import ClientError

AWS_REGION = os.getenv("AWS_REGION", "")
AWS_CLIENT_SECRET_NAME = os.getenv("AWS_CLIENT_SECRET_NAME", "")

"""
In AWS Secret Manager, each "secret" is a collection of key-value pairs.
These can be added to or removed from a secret using the AWS Secrets Manager API.
"""


def get_client_secret(secret_key: str) -> str:
    """
    Retrieve a secret value from AWS Secrets Manager using a secret_key
    """

    # Create a Secrets Manager client
    session = Session()
    client = session.client(service_name="secretsmanager", region_name=AWS_REGION)

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=AWS_CLIENT_SECRET_NAME
        )
    except ClientError as e:
        # For a list of exceptions thrown, see
        # https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html
        raise e

    # Decrypts secret using the associated KMS key.
    if "SecretString" in get_secret_value_response:
        secret = get_secret_value_response["SecretString"]
    else:
        secret = get_secret_value_response["SecretBinary"]

    # Parse the secret string as JSON and extract the value for the given key
    secret_dict = json.loads(secret)
    return secret_dict[secret_key]


def add_client_secret(secret_key: str, secret_value: str) -> dict:
    """
    Add a key-value pair to the AWS Secrets Manager secret
    """

    # Create a Secrets Manager client
    session = Session()
    client = session.client(service_name="secretsmanager", region_name=AWS_REGION)

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=AWS_CLIENT_SECRET_NAME
        )
    except ClientError as e:
        # For a list of exceptions thrown, see
        # https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html
        raise e

    # Decrypts secret using the associated KMS key.
    if "SecretString" in get_secret_value_response:
        secret = get_secret_value_response["SecretString"]
    else:
        secret = get_secret_value_response["SecretBinary"]

    # Parse the secret string as JSON
    secret_dict = json.loads(secret)

    # Add the key from the secret
    if secret_key not in secret_dict:
        secret_dict[secret_key] = secret_value
    else:
        raise KeyError(f"Key '{secret_key}' already exists in the secret.")

    # Update the secret with the modified data
    put_secret_response = client.put_secret_value(
        SecretId=AWS_CLIENT_SECRET_NAME, SecretString=json.dumps(secret_dict)
    )

    return put_secret_response


def remove_client_secret(secret_key: str) -> dict:
    """
    Remove a key-value pair from the AWS Secrets Manager secret
    """

    # Create a Secrets Manager client
    session = Session()
    client = session.client(service_name="secretsmanager", region_name=AWS_REGION)

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=AWS_CLIENT_SECRET_NAME
        )
    except ClientError as e:
        # For a list of exceptions thrown, see
        # https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html
        raise e

    # Decrypts secret using the associated KMS key.
    if "SecretString" in get_secret_value_response:
        secret = get_secret_value_response["SecretString"]
    else:
        secret = get_secret_value_response["SecretBinary"]

    # Parse the secret string as JSON
    secret_dict = json.loads(secret)

    # Remove the key from the secret
    if secret_key in secret_dict:
        del secret_dict[secret_key]
    else:
        raise KeyError(f"Key '{secret_key}' not found in the secret.")

    # Update the secret with the modified data
    put_secret_response = client.put_secret_value(
        SecretId=AWS_CLIENT_SECRET_NAME, SecretString=json.dumps(secret_dict)
    )

    return put_secret_response
