import uuid
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi import HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from api.routes import admin as admin_routes
from api.routes.admin._catering import (
    import_account_catering_menu_items,
    parse_catering_menu_csv,
)
from db.pal_repository.catering_menu import CateringMenuRepository
from db.repositories.project_repository import ProjectRepositoryAsync
from db.tables import CateringMenu
from services import catering_service
from services.auth_types import UserContext, UserRole


def _upload(content: bytes, filename: str = "menu.csv") -> UploadFile:
    return UploadFile(filename=filename, file=BytesIO(content))


class _Session:
    def __init__(
        self,
        projects: list[SimpleNamespace] | None = None,
        existing_items: list[CateringMenu] | None = None,
    ) -> None:
        self.added: list[CateringMenu] = []
        self.committed = False
        self.existing_items = existing_items or []
        self.projects = projects or []

    async def commit(self) -> None:
        self.committed = True


class _ScalarResult:
    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows

    def all(self) -> list[Any]:
        return self.rows


class _ExecuteResult:
    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows

    def scalars(self) -> _ScalarResult:
        return _ScalarResult(self.rows)


class _RepositorySession(_Session):
    def __init__(self, execute_rows: list[Any] | None = None) -> None:
        super().__init__()
        self.execute_rows = execute_rows or []
        self.rolled_back = False

    async def execute(self, _statement: Any) -> _ExecuteResult:
        return _ExecuteResult(self.execute_rows)

    async def rollback(self) -> None:
        self.rolled_back = True

    def add(self, item: CateringMenu) -> None:
        self.added.append(item)


class _ProjectRepository:
    def __init__(self, session: _Session) -> None:
        self.session = session

    async def list_projects_by_account_id(
        self, _account_id: uuid.UUID
    ) -> list[SimpleNamespace]:
        return self.session.projects


class _MenuRepository:
    def __init__(self, session: _Session) -> None:
        self.session = session

    async def list_by_account_and_project_ids(
        self,
        _account_id: uuid.UUID,
        _project_ids: list[uuid.UUID],
    ) -> list[CateringMenu]:
        return self.session.existing_items

    def add(
        self,
        account_id: uuid.UUID,
        project_id: uuid.UUID,
        item_name: str,
        item_price: Decimal,
    ) -> CateringMenu:
        item = CateringMenu(
            account_id=account_id,
            project_id=project_id,
            item_name=item_name,
            item_price=item_price,
        )
        self.session.added.append(item)
        return item


def _as_async_session(session: _Session) -> AsyncSession:
    return cast(AsyncSession, session)


def test_parse_catering_menu_csv_accepts_name_and_price_aliases() -> None:
    rows = parse_catering_menu_csv(b"name,price\nBrisket,$23.00\nSides,4\n")

    assert [row.item_name for row in rows] == ["Brisket", "Sides"]
    assert [row.item_price for row in rows] == [Decimal("23.00"), Decimal("4.00")]


def test_parse_catering_menu_csv_rejects_duplicate_names() -> None:
    with pytest.raises(ValueError, match="duplicate item_name 'brisket'"):
        parse_catering_menu_csv(b"item_name,item_price\nBrisket,23\nbrisket,24\n")


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"\xff", "CSV must be UTF-8 encoded"),
        (b"", "CSV must include item_name and item_price columns"),
        (b"item_name,item_price\n\n", "CSV must contain at least one"),
        (b"item_name,item_price\n,23\n", "item_name is required"),
        (b"item_name,item_price\nBrisket,\n", "item_price is required"),
        (b"item_name,item_price\nBrisket,nope\n", "valid number"),
        (b"item_name,item_price\nBrisket,NaN\n", "valid number"),
        (b"item_name,item_price\nBrisket,Infinity\n", "valid number"),
        (b"item_name,item_price\nBrisket,-1\n", "greater than or equal to 0"),
    ],
)
def test_parse_catering_menu_csv_reports_validation_errors(
    content: bytes,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        parse_catering_menu_csv(content)


@pytest.mark.asyncio
async def test_service_import_inserts_menu_rows_for_every_account_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    account_id = uuid.uuid4()
    projects = [
        SimpleNamespace(id=uuid.uuid4(), name="spring-valley"),
        SimpleNamespace(id=uuid.uuid4(), name="san-diego"),
    ]
    session = _Session(projects=projects)

    monkeypatch.setattr(
        "services.catering_service._implementation.ProjectRepositoryAsync",
        _ProjectRepository,
    )
    monkeypatch.setattr(
        "services.catering_service._implementation.CateringMenuRepository",
        _MenuRepository,
    )

    result = await catering_service.import_account_catering_menu_items(
        _as_async_session(session),
        account_id,
        [
            catering_service.CateringMenuImportItem("Brisket", Decimal("23.00")),
            catering_service.CateringMenuImportItem("Sides", Decimal("4.00")),
        ],
    )

    assert result.rows_received == 2
    assert result.projects_updated == 2
    assert result.inserted_items == 4
    assert result.updated_items == 0
    assert session.committed is True
    assert {(item.account_id, item.project_id) for item in session.added} == {
        (account_id, projects[0].id),
        (account_id, projects[1].id),
    }
    assert {item.item_name for item in session.added} == {"Brisket", "Sides"}


@pytest.mark.asyncio
async def test_service_import_updates_existing_catering_menu_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    account_id = uuid.uuid4()
    project_id = uuid.uuid4()
    existing = CateringMenu(
        account_id=account_id,
        project_id=project_id,
        item_name="brisket",
        item_price=Decimal("20.00"),
    )
    session = _Session(
        projects=[SimpleNamespace(id=project_id, name="spring-valley")],
        existing_items=[existing],
    )

    monkeypatch.setattr(
        "services.catering_service._implementation.ProjectRepositoryAsync",
        _ProjectRepository,
    )
    monkeypatch.setattr(
        "services.catering_service._implementation.CateringMenuRepository",
        _MenuRepository,
    )

    result = await catering_service.import_account_catering_menu_items(
        _as_async_session(session),
        account_id,
        [catering_service.CateringMenuImportItem("Brisket", Decimal("23.00"))],
    )

    assert result.inserted_items == 0
    assert result.updated_items == 1
    assert existing.item_price == Decimal("23.00")
    assert session.added == []
    assert session.committed is True


@pytest.mark.asyncio
async def test_catering_menu_repository_lists_empty_project_ids() -> None:
    result = await CateringMenuRepository(
        _as_async_session(_RepositorySession())
    ).list_by_account_and_project_ids(uuid.uuid4(), [])

    assert result == []


@pytest.mark.asyncio
async def test_catering_menu_repository_lists_account_project_rows() -> None:
    existing = CateringMenu(
        account_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        item_name="Brisket",
        item_price=Decimal("20.00"),
    )
    session = _RepositorySession(execute_rows=[existing])

    result = await CateringMenuRepository(
        _as_async_session(session)
    ).list_by_account_and_project_ids(
        cast(uuid.UUID, existing.account_id),
        [existing.project_id],
    )

    assert result == [existing]


def test_catering_menu_repository_add_stages_item() -> None:
    session = _RepositorySession()
    account_id = uuid.uuid4()
    project_id = uuid.uuid4()

    item = CateringMenuRepository(_as_async_session(session)).add(
        account_id=account_id,
        project_id=project_id,
        item_name="Brisket",
        item_price=Decimal("23.00"),
    )

    assert session.added == [item]
    assert item.account_id == account_id
    assert item.project_id == project_id


@pytest.mark.asyncio
async def test_project_repository_lists_projects_by_account_id() -> None:
    project = SimpleNamespace(id=uuid.uuid4(), name="spring-valley")
    session = _RepositorySession(execute_rows=[project])

    result = await ProjectRepositoryAsync(
        _as_async_session(session)
    ).list_projects_by_account_id(uuid.uuid4())

    assert result == [project]


@pytest.mark.asyncio
async def test_route_import_returns_service_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    account_id = uuid.uuid4()

    async def get_account_async(
        _session: AsyncSession,
        _account_name: str,
    ) -> SimpleNamespace:
        return SimpleNamespace(id=account_id)

    async def import_rows(
        _session: AsyncSession,
        _account_id: uuid.UUID,
        rows: list[catering_service.CateringMenuImportItem],
    ) -> catering_service.CateringMenuImportStats:
        assert [row.item_name for row in rows] == ["Brisket"]
        return catering_service.CateringMenuImportStats(
            inserted_items=2,
            projects_updated=2,
            rows_received=1,
            updated_items=0,
        )

    monkeypatch.setattr(
        "api.routes.admin._catering.account_service.get_account_async",
        get_account_async,
    )
    monkeypatch.setattr(
        "api.routes.admin._catering.catering_service.import_account_catering_menu_items",
        import_rows,
    )

    result = await import_account_catering_menu_items(
        "calibbq",
        _upload(b"item_name,item_price\nBrisket,23\n"),
        _as_async_session(_Session()),
    )

    assert result.account_name == "calibbq"
    assert result.rows_received == 1
    assert result.projects_updated == 2
    assert result.inserted_items == 2
    assert result.updated_items == 0


@pytest.mark.asyncio
async def test_admin_route_import_delegates_to_catering_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def import_rows(
        account_name: str,
        _file: UploadFile,
        _session: AsyncSession,
    ) -> str:
        return account_name

    monkeypatch.setattr(
        "api.routes.admin._catering.import_account_catering_menu_items",
        import_rows,
    )

    result = await admin_routes.import_account_catering_menu_items(
        "calibbq",
        _upload(b"item_name,item_price\nBrisket,23\n"),
        context=UserContext(
            username="user-1",
            email="admin@example.com",
            groups=[],
            display_name="Admin",
            role=UserRole.Admin,
        ),
        session=_as_async_session(_Session()),
    )

    assert result == "calibbq"


@pytest.mark.asyncio
async def test_route_import_rejects_invalid_csv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def get_account_async(
        _session: AsyncSession,
        _account_name: str,
    ) -> SimpleNamespace:
        return SimpleNamespace(id=uuid.uuid4())

    monkeypatch.setattr(
        "api.routes.admin._catering.account_service.get_account_async",
        get_account_async,
    )

    with pytest.raises(HTTPException, match="item_price is required"):
        await import_account_catering_menu_items(
            "calibbq",
            _upload(b"item_name,item_price\nBrisket,\n"),
            _as_async_session(_Session()),
        )


@pytest.mark.asyncio
async def test_route_import_rejects_missing_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def get_account_async(
        _session: AsyncSession,
        _account_name: str,
    ) -> None:
        return None

    monkeypatch.setattr(
        "api.routes.admin._catering.account_service.get_account_async",
        get_account_async,
    )

    with pytest.raises(HTTPException, match="Account calibbq not found"):
        await import_account_catering_menu_items(
            "calibbq",
            _upload(b"item_name,item_price\nBrisket,23\n"),
            _as_async_session(_Session()),
        )


@pytest.mark.asyncio
async def test_route_import_rejects_accounts_without_projects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def get_account_async(
        _session: AsyncSession,
        _account_name: str,
    ) -> SimpleNamespace:
        return SimpleNamespace(id=uuid.uuid4())

    async def import_rows(
        _session: AsyncSession,
        _account_id: uuid.UUID,
        _rows: list[catering_service.CateringMenuImportItem],
    ) -> catering_service.CateringMenuImportStats:
        return catering_service.CateringMenuImportStats(
            inserted_items=0,
            projects_updated=0,
            rows_received=1,
            updated_items=0,
        )

    monkeypatch.setattr(
        "api.routes.admin._catering.account_service.get_account_async",
        get_account_async,
    )
    monkeypatch.setattr(
        "api.routes.admin._catering.catering_service.import_account_catering_menu_items",
        import_rows,
    )

    with pytest.raises(HTTPException, match="has no projects"):
        await import_account_catering_menu_items(
            "calibbq",
            _upload(b"item_name,item_price\nBrisket,23\n"),
            _as_async_session(_Session()),
        )


@pytest.mark.asyncio
async def test_route_import_rejects_non_csv_files() -> None:
    with pytest.raises(HTTPException, match="Upload a CSV file"):
        await import_account_catering_menu_items(
            "calibbq",
            _upload(b"item_name,item_price\nBrisket,23\n", filename="menu.txt"),
            _as_async_session(_Session()),
        )
