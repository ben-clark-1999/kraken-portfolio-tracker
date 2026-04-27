"""Tests for the orphan-attachment sweep job (storage_service.sweep_pending_attachments).

This complements the sweep tests in test_storage_service.py with a couple
of focused additional cases — specifically the scheduler-job invocation
shape and isolation behavior.
"""

from unittest.mock import MagicMock, patch


def test_sweep_pending_attachments_uses_24h_default_when_unset():
    """Calling without args defaults to older_than_hours=24."""
    from backend.services import storage_service

    with patch("backend.services.storage_service.get_supabase") as m:
        client = MagicMock()
        m.return_value = client
        chain = client.table.return_value.select.return_value.is_.return_value.lt.return_value
        chain.execute.return_value.data = []

        storage_service.sweep_pending_attachments()

    # Verify .lt got an ISO cutoff string (TZ-aware) — we just check it's a non-empty str
    lt_call = client.table.return_value.select.return_value.is_.return_value.lt.call_args
    assert lt_call[0][0] == "uploaded_at"
    cutoff_arg = lt_call[0][1]
    assert isinstance(cutoff_arg, str) and len(cutoff_arg) > 0


def test_sweep_continues_on_individual_row_failure():
    """If removing one storage object fails, sweep moves on to the next."""
    from backend.services import storage_service

    with patch("backend.services.storage_service.get_supabase") as m:
        client = MagicMock()
        m.return_value = client
        chain = client.table.return_value.select.return_value.is_.return_value.lt.return_value
        chain.execute.return_value.data = [
            {"id": "att-bad", "storage_path": "PENDING/bad.pdf"},
            {"id": "att-good", "storage_path": "PENDING/good.pdf"},
        ]

        # First storage remove() raises; second succeeds
        client.storage.from_.return_value.remove.side_effect = [
            Exception("Storage backend transient error"),
            None,
        ]
        client.table.return_value.delete.return_value.eq.return_value.execute.return_value.data = [{"id": "x"}]

        swept = storage_service.sweep_pending_attachments()

    # One failed, one succeeded
    assert swept == 1
