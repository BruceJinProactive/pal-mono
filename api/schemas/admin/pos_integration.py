import uuid

from pydantic import BaseModel

from db.tables.pos_integration import POSProvider, POSState


class CreatePOSIntegrationRequest(BaseModel):
    store_identifier: str
    provider: POSProvider
    state: POSState = POSState.ACTIVATE


class SetupProjectPOSIntegrationRequest(BaseModel):
    """Request to setup POS integration for a project"""

    project_id: uuid.UUID
    store_identifier: str
    provider: POSProvider
    state: POSState = POSState.ACTIVATE
