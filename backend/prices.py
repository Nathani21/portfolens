"""Price providers and a small cache. All network calls to price APIs live here.

Live mode: Finnhub for current quotes, Massive for daily price history.
Demo mode: made-up prices from FakePrices, used when either API key is missing.
"""

import json
import math
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

from portfolio import Quote

MAX_TICKERS = 20
TICKER_PATTERN = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


class PriceError(Exception):
    """A price problem with a message that can be shown to the user."""


class InvalidTicker(PriceError):
    """The ticker text itself is not valid."""


class UnknownTicker(PriceError):
    """The ticker is valid, but the provider has no prices for it."""


# --- Input cleaning ---

def clean_ticker(raw):
    """Uppercase and check one ticker. Raises InvalidTicker."""
    ticker = str(raw).strip().upper()
    if not TICKER_PATTERN.match(ticker):
        raise InvalidTicker(f"'{str(raw).strip()}' isn't a valid ticker.")
    return ticker


def parse_tickers(text):
    """Turn "aapl, MSFT,aapl" into ["AAPL", "MSFT"]. Raises InvalidTicker."""
    tickers = []
    for part in str(text).split(","):
        if not part.strip():
            continue
        ticker = clean_ticker(part)
        if ticker not in tickers:
            tickers.append(ticker)
    if not tickers:
        raise InvalidTicker("Give at least one ticker.")
    if len(tickers) > MAX_TICKERS:
        raise InvalidTicker(f"Ask for {MAX_TICKERS} tickers or fewer.")
    return tickers


# --- Parsing provider responses ---

def _positive_number(value):
    """True for a finite number above zero (bools don't count)."""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value > 0
    )


def parse_finnhub_quote(ticker, data):
    """Turn a Finnhub /quote response into a Quote.

    Finnhub answers an unknown symbol with zeros instead of an error,
    so zero prices raise UnknownTicker.
    """
    if not isinstance(data, dict):
        raise PriceError("The price service sent an unexpected response.")
    price, prev_close = data.get("c"), data.get("pc")
    if not (_positive_number(price) and _positive_number(prev_close)):
        raise UnknownTicker(f"No price found for {ticker}.")
    return Quote(price=float(price), prev_close=float(prev_close))


def parse_massive_bars(ticker, data):
    """Turn a Massive daily aggregates response into [{"date", "close"}], oldest first.

    Massive's "t" is the bar's start in Unix milliseconds. Daily bars start at
    midnight US Eastern, which is the same calendar date in UTC.
    Malformed bars, including timestamps too large to be a date, are skipped.
    """
    if not isinstance(data, dict):
        raise PriceError("The price service sent an unexpected response.")
    results = data.get("results")
    if results is None:
        results = []
    if not isinstance(results, list):
        raise PriceError("The price service sent an unexpected response.")
    bars = []
    for bar in results:
        if not isinstance(bar, dict):
            continue
        timestamp, close = bar.get("t"), bar.get("c")
        if not (_positive_number(timestamp) and _positive_number(close)):
            continue
        try:
            day = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc).date()
        except (OverflowError, OSError, ValueError):
            continue
        bars.append({"date": day.isoformat(), "close": float(close)})
    if not bars:
        raise UnknownTicker(f"No price history found for {ticker}.")
    bars.sort(key=lambda b: b["date"])
    return bars


# --- HTTP ---

def get_json(url, headers):
    """GET a URL and return parsed JSON. Raises PriceError with a safe message.

    API keys travel in headers, never in the URL, so errors can't leak them.
    """
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 429:
            raise PriceError("The price service is busy. Try again in a minute.") from None
        if error.code in (401, 403):
            raise PriceError("The price service rejected the API key or plan.") from None
        raise PriceError(f"The price service returned an error ({error.code}).") from None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        raise PriceError("Could not reach the price service.") from None


# --- Providers ---

class FinnhubQuotes:
    """Current quotes from Finnhub (free tier: 60 calls/min, US only)."""

    URL = "https://finnhub.io/api/v1/quote"

    def __init__(self, api_key, fetch=get_json):
        """`fetch(url, headers)` returns parsed JSON; tests pass a fake one."""
        self._api_key = api_key
        self._fetch = fetch

    def quote(self, ticker):
        """Return the Quote for one ticker."""
        url = f"{self.URL}?{urllib.parse.urlencode({'symbol': ticker})}"
        data = self._fetch(url, {"X-Finnhub-Token": self._api_key})
        return parse_finnhub_quote(ticker, data)


class MassiveHistory:
    """Daily closing prices from Massive (free plan: end-of-day data, 5 calls/min)."""

    URL = "https://api.massive.com/v2/aggs/ticker/{ticker}/range/1/day/{start}/{end}"

    def __init__(self, api_key, fetch=get_json, today=date.today):
        """`fetch(url, headers)` returns parsed JSON; `today()` returns the end date."""
        self._api_key = api_key
        self._fetch = fetch
        self._today = today

    def history(self, ticker, days):
        """Return daily closes for the last `days` calendar days, oldest first."""
        end = self._today()
        start = end - timedelta(days=days)
        url = self.URL.format(
            ticker=urllib.parse.quote(ticker, safe=""),
            start=start.isoformat(),
            end=end.isoformat(),
        )
        data = self._fetch(
            url + "?adjusted=true&sort=asc",
            {"Authorization": f"Bearer {self._api_key}"},
        )
        return parse_massive_bars(ticker, data)


# Made-up demo prices: (price, previous close). Not real market data.
DEMO_QUOTES = {
    "AAPL": (231.50, 228.90),
    "MSFT": (428.10, 431.00),
    "NVDA": (142.30, 138.70),
    "GOOGL": (176.20, 175.00),
    "AMZN": (205.40, 207.90),
}


class FakePrices:
    """Deterministic made-up prices for demo mode and tests. No network."""

    def __init__(self, today=date.today):
        """`today()` returns the date history ends before; tests pass a fixed one."""
        self._today = today

    def _lookup(self, ticker):
        """Return (price, prev_close). Raises UnknownTicker for non-demo tickers."""
        if ticker not in DEMO_QUOTES:
            names = ", ".join(DEMO_QUOTES)
            raise UnknownTicker(f"{ticker} isn't in the demo data. Try {names}.")
        return DEMO_QUOTES[ticker]

    def quote(self, ticker):
        """Return the demo Quote for one ticker."""
        price, prev_close = self._lookup(ticker)
        return Quote(price=price, prev_close=prev_close)

    def history(self, ticker, days):
        """Weekday closes for the last `days` days, ending exactly at the previous close."""
        _, prev_close = self._lookup(ticker)
        end = self._today()
        dates = [end - timedelta(days=n) for n in range(days, 0, -1)]
        weekdays = [d for d in dates if d.weekday() < 5]
        bars = []
        for i, day in enumerate(weekdays, start=1):
            progress = i / len(weekdays)
            trend = 0.92 + 0.08 * progress
            wobble = 0.015 * math.sin(i * 1.3 + len(ticker)) * (1 - progress)
            close = round(prev_close * (trend + wobble), 2)
            bars.append({"date": day.isoformat(), "close": close})
        return bars


# --- Cache and service ---

class TTLCache:
    """A thread-safe dict whose entries expire after ttl_seconds.

    FastAPI runs `def` routes on a thread pool, so every read and write
    holds a lock. Expired entries are removed on every `set`, and when
    `max_entries` is reached the oldest entry is evicted.
    """

    def __init__(self, ttl_seconds, clock=time.monotonic, max_entries=1000):
        """`clock()` returns seconds; tests pass a fake clock they can move."""
        self._ttl = ttl_seconds
        self._clock = clock
        self._max_entries = max_entries
        self._items = {}
        self._lock = threading.Lock()

    def __len__(self):
        """Number of stored entries, expired ones included until the next `set`."""
        with self._lock:
            return len(self._items)

    def get(self, key):
        """Return the cached value, or None if missing or expired."""
        with self._lock:
            item = self._items.get(key)
            if item is None:
                return None
            value, expires_at = item
            if self._clock() >= expires_at:
                del self._items[key]
                return None
            return value

    def set(self, key, value):
        """Store a value until ttl_seconds from now."""
        with self._lock:
            now = self._clock()
            expired = [k for k, (_, expires_at) in self._items.items() if now >= expires_at]
            for k in expired:
                del self._items[k]
            # Re-insert at the end, so dict order is oldest first.
            self._items.pop(key, None)
            while len(self._items) >= self._max_entries:
                del self._items[next(iter(self._items))]
            self._items[key] = (value, now + self._ttl)


class PriceService:
    """Quotes and history from any providers, cached to respect free-tier limits."""

    def __init__(
        self,
        quote_source,
        history_source,
        quote_ttl=60,
        history_ttl=12 * 3600,
        clock=time.monotonic,
    ):
        """Sources need `quote(ticker)` and `history(ticker, days)`. TTLs are in seconds."""
        self._quote_source = quote_source
        self._history_source = history_source
        self._quotes = TTLCache(quote_ttl, clock)
        self._history = TTLCache(history_ttl, clock)

    def quotes(self, tickers):
        """Return (found, errors): ticker -> Quote, and ticker -> error message."""
        found, errors = {}, {}
        for ticker in tickers:
            quote = self._quotes.get(ticker)
            if quote is None:
                try:
                    quote = self._quote_source.quote(ticker)
                except PriceError as error:
                    errors[ticker] = str(error)
                    continue
                self._quotes.set(ticker, quote)
            found[ticker] = quote
        return found, errors

    def history(self, ticker, days=30):
        """Return daily closes for one ticker. Raises PriceError."""
        key = (ticker, days)
        bars = self._history.get(key)
        if bars is None:
            bars = self._history_source.history(ticker, days)
            self._history.set(key, bars)
        return list(bars)


def make_price_service(env=None):
    """Return (service, mode). Live only when both API keys are set, else demo."""
    env = os.environ if env is None else env
    finnhub_key = env.get("FINNHUB_API_KEY", "").strip()
    massive_key = env.get("MASSIVE_API_KEY", "").strip()
    if finnhub_key and massive_key:
        service = PriceService(FinnhubQuotes(finnhub_key), MassiveHistory(massive_key))
        return service, "live"
    demo = FakePrices()
    return PriceService(demo, demo), "demo"
