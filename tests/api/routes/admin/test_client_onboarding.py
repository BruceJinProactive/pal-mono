from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel

from db.tables import ClientOnboardingContractType, ClientOnboardingStatus
from services.client_onboarding_service import (
    CreateClientOnboardingAccountResult,
    DuplicateClientOnboardingError,
)

ACCOUNT_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
AE_USER_ID = UUID("11111111-2222-3333-4444-555555555555")
FDE_USER_ID = UUID("22222222-3333-4444-5555-666666666666")
LIFECYCLE_ID = UUID("bbbbbbbb-cccc-dddd-eeee-ffffffffffff")
INVITATION_ID = UUID("99999999-8888-7777-6666-555555555555")
pytest: Any = importlib.import_module("pytest")


class _CreateAccountRequest(BaseModel):
    pass


class _AccountStatusResponse(BaseModel):
    pass


class _CreateAgentRequest(BaseModel):
    pass


class _CreateProjectRequest(BaseModel):
    pass


def _load_onboarding_schema_module(monkeypatch: Any) -> Any:
    account_module = ModuleType("api.schemas.admin.account")
    account_module.__dict__["AccountStatusResponse"] = _AccountStatusResponse
    account_module.__dict__["CreateAccountRequest"] = _CreateAccountRequest

    agent_module = ModuleType("api.schemas.admin.agent")
    agent_module.__dict__["CreateAgentRequest"] = _CreateAgentRequest

    project_module = ModuleType("api.schemas.admin.project")
    project_module.__dict__["CreateProjectRequest"] = _CreateProjectRequest

    monkeypatch.setitem(sys.modules, "api.schemas.admin.account", account_module)
    monkeypatch.setitem(sys.modules, "api.schemas.admin.agent", agent_module)
    monkeypatch.setitem(sys.modules, "api.schemas.admin.project", project_module)

    module_path = Path("api/schemas/admin/onboarding.py")
    spec = importlib.util.spec_from_file_location(
        "api.schemas.admin.onboarding",
        module_path,
    )
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "api.schemas.admin.onboarding", module)
    spec.loader.exec_module(module)
    return module


def _load_client_onboarding_route_module(monkeypatch: Any) -> Any:
    admin_package = ModuleType("api.routes.admin")
    admin_package.__dict__["__path__"] = []
    utils_module = ModuleType("api.routes.admin._utils")
    utils_module.__dict__["UserContext"] = object

    monkeypatch.setitem(sys.modules, "api.routes.admin", admin_package)
    monkeypatch.setitem(sys.modules, "api.routes.admin._utils", utils_module)

    module_path = Path("api/routes/admin/_client_onboarding.py")
    spec = importlib.util.spec_from_file_location(
        "_test_client_onboarding_route",
        module_path,
    )
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def onboarding_schema(monkeypatch: Any) -> Any:
    return _load_onboarding_schema_module(monkeypatch)


@pytest.fixture
def onboarding_request(onboarding_schema: Any) -> Any:
    return onboarding_schema.CreateClientOnboardingAccountRequest(
        account_name="acme",
        account_display_name="Acme",
        client_company_name="Acme Inc.",
        signer_name="Client Signer",
        signer_email="Signer@Example.com",
        contract_type=ClientOnboardingContractType.order_form_tos,
        order_form_id="order-123",
        docusign_envelope_id="envelope-123",
        fde_owner_user_id=FDE_USER_ID,
        folk_company_id="folk-company",
        folk_contact_id="folk-contact",
        scoping_doc_url="https://notion.example/scoping",
        idempotency_key="PAL-11566-acme",
    )


@pytest.fixture
def service_result() -> CreateClientOnboardingAccountResult:
    return CreateClientOnboardingAccountResult(
        account_id=ACCOUNT_ID,
        account_name="acme",
        account_created=True,
        lifecycle_id=LIFECYCLE_ID,
        lifecycle_status=ClientOnboardingStatus.invite_sent,
        invitation_id=INVITATION_ID,
        signer_email="signer@example.com",
        ae_owner_user_id=AE_USER_ID,
        fde_owner_user_id=FDE_USER_ID,
    )


def test_create_client_onboarding_account_returns_service_response(
    onboarding_request: Any,
    service_result: CreateClientOnboardingAccountResult,
    mocker: Any,
    monkeypatch: Any,
) -> None:
    client_onboarding_route = _load_client_onboarding_route_module(monkeypatch)
    session = MagicMock()
    context = MagicMock()
    create_account = mocker.patch.object(
        client_onboarding_route.client_onboarding_service,
        "create_client_onboarding_account",
        return_value=service_result,
    )

    response = client_onboarding_route.create_client_onboarding_account(
        onboarding_request,
        context,
        session,
    )

    assert response.account_id == ACCOUNT_ID
    assert response.lifecycle_status == ClientOnboardingStatus.invite_sent
    assert response.signer_email == "signer@example.com"
    service_params = create_account.call_args.kwargs["params"]
    assert service_params.signer_email == "Signer@example.com"
    assert service_params.docusign_envelope_id == "envelope-123"


def test_create_client_onboarding_account_maps_duplicates_to_conflict(
    onboarding_request: Any,
    mocker: Any,
    monkeypatch: Any,
) -> None:
    client_onboarding_route = _load_client_onboarding_route_module(monkeypatch)
    mocker.patch.object(
        client_onboarding_route.client_onboarding_service,
        "create_client_onboarding_account",
        side_effect=DuplicateClientOnboardingError("duplicate onboarding"),
    )

    with pytest.raises(HTTPException) as exc_info:
        client_onboarding_route.create_client_onboarding_account(
            onboarding_request,
            MagicMock(),
            MagicMock(),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "duplicate onboarding"


def test_create_client_onboarding_account_maps_value_error_to_bad_request(
    onboarding_request: Any,
    mocker: Any,
    monkeypatch: Any,
) -> None:
    client_onboarding_route = _load_client_onboarding_route_module(monkeypatch)
    mocker.patch.object(
        client_onboarding_route.client_onboarding_service,
        "create_client_onboarding_account",
        side_effect=ValueError("invalid AE user id"),
    )

    with pytest.raises(HTTPException) as exc_info:
        client_onboarding_route.create_client_onboarding_account(
            onboarding_request,
            MagicMock(),
            MagicMock(),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "invalid AE user id"


def test_create_client_onboarding_account_request_requires_docusign_reference(
    onboarding_schema: Any,
) -> None:
    with pytest.raises(ValueError, match="At least one DocuSign reference is required"):
        onboarding_schema.CreateClientOnboardingAccountRequest(
            account_name="acme",
            client_company_name="Acme Inc.",
            signer_email="signer@example.com",
            contract_type=ClientOnboardingContractType.order_form_tos,
        )


def test_create_client_onboarding_account_request_rejects_blank_docusign_reference(
    onboarding_schema: Any,
) -> None:
    with pytest.raises(ValueError, match="At least one DocuSign reference is required"):
        onboarding_schema.CreateClientOnboardingAccountRequest(
            account_name="acme",
            client_company_name="Acme Inc.",
            signer_email="signer@example.com",
            contract_type=ClientOnboardingContractType.order_form_tos,
            docusign_contract_id="   ",
        )
