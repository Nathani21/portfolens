"""Portfolens API."""

from fastapi import FastAPI, HTTPException, Query

from portfolio import DEMO_HOLDINGS, portfolio_summary
from prices import (
    InvalidTicker,
    PriceError,
    UnknownTicker,
    clean_ticker,
    make_price_service,
    parse_tickers,
)
from ui_builders import create_dashboard_messages

app = FastAPI(title="Portfolens API")
prices, PRICE_MODE = make_price_service()


@app.get("/health")
def health():
    """Report that the API is running, and whether prices are live or demo."""
    return {"status": "ok", "prices": PRICE_MODE}


@app.get("/quotes")
def get_quotes(tickers: str = Query(..., description="Comma-separated, e.g. AAPL,MSFT")):
    """Current price and previous close for each ticker.

    Tickers without a price are listed in "errors" instead of failing the request.
    """
    try:
        symbols = parse_tickers(tickers)
    except InvalidTicker as error:
        raise HTTPException(status_code=400, detail=str(error)) from None
    found, errors = prices.quotes(symbols)
    return {
        "mode": PRICE_MODE,
        "quotes": {
            ticker: {"price": quote.price, "prev_close": quote.prev_close}
            for ticker, quote in found.items()
        },
        "errors": errors,
    }


@app.get("/history/{ticker}")
def get_history(ticker: str, days: int = Query(30, ge=5, le=365)):
    """Daily closing prices for one ticker over the last `days` calendar days."""
    try:
        symbol = clean_ticker(ticker)
        bars = prices.history(symbol, days)
    except InvalidTicker as error:
        raise HTTPException(status_code=400, detail=str(error)) from None
    except UnknownTicker as error:
        raise HTTPException(status_code=404, detail=str(error)) from None
    except PriceError as error:
        raise HTTPException(status_code=502, detail=str(error)) from None
    return {"mode": PRICE_MODE, "ticker": symbol, "bars": bars}


@app.get("/dashboard")
def get_dashboard():
    """A2UI messages that draw the demo portfolio dashboard.

    Holdings without a price still appear in the "missing" note, not as an error.
    """
    holdings = list(DEMO_HOLDINGS)
    found, _errors = prices.quotes([h.ticker for h in holdings])
    summary = portfolio_summary(holdings, found)
    return {"messages": create_dashboard_messages(summary, PRICE_MODE)}
