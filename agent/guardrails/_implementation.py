import os

import boto3
from botocore.exceptions import ClientError

from agent.guardrails.rules.check_blacklisted import check_blacklisted
from agent.guardrails.rules.check_code_or_injection import check_code_or_injection
from agent.guardrails.rules.check_encoded_text import check_encoded_text
from agent.guardrails.rules.check_length import check_length
from agent.guardrails.rules.check_repeated import check_repeated
from agent.guardrails.rules.check_special_characters import check_special_characters
from agent.guardrails.rules.check_unicode import check_unicode
from utils.log import logger


def check_input(prompt: str) -> bool:  # rule-based approach
    """
    Central function that chains all rules together.
    Returns True only if all individual checks pass.
    """
    checks = [
        check_length,
        check_blacklisted,
        check_repeated,
        check_encoded_text,
        check_special_characters,
        check_code_or_injection,
        check_unicode,
    ]
    return all(rule(prompt) for rule in checks)


def check_input_bedrock(prompt: str) -> bool:  # aws bedrock approach
    """
    Checks a prompt against a Bedrock guardrail.
    Returns True if the prompt is allowed (no intervention),
    False if the guardrail blocks it.
    """
    content = [{"text": {"text": prompt}}]
    AWS_REGION = os.getenv("AWS_REGION", "")
    AWS_BEDROCK_GUARDRAIL_ID = os.getenv("AWS_BEDROCK_GUARDRAIL_ID", "")
    AWS_BEDROCK_GUARDRAIL_VERSION = os.getenv("AWS_BEDROCK_GUARDRAIL_VERSION", "")

    if not (AWS_REGION and AWS_BEDROCK_GUARDRAIL_ID and AWS_BEDROCK_GUARDRAIL_VERSION):
        raise ValueError(
            f"Missing required environment variables: "
            f"AWS_REGION={AWS_REGION or '[missing]'}, "
            f"AWS_BEDROCK_GUARDRAIL_ID={AWS_BEDROCK_GUARDRAIL_ID or '[missing]'}"
            f", AWS_BEDROCK_GUARDRAIL_VERSION={AWS_BEDROCK_GUARDRAIL_VERSION or '[missing]'}"
        )

    try:
        bedrock_runtime = boto3.client("bedrock-runtime", region_name=AWS_REGION)
        response = bedrock_runtime.apply_guardrail(  # useful doc: https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_ApplyGuardrail.html
            guardrailIdentifier=AWS_BEDROCK_GUARDRAIL_ID,  # required field
            guardrailVersion=AWS_BEDROCK_GUARDRAIL_VERSION,  # required field; ex. "DRAFT", "1","2", ...
            source="INPUT",  # required field; INPUT | OUTPUT
            content=content,  # required field
        )

        if response.get("action") == "GUARDRAIL_INTERVENED":
            logger.info("Guardrail intervened:")
            for output in response.get("outputs", []):
                logger.info(f" - {output.get('text')}")
            return False
        else:
            return True

    except ClientError as e:
        logger.error(f"[ClientError] {e.response['Error']['Message']}")
        raise e
    except Exception as e:
        logger.error(f"[Error] {str(e)}")
        raise e
