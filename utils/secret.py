import json
import os

from boto3.session import Session
from botocore.exceptions import ClientError

AWS_REGION = os.getenv("AWS_REGION", "")
AWS_CLIENT_SECRET_NAME = os.getenv("AWS_CLIENT_SECRET_NAME", "")


def get_client_secret(secret_key: str) -> str:
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
