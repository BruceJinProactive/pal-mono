import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from api.routes.v1_router import v1_router
from api.settings import api_settings
from utils.log import configure_global_logger, logger, patch_agno_logger_to_use_root


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs on startup
    loop = asyncio.get_event_loop()
    logger.info(f"Using event loop: {loop.__class__.__name__}")

    yield

    # Runs on shutdown
    logger.info("App is shutting down")


def create_app(lifespan=lifespan) -> FastAPI:
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
        lifespan=lifespan,
    )

    # Add v1 router
    app.include_router(v1_router)

    # Add Middlewares
    app.add_middleware(
        CORSMiddleware,
        allow_origins=api_settings.cors_origin_list or [],
        allow_origin_regex=r"https://.*-proactiveailab\.vercel\.app",  # For Vercel Preview URLs
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    return app


# Configure global logger
configure_global_logger()
patch_agno_logger_to_use_root()

# Create FastAPI app
app = create_app()
