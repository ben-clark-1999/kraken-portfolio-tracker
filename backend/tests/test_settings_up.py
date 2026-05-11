from backend.config import settings


def test_up_pat_present_and_nonempty():
    assert hasattr(settings, "up_pat")
    assert isinstance(settings.up_pat, str)
    assert len(settings.up_pat) > 0
