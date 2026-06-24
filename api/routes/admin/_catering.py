import csv
import io
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.admin.catering import CateringMenuImportResponse
from services import account_service, catering_service


def _normalize_price(value: str) -> Decimal:
    """Normalize a CSV price string into a two-decimal Decimal."""
    normalized = value.strip().replace("$", "").replace(",", "")
    if not normalized:
        raise ValueError("item_price is required")

    try:
        price = Decimal(normalized)
    except InvalidOperation as exc:
        raise ValueError("item_price must be a valid number") from exc

    if not price.is_finite():
        raise ValueError("item_price must be a valid number")

    if price < 0:
        raise ValueError("item_price must be greater than or equal to 0")

    try:
        return price.quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise ValueError("item_price must be a valid number") from exc


def _get_value(row: dict[str, str], *keys: str) -> str:
    """Return the first present CSV value for any accepted column key."""
    for key in keys:
        value = row.get(key)
        if value is not None:
            return value.strip()
    return ""


def parse_catering_menu_csv(
    content: bytes,
) -> list[catering_service.CateringMenuImportItem]:
    """Parse and validate account catering menu CSV bytes."""
    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("CSV must be UTF-8 encoded") from exc

    reader = csv.DictReader(io.StringIO(decoded))
    if not reader.fieldnames:
        raise ValueError("CSV must include item_name and item_price columns")

    rows: list[catering_service.CateringMenuImportItem] = []
    errors: list[str] = []
    seen_names: set[str] = set()

    for index, raw_row in enumerate(reader, start=2):
        normalized_row = {
            key.strip().lower(): value.strip()
            for key, value in raw_row.items()
            if key is not None and isinstance(value, str)
        }
        if not any(value.strip() for value in normalized_row.values()):
            continue

        item_name = _get_value(normalized_row, "item_name", "name")
        if not item_name:
            errors.append(f"Row {index}: item_name is required")
            continue

        seen_name = item_name.casefold()
        if seen_name in seen_names:
            errors.append(f"Row {index}: duplicate item_name '{item_name}'")
            continue
        seen_names.add(seen_name)

        price_value = _get_value(normalized_row, "item_price", "price")
        try:
            item_price = _normalize_price(price_value)
        except ValueError as exc:
            errors.append(f"Row {index}: {exc}")
            continue

        rows.append(
            catering_service.CateringMenuImportItem(
                item_name=item_name,
                item_price=item_price,
            )
        )

    if errors:
        raise ValueError("; ".join(errors))

    if not rows:
        raise ValueError("CSV must contain at least one catering menu item")

    return rows


async def import_account_catering_menu_items(
    account_name: str,
    file: UploadFile,
    session: AsyncSession,
) -> CateringMenuImportResponse:
    """Import flat catering menu CSV rows for every project in an account."""
    filename = file.filename or ""
    if filename and not filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Upload a CSV file.",
            headers={"Content-Type": "application/json"},
        )

    content = await file.read()
    try:
        rows = parse_catering_menu_csv(content)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
            headers={"Content-Type": "application/json"},
        ) from exc

    account = await account_service.get_account_async(session, account_name)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {account_name} not found",
            headers={"Content-Type": "application/json"},
        )

    stats = await catering_service.import_account_catering_menu_items(
        session,
        account.id,
        rows,
    )
    if stats.projects_updated == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Account {account_name} has no projects to update",
            headers={"Content-Type": "application/json"},
        )

    return CateringMenuImportResponse(
        account_name=account_name,
        inserted_items=stats.inserted_items,
        projects_updated=stats.projects_updated,
        rows_received=stats.rows_received,
        updated_items=stats.updated_items,
    )
