import pytest
from backend.services.up_recurring_service import normalise


# Real-shaped UP merchant strings (anonymised) and what they should
# normalise to so they group together.
@pytest.mark.parametrize("raw,expected", [
    # Plain merchant — no change
    ("Spotify", "spotify"),
    ("Netflix", "netflix"),
    # Trailing store/terminal numbers
    ("COLES 0382 BONDI", "coles bondi"),
    ("WOOLWORTHS 1234567", "woolworths"),
    ("ANYTIME FITNESS 567890", "anytime fitness"),
    # Card-network prefixes
    ("SQ *PINOS BARBER SHOP", "pinos barber shop"),
    ("PY *SUSHI HUB", "sushi hub"),
    ("PAYPAL *ADOBE INC", "adobe inc"),
    ("TPG *SPOTIFY", "spotify"),
    # Generic asterisk pattern
    ("ABC *COMPANY NAME", "company name"),
    # Whitespace + case
    ("  spotify  ", "spotify"),
    ("Spotify   AU", "spotify au"),
    # Edge: empty after strip
    ("", ""),
    # Edge: only digits
    ("12345678", ""),
    # Real Apple-shaped
    ("APPLE.COM/BILL ITUNES.COM", "apple.com/bill itunes.com"),
])
def test_normalise(raw: str, expected: str):
    assert normalise(raw) == expected
