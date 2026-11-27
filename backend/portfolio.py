"""Portfolio maths as pure functions. No FastAPI or other web imports."""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Holding:
    """One position: how many shares, bought at what average price per share."""

    ticker: str
    shares: float
    avg_cost: float


@dataclass(frozen=True)
class Quote:
    """The latest price and the previous day's close for one ticker."""

    price: float
    prev_close: float


# A made-up demo portfolio, shown until users can bring their own holdings.
# The tickers match the demo prices in prices.DEMO_QUOTES.
DEMO_HOLDINGS = (
    Holding("AAPL", 10, 150),
    Holding("MSFT", 6, 250),
    Holding("NVDA", 25, 90),
    Holding("GOOGL", 12, 140),
    Holding("AMZN", 8, 180),
)


def percent(part, whole):
    """Return part as a percentage of whole, or None when whole is zero."""
    if whole == 0:
        return None
    return part / whole * 100


def parse_holdings(data):
    """Turn a list of dicts into Holdings.

    Raises ValueError with a message that can be shown to the user.
    """
    if not isinstance(data, list) or not data:
        raise ValueError("Holdings must be a non-empty list.")

    holdings = []
    seen = set()
    for number, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            raise ValueError(
                f"Holding {number} must have a ticker, shares and avg_cost."
            )

        ticker = str(item.get("ticker") or "").strip().upper()
        if not ticker:
            raise ValueError(f"Holding {number} is missing a ticker.")
        if ticker in seen:
            raise ValueError(f"{ticker} appears more than once.")

        try:
            shares = float(item.get("shares"))
            avg_cost = float(item.get("avg_cost"))
        except (TypeError, ValueError):
            raise ValueError(f"{ticker}: shares and avg_cost must be numbers.") from None
        if not (math.isfinite(shares) and math.isfinite(avg_cost)):
            raise ValueError(f"{ticker}: shares and avg_cost must be numbers.")
        if shares <= 0:
            raise ValueError(f"{ticker}: shares must be more than 0.")
        if avg_cost < 0:
            raise ValueError(f"{ticker}: avg_cost cannot be negative.")

        seen.add(ticker)
        holdings.append(Holding(ticker, shares, avg_cost))
    return holdings


def position_summary(holding, quote):
    """Value, cost, profit/loss and today's change for one holding."""
    value = holding.shares * quote.price
    cost = holding.shares * holding.avg_cost
    pnl = value - cost
    return {
        "ticker": holding.ticker,
        "shares": holding.shares,
        "price": quote.price,
        "value": value,
        "cost": cost,
        "pnl": pnl,
        "pnl_pct": percent(pnl, cost),
        "day_change": holding.shares * (quote.price - quote.prev_close),
        "day_change_pct": percent(quote.price - quote.prev_close, quote.prev_close),
    }


def portfolio_summary(holdings, quotes):
    """Totals, per-position figures and allocation for the whole portfolio.

    `quotes` maps ticker to Quote. Holdings without a quote are listed in
    `missing` and left out of every total. Positions are sorted by value,
    largest first, and each gets a `weight_pct` share of the total value.
    """
    positions = []
    missing = []
    for holding in holdings:
        quote = quotes.get(holding.ticker)
        if quote is None:
            missing.append(holding.ticker)
            continue
        positions.append(position_summary(holding, quote))

    total_value = sum(p["value"] for p in positions)
    total_cost = sum(p["cost"] for p in positions)
    day_change = sum(p["day_change"] for p in positions)
    pnl = total_value - total_cost

    for position in positions:
        position["weight_pct"] = percent(position["value"], total_value)
    positions.sort(key=lambda p: p["value"], reverse=True)

    return {
        "positions": positions,
        "missing": missing,
        "total_value": total_value,
        "total_cost": total_cost,
        "pnl": pnl,
        "pnl_pct": percent(pnl, total_cost),
        "day_change": day_change,
        "day_change_pct": percent(day_change, total_value - day_change),
    }
