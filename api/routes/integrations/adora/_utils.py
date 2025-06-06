from fastapi import Request


def is_dev_mode(request: Request) -> bool:
    """
    Check if the request has a 'dev' header set to true.
    This is used to activate development-specific workflows.

    Args:
        request: The FastAPI request object

    Returns:
        bool: True if dev mode is enabled, False otherwise
    """
    dev_header = request.headers.get("dev", "false").lower()
    return dev_header == "true"
