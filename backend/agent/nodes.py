"""
LangGraph node functions for the travel agent.

Each node receives the full TravelAgentState, performs its work,
and returns a dict of state updates to apply.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from agent.prompts import (
    FOLLOW_UP_PROMPT,
    INTENT_EXTRACTION_PROMPT,
    NO_RESULTS_PROMPT,
    RESPONSE_GENERATION_PROMPT,
    SYSTEM_PROMPT,
)
from agent.state import Coords, IntentModel, PlaceResult, TravelAgentState
from mcp.tools.filter_tool import filter_and_rank_places
from mcp.tools.geocoding_tool import geocode_location
from mcp.tools.places_tool import get_place_details, search_places

logger = logging.getLogger(__name__)


# ── LLM factory ──────────────────────────────────────────────────────────────

def _get_llm(temperature: float = 0.2) -> ChatGoogleGenerativeAI:
    from config import settings
    if settings.use_mocks:
        from mcp.tools.mock_data import MockLLM
        return MockLLM()  # type: ignore[return-value]
    return ChatGoogleGenerativeAI(
        model=settings.gemini_model,
        google_api_key=settings.gemini_api_key,
        temperature=temperature,
    )


# ── JSON extraction helper ────────────────────────────────────────────────────

def _extract_json(text: str) -> dict:
    """Extract the first JSON object from text, stripping markdown fences."""
    # Strip ```json ... ``` fences
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        return json.loads(fenced.group(1))
    # Bare JSON object
    bare = re.search(r"\{.*\}", text, re.DOTALL)
    if bare:
        return json.loads(bare.group(0))
    raise ValueError(f"No JSON object found in LLM response: {text!r}")


# ── Node 1: Intent extraction ─────────────────────────────────────────────────

async def intent_extraction_node(state: TravelAgentState) -> Dict[str, Any]:
    """
    Extract structured intent from the latest user message.

    - For new conversations: parses query, location, budget, etc.
    - For follow-up turns: detects and classifies the follow-up type.
    - Returns early with a clarification response if location is missing.
    """
    logger.info("NODE intent_extraction (turn=%d)", state.get("turn_count", 0))

    messages = state.get("messages", [])
    if not messages:
        return {
            "final_response": "Hello! I'm your AI travel agent. Where would you like to explore?",
            "turn_count": 1,
        }

    last_message = messages[-1].content

    # Build conversation history string for the prompt
    history_lines: List[str] = []
    for msg in messages[:-1]:
        if isinstance(msg, HumanMessage):
            history_lines.append(f"User: {msg.content}")
        elif isinstance(msg, AIMessage):
            history_lines.append(f"Agent: {msg.content}")
    history = "\n".join(history_lines) or "None"

    llm = _get_llm(temperature=0.1)

    # ── Detect follow-up ─────────────────────────────────────────────────
    has_prior_results = bool(state.get("filtered_places")) and state.get("turn_count", 0) > 0

    if has_prior_results:
        places_summary = [
            {"name": p.name, "place_id": p.place_id}
            for p in (state.get("filtered_places") or [])
        ]
        fu_prompt = FOLLOW_UP_PROMPT.format(
            places=json.dumps(places_summary, ensure_ascii=False),
            context=state.get("follow_up_context") or "",
            user_message=last_message,
        )
        try:
            fu_response = await llm.ainvoke(
                [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=fu_prompt)]
            )
            fu_data = _extract_json(fu_response.content)
            follow_up_intent = fu_data.get("intent", "new_search")
            if follow_up_intent != "new_search":
                return {
                    "follow_up_context": json.dumps(fu_data),
                    "turn_count": state.get("turn_count", 0) + 1,
                }
        except Exception as exc:
            logger.warning("Follow-up classification failed (%s); treating as new search", exc)

    # ── Extract fresh intent ──────────────────────────────────────────────
    intent_prompt = INTENT_EXTRACTION_PROMPT.format(
        user_message=last_message,
        history=history,
    )
    try:
        response = await llm.ainvoke(
            [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=intent_prompt)]
        )
        intent_data = _extract_json(response.content)

        # Normalise nullable fields
        for field in ("location", "budget", "cuisine_type", "vibe", "time_of_day"):
            if intent_data.get(field) in (None, "null", ""):
                intent_data[field] = None
        if intent_data.get("party_size") in (None, "null"):
            intent_data["party_size"] = None

        intent = IntentModel(**intent_data)

        if not intent.location:
            clarification = (
                "I'd love to help! Could you tell me which city or area you're looking in? "
                "For example: 'Bandra, Mumbai' or 'Connaught Place, Delhi'."
            )
            return {
                "error": "missing_location",
                "final_response": clarification,
                "turn_count": state.get("turn_count", 0) + 1,
                "follow_up_context": None,
            }

        return {
            "intent": intent,
            "error": None,
            "follow_up_context": None,
            "turn_count": state.get("turn_count", 0) + 1,
        }

    except Exception as exc:
        logger.exception("Intent extraction failed")
        return {
            "error": f"intent_extraction_failed: {exc}",
            "final_response": "I had trouble understanding your request. Could you rephrase it?",
            "turn_count": state.get("turn_count", 0) + 1,
        }


# ── Node 2: Geocoding ─────────────────────────────────────────────────────────

async def geocoding_node(state: TravelAgentState) -> Dict[str, Any]:
    """
    Resolve the location string in the current intent to lat/lng coordinates.
    """
    logger.info("NODE geocoding")

    if state.get("final_response"):  # already have an early-exit response
        return {}

    intent: IntentModel | None = state.get("intent")
    if not intent or not intent.location:
        return {
            "error": "missing_location",
            "final_response": "Please tell me which area you'd like to search in.",
        }

    try:
        coords = await geocode_location(intent.location)
        return {"location_coords": coords, "error": None}
    except ValueError as exc:
        return {
            "error": "geocoding_failed",
            "final_response": (
                f"I couldn't find '{intent.location}'. "
                "Could you be more specific? For example, include the city name."
            ),
        }
    except Exception as exc:
        logger.exception("Geocoding error")
        return {
            "error": "geocoding_failed",
            "final_response": "There was a problem looking up that location. Please try again.",
        }


# ── Node 3: Places search ─────────────────────────────────────────────────────

async def places_search_node(state: TravelAgentState) -> Dict[str, Any]:
    """
    Call the Google Places API to fetch up to max_results candidates.
    """
    logger.info("NODE places_search")

    if state.get("final_response"):
        return {}

    intent: IntentModel | None = state.get("intent")
    coords: Coords | None = state.get("location_coords")

    if not intent or not coords:
        return {
            "error": "missing_data",
            "final_response": "Something went wrong while setting up the search. Please try again.",
        }

    from config import settings

    try:
        places = await search_places(
            query=f"{intent.query} {intent.cuisine_type or ''}".strip(),
            lat=coords.lat,
            lng=coords.lng,
            radius=settings.default_radius_meters,
            place_type=intent.place_type or "restaurant",
            max_results=settings.max_results,
        )
        return {"raw_places": places, "error": None}
    except Exception as exc:
        logger.exception("Places search error")
        return {
            "error": "places_search_failed",
            "final_response": "I had trouble searching for places. Please try again in a moment.",
        }


# ── Node 4: Filter & rank ─────────────────────────────────────────────────────

async def filter_and_rank_node(state: TravelAgentState) -> Dict[str, Any]:
    """
    Filter raw places by budget/rating and rank by relevance + distance.
    Returns the top 5 places (or fewer if not enough qualify).
    """
    logger.info("NODE filter_and_rank")

    if state.get("final_response"):
        return {}

    raw_places: List[PlaceResult] = state.get("raw_places") or []
    intent: IntentModel | None = state.get("intent")
    coords: Coords | None = state.get("location_coords")

    if not raw_places:
        return {
            "filtered_places": [],
            "final_response": (
                "I couldn't find any places matching your request in that area. "
                "Try expanding the radius or adjusting your search."
            ),
        }

    filtered = await filter_and_rank_places(
        places=raw_places,
        budget=intent.budget if intent else None,
        min_rating=3.5,
        user_lat=coords.lat if coords else None,
        user_lng=coords.lng if coords else None,
    )

    top = filtered[:5]

    if not top:
        return {
            "filtered_places": [],
            "final_response": (
                "No places met the filters (rating ≥ 3.5, budget constraint). "
                "Would you like me to try with relaxed criteria?"
            ),
        }

    return {"filtered_places": top, "error": None}


# ── Node 5: Response generation ───────────────────────────────────────────────

async def response_generation_node(state: TravelAgentState) -> Dict[str, Any]:
    """
    Generate a natural-language response summarising the top recommendations.
    """
    logger.info("NODE response_generation")

    # If a previous node already set final_response (e.g. no results), just emit it.
    if state.get("final_response") and not state.get("filtered_places"):
        ai_msg = AIMessage(content=state["final_response"])
        return {"messages": [ai_msg]}

    intent: IntentModel | None = state.get("intent")
    filtered: List[PlaceResult] = state.get("filtered_places") or []

    if not filtered:
        llm = _get_llm(temperature=0.5)
        no_results_prompt = NO_RESULTS_PROMPT.format(
            user_query=intent.query if intent else "places",
            location=intent.location if intent else "that area",
            budget=intent.budget if intent else "any",
        )
        resp = await llm.ainvoke(
            [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=no_results_prompt)]
        )
        ai_msg = AIMessage(content=resp.content)
        return {"final_response": resp.content, "messages": [ai_msg]}

    # Summarise places for the prompt
    places_summary = []
    for i, p in enumerate(filtered, 1):
        places_summary.append(
            {
                "rank": i,
                "name": p.name,
                "rating": p.rating,
                "price": p.price_symbol or "₹",
                "address": p.address,
                "is_open": p.is_open,
                "distance_km": round(p.distance_meters / 1000, 1) if p.distance_meters else None,
            }
        )

    llm = _get_llm(temperature=0.7)
    prompt = RESPONSE_GENERATION_PROMPT.format(
        user_query=intent.query if intent else "recommendation",
        location=intent.location if intent else "the area",
        num_results=len(filtered),
        places=json.dumps(places_summary, ensure_ascii=False, indent=2),
    )

    response = await llm.ainvoke(
        [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)]
    )

    follow_up_ctx = (
        f"Last search: {intent.query if intent else ''} in {intent.location if intent else ''}"
    )
    ai_msg = AIMessage(content=response.content)

    return {
        "final_response": response.content,
        "follow_up_context": follow_up_ctx,
        "messages": [ai_msg],
    }


# ── Node 6: Follow-up handler ─────────────────────────────────────────────────

async def follow_up_handler_node(state: TravelAgentState) -> Dict[str, Any]:
    """
    Handle follow-up questions about previously shown recommendations.

    Supports: open_now, more_results, place_details, book_table, directions,
    and general conversation via the LLM.
    """
    logger.info("NODE follow_up_handler")

    from config import settings

    raw_ctx = state.get("follow_up_context") or "{}"
    try:
        fu_data = json.loads(raw_ctx)
    except json.JSONDecodeError:
        fu_data = {}

    fu_intent = fu_data.get("intent", "general")
    place_name: str = fu_data.get("place_name") or ""
    filtered: List[PlaceResult] = state.get("filtered_places") or []

    def _find_place(name: str) -> PlaceResult | None:
        if not name:
            return filtered[0] if filtered else None
        name_lower = name.lower()
        return next((p for p in filtered if name_lower in p.name.lower()), None)

    response_text = ""

    # ── open_now ──────────────────────────────────────────────────────────
    if fu_intent == "open_now":
        open_now = [p for p in filtered if p.is_open is True]
        closed = [p for p in filtered if p.is_open is False]
        unknown = [p for p in filtered if p.is_open is None]
        parts = []
        if open_now:
            parts.append("Currently open: " + ", ".join(p.name for p in open_now))
        if closed:
            parts.append("Currently closed: " + ", ".join(p.name for p in closed))
        if unknown:
            parts.append(
                "Hours unknown (I recommend calling ahead): "
                + ", ".join(p.name for p in unknown)
            )
        response_text = "\n".join(parts) or "I don't have opening-hours info for these places."

    # ── more_results ──────────────────────────────────────────────────────
    elif fu_intent == "more_results":
        current_intent: IntentModel | None = state.get("intent")
        current_coords: Coords | None = state.get("location_coords")
        if current_intent and current_coords:
            try:
                new_raw = await search_places(
                    query=current_intent.query,
                    lat=current_coords.lat,
                    lng=current_coords.lng,
                    radius=settings.default_radius_meters * 2,
                    place_type=current_intent.place_type or "restaurant",
                    max_results=settings.max_results,
                )
                existing_ids = {p.place_id for p in filtered}
                extras = [p for p in new_raw if p.place_id not in existing_ids][:5]
                if extras:
                    combined = filtered + extras
                    ai_msg = AIMessage(
                        content=f"I found {len(extras)} more option(s) for you!"
                    )
                    return {
                        "filtered_places": combined,
                        "final_response": f"Here are {len(extras)} more options!",
                        "messages": [ai_msg],
                    }
                else:
                    response_text = (
                        "I couldn't find more options nearby. "
                        "Would you like to try a different area?"
                    )
            except Exception:
                response_text = "I had trouble finding more options. Please try again."
        else:
            response_text = "I don't have enough context. Could you start a new search?"

    # ── place_details ─────────────────────────────────────────────────────
    elif fu_intent == "place_details":
        target = _find_place(place_name)
        if target:
            try:
                details = await get_place_details(target.place_id)
                lines = [f"More about {target.name}:"]
                if details.get("phone"):
                    lines.append(f"📞 {details['phone']}")
                if details.get("website"):
                    lines.append(f"🌐 {details['website']}")
                lines.append(f"📍 {target.address}")
                lines.append(f"⭐ {target.rating}/5 ({target.total_ratings} reviews)")
                if details.get("weekday_text"):
                    lines.append("🕐 Hours:")
                    for day in details["weekday_text"]:
                        lines.append(f"   {day}")
                if details.get("reviews"):
                    lines.append("💬 Recent reviews:")
                    for rv in details["reviews"][:2]:
                        lines.append(f'   "{rv["text"][:100]}..." — {rv["author"]}')
                response_text = "\n".join(lines)
            except Exception:
                response_text = (
                    f"{target.name} — {target.address} | Rating: {target.rating}/5"
                )
        else:
            response_text = "Which place would you like to know more about?"

    # ── book_table ────────────────────────────────────────────────────────
    elif fu_intent == "book_table":
        target = _find_place(place_name)
        if target:
            maps_link = target.maps_url
            response_text = (
                f"To reserve a table at {target.name}, I recommend calling them directly "
                f"or using this Google Maps link: {maps_link}\n"
                "Would you like me to find their phone number?"
            )
        else:
            response_text = "Which place would you like to book at?"

    # ── directions ────────────────────────────────────────────────────────
    elif fu_intent == "directions":
        target = _find_place(place_name)
        if target:
            response_text = f"Directions to {target.name}: {target.directions_url}"
        else:
            response_text = "Which place would you like directions to?"

    # ── general / fallback ────────────────────────────────────────────────
    else:
        llm = _get_llm(temperature=0.7)
        messages = state.get("messages", [])
        try:
            resp = await llm.ainvoke(
                [SystemMessage(content=SYSTEM_PROMPT), *messages]
            )
            response_text = resp.content
        except Exception:
            response_text = "How can I help you further with your travel plans?"

    ai_msg = AIMessage(content=response_text)
    return {"final_response": response_text, "messages": [ai_msg]}
