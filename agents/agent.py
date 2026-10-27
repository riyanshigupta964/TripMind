"""TripMind Supervisor — multi-agent travel planning orchestrator.

Architecture:
  Supervisor reasons about budget/planning directly, then delegates to 4 subagents:
    - flight-agent   : searches real flights (SerpAPI Google Flights)
    - hotel-agent    : searches real hotels (Google Hotels via fast_hotels)
    - weather-agent  : fetches weather forecasts (Open-Meteo)
    - itinerary-agent: builds day-by-day plan from flight + hotel + weather context
"""

from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from langchain_groq import ChatGroq


from langgraph.checkpoint.memory import InMemorySaver
from langchain.agents import create_agent
from langchain_core.tools import tool
from contextvars import ContextVar


from tools.flights import get_airport_code
from tools.flights import search_flights
from tools.hotels import search_hotels as _search_hotels_impl
from tools.weather import get_weather_forecast

ROOT = Path(__file__).resolve().parent.parent

MODEL = ChatGroq(
    model="qwen/qwen3.8-27b",
    temperature=0,
    max_retries=1,
    max_tokens=800,
    reasoning_effort="none",
)

# ── Subagents ─────────────────────────────────────────────────────────────────

planning_subagent = {
    "name": "planning-agent",
    "description": "Creates a trip budget and hotel category from the user's trip details. Call first.",
    "system_prompt": (
        "You are TripMind's planning agent. Return only valid JSON with "
        "trip details, duration_days, travelers, budget allocations for flights, "
        "hotel, activities, food, transport and miscellaneous expenses, "
        "hotel_per_night, hotel_category, search_requirements, and brief planning_notes. "
        "Use INR. Allocate the budget realistically, ensure allocations do not exceed "
        "the total budget, and calculate hotel_per_night using the number of nights. "
        "Never invent user-provided details. Return JSON only, without markdown."
    ),
    "tools": [],
}

flight_subagent = {
    "name": "flight-agent",
    "description": "Searches real flights. Provide origin, destination, date, and travelers. Check multiple airports when applicable.",
    "system_prompt": (
        "Find airport IATA codes using get_airport_code, then search with search_flights. "
        "Check multiple airports when applicable. For multi-city trips, use the specified "
        "return origin or a nearby airport. Prefer nonstop flights; clearly flag connections. "
        "Preserve the returned flight details and never invent results."
    ),
    "tools": [get_airport_code, search_flights],
}

# Track hotel searches separately for each execution context.
_hotel_search_count = ContextVar("hotel_search_count", default=0)

@tool("search_hotels")
def guarded_search_hotels(
    city: str,
    checkin_date: str,
    checkout_date: str,
    budget_per_night: int,
    duration_days: int,
    search_term: str | None = None,
    guests: int = 2,
) -> dict:
    """Search for hotels once per trip request."""
    count = _hotel_search_count.get()

    if count >= 1:
        return {
            "options": [],
            "message": (
                "Hotel search has already been attempted for this trip. "
                "Do not search again. Continue planning with the available results."
            ),
        }

    _hotel_search_count.set(count + 1)

    return _search_hotels_impl(
        city=city,
        checkin_date=checkin_date,
        checkout_date=checkout_date,
        budget_per_night=budget_per_night,
        duration_days=duration_days,
        search_term=search_term,
        guests=guests,
    )


hotel_subagent = {
    "name": "hotel-agent",
    "description": "Searches hotels by city, dates, nightly budget, and preferences.",
    "system_prompt": (
        "Call search_hotels using the supervisor's parameters. "
        "Return all available results without filtering or inventing data. "
        "Include options even if they exceed the budget."
    ),
    "tools": [guarded_search_hotels],
}

weather_subagent = {
    "name": "weather-agent",
    "description": "Fetches weather forecasts or historical climate estimates for a destination and dates.",
    "system_prompt": (
        "Call get_weather_forecast with the provided destination, start_date, "
        "and end_date. Return the complete result, including forecast, summary, "
        "clothing recommendations, and activity suggestions. Never invent data."
    ),
    "tools": [get_weather_forecast],
}


itinerary_subagent = {
    "name": "itinerary-agent",
    "description": "Creates a day-by-day itinerary and packing list after flight, hotel, and weather searches.",
    "system_prompt": (
        "Create a practical daily itinerary and concise packing list using the supplied trip context. "
        "Account for arrival time, airport transfers, return departure, weather, budget, and interests. "
        "Include morning, afternoon, and evening activities, approximate INR costs, and real venues "
        "when reliable information is available. Account for inter-city travel when applicable. "
        "Tailor packing recommendations to the destination, weather, and activities. "
        "Never invent confirmed prices or bookings."
    ),
    "tools": [],
}

# ── System Prompt ──────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """ You are TripMind, a concise travel-planning assistant.

Collect these details before planning: origin, destination, departure date,
return date, total budget in INR, and number of travelers. Ask one or two
questions at a time.

When all details are available:
- Use get_airport_code and search_flights to search for flights.
- Use search_hotels to search for hotel options.
- Use get_weather_forecast to obtain weather information.
- Create a practical budget breakdown, day-by-day itinerary, and packing list
  using the available results.

Never invent prices, availability, weather, or search results.
Do not repeat failed searches automatically.
Clearly distinguish estimates from confirmed information.

BUDGET VALIDATION RULES:
- Treat budget_inr as the total budget for all travelers combined.
- Include flights for every traveler, the full hotel stay, food, transport, activities and miscellaneous expenses.
- Calculate the estimated total before finalizing the plan.
- If expenses exceed budget_inr, explicitly mark the plan OVER BUDGET and state the shortfall in INR.
- Never claim an over-budget trip fits the budget.
- Suggest cheaper alternatives only when supported by search results. Never invent prices or availability.
- Ensure the budget breakdown and recommendation agree with the estimated total.

Return one valid JSON object, without Markdown or surrounding text.

For ordinary questions or missing details:
{"type":"text","content":"Your response"}

For completed trip plans:
{"type":"trip_plan","title":"Trip title","overview":{},"flight":{},"hotel":{},"weather":{},"budget_breakdown":[],"itinerary":[],"packing":[],"recommendation":"..."}

For destination comparisons:
{"type":"comparison","title":"Comparison title","options":[],"recommendation":"..."}

Include only supported fields. Never use null values.
All amount_inr values must be integers.
Keep responses concise and user-friendly.

Tool usage rules:
- Call get_airport_code only when an airport code is needed.
- Look up each unique city only once per trip request.
- Reuse airport lookup results; do not search a city again with different wording.
- Do not assume every destination is in India; include the country supplied by the user.
- After obtaining origin and destination codes, call search_flights once for the requested leg.
- Call search_hotels at most once per trip request. Never call it again with a higher budget if the result contains no hotels.
- If search_hotels returns an empty options list, report that no hotel results were found and continue the trip plan without retrying or increasing the budget.
- Never use repeated hotel searches to find results at progressively higher budgets. Ask the user before changing the hotel budget or search criteria.
- Never repeat a successful tool call with the same inputs.
- If a tool fails, do not retry automatically; explain the limitation.
- Do not search nearby/alternate airports unless the user asks or the first search returns no options.
- Keep responses and tool usage concise; stop searching when enough results are available.
"""

# ── Agent ──────────────────────────────────────────────────────────────────────

_checkpointer = InMemorySaver()

agent = create_agent(
    model=MODEL,
    tools=[
        get_airport_code,
        search_flights,
        guarded_search_hotels,
        get_weather_forecast,
    ],
    system_prompt=SYSTEM_PROMPT,
    checkpointer=_checkpointer,
)

def _ensure_json(text: str) -> str:
    """If the agent didn't return JSON, wrap it so the UI can render it."""
    import json, re
    text = text.strip()
    # Already valid JSON?
    try:
        json.loads(text)
        return text
    except Exception:
        pass
    # JSON inside a code fence?
    m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if m:
        try:
            json.loads(m.group(1))
            return m.group(1)
        except Exception:
            pass
    # Bare JSON block anywhere?
    m = re.search(r'(\{.*\})', text, re.DOTALL)
    if m:
        try:
            json.loads(m.group(1))
            return m.group(1)
        except Exception:
            pass
    # Fallback: wrap as text type so UI renders markdown
    import json as _json
    return _json.dumps({"type": "text", "content": text})

def chat_invoke(message: str, thread_id: str) -> str:
    """Send a user message and return the final assistant response as JSON."""
    _hotel_search_count.set(0)

    import json
    import traceback

    try:
        result = agent.invoke(
            {"messages": [{"role": "user", "content": message}]},
            config={
                "recursion_limit": 12,
                "configurable": {"thread_id": thread_id},
            },
        )
        messages = result.get("messages", [])

        # Search backward for the final assistant response.
        for msg in reversed(messages):
            role = getattr(msg, "type", "")
            content = getattr(msg, "content", "")

            # Ignore human and tool messages.
            if role != "ai":
                continue

            # Ignore assistant messages that only request tool calls.
            if getattr(msg, "tool_calls", []):
                continue

            # Return a normal text response.
            if isinstance(content, str) and content.strip():
                return _ensure_json(content.strip())

            # Handle responses represented as text blocks.
            if isinstance(content, list):
                text_parts = [
                    item.get("text", "")
                    for item in content
                    if isinstance(item, dict)
                    and item.get("type") == "text"
                ]

                combined = "\n".join(text_parts).strip()

                if combined:
                    return _ensure_json(combined)

        return json.dumps({
            "type": "text",
            "content": "TripMind could not produce a final response. Please try again."
        })

    except Exception as e:
        traceback.print_exc()

        error_message = str(e).lower()

        if (
            "resource_exhausted" in error_message
            or "429" in error_message
            or "input tokens per minute" in error_message
            or "error code: 413" in error_message
        ):
            user_message = (
                "TripMind temporarily reached Groq's free-tier token rate limit. "
                "Wait about 60 seconds, then try again with a shorter message. "
                "No paid upgrade is required to handle this error; availability "
                "depends on the provider's current free-tier limits."
            )
        elif "recursion limit" in error_message or "graphrecursionerror" in error_message:
            user_message = (
                "TripMind stopped a repeated tool-call loop to avoid excessive API use. "
                "Please try again with the trip details in one message, including "
                "origin, destination and country, dates, budget in INR, and travelers."
            )
        else:
            user_message = (
                f"TripMind encountered an error: {type(e).__name__}: {e}"
            )

        return json.dumps({
            "type": "text",
            "content": user_message
        })