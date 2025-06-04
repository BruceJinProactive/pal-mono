import json
import os

from boto3.session import Session
from botocore.exceptions import ClientError

AWS_REGION = os.getenv("AWS_REGION", "")
AWS_CLIENT_SECRET_NAME = os.getenv("AWS_CLIENT_SECRET_NAME", "")
AWS_SERVER_SECRET_NAME = os.getenv("AWS_SERVER_SECRET_NAME", "")

"""
In AWS Secret Manager, each "secret" is a collection of key-value pairs.
These can be added to or removed from a secret using the AWS Secrets Manager API.
"""


def get_client_secret(secret_key: str) -> str:
    """
    Retrieves secret value stored in the client secret store.
    """
    return get_secret(secret_key, AWS_CLIENT_SECRET_NAME)


def get_server_secret(secret_key: str) -> str:
    """
    Retrieves secret value stored in the server secret store.
    """
    return get_secret(secret_key, AWS_SERVER_SECRET_NAME)


def get_client_secret_with_fallback(secret_key: str) -> str:
    """
    Retrieve the value of a secret key from AWS Secrets Manager or fallback to an environment variables.

    Args:
        secret_key (str): The key of the secret to retrieve.

    Returns:
        str: The value of the secret.

    Raises:
        ValueError: If the secret is not found in AWS Secrets Manager or environment variables.
    """
    try:
        # Attempt to retrieve the secret from AWS Secrets Manager
        secret_value = get_client_secret(secret_key)
    except Exception:
        # Fallback to environment variable
        secret_value = os.getenv(secret_key, "")

    if not secret_value:
        raise ValueError(
            f"Secret not found in AWS Secrets Manager or environment variables for key: {secret_key}"
        )

    return secret_value


def get_secret(secret_key: str, secret_store: str) -> str:
    """
    Retrieve a secret value from AWS Secrets Manager using a secret_key
    """

    # Create a Secrets Manager client
    session = Session()
    client = session.client(service_name="secretsmanager", region_name=AWS_REGION)

    try:
        get_secret_value_response = client.get_secret_value(SecretId=secret_store)
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

    try:
        return secret_dict[secret_key]
    except KeyError:
        runtime_env = os.getenv("RUNTIME_ENV", "")
        if runtime_env == "" or runtime_env == "dev":
            secret_value = os.getenv(secret_key, "")

            if secret_value:
                return secret_value

        raise KeyError(f"Secret not found in AWS Secrets Manager for key: {secret_key}")


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


def upsert_client_secret(secret_key: str, secret_value: str) -> dict:
    """
    Update/add a key-value pair to the AWS Secrets Manager secret
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
    secret_dict[secret_key] = secret_value
    # Update the secret with the modified data
    put_secret_response = client.put_secret_value(
        SecretId=AWS_CLIENT_SECRET_NAME, SecretString=json.dumps(secret_dict)
    )

    return put_secret_response


def _get_client_secrets():
    """
    Retrieve all key-value pairs from the AWS Secrets Manager secret
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

    return secret_dict
