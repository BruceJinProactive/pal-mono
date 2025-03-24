from agent.guardrails.rules.check_length import check_length


def check_input(prompt: str) -> bool:
    """
    Central function that chains all rules together.
    Returns True only if all individual checks pass.
    """
    return check_length(prompt)
