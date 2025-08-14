import threading

from fastapi import HTTPException, Request, status

from utils.log import logger

_oauth_state = {}
_oauth_state_lock = threading.Lock()


def valid_request(request: Request, is_callback=False):
    # For Square, just check the state parameter for CSRF protection
    state = request.query_params.get("state")
    logger.info(f"[Square OAuth] uncleaned state inside valid_request: {state}")
    state = state.replace("#_=_", "") if state else None
    logger.info(f"Cleaned state inside valid_request: {state}")
    if is_callback:
        if not state or state not in _oauth_state:
            logger.error(f"[Square OAuth] Invalid or missing state parameter: {state}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or missing state parameter",
            )
        account_name = _oauth_state[state]
        del _oauth_state[state]
        return account_name
    return True
