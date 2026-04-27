"""Sanity-check the centralised asset registry."""
from backend.config.assets import ASSET_MAP, BALANCE_KEY_TO_DISPLAY, LEDGER_ASSET_TO_DISPLAY


def test_asset_map_has_eth_sol_ada_link():
    assert set(ASSET_MAP.keys()) == {"ETH", "SOL", "ADA", "LINK"}


def test_every_asset_has_pair_and_keys():
    for asset, info in ASSET_MAP.items():
        assert "pair" in info, f"{asset} missing pair"
        assert "keys" in info, f"{asset} missing keys"
        assert info["keys"], f"{asset} has empty keys list"
        assert info["pair"].endswith("AUD"), f"{asset} pair must be AUD-quoted"


def test_balance_key_to_display_covers_all_asset_map_keys():
    for asset, info in ASSET_MAP.items():
        for key in info["keys"]:
            assert BALANCE_KEY_TO_DISPLAY[key] == asset


def test_balance_key_to_display_covers_ledger_codes():
    for ledger_code, display in LEDGER_ASSET_TO_DISPLAY.items():
        assert BALANCE_KEY_TO_DISPLAY[ledger_code] == display
