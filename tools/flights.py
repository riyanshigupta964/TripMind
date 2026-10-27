"""Flight tools — two-step: airport code lookup (Tavily) + flight search (fli / SerpAPI).

Requires env vars:
  TAVILY_API_KEY   — tavily.com key (used for airport code lookup)
  SERPAPI_API_KEY  — serpapi.com key (used for Google Flights search, if search_flights is called)
"""

import os
import re
from functools import lru_cache
from datetime import datetime

from dateutil import parser as dateparser
from tavily import TavilyClient
from serpapi import GoogleSearch
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


# ── Tool 1: Airport code lookup (Tavily) ──────────────────────────────────────

@lru_cache(maxsize=128)
def _cached_airport_lookup(city_key: str) -> tuple:
    """Cache successful airport lookups. Exceptions are not cached."""
    client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
    response = client.search(
        query=f"IATA airport code(s) for commercial airports serving {city_key}",
        max_results=3,
        search_depth="basic",
        include_answer=True,
    )
    answer = response.get("answer", "") or ""
    results = tuple(
        (
            r.get("title", "")[:120],
            r.get("content", "")[:180],
            r.get("url", "")[:200],
        )
        for r in response.get("results", [])[:3]
    )
    return answer[:300], results


def get_airport_code(city: str) -> dict:
    """Look up airport IATA codes for a city, reusing successful cached results.

    Args:
        city: City or region, optionally including country, e.g. "Bhopal, India"
             or "Bali, Indonesia".
    """
    normalized_city = " ".join(city.strip().split())
    cache_key = normalized_city.casefold()
    print(f"\\n🔍 get_airport_code [Tavily/cache] | {normalized_city}")

    try:
        answer, cached_results = _cached_airport_lookup(cache_key)
        results = [
            {"title": title, "content": content, "url": url}
            for title, content, url in cached_results
        ]
        print(f"   → {len(results)} result(s) returned")
        return {
            "city": normalized_city,
            "answer": answer,
            "search_results": results,
        }
    except Exception as e:
        # Failed requests are not cached, so a later user-initiated retry can work.
        return {"city": normalized_city, "error": f"Tavily search failed: {e}"}


# ── Tool 2: Flight search ──────────────────────────────────────────────────────

def _parse_date(date_str: str) -> str:
    try:
        dt = dateparser.parse(date_str)
    except Exception:
        m = re.search(r"\d{4}-\d{2}-\d{2}", date_str)
        if not m:
            raise ValueError(f"Cannot parse date: '{date_str}'")
        dt = datetime.fromisoformat(m.group())

    today = datetime.today()
    while dt.date() < today.date():
        dt = dt.replace(year=dt.year + 1)
        print(f"   ℹ️  Date was in the past — advanced to {dt.strftime('%Y-%m-%d')}")

    return dt.strftime("%Y-%m-%d")


def _fmt_mins(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    return f"{h}h {m:02d}m"


def _parse_items(items: list, adults: int) -> list[dict]:
    offers = []
    for item in items:
        segs = item.get("flights", [])
        if not segs:
            continue
        price_total = item.get("price")
        if not price_total:
            continue

        first = segs[0]
        last = segs[-1]
        stops = len(segs) - 1
        price_pp = round(price_total / adults) if adults > 0 else price_total
        dep_time = first["departure_airport"]["time"][11:16]
        arr_time = last["arrival_airport"]["time"][11:16]

        layovers = [
            {"city": lv.get("name", lv.get("id", "?")), "duration": _fmt_mins(lv.get("duration", 0))}
            for lv in item.get("layovers", [])
        ]

        offers.append({
            "airline": first.get("airline", ""),
            "flight_number": first.get("flight_number", ""),
            "price_per_person_inr": price_pp,
            "total_price_inr": price_total,
            "departure_time": dep_time,
            "arrival_time": arr_time,
            "duration": _fmt_mins(item.get("total_duration", 0)),
            "stops": stops,
            "direct": stops == 0,
            "layovers": layovers,
            "from": first["departure_airport"]["id"],
            "to": last["arrival_airport"]["id"],
        })

    offers.sort(key=lambda r: (not r["direct"], r["total_price_inr"]))
    return offers[:3]


def search_flights (
    origin_iata: str,
    dest_iata: str,
    date: str,
    travelers: int = 1,
    direct_only: bool = False,
)-> dict:
    """Flight Agent — Step 2: Search one-way flights via Google Flights (SerpAPI).

    Call this independently for each leg — outbound and return — so you can
    mix airports freely (e.g. fly into GOX, return from GOI if cheaper).

    Args:
        origin_iata: Departure IATA code, e.g. "PNQ".
        dest_iata: Arrival IATA code, e.g. "GOX".
        date: Flight date, e.g. "2026-08-01" or "1 August 2026".
        travelers: Number of adult passengers.
        direct_only: If True, return only nonstop options.

    Returns:
        Dict with route (str) and flights (list of up to 3 options).
        Each flight: airline, flight_number, price_per_person_inr, total_price_inr,
        departure_time, arrival_time, duration, stops, direct (bool),
        layovers [{city, duration}], from, to.
    """
    date_str = _parse_date(date)
    print(f"\n✈️  search_flights | {origin_iata}→{dest_iata} | {date_str} | {travelers} pax | direct_only={direct_only}")

    try:
        api_key = os.environ.get("SERPAPI_API_KEY")

        if not api_key:
            return {
                "route": f"{origin_iata} → {dest_iata}",
                "flights": [],
                "error": "SERPAPI_API_KEY is missing from your .env file."
            }

        from serpapi import GoogleSearch

        params = {
            "api_key": api_key,
            "engine": "google_flights",
            "departure_id": origin_iata,
            "arrival_id": dest_iata,
            "outbound_date": date_str,
            "currency": "INR",
            "hl": "en",
            "adults": travelers,
            "type": "2",
        }

        raw = GoogleSearch(params).get_dict()

        if raw.get("error"):
            print(f"[warning] Flight search failed: {raw['error']}")
            return {
                "route": f"{origin_iata} → {dest_iata}",
                "flights": [],
                "error": raw["error"]
            }

        all_items = (
            list(raw.get("best_flights", []))
            + list(raw.get("other_flights", []))
        )

        flights = _parse_items(all_items, travelers)

        if direct_only:
            flights = [flight for flight in flights if flight["direct"]]

        return {
            "route": f"{origin_iata} → {dest_iata}",
            "flights": flights
        }

    except Exception as e:
        print(f"[warning] Flight search error: {e}")
        return {
            "route": f"{origin_iata} → {dest_iata}",
            "flights": [],
            "error": str(e)
        }