"""Single source of truth for tracked assets.

Adding a new tracked asset = add one entry to ASSET_MAP and (optionally)
LEDGER_ASSET_TO_DISPLAY. BALANCE_KEY_TO_DISPLAY auto-derives.
"""

# Display name → spot/staked/bonded balance keys + AUD trading pair
ASSET_MAP: dict[str, dict] = {
    "ETH": {
        "keys": ["XETH", "ETH", "ETH.B", "XETH.B", "ETH.S", "ETH2", "ETH2.S", "ETH.F"],
        "pair": "ETHAUD",
    },
    "SOL": {
        "keys": ["SOL", "SOL.S", "SOL.F", "SOL03.S"],
        "pair": "SOLAUD",
    },
    "ADA": {
        "keys": ["ADA", "ADA.S", "ADA.F"],
        "pair": "ADAAUD",
    },
    "LINK": {
        "keys": ["LINK", "LINK.S", "LINK.F"],
        "pair": "LINKAUD",
    },
}

# Ledger asset code → display name (used during trade reconstruction).
# The ledger uses native Kraken codes, e.g. XETH for ETH.
LEDGER_ASSET_TO_DISPLAY: dict[str, str] = {
    "XETH": "ETH",
    "SOL": "SOL",
    "ADA": "ADA",
    "LINK": "LINK",
}

# Auto-derived: every Kraken balance key → display name. Used for balance
# reconstruction across spot + staking variants.
BALANCE_KEY_TO_DISPLAY: dict[str, str] = {}
for _display_name, _info in ASSET_MAP.items():
    for _key in _info["keys"]:
        BALANCE_KEY_TO_DISPLAY[_key] = _display_name
for _key, _display_name in LEDGER_ASSET_TO_DISPLAY.items():
    BALANCE_KEY_TO_DISPLAY[_key] = _display_name
