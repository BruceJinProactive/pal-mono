from fastapi import HTTPException, Request, status

# TODO: Replace with Redis or database-backed state management
# _oauth_state = {}
import threading

_oauth_state = {}
_oauth_state_lock = threading.Lock()


def valid_request(request: Request, app_name: str, is_callback=False):
    # For Square, just check the state parameter for CSRF protection
    state = request.query_params.get("state")
    if is_callback:
        if not state or state not in _oauth_state:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or missing state parameter",
            )
        del _oauth_state[state]
    return True
