import os

import boto3
from botocore.exceptions import ClientError
from ddtrace.llmobs.decorators import task

from agent.guardrails.rules.check_blacklisted import check_blacklisted
from agent.guardrails.rules.check_code_or_injection import check_code_or_injection
from agent.guardrails.rules.check_encoded_text import check_encoded_text
from agent.guardrails.rules.check_length import check_length
from agent.guardrails.rules.check_repeated import check_repeated
from agent.guardrails.rules.check_special_characters import check_special_characters
from agent.guardrails.rules.check_unicode import check_unicode
from utils.log import logger


@task
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


@task(name="Bedrock Checking")
def check_input_bedrock(prompt: str) -> bool:  # aws bedrock approach
    """
    Checks a prompt against a Bedrock guardrail.
    Gets region, guardrail ID, and guardrail version from environment variables.

    Args:
        prompt: The text to check

    Returns:
        True if the prompt is allowed (no intervention),
        False if the guardrail blocks it.
    """
    # Get region and version from environment variables
    region = os.getenv("AWS_REGION", "")
    guardrail_version = os.getenv("AWS_BEDROCK_GUARDRAIL_VERSION", "")
    guardrail_id = os.getenv("AWS_BEDROCK_GUARDRAIL_ID", "")

    content = [{"text": {"text": prompt}}]

    if not region or not guardrail_version or not guardrail_id:
        raise ValueError(
            f"Values missing for Bedrock guardrail checks. "
            f"Region: {region or '[missing]'}, "
            f"Guardrail version: {guardrail_version or '[missing]'}, "
            f"Guardrail ID: {guardrail_id or '[missing]'}"
        )

    try:
        bedrock_runtime = boto3.client("bedrock-runtime", region_name=region)
        response = bedrock_runtime.apply_guardrail(  # useful doc: https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_ApplyGuardrail.html
            guardrailIdentifier=guardrail_id,
            guardrailVersion=guardrail_version,  # ex. "DRAFT", "1","2", ...
            source="INPUT",  # INPUT | OUTPUT
            content=content,  #
        )

        if response.get("action") == "GUARDRAIL_INTERVENED":
            logger.debug("Guardrail intervened:")
            for output in response.get("outputs", []):
                logger.debug(f" - {output.get('text')}")
            return False
        else:
            return True

    except ClientError as e:
        logger.error(f"[ClientError] {e.response['Error']['Message']}")
        raise e
    except Exception as e:
        logger.error(f"[Error] {str(e)}")
        raise e
