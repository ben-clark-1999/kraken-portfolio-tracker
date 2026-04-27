"""Service layer for the Tax Hub feature.

Encapsulates DB operations for tax_deductibles, tax_income, tax_paid and
their attachments. Routers are thin wrappers over this module.

Date column naming differs by table:
  - tax_deductibles → date_paid
  - tax_income      → date_received
  - tax_paid        → date_paid

The service normalizes to a single `date` field in the API response
(TaxEntry).
"""

from datetime import date as date_t, datetime

from backend.db.supabase_client import get_supabase
from backend.models.tax import (
    DeductibleType,
    IncomeType,
    TaxAttachment,
    TaxEntry,
    TaxEntryCreate,
    TaxEntryKind,
    TaxEntryUpdate,
    TaxPaidType,
)
from backend.utils.financial_year import financial_year_from


class TaxServiceError(Exception):
    pass


class EntryNotFoundError(TaxServiceError):
    pass


# ── Kind metadata ────────────────────────────────────────────────

_KIND_TABLE = {
    TaxEntryKind.DEDUCTIBLE: "tax_deductibles",
    TaxEntryKind.INCOME: "tax_income",
    TaxEntryKind.TAX_PAID: "tax_paid",
}

_KIND_DATE_COLUMN = {
    TaxEntryKind.DEDUCTIBLE: "date_paid",
    TaxEntryKind.INCOME: "date_received",
    TaxEntryKind.TAX_PAID: "date_paid",
}

_KIND_TYPE_ENUM = {
    TaxEntryKind.DEDUCTIBLE: DeductibleType,
    TaxEntryKind.INCOME: IncomeType,
    TaxEntryKind.TAX_PAID: TaxPaidType,
}


def _validate_type(kind: TaxEntryKind, type_value: str) -> None:
    enum_class = _KIND_TYPE_ENUM[kind]
    valid = {e.value for e in enum_class}
    if type_value not in valid:
        raise ValueError(
            f"Invalid type '{type_value}' for kind '{kind.value}'. "
            f"Valid: {sorted(valid)}"
        )


def _row_to_entry(kind: TaxEntryKind, row: dict, attachments: list[TaxAttachment] | None = None) -> TaxEntry:
    date_col = _KIND_DATE_COLUMN[kind]
    return TaxEntry(
        id=row["id"],
        description=row["description"],
        amount_aud=float(row["amount_aud"]),
        date=row[date_col],
        type=row["type"],
        notes=row.get("notes"),
        financial_year=row["financial_year"],
        attachments=attachments or [],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


# ── CRUD ─────────────────────────────────────────────────────────

def create_entry(kind: TaxEntryKind, payload: TaxEntryCreate) -> TaxEntry:
    _validate_type(kind, payload.type)

    parsed_date = date_t.fromisoformat(payload.date)
    fy = financial_year_from(parsed_date)
    date_col = _KIND_DATE_COLUMN[kind]
    table = _KIND_TABLE[kind]

    insert_row = {
        "description": payload.description.strip(),
        "amount_aud": payload.amount_aud,
        date_col: payload.date,
        "type": payload.type,
        "notes": payload.notes,
        "financial_year": fy,
    }

    db = get_supabase()
    result = db.table(table).insert(insert_row).execute()
    if not result.data:
        raise TaxServiceError(f"Insert returned no data for kind={kind.value}")

    return _row_to_entry(kind, result.data[0])


def _get_attachments_for(parent_kind: TaxEntryKind, ids: list[str]) -> dict[str, list[TaxAttachment]]:
    """Fetch attachments grouped by parent_id. Empty dict if no ids."""
    if not ids:
        return {}
    db = get_supabase()
    result = (
        db.table("tax_attachments")
        .select("*")
        .in_("parent_id", ids)
        .eq("parent_kind", parent_kind.value)
        .execute()
    )
    grouped: dict[str, list[TaxAttachment]] = {}
    for row in result.data or []:
        att = TaxAttachment(
            id=row["id"],
            filename=row["filename"],
            content_type=row["content_type"],
            size_bytes=row["size_bytes"],
            uploaded_at=row["uploaded_at"],
        )
        grouped.setdefault(row["parent_id"], []).append(att)
    return grouped


def get_entries(kind: TaxEntryKind, fy: str) -> list[TaxEntry]:
    table = _KIND_TABLE[kind]
    date_col = _KIND_DATE_COLUMN[kind]

    db = get_supabase()
    result = (
        db.table(table)
        .select("*")
        .eq("financial_year", fy)
        .order(date_col, desc=True)
        .execute()
    )
    rows = result.data or []
    if not rows:
        return []

    attachments_by_parent = _get_attachments_for(kind, [r["id"] for r in rows])
    return [_row_to_entry(kind, r, attachments_by_parent.get(r["id"], [])) for r in rows]


def get_entry(kind: TaxEntryKind, id: str) -> TaxEntry:
    table = _KIND_TABLE[kind]
    db = get_supabase()
    result = db.table(table).select("*").eq("id", id).execute()
    rows = result.data or []
    if not rows:
        raise EntryNotFoundError(f"{kind.value} entry not found: {id}")

    attachments_by_parent = _get_attachments_for(kind, [id])
    return _row_to_entry(kind, rows[0], attachments_by_parent.get(id, []))


def update_entry(kind: TaxEntryKind, id: str, patch: TaxEntryUpdate) -> TaxEntry:
    if patch.type is not None:
        _validate_type(kind, patch.type)

    # Need existing row to know whether date changed (for FY recompute)
    existing = get_entry(kind, id)

    update_row: dict = {}
    if patch.description is not None:
        update_row["description"] = patch.description.strip()
    if patch.amount_aud is not None:
        update_row["amount_aud"] = patch.amount_aud
    if patch.type is not None:
        update_row["type"] = patch.type
    if patch.notes is not None:
        update_row["notes"] = patch.notes
    if patch.date is not None:
        date_col = _KIND_DATE_COLUMN[kind]
        update_row[date_col] = patch.date
        update_row["financial_year"] = financial_year_from(date_t.fromisoformat(patch.date))

    if not update_row:
        return existing  # no-op patch

    update_row["updated_at"] = datetime.now().isoformat()

    table = _KIND_TABLE[kind]
    db = get_supabase()
    result = db.table(table).update(update_row).eq("id", id).execute()
    rows = result.data or []
    if not rows:
        raise EntryNotFoundError(f"{kind.value} entry not found: {id}")

    attachments_by_parent = _get_attachments_for(kind, [id])
    return _row_to_entry(kind, rows[0], attachments_by_parent.get(id, []))


def delete_entry(kind: TaxEntryKind, id: str) -> None:
    """Hard-delete an entry. Attachment cascade is added in Task 8."""
    db = get_supabase()
    table = _KIND_TABLE[kind]
    result = db.table(table).delete().eq("id", id).execute()
    if not result.data:
        raise EntryNotFoundError(f"{kind.value} entry not found: {id}")
