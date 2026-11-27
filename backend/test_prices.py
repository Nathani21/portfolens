import io
import urllib.error
from datetime import date, datetime, timezone

import pytest

import prices
from portfolio import Quote
from prices import (
    FakePrices,
    FinnhubQuotes,
    InvalidTicker,
    MassiveHistory,
    PriceError,
    PriceService,
    TTLCache,
    UnknownTicker,
    clean_ticker,
    get_json,
    make_price_service,
    parse_finnhub_quote,
    parse_massive_bars,
    parse_tickers,
)

TODAY = date(2026, 11, 27)  # a Friday


def ms(year, month, day):
    """Massive-style timestamp: midnight US Eastern (05:00 UTC in winter)."""
    moment = datetime(year, month, day, 5, tzinfo=timezone.utc)
    return int(moment.timestamp() * 1000)


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class CountingSource:
    """Wraps FakePrices and counts calls, to prove the cache works."""

    def __init__(self):
        self.inner = FakePrices(today=lambda: TODAY)
        self.quote_calls = 0
        self.history_calls = 0

    def quote(self, ticker):
        self.quote_calls += 1
        return self.inner.quote(ticker)

    def history(self, ticker, days):
        self.history_calls += 1
        return self.inner.history(ticker, days)


# --- clean_ticker / parse_tickers ---

@pytest.mark.parametrize("raw, expected", [("aapl", "AAPL"), (" brk.b ", "BRK.B"), ("BF-B", "BF-B")])
def test_clean_ticker(raw, expected):
    assert clean_ticker(raw) == expected


@pytest.mark.parametrize("raw", ["", "  ", "1ABC", "AAPL/../X", "TOOLONGTICKER", "A B"])
def test_clean_ticker_rejects(raw):
    with pytest.raises(InvalidTicker):
        clean_ticker(raw)


def test_parse_tickers_cleans_and_dedupes():
    assert parse_tickers("aapl, MSFT,,aapl ") == ["AAPL", "MSFT"]


def test_parse_tickers_needs_one():
    with pytest.raises(InvalidTicker, match="at least one"):
        parse_tickers(" , ")


def test_parse_tickers_limit():
    many = ",".join(f"T{n}" for n in range(21))
    with pytest.raises(InvalidTicker, match="20 tickers or fewer"):
        parse_tickers(many)


# --- parse_finnhub_quote ---

def test_parse_finnhub_quote():
    data = {"c": 248.8, "d": -4.09, "dp": -1.6173, "pc": 252.89, "t": 1774641600}
    assert parse_finnhub_quote("AAPL", data) == Quote(price=248.8, prev_close=252.89)


@pytest.mark.parametrize(
    "data",
    [
        {"c": 0, "d": None, "dp": None, "pc": 0, "t": 0},  # Finnhub's unknown symbol
        {"c": "248.8", "pc": 252.89},
        {"c": True, "pc": 252.89},
        {},
    ],
)
def test_parse_finnhub_quote_unknown(data):
    with pytest.raises(UnknownTicker, match="No price found for XYZ"):
        parse_finnhub_quote("XYZ", data)


def test_parse_finnhub_quote_unexpected():
    with pytest.raises(PriceError, match="unexpected response"):
        parse_finnhub_quote("AAPL", ["not", "a", "dict"])


# --- parse_massive_bars ---

def test_parse_massive_bars_sorts_and_converts_dates():
    data = {
        "results": [
            {"t": ms(2026, 11, 25), "c": 231.0},
            {"t": ms(2026, 11, 24), "c": 229.5},
        ]
    }
    assert parse_massive_bars("AAPL", data) == [
        {"date": "2026-11-24", "close": 229.5},
        {"date": "2026-11-25", "close": 231.0},
    ]


def test_parse_massive_bars_skips_bad_bars():
    data = {"results": [{"t": ms(2026, 11, 24)}, "junk", {"t": ms(2026, 11, 25), "c": 231}]}
    assert parse_massive_bars("AAPL", data) == [{"date": "2026-11-25", "close": 231.0}]


@pytest.mark.parametrize("data", [{"results": []}, {"status": "OK"}, {"results": None}])
def test_parse_massive_bars_empty(data):
    with pytest.raises(UnknownTicker, match="No price history found for XYZ"):
        parse_massive_bars("XYZ", data)


# --- providers (fake fetch, no network) ---

def test_finnhub_sends_key_in_header_not_url():
    calls = []

    def fetch(url, headers):
        calls.append((url, headers))
        return {"c": 10, "pc": 9}

    quote = FinnhubQuotes("secret-key", fetch=fetch).quote("BRK.B")
    url, headers = calls[0]
    assert url == "https://finnhub.io/api/v1/quote?symbol=BRK.B"
    assert headers == {"X-Finnhub-Token": "secret-key"}
    assert "secret-key" not in url
    assert quote == Quote(price=10, prev_close=9)


def test_massive_builds_date_range_and_bearer_header():
    calls = []

    def fetch(url, headers):
        calls.append((url, headers))
        return {"results": [{"t": ms(2026, 11, 26), "c": 5}]}

    bars = MassiveHistory("secret-key", fetch=fetch, today=lambda: TODAY).history("AAPL", 30)
    url, headers = calls[0]
    assert url == (
        "https://api.massive.com/v2/aggs/ticker/AAPL/range/1/day/"
        "2026-10-28/2026-11-27?adjusted=true&sort=asc"
    )
    assert headers == {"Authorization": "Bearer secret-key"}
    assert bars == [{"date": "2026-11-26", "close": 5.0}]


# --- FakePrices ---

def test_fake_quote():
    assert FakePrices().quote("AAPL") == Quote(price=231.50, prev_close=228.90)


def test_fake_unknown_ticker_lists_demo_tickers():
    with pytest.raises(UnknownTicker, match="Try AAPL, MSFT"):
        FakePrices().quote("TSLA")


def test_fake_history_weekdays_only_and_ends_at_prev_close():
    bars = FakePrices(today=lambda: TODAY).history("AAPL", 14)
    days = [date.fromisoformat(b["date"]) for b in bars]
    assert all(d.weekday() < 5 for d in days)
    assert days == sorted(days)
    assert days[-1] == date(2026, 11, 26)  # yesterday; today isn't closed yet
    assert len(bars) == 10  # 14 calendar days before Friday = 10 weekdays
    assert bars[-1]["close"] == pytest.approx(228.90)


# --- TTLCache ---

def test_cache_hit_then_expiry():
    clock = FakeClock()
    cache = TTLCache(60, clock)
    cache.set("AAPL", 1)
    clock.now += 59
    assert cache.get("AAPL") == 1
    clock.now += 1
    assert cache.get("AAPL") is None


def test_cache_missing_key():
    assert TTLCache(60).get("nope") is None


# --- PriceService ---

def test_service_caches_quotes():
    clock = FakeClock()
    source = CountingSource()
    service = PriceService(source, source, quote_ttl=60, clock=clock)
    service.quotes(["AAPL", "MSFT"])
    service.quotes(["AAPL", "MSFT"])
    assert source.quote_calls == 2
    clock.now += 60
    service.quotes(["AAPL"])
    assert source.quote_calls == 3


def test_service_collects_errors_without_failing_others():
    source = CountingSource()
    found, errors = PriceService(source, source).quotes(["AAPL", "TSLA"])
    assert list(found) == ["AAPL"]
    assert "TSLA isn't in the demo data" in errors["TSLA"]


def test_service_does_not_cache_errors():
    source = CountingSource()
    service = PriceService(source, source)
    service.quotes(["TSLA"])
    service.quotes(["TSLA"])
    assert source.quote_calls == 2


def test_service_caches_history_per_ticker_and_days():
    source = CountingSource()
    service = PriceService(source, source)
    service.history("AAPL", 30)
    service.history("AAPL", 30)
    assert source.history_calls == 1
    service.history("AAPL", 60)
    assert source.history_calls == 2


def test_service_history_returns_a_copy():
    source = CountingSource()
    service = PriceService(source, source)
    service.history("AAPL", 30).clear()
    assert service.history("AAPL", 30) != []


# --- make_price_service ---

@pytest.mark.parametrize(
    "env, mode",
    [
        ({}, "demo"),
        ({"FINNHUB_API_KEY": "a"}, "demo"),
        ({"MASSIVE_API_KEY": "b"}, "demo"),
        ({"FINNHUB_API_KEY": " ", "MASSIVE_API_KEY": "b"}, "demo"),
        ({"FINNHUB_API_KEY": "a", "MASSIVE_API_KEY": "b"}, "live"),
    ],
)
def test_make_price_service_mode(env, mode):
    _, actual = make_price_service(env)
    assert actual == mode


# --- get_json error messages (urlopen replaced, no network) ---

def http_error(code):
    return urllib.error.HTTPError("https://example.com", code, "error", {}, io.BytesIO())


@pytest.mark.parametrize(
    "error, message",
    [
        (http_error(429), "busy"),
        (http_error(401), "rejected the API key"),
        (http_error(403), "rejected the API key"),
        (http_error(500), r"error \(500\)"),
        (urllib.error.URLError("no network"), "Could not reach"),
        (TimeoutError(), "Could not reach"),
    ],
)
def test_get_json_errors(monkeypatch, error, message):
    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(prices.urllib.request, "urlopen", fail)
    with pytest.raises(PriceError, match=message):
        get_json("https://example.com", {})


def test_get_json_parses(monkeypatch):
    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(
        prices.urllib.request, "urlopen", lambda *a, **k: Response(b'{"c": 1}')
    )
    assert get_json("https://example.com", {}) == {"c": 1}
