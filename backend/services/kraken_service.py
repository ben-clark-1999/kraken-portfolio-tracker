from decimal import Decimal
from kraken.spot import User, Market
from backend.config import settings


class KrakenServiceError(Exception):
    """Raised when a Kraken API call fails."""


# Mapping from display asset name → list of Kraken balance keys (spot + staked/bonded variants) + AUD pair
ASSET_MAP: dict[str, dict] = {
    "ETH": {
        "keys": ["XETH", "ETH", "ETH.B", "ETH.S", "ETH2", "ETH2.S", "ETH.F"],
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
}

# Mapping from Kraken pair name → display asset name (for trade history)
# Includes both current and legacy pair names — Kraken renamed XETHZAUD → ETHAUD,
# but historical trades may still appear under the old name.
PAIR_TO_ASSET: dict[str, str] = {
    "ETHAUD":   "ETH",
    "XETHZAUD": "ETH",
    "SOLAUD":   "SOL",
    "ADAAUD":   "ADA",
}

_user: User | None = None
_market: Market | None = None


def _get_user() -> User:
    global _user
    if _user is None:
        _user = User(key=settings.kraken_api_key, secret=settings.kraken_api_secret)
    return _user


def _get_market() -> Market:
    global _market
    if _market is None:
        _market = Market()
    return _market


def get_balances() -> dict[str, Decimal]:
    """
    Returns current balances for tracked assets, summing across spot + staked/bonded variants.
    Result: {"ETH": Decimal("0.9445"), "SOL": Decimal("9.03"), "ADA": Decimal("692.77")}
    """
    try:
        raw = _get_user().get_account_balance()
    except Exception as e:
        raise KrakenServiceError(f"get_balances failed: {e}") from e

    result: dict[str, Decimal] = {}
    for asset_name, info in ASSET_MAP.items():
        total = Decimal("0")
        for kraken_key in info["keys"]:
            raw_balance = raw.get(kraken_key, "0")
            total += Decimal(str(raw_balance))
        if total > 0:
            result[asset_name] = total
    return result


def get_ticker_prices(assets: list[str]) -> dict[str, Decimal]:
    """
    Returns live AUD prices for given asset names (e.g. ["ETH", "SOL", "ADA"]).
    Result: {"ETH": Decimal("3000.00"), "SOL": Decimal("220.50"), ...}
    """
    name_to_pair = {name: info["pair"] for name, info in ASSET_MAP.items()}
    pairs = [name_to_pair[a] for a in assets if a in name_to_pair]
    if not pairs:
        return {}

    pair_str = ",".join(pairs)
    try:
        raw = _get_market().get_ticker(pair=pair_str)
    except Exception as e:
        raise KrakenServiceError(f"get_ticker_prices failed: {e}") from e

    result: dict[str, Decimal] = {}
    pair_to_name = {info["pair"]: name for name, info in ASSET_MAP.items()}
    for pair, data in raw.items():
        asset_name = pair_to_name.get(pair)
        if asset_name:
            # 'c' is last trade price: [price, lot_volume]
            result[asset_name] = Decimal(str(data["c"][0]))
    return result


def get_trade_history(since_trade_id: str | None = None) -> list[dict]:
    """
    Returns all buy trades for tracked asset pairs.
    Paginates through all pages on first run (since_trade_id=None).
    On subsequent runs, pass the last known trade_id to fetch only new trades.

    Each returned dict contains:
      trade_id, asset, time (float unix), price (str), vol (str), cost (str)
    """
    user = _get_user()
    trades: list[dict] = []
    offset = 0

    while True:
        try:
            result = user.get_trades_history(ofs=offset)
        except Exception as e:
            raise KrakenServiceError(f"get_trade_history failed: {e}") from e
        raw_trades: dict = result.get("trades", {})
        count: int = result.get("count", 0)

        for trade_id, trade in raw_trades.items():
            # Stop if we've reached a trade we already processed
            if since_trade_id and trade_id == since_trade_id:
                return trades

            pair = trade.get("pair", "")
            asset = PAIR_TO_ASSET.get(pair)
            if not asset:
                continue  # skip non-tracked pairs
            if trade.get("type") != "buy":
                continue  # skip sells for Phase 1

            trades.append({
                "trade_id": trade_id,
                "asset": asset,
                "time": float(trade["time"]),
                "price": str(trade["price"]),
                "vol": str(trade["vol"]),
                "cost": str(trade["cost"]),
            })

        page_len = len(raw_trades)
        if page_len == 0:
            break
        offset += page_len
        if offset >= count:
            break

    return trades
