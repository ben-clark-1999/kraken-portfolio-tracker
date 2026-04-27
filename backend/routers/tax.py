"""HTTP layer for /api/tax/*. All logic lives in tax_service / storage_service."""

from typing import Optional

from fastapi import APIRouter, Form, HTTPException, UploadFile, File

from backend.models.tax import (
    FYOverview,
    TaxAttachment,
    TaxEntry,
    TaxEntryCreate,
    TaxEntryKind,
    TaxEntryUpdate,
)
from backend.services import storage_service, tax_service
from backend.services.tax_service import EntryNotFoundError
from backend.services.storage_service import (
    AttachmentValidationError,
    StorageBackendError,
)

router = APIRouter(prefix="/api/tax", tags=["tax"])


_KIND_PATH = {
    "deductibles": TaxEntryKind.DEDUCTIBLE,
    "income": TaxEntryKind.INCOME,
    "paid": TaxEntryKind.TAX_PAID,
}


def _kind_or_404(path_kind: str) -> TaxEntryKind:
    if path_kind not in _KIND_PATH:
        raise HTTPException(404, f"Unknown kind path: {path_kind}")
    return _KIND_PATH[path_kind]


# ── Overview ───────────────────────────────────────────────────

@router.get("/overview", response_model=list[FYOverview])
async def get_overview() -> list[FYOverview]:
    return tax_service.get_overview()


# ── Attachments (declared BEFORE per-kind catch-all routes) ─────
# The /{path_kind}/... routes below would otherwise shadow these,
# since FastAPI dispatches in declaration order.

@router.post("/attachments", response_model=TaxAttachment)
async def upload_attachment(
    parent_kind: str = Form(...),
    parent_id: Optional[str] = Form(None),
    file: UploadFile = File(...),
) -> TaxAttachment:
    if parent_kind not in {"deductible", "income", "tax_paid"}:
        raise HTTPException(400, f"Invalid parent_kind: {parent_kind}")
    try:
        return storage_service.upload_attachment(parent_kind, parent_id, file)
    except AttachmentValidationError as e:
        message = str(e)
        if "size" in message:
            raise HTTPException(413, message)
        raise HTTPException(415, message)
    except StorageBackendError as e:
        raise HTTPException(502, str(e))


@router.get("/attachments/{id}/url")
async def get_attachment_url(id: str) -> dict:
    try:
        url, expires = storage_service.create_signed_url(id)
    except StorageBackendError as e:
        raise HTTPException(502, str(e))
    return {"url": url, "expires_at": expires.isoformat()}


@router.delete("/attachments/{id}", status_code=204)
async def delete_attachment(id: str) -> None:
    try:
        storage_service.delete_attachment(id)
    except StorageBackendError as e:
        raise HTTPException(502, str(e))


# ── Per-kind list / CRUD ───────────────────────────────────────

@router.get("/{path_kind}", response_model=list[TaxEntry])
async def list_entries(path_kind: str, fy: str) -> list[TaxEntry]:
    kind = _kind_or_404(path_kind)
    return tax_service.get_entries(kind, fy)


@router.post("/{path_kind}", response_model=TaxEntry)
async def create_entry(path_kind: str, payload: TaxEntryCreate) -> TaxEntry:
    kind = _kind_or_404(path_kind)
    try:
        return tax_service.create_entry(kind, payload)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.patch("/{path_kind}/{id}", response_model=TaxEntry)
async def update_entry(path_kind: str, id: str, patch: TaxEntryUpdate) -> TaxEntry:
    kind = _kind_or_404(path_kind)
    try:
        return tax_service.update_entry(kind, id, patch)
    except EntryNotFoundError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/{path_kind}/{id}", status_code=204)
async def delete_entry(path_kind: str, id: str) -> None:
    kind = _kind_or_404(path_kind)
    try:
        tax_service.delete_entry(kind, id)
    except EntryNotFoundError as e:
        raise HTTPException(404, str(e))
    except StorageBackendError as e:
        raise HTTPException(502, str(e))
