from datetime import date

import pytest
from fastapi.testclient import TestClient

import main
from prices import FakePrices, PriceError, PriceService


@pytest.fixture
def client(monkeypatch):
    """A client whose prices always come from demo data, even if API keys are set."""
    demo = FakePrices(today=lambda: date(2026, 11, 27))
    monkeypatch.setattr(main, "prices", PriceService(demo, demo))
    monkeypatch.setattr(main, "PRICE_MODE", "demo")
    return TestClient(main.app)


def test_health(client):
    assert client.get("/health").json() == {"status": "ok", "prices": "demo"}


def test_quotes(client):
    response = client.get("/quotes", params={"tickers": "aapl,MSFT"})
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "demo"
    assert body["quotes"]["AAPL"] == pytest.approx({"price": 231.5, "prev_close": 228.9})
    assert list(body["quotes"]) == ["AAPL", "MSFT"]
    assert body["errors"] == {}


def test_quotes_unknown_ticker_is_reported_not_fatal(client):
    body = client.get("/quotes", params={"tickers": "AAPL,TSLA"}).json()
    assert list(body["quotes"]) == ["AAPL"]
    assert "TSLA" in body["errors"]


def test_quotes_bad_ticker(client):
    response = client.get("/quotes", params={"tickers": "AAPL,../x"})
    assert response.status_code == 400
    assert "isn't a valid ticker" in response.json()["detail"]


def test_quotes_needs_tickers(client):
    assert client.get("/quotes").status_code == 422


def test_history(client):
    response = client.get("/history/aapl", params={"days": 14})
    assert response.status_code == 200
    body = response.json()
    assert body["ticker"] == "AAPL"
    assert len(body["bars"]) == 10
    assert body["bars"][-1]["date"] == "2026-11-26"
    assert body["bars"][-1]["close"] == pytest.approx(228.9)


def test_history_unknown_ticker(client):
    assert client.get("/history/TSLA").status_code == 404


def test_history_bad_ticker(client):
    assert client.get("/history/1ABC").status_code == 400


@pytest.mark.parametrize("days", [4, 366])
def test_history_days_out_of_range(client, days):
    assert client.get("/history/AAPL", params={"days": days}).status_code == 422


def test_history_provider_failure(client, monkeypatch):
    class Broken:
        """A history source that always fails like a busy provider."""

        def history(self, ticker, days):
            """Always raise PriceError."""
            raise PriceError("The price service is busy. Try again in a minute.")

    monkeypatch.setattr(main, "prices", PriceService(FakePrices(), Broken()))
    response = client.get("/history/AAPL")
    assert response.status_code == 502
    assert "busy" in response.json()["detail"]


def test_dashboard(client):
    response = client.get("/dashboard")
    assert response.status_code == 200
    messages = response.json()["messages"]
    assert len(messages) == 1
    surface = messages[0]["createSurface"]
    assert messages[0]["version"] == "1.0"
    assert surface["surfaceId"] == "portfolio_dashboard"
    model = surface["dataModel"]
    assert model["totals"]["value"] == "$12,198.70"
    assert model["mode_note"].startswith("Demo prices")
    assert len(model["positions"]) == 5
    assert model["missing_note"] == ""
