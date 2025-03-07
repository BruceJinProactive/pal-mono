from fastapi import APIRouter, HTTPException, Request, status

from api.routes.endpoints import endpoints

from .shopify import _implementation

integrations_router = APIRouter(prefix=endpoints.INTEGRATIONS, tags=["Integrations"])


@integrations_router.get("/shopify/{app_name}/install", status_code=status.HTTP_200_OK)
async def install(request: Request, app_name: str):
    """
    Redirects to the installation page for the integration.
    """
    return await _implementation.install(request, app_name)


@integrations_router.get("/shopify/{app_name}/callback", status_code=status.HTTP_200_OK)
async def callback(request: Request, app_name: str):
    """
    Handles the callback from the integration.
    """
    return await _implementation.callback(request, app_name)
