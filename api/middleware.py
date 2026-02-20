import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from utils.log import logger, request_id_ctx


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware that adds correlation ID and logs request/response summary."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Extract or generate correlation ID
        rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        token = request_id_ctx.set(rid)

        start = time.monotonic()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = rid
            return response
        except Exception:
            logger.exception(
                "Unhandled exception during request %s %s",
                request.method,
                request.url.path,
            )
            raise
        finally:
            duration_ms = (time.monotonic() - start) * 1000
            logger.info(
                "%s %s %d %.1fms",
                request.method,
                request.url.path,
                status_code,
                duration_ms,
                extra={"request_id": rid, "duration_ms": round(duration_ms, 1)},
            )
            request_id_ctx.reset(token)
