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
from datetime import datetime
from decimal import Decimal

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
from backend.services import kraken_service, storage_service, sync_service
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


# ── Storage namespace mapping ────────────────────────────────────

_STORAGE_NAMESPACE = {
    TaxEntryKind.DEDUCTIBLE: "deductibles",
    TaxEntryKind.INCOME: "income",
    TaxEntryKind.TAX_PAID: "tax_paid",
}


def _rebind_pending_attachments(
    kind: TaxEntryKind,
    entry_id: str,
    fy: str,
    attachment_ids: list[str],
) -> list[TaxAttachment]:
    """Bind PENDING attachments to a newly-created entry and move objects
    from PENDING/{file} to {namespace}/{fy}/{file}.
    """
    if not attachment_ids:
        return []

    db = get_supabase()
    pending_rows = (
        db.table("tax_attachments")
        .select("*")
        .in_("id", attachment_ids)
        .execute()
        .data
        or []
    )
    if not pending_rows:
        return []

    namespace = _STORAGE_NAMESPACE[kind]

    moved_paths: list[tuple[str, str]] = []  # (att_id, new_path)
    for row in pending_rows:
        old_path = row["storage_path"]
        filename = old_path.split("/")[-1]
        new_path = f"{namespace}/{fy}/{filename}"
        try:
            db.storage.from_(storage_service.BUCKET).move(old_path, new_path)
        except Exception as e:
            raise storage_service.StorageBackendError(
                f"Failed to move {old_path} → {new_path}: {e}"
            ) from e
        moved_paths.append((row["id"], new_path))

    # Update DB rows: set parent_id and new storage_path
    for att_id, new_path in moved_paths:
        db.table("tax_attachments").update({
            "parent_id": entry_id,
            "storage_path": new_path,
            "parent_kind": kind.value,
        }).eq("id", att_id).execute()

    return [TaxAttachment(
        id=row["id"],
        filename=row["filename"],
        content_type=row["content_type"],
        size_bytes=row["size_bytes"],
        uploaded_at=row["uploaded_at"],
    ) for row in pending_rows]


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

    entry_row = result.data[0]
    attachments = _rebind_pending_attachments(kind, entry_row["id"], fy, payload.attachment_ids)
    return _row_to_entry(kind, entry_row, attachments)


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
    """Hard-delete an entry and cascade its attachments (DB + Storage)."""
    db = get_supabase()

    attachment_rows = (
        db.table("tax_attachments")
        .select("id, storage_path")
        .eq("parent_kind", kind.value)
        .eq("parent_id", id)
        .execute()
        .data
        or []
    )

    if attachment_rows:
        paths = [r["storage_path"] for r in attachment_rows]
        try:
            db.storage.from_(storage_service.BUCKET).remove(paths)
        except Exception as e:
            raise storage_service.StorageBackendError(
                f"Failed to delete storage objects for entry {id}: {e}"
            ) from e
        db.table("tax_attachments").delete().eq("parent_kind", kind.value).eq("parent_id", id).execute()

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
    """Group Kraken lots by financial year, summing AUD spent and buy counts.

    Reads existing lots from sync_service. Current value is computed using
    fresh ticker prices. Excludes nothing — every lot counts as a buy in
    the FY it was acquired.
    """
    lots = sync_service.get_all_lots()
    if not lots:
        return {}

    prices = kraken_service.get_ticker_prices(list({lot.asset for lot in lots}))

    by_fy: dict[str, dict] = {}
    for lot in lots:
        acquired_dt = datetime.fromisoformat(lot.acquired_at)
        fy = financial_year_from(acquired_dt.date())

        bucket = by_fy.setdefault(fy, {
            "total_aud_invested": 0.0,
            "total_buys": 0,
            "per_asset": {},
        })
        bucket["total_aud_invested"] += float(lot.cost_aud)
        bucket["total_buys"] += 1

        asset_bucket = bucket["per_asset"].setdefault(lot.asset, {
            "aud_spent": 0.0,
            "buy_count": 0,
            "current_value_aud": 0.0,
        })
        asset_bucket["aud_spent"] += float(lot.cost_aud)
        asset_bucket["buy_count"] += 1

    # Fill current_value_aud from remaining_quantity * current price
    for lot in lots:
        fy = financial_year_from(datetime.fromisoformat(lot.acquired_at).date())
        price = prices.get(lot.asset, Decimal("0"))
        contribution = float(Decimal(str(lot.remaining_quantity)) * price)
        by_fy[fy]["per_asset"][lot.asset]["current_value_aud"] += contribution

    return by_fy
