from agent.guardrails.rules.check_blacklisted import check_blacklisted
from agent.guardrails.rules.check_code_or_injection import check_code_or_injection
from agent.guardrails.rules.check_encoded_text import check_encoded_text
from agent.guardrails.rules.check_length import check_length
from agent.guardrails.rules.check_repeated import check_repeated
from agent.guardrails.rules.check_special_characters import check_special_characters
from agent.guardrails.rules.check_unicode import check_unicode


def check_input(prompt: str) -> bool:
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
