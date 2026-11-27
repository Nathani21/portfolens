# Portfolens

![CI](https://github.com/Nathani21/portfolens/actions/workflows/ci.yml/badge.svg)

A stock portfolio dashboard where an AI agent builds the view with Google's A2UI protocol.

🚧 Work in progress.

## Structure
- `backend/`: FastAPI API (Python 3.13)
- `frontend/`: Next.js app

## Run locally
**Backend**
```
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload
```

**Frontend**
```
cd frontend
npm install
npm run dev
```

Without API keys the backend runs in **demo mode** with made-up prices for AAPL, MSFT, NVDA, GOOGL and AMZN. For live prices, set both keys in the terminal before starting it:
```
$env:FINNHUB_API_KEY = "your-finnhub-key"
$env:MASSIVE_API_KEY = "your-massive-key"
```
Check http://127.0.0.1:8000/health: `"prices"` says `demo` or `live`.