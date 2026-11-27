# Portfolens

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