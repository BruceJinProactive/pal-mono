from aws_xray_sdk.core import xray_recorder
from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware

from api.routes.v1_router import v1_router
from api.settings import api_settings

# Configure X-Ray
xray_recorder.configure(service="pal-mono-api")


class XRayMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        with xray_recorder.in_segment("fastapi_request") as segment:
            segment.put_annotation("path", request.url.path)
            segment.put_annotation("method", request.method)
            response = await call_next(request)
            segment.put_annotation("status_code", response.status_code)
        return response


def create_app() -> FastAPI:
    """Create a FastAPI App

    Returns:
        FastAPI: FastAPI App
    """

    # Create FastAPI App
    app: FastAPI = FastAPI(
        title=api_settings.title,
        version=api_settings.version,
        docs_url="/docs" if api_settings.docs_enabled else None,
        redoc_url="/redoc" if api_settings.docs_enabled else None,
        openapi_url="/openapi.json" if api_settings.docs_enabled else None,
    )

    # Add v1 router
    app.include_router(v1_router)

    # Add Middlewares
    app.add_middleware(
        CORSMiddleware,
        allow_origins=api_settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    return app


# Create FastAPI app
app = create_app()

# Add X-Ray middleware
app.add_middleware(XRayMiddleware)
