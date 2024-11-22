import json
import os

from boto3.session import Session
from botocore.exceptions import ClientError

AWS_REGION = os.getenv("AWS_REGION", "")
AWS_CLIENT_SECRET_NAME = os.getenv("AWS_CLIENT_SECRET_NAME", "")

"""
In AWS Secret Manager, each "secret" is a collection of "tags", or key-value pairs.
Tags can be added to or removed from a secret using the AWS Secrets Manager API.
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


def tag_client_resource(secret_key: str, secret_value: str) -> dict:
    """
    Add a tag (key-value pair) to the AWS Secrets Manager secret
    See https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/secretsmanager/client/tag_resource.html
    """

    # Create a Secrets Manager client
    session = Session()
    client = session.client(service_name="secretsmanager", region_name=AWS_REGION)

    try:
        tag_resource_response = client.tag_resource(
            SecretId=AWS_CLIENT_SECRET_NAME,
            Tags=[{"Key": secret_key, "Value": secret_value}],
        )
    except ClientError as e:
        # For a list of exceptions thrown, see
        # https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_TagResource.html
        raise e

    return tag_resource_response


def untag_client_resource(secret_key: str) -> dict:
    """
    Remove a tag (key-value pair) from the AWS Secrets Manager secret
    See https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/secretsmanager/client/untag_resource.html
    """

    # Create a Secrets Manager client
    session = Session()
    client = session.client(service_name="secretsmanager", region_name=AWS_REGION)

    try:
        untag_resource_response = client.untag_resource(
            SecretId=AWS_CLIENT_SECRET_NAME, TagKeys=[secret_key]
        )
    except ClientError as e:
        # For a list of exceptions thrown, see
        # https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_UntagResource.html
        raise e

    return untag_resource_response
