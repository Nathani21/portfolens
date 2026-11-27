import pytest

from portfolio import (
    Holding,
    Quote,
    parse_holdings,
    percent,
    portfolio_summary,
    position_summary,
)

# Fixed sample data, so tests never touch a price API.
HOLDINGS = [Holding("AAPL", 10, 150), Holding("MSFT", 6, 250)]
QUOTES = {
    "AAPL": Quote(price=200, prev_close=190),
    "MSFT": Quote(price=400, prev_close=410),
}


# --- percent ---

def test_percent():
    assert percent(1, 4) == pytest.approx(25.0)


def test_percent_of_zero_is_none():
    assert percent(5, 0) is None


# --- parse_holdings ---

def test_parse_holdings_cleans_tickers_and_numbers():
    holdings = parse_holdings([{"ticker": " aapl ", "shares": "10", "avg_cost": 150}])
    assert holdings == [Holding("AAPL", 10.0, 150.0)]


def test_parse_holdings_allows_zero_cost():
    holdings = parse_holdings([{"ticker": "GIFT", "shares": 1, "avg_cost": 0}])
    assert holdings[0].avg_cost == 0


@pytest.mark.parametrize(
    "data, message",
    [
        ([], "non-empty list"),
        ("AAPL", "non-empty list"),
        ([1], "must have a ticker"),
        ([{"shares": 1, "avg_cost": 1}], "missing a ticker"),
        ([{"ticker": "  ", "shares": 1, "avg_cost": 1}], "missing a ticker"),
        (
            [
                {"ticker": "AAPL", "shares": 1, "avg_cost": 1},
                {"ticker": "aapl", "shares": 2, "avg_cost": 1},
            ],
            "AAPL appears more than once",
        ),
        ([{"ticker": "AAPL", "shares": "ten", "avg_cost": 1}], "must be numbers"),
        ([{"ticker": "AAPL", "avg_cost": 1}], "must be numbers"),
        ([{"ticker": "AAPL", "shares": "nan", "avg_cost": 1}], "must be numbers"),
        ([{"ticker": "AAPL", "shares": 1, "avg_cost": "inf"}], "must be numbers"),
        ([{"ticker": "AAPL", "shares": 0, "avg_cost": 1}], "more than 0"),
        ([{"ticker": "AAPL", "shares": -3, "avg_cost": 1}], "more than 0"),
        ([{"ticker": "AAPL", "shares": 1, "avg_cost": -1}], "cannot be negative"),
    ],
)
def test_parse_holdings_rejects_bad_input(data, message):
    with pytest.raises(ValueError, match=message):
        parse_holdings(data)


# --- position_summary ---

def test_position_summary_gain():
    p = position_summary(HOLDINGS[0], QUOTES["AAPL"])
    assert p["value"] == pytest.approx(2000)
    assert p["cost"] == pytest.approx(1500)
    assert p["pnl"] == pytest.approx(500)
    assert p["pnl_pct"] == pytest.approx(33.3333, rel=1e-4)
    assert p["day_change"] == pytest.approx(100)
    assert p["day_change_pct"] == pytest.approx(5.2632, rel=1e-4)


def test_position_summary_down_today():
    p = position_summary(HOLDINGS[1], QUOTES["MSFT"])
    assert p["day_change"] == pytest.approx(-60)
    assert p["day_change_pct"] == pytest.approx(-2.4390, rel=1e-4)


def test_position_summary_zero_cost_has_no_pnl_pct():
    p = position_summary(Holding("GIFT", 2, 0), Quote(price=10, prev_close=10))
    assert p["pnl"] == pytest.approx(20)
    assert p["pnl_pct"] is None


# --- portfolio_summary ---

def test_portfolio_totals():
    s = portfolio_summary(HOLDINGS, QUOTES)
    assert s["total_value"] == pytest.approx(4401)
    assert s["total_cost"] == pytest.approx(3000)
    assert s["pnl"] == pytest.approx(1400)
    assert s["pnl_pct"] == pytest.approx(46.6667, rel=1e-4)
    assert s["day_change"] == pytest.approx(40)
    # Yesterday's value was 4400 - 40 = 4360
    assert s["day_change_pct"] == pytest.approx(40 / 4360 * 100)
    assert s["missing"] == []


def test_portfolio_weights_and_order():
    s = portfolio_summary(HOLDINGS, QUOTES)
    assert [p["ticker"] for p in s["positions"]] == ["MSFT", "AAPL"]
    weights = [p["weight_pct"] for p in s["positions"]]
    assert weights == pytest.approx([54.5455, 45.4545], rel=1e-4)
    assert sum(weights) == pytest.approx(100)


def test_portfolio_missing_quote_is_listed_and_left_out():
    s = portfolio_summary(HOLDINGS, {"AAPL": QUOTES["AAPL"]})
    assert s["missing"] == ["MSFT"]
    assert s["total_value"] == pytest.approx(2000)
    assert s["positions"][0]["weight_pct"] == pytest.approx(100)


def test_portfolio_with_no_quotes():
    s = portfolio_summary(HOLDINGS, {})
    assert s["positions"] == []
    assert s["missing"] == ["AAPL", "MSFT"]
    assert s["total_value"] == 0
    assert s["pnl_pct"] is None
    assert s["day_change_pct"] is None


def test_portfolio_summary_does_not_change_inputs():
    holdings = list(HOLDINGS)
    portfolio_summary(holdings, QUOTES)
    assert holdings == HOLDINGS
