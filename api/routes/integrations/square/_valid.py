from fastapi import HTTPException, Request, status

from utils.log import logger


def valid_request(request: Request, is_callback=False):
    if is_callback:
        state = request.query_params.get("state")
        if not state:
            logger.error(f"[Square OAuth] Invalid or missing state parameter: {state}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or missing state parameter",
            )
        return state
    return True
