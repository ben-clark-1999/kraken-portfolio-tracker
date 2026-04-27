"""Service layer for tax attachment file storage on Supabase Storage.

All file operations go through this module — never the Supabase Storage
SDK directly from anywhere else. Frontend never receives storage paths
or URLs except through `create_signed_url`, which mints 5-minute signed
URLs that the browser uses to read the object directly from Storage.
"""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import UploadFile

from backend.db.supabase_client import get_supabase
from backend.models.tax import TaxAttachment


BUCKET = "tax-attachments"
ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/pdf",
}
MAX_FILE_BYTES = 10 * 1024 * 1024
SIGNED_URL_TTL_SECONDS = 300  # 5 minutes


class StorageServiceError(Exception):
    pass


class AttachmentValidationError(StorageServiceError):
    """413 / 415 — file too large or wrong content-type."""


class StorageBackendError(StorageServiceError):
    """502 — Supabase Storage rejected the request."""


def _ext_from_content_type(content_type: str) -> str:
    return {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "application/pdf": ".pdf",
    }[content_type]


def _read_into_memory(file: UploadFile) -> bytes:
    """Read the upload into memory. Tax-attachment uploads are <10 MB."""
    return file.file.read()


def upload_attachment(
    parent_kind: str,
    parent_id: str | None,
    file: UploadFile,
) -> TaxAttachment:
    """Validate, upload to Storage, and insert a tax_attachments row.

    parent_id=None means a pending upload (entry not yet created); the
    storage path lives under PENDING/ until the entry-create endpoint
    rebinds it.
    """
    content_type = file.content_type or ""
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise AttachmentValidationError(
            f"content-type '{content_type}' not allowed. "
            f"Permitted: {sorted(ALLOWED_CONTENT_TYPES)}"
        )

    body = _read_into_memory(file)
    if len(body) > MAX_FILE_BYTES:
        raise AttachmentValidationError(
            f"file size {len(body)} bytes exceeds {MAX_FILE_BYTES}"
        )
    if len(body) == 0:
        raise AttachmentValidationError("file is empty")

    ext = _ext_from_content_type(content_type)
    storage_filename = f"{uuid.uuid4()}{ext}"
    # All uploads land under PENDING/. tax_service.create_entry rebinds them
    # to the kind/{fy}/ namespace once the entry exists. Direct upload to a
    # known parent is not used in Spec 1.
    storage_path = f"PENDING/{storage_filename}"

    db = get_supabase()
    try:
        db.storage.from_(BUCKET).upload(
            storage_path,
            body,
            {"content-type": content_type},
        )
    except Exception as e:
        raise StorageBackendError(f"Supabase Storage upload failed: {e}") from e

    insert_row = {
        "parent_kind": parent_kind,
        "parent_id": parent_id,
        "storage_path": storage_path,
        "filename": file.filename or "untitled",
        "content_type": content_type,
        "size_bytes": len(body),
    }
    result = db.table("tax_attachments").insert(insert_row).execute()
    if not result.data:
        # Roll back the upload
        try:
            db.storage.from_(BUCKET).remove([storage_path])
        except Exception:
            pass
        raise StorageServiceError("Insert into tax_attachments returned no data")

    row = result.data[0]
    return TaxAttachment(
        id=row["id"],
        filename=row["filename"],
        content_type=row["content_type"],
        size_bytes=row["size_bytes"],
        uploaded_at=row["uploaded_at"],
    )


def create_signed_url(attachment_id: str) -> tuple[str, datetime]:
    db = get_supabase()
    rows = db.table("tax_attachments").select("storage_path").eq("id", attachment_id).execute().data or []
    if not rows:
        raise StorageServiceError(f"Attachment not found: {attachment_id}")

    storage_path = rows[0]["storage_path"]
    try:
        signed = db.storage.from_(BUCKET).create_signed_url(storage_path, SIGNED_URL_TTL_SECONDS)
    except Exception as e:
        raise StorageBackendError(f"Failed to mint signed URL: {e}") from e

    url = signed.get("signedURL") or signed.get("signed_url")
    if not url:
        raise StorageBackendError(f"Storage SDK returned no URL: {signed!r}")

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=SIGNED_URL_TTL_SECONDS)
    return url, expires_at


def delete_attachment(attachment_id: str) -> None:
    """Delete the storage object first, then the DB row.

    If the storage delete fails, do NOT delete the DB row — the orphaned
    object is recoverable; an orphaned row pointing nowhere is not.
    """
    db = get_supabase()
    rows = db.table("tax_attachments").select("storage_path").eq("id", attachment_id).execute().data or []
    if not rows:
        return  # idempotent

    storage_path = rows[0]["storage_path"]
    try:
        db.storage.from_(BUCKET).remove([storage_path])
    except Exception as e:
        raise StorageBackendError(f"Failed to delete storage object {storage_path}: {e}") from e

    db.table("tax_attachments").delete().eq("id", attachment_id).execute()


def sweep_pending_attachments(older_than_hours: int = 24) -> int:
    """Delete attachments with parent_id IS NULL older than `older_than_hours`.

    Returns the count of swept items. Called from the APScheduler job.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=older_than_hours)

    db = get_supabase()
    rows = (
        db.table("tax_attachments")
        .select("id, storage_path")
        .is_("parent_id", "null")
        .lt("uploaded_at", cutoff.isoformat())
        .execute()
        .data
        or []
    )

    swept = 0
    for row in rows:
        try:
            db.storage.from_(BUCKET).remove([row["storage_path"]])
            db.table("tax_attachments").delete().eq("id", row["id"]).execute()
            swept += 1
        except Exception:
            # Log-and-continue; sweep will retry next run
            continue

    return swept
