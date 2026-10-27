# TripMind — React + FastAPI upgrade

This adds a React/Vite frontend and a FastAPI backend while preserving the existing Streamlit/LangGraph application and travel tools. The API calls the existing `agents.agent.chat_invoke()` implementation, so Groq's provider quota still applies.

## Requirements
- Python 3.12 recommended for the existing project
- Node.js 20+ and npm
- Existing API credentials configured locally in `.env`

## 1. Backend setup (Windows CMD)
From the project root:

```cmd
python -m venv .venv-api
.venv-api\Scripts\activate
python -m pip install -r requirements.txt
python -m pip install -r backend\requirements.txt
```

The root requirements are retained for the existing agent/tools. If the existing agent imports `langchain_groq`, install it if missing:

```cmd
python -m pip install langchain-groq fast-hotels selectolax primp google-search-results
```

Copy `.env.example` to `.env` and enter your own keys locally. Never commit `.env`.

Run the API:

```cmd
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Health check: http://127.0.0.1:8000/api/health
Interactive API docs: http://127.0.0.1:8000/docs

## 2. Frontend setup
Open a second terminal at the project root:

```cmd
cd frontend
copy .env.example .env
npm install
npm run dev
```

Open the URL printed by Vite (normally http://localhost:5173). The frontend calls `http://127.0.0.1:8000` by default; override `VITE_API_URL` if needed.

## 3. Supabase setup
1. Create a Supabase project.
2. Open SQL Editor and run `supabase_schema.sql`.
3. Put `SUPABASE_URL` and a backend-only key in `.env`.
4. The API attempts to persist each generated plan to `public.trips`; the app still works if Supabase is not configured.

For production, use authentication and Row Level Security policies appropriate to your user model. Do not expose the service-role key in the frontend.

## API contract
- `GET /api/health` — status check
- `POST /api/plan` — validates origin, destination, dates, travelers, budget, vibe, and preferences, then calls the existing agent.

## Notes
- The original Streamlit UI remains available using `python -m streamlit run app.py`.
- A React/FastAPI shell and optional Supabase persistence have been added, but external API integrations and deployment must still be tested with your own credentials. Groq rate limits remain controlled by Groq.
- Deploy frontend and backend separately; configure `FRONTEND_ORIGINS` and `VITE_API_URL` for the deployed domains.
