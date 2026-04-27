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

from collections import defaultdict
from datetime import date as date_t

from backend.db.supabase_client import get_supabase
from backend.models.tax import (
    DeductibleType,
    FYOverview,
    IncomeType,
    KrakenAssetActivity,
    KrakenFYActivity,
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
        "description": payload.description,
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
        .eq("parent_kind", parent_kind.value)
        .in_("parent_id", ids)
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

    # Fetch existing row so we can short-circuit on a no-op patch and
    # raise EntryNotFoundError if the row doesn't exist.
    existing = get_entry(kind, id)

    update_row: dict = {}
    if patch.description is not None:
        update_row["description"] = patch.description
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


# ── Overview / aggregation ───────────────────────────────────────

def get_overview() -> list[FYOverview]:
    """Aggregate totals per FY across all three entry tables, plus Kraken activity.

    Returns one FYOverview per FY that has *any* data (entry rows in any table
    OR Kraken activity for that FY). Sorted by FY descending (newest first).
    """
    db = get_supabase()

    deductibles_by_fy: dict[str, float] = defaultdict(float)
    income_by_fy: dict[str, float] = defaultdict(float)
    tax_paid_by_fy: dict[str, float] = defaultdict(float)

    for row in db.table("tax_deductibles").select("financial_year, amount_aud").execute().data or []:
        deductibles_by_fy[row["financial_year"]] += float(row["amount_aud"])
    for row in db.table("tax_income").select("financial_year, amount_aud").execute().data or []:
        income_by_fy[row["financial_year"]] += float(row["amount_aud"])
    for row in db.table("tax_paid").select("financial_year, amount_aud").execute().data or []:
        tax_paid_by_fy[row["financial_year"]] += float(row["amount_aud"])

    kraken_by_fy = get_kraken_activity_by_fy()

    all_fys = (
        set(deductibles_by_fy)
        | set(income_by_fy)
        | set(tax_paid_by_fy)
        | set(kraken_by_fy)
    )

    overviews: list[FYOverview] = []
    for fy in sorted(all_fys, reverse=True):
        kraken = kraken_by_fy.get(fy, {"total_aud_invested": 0.0, "total_buys": 0, "per_asset": {}})
        overviews.append(FYOverview(
            financial_year=fy,
            income_total_aud=round(income_by_fy[fy], 2),
            tax_paid_total_aud=round(tax_paid_by_fy[fy], 2),
            deductibles_total_aud=round(deductibles_by_fy[fy], 2),
            kraken_activity=KrakenFYActivity(
                total_aud_invested=kraken["total_aud_invested"],
                total_buys=kraken["total_buys"],
                per_asset={
                    asset: KrakenAssetActivity(**vals) for asset, vals in kraken["per_asset"].items()
                },
            ),
        ))
    return overviews


def get_kraken_activity_by_fy() -> dict[str, dict]:
    """Stub — implementation lands in Task 6."""
    return {}
