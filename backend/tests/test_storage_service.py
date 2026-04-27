import io
from unittest.mock import MagicMock, patch

import pytest
from fastapi import UploadFile


@pytest.fixture
def mock_supabase():
    with patch("backend.services.storage_service.get_supabase") as m:
        client = MagicMock()
        m.return_value = client
        yield client


def _make_upload_file(filename: str, content_type: str, body: bytes) -> UploadFile:
    return UploadFile(filename=filename, file=io.BytesIO(body), headers={"content-type": content_type})


def test_upload_rejects_oversized_file(mock_supabase):
    from backend.services import storage_service
    from backend.services.storage_service import AttachmentValidationError

    huge_body = b"x" * (10 * 1024 * 1024 + 1)  # 10 MB + 1 byte
    file = _make_upload_file("big.pdf", "application/pdf", huge_body)

    with pytest.raises(AttachmentValidationError, match="size"):
        storage_service.upload_attachment("deductible", None, file)


def test_upload_rejects_disallowed_content_type(mock_supabase):
    from backend.services import storage_service
    from backend.services.storage_service import AttachmentValidationError

    file = _make_upload_file("evil.exe", "application/x-msdownload", b"MZ...")

    with pytest.raises(AttachmentValidationError, match="content-type"):
        storage_service.upload_attachment("deductible", None, file)


def test_upload_pending_inserts_with_null_parent_id(mock_supabase):
    from backend.services import storage_service

    file = _make_upload_file("receipt.pdf", "application/pdf", b"%PDF-1.4 ...")

    inserted = {
        "id": "att-1",
        "filename": "receipt.pdf",
        "content_type": "application/pdf",
        "size_bytes": 12,
        "uploaded_at": "2026-03-15T00:00:00+11:00",
    }
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [inserted]
    mock_supabase.storage.from_.return_value.upload.return_value = None

    result = storage_service.upload_attachment("deductible", None, file)

    assert result.id == "att-1"
    insert_call = mock_supabase.table.return_value.insert.call_args[0][0]
    assert insert_call["parent_id"] is None
    assert insert_call["storage_path"].startswith("PENDING/")
    assert insert_call["storage_path"].endswith(".pdf")


def test_create_signed_url_calls_storage_sdk(mock_supabase):
    from backend.services import storage_service

    fetch_chain = mock_supabase.table.return_value.select.return_value.eq.return_value
    fetch_chain.execute.return_value.data = [{
        "id": "att-1",
        "storage_path": "deductibles/2025-26/abc.pdf",
    }]
    mock_supabase.storage.from_.return_value.create_signed_url.return_value = {
        "signedURL": "https://signed.example/abc",
    }

    url, expires = storage_service.create_signed_url("att-1")

    assert url == "https://signed.example/abc"
    mock_supabase.storage.from_.return_value.create_signed_url.assert_called_once()


def test_delete_removes_storage_object_then_row(mock_supabase):
    from backend.services import storage_service

    fetch_chain = mock_supabase.table.return_value.select.return_value.eq.return_value
    fetch_chain.execute.return_value.data = [{
        "id": "att-1",
        "storage_path": "deductibles/2025-26/abc.pdf",
    }]
    delete_chain = mock_supabase.table.return_value.delete.return_value.eq.return_value
    delete_chain.execute.return_value.data = [{"id": "att-1"}]

    storage_service.delete_attachment("att-1")

    mock_supabase.storage.from_.return_value.remove.assert_called_once_with(["deductibles/2025-26/abc.pdf"])
    mock_supabase.table.return_value.delete.return_value.eq.assert_called_with("id", "att-1")


def test_upload_rejects_empty_file(mock_supabase):
    from backend.services import storage_service
    from backend.services.storage_service import AttachmentValidationError

    file = _make_upload_file("empty.pdf", "application/pdf", b"")

    with pytest.raises(AttachmentValidationError, match="empty"):
        storage_service.upload_attachment("deductible", None, file)


def test_upload_rolls_back_storage_object_when_db_insert_fails(mock_supabase):
    from backend.services import storage_service
    from backend.services.storage_service import StorageServiceError

    file = _make_upload_file("receipt.pdf", "application/pdf", b"%PDF-1.4 ...")

    # Storage upload succeeds
    mock_supabase.storage.from_.return_value.upload.return_value = None
    # But DB insert returns no data (simulates conflict / RLS rejection)
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = []
    mock_supabase.storage.from_.return_value.remove.return_value = None

    with pytest.raises(StorageServiceError):
        storage_service.upload_attachment("deductible", None, file)

    # Verify the storage object was rolled back
    mock_supabase.storage.from_.return_value.remove.assert_called_once()
    removed_paths = mock_supabase.storage.from_.return_value.remove.call_args[0][0]
    assert len(removed_paths) == 1
    assert removed_paths[0].startswith("PENDING/")


def test_sweep_pending_attachments_removes_orphans(mock_supabase):
    from backend.services import storage_service

    orphan_rows = [
        {"id": "att-1", "storage_path": "PENDING/old1.pdf"},
        {"id": "att-2", "storage_path": "PENDING/old2.pdf"},
    ]

    chain = (
        mock_supabase.table.return_value
        .select.return_value
        .is_.return_value
        .lt.return_value
    )
    chain.execute.return_value.data = orphan_rows

    mock_supabase.storage.from_.return_value.remove.return_value = None
    mock_supabase.table.return_value.delete.return_value.eq.return_value.execute.return_value.data = [{"id": "x"}]

    swept = storage_service.sweep_pending_attachments(older_than_hours=24)

    assert swept == 2
    # Storage SDK called once per orphan
    assert mock_supabase.storage.from_.return_value.remove.call_count == 2


def test_sweep_pending_attachments_returns_zero_when_no_orphans(mock_supabase):
    from backend.services import storage_service

    chain = (
        mock_supabase.table.return_value
        .select.return_value
        .is_.return_value
        .lt.return_value
    )
    chain.execute.return_value.data = []

    swept = storage_service.sweep_pending_attachments()

    assert swept == 0
    mock_supabase.storage.from_.return_value.remove.assert_not_called()
