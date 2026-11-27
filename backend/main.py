"""Portfolens API."""

from fastapi import FastAPI

app = FastAPI(title="Portfolens API")


@app.get("/health")
def health():
    """Report that the API is running."""
    return {"status": "ok"}