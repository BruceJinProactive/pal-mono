from agent.guardrails.rules.check_blacklisted import check_blacklisted
from agent.guardrails.rules.check_length import check_length
from agent.guardrails.rules.check_repeated import check_repeated


def check_input(prompt: str) -> bool:
    """
    Central function that chains all rules together.
    Returns True only if all individual checks pass.
    """
    checks = [check_length, check_blacklisted, check_repeated]
    return all(rule(prompt) for rule in checks)
