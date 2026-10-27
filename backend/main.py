"""FastAPI API for TripMind. The existing LangGraph/Groq agent is reused."""
from __future__ import annotations
import json, os, uuid
from datetime import date
from typing import Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator
from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(ROOT, ".env"))

app = FastAPI(title="TripMind API", version="1.0.0", description="AI-powered personalized travel planning API")
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("FRONTEND_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(","), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

class PlanRequest(BaseModel):
    origin: str = Field(min_length=2, max_length=100)
    destination: str = Field(min_length=2, max_length=100)
    start_date: date
    end_date: date
    travelers: int = Field(default=2, ge=1, le=20)
    budget_inr: int = Field(gt=0, le=100_000_000)
    preferences: list[str] = Field(default_factory=list, max_length=12)
    vibe: str = Field(default="balanced", max_length=60)

    @model_validator(mode="after")
    def dates_make_sense(self):
        if self.end_date <= self.start_date:
            raise ValueError("End date must be after start date.")
        if self.start_date < date.today():
            raise ValueError("Start date cannot be in the past.")
        return self

class PlanResponse(BaseModel):
    ok: bool
    plan: Any
    saved: bool = False
    message: str = ""

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "TripMind API", "version": app.version}

@app.post("/api/plan", response_model=PlanResponse)
def create_plan(payload: PlanRequest):
    """Generate a plan through the existing agent, then optionally persist it."""
    prompt = (
        f"Plan a trip from {payload.origin} to {payload.destination}, from {payload.start_date.isoformat()} "
        f"to {payload.end_date.isoformat()}, for {payload.travelers} traveler(s), total budget â‚¹{payload.budget_inr:,} INR. "
        f"Travel vibe: {payload.vibe}. Preferences: {', '.join(payload.preferences) if payload.preferences else 'balanced general recommendations'}. "
        "Return a concise complete trip plan with flight, hotel, weather, day-wise itinerary, budget breakdown, and packing suggestions. "
        "Do not invent live prices or availability; clearly label estimates and unavailable data."
    )
    try:
        from agents.agent import chat_invoke
        raw = chat_invoke(prompt, thread_id=str(uuid.uuid4()))
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            parsed = {"type": "text", "content": str(raw)}
        saved = _save_trip(payload, parsed)
        return PlanResponse(ok=True, plan=parsed, saved=saved, message="Trip plan generated." + (" Saved to Supabase." if saved else ""))
    except Exception as exc:
        # Avoid leaking secrets or internal tracebacks to the browser.
        import traceback; traceback.print_exc(); message = str(exc).lower()
        if "429" in message or "rate limit" in message or "tokens per day" in message:
            raise HTTPException(status_code=429, detail="The AI provider's token limit has been reached. Wait for quota reset and retry.") from exc
        raise HTTPException(status_code=503, detail="Trip planning is temporarily unavailable. Check backend logs and API configuration.") from exc

def _save_trip(payload: PlanRequest, plan: Any) -> bool:
    """Optional Supabase REST persistence. App remains usable without Supabase."""
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "") or os.getenv("SUPABASE_ANON_KEY", "")
    if not url or not key:
        return False
    try:
        import requests
        response = requests.post(
            f"{url}/rest/v1/trips",
            headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json", "Prefer": "return=minimal"},
            json={"origin": payload.origin, "destination": payload.destination, "start_date": payload.start_date.isoformat(), "end_date": payload.end_date.isoformat(), "travelers": payload.travelers, "budget_inr": payload.budget_inr, "preferences": payload.preferences, "vibe": payload.vibe, "itinerary": plan},
            timeout=8,
        )
        if response.status_code not in (200, 201, 204):
            print(f"Supabase save failed: HTTP {response.status_code}; response: {response.text[:1000]}", flush=True)
        return response.status_code in (200, 201, 204)
    except Exception as exc:
        print(f"Supabase save exception: {type(exc).__name__}: {exc}", flush=True)
        return False

