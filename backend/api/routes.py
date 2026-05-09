"""
FastAPI route handlers for the travel agent API.

Endpoints
---------
POST   /api/v1/chat                   — synchronous chat
POST   /api/v1/chat/stream            — SSE streaming chat
GET    /api/v1/session/{session_id}   — conversation history
DELETE /api/v1/session/{session_id}   — clear session
GET    /api/v1/health                 — health check
GET    /api/v1/place/{place_id}       — place details
"""
from __future__ import annotations

import json
import logging
import time
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Request
from langchain_core.messages import AIMessage, HumanMessage
from sse_starlette.sse import EventSourceResponse

from agent.graph import travel_agent
from agent.state import TravelAgentState
from api.schemas import (
    ChatRequest,
    ChatResponse,
    DeleteSessionResponse,
    HealthResponse,
    PlaceDetailResponse,
    PlaceResponse,
    SessionResponse,
)
from mcp.tools.places_tool import get_place_details

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["Travel Agent API"])

# ── Startup time for uptime tracking ─────────────────────────────────────────
_START_TIME = time.time()

# ── Deleted-session registry (soft delete) ────────────────────────────────────
_deleted_sessions: set[str] = set()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_config(session_id: str) -> dict:
    return {"configurable": {"thread_id": session_id}}


def _extract_places(state: TravelAgentState, api_key: str = "") -> list[PlaceResponse]:
    places_raw = state.get("filtered_places") or []
    out: list[PlaceResponse] = []
    for p in places_raw:
        d = p.to_api_dict(api_key=api_key)
        out.append(PlaceResponse(**d))
    return out


def _extract_follow_up(text: str | None) -> str | None:
    """Return the last sentence of the response as a follow-up hint (if any)."""
    if not text:
        return None
    sentences = text.replace("\n", " ").split(". ")
    return sentences[-1].strip() if len(sentences) > 1 else None


# ── POST /chat ────────────────────────────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Process a user message and return a complete agent response.

    The agent maintains conversation history across calls for the same session_id.
    """
    from config import settings

    session_id = request.session_id
    if session_id in _deleted_sessions:
        _deleted_sessions.discard(session_id)  # allow re-use after clear

    logger.info("POST /chat session=%s", session_id)

    input_state: dict = {
        "messages": [HumanMessage(content=request.message)],
        "session_id": session_id,
        "turn_count": 0,
        "intent": None,
        "location_coords": None,
        "raw_places": None,
        "filtered_places": None,
        "final_response": None,
        "follow_up_context": None,
        "error": None,
    }

    config = _build_config(session_id)

    try:
        result: TravelAgentState = await travel_agent.ainvoke(input_state, config=config)
    except Exception as exc:
        logger.exception("Agent invocation failed")
        raise HTTPException(status_code=500, detail=f"Agent error: {exc}") from exc

    response_text = result.get("final_response") or "I'm not sure how to help with that. Could you rephrase?"
    places = _extract_places(result, api_key=settings.google_places_api_key)

    return ChatResponse(
        response=response_text,
        places=places,
        session_id=session_id,
        follow_up=_extract_follow_up(response_text),
        turn_count=result.get("turn_count", 1),
    )


# ── POST /chat/stream ─────────────────────────────────────────────────────────

@router.post("/chat/stream")
async def chat_stream(request: ChatRequest, req: Request):
    """
    Stream the agent response token-by-token using Server-Sent Events.

    Event types emitted:
      - {"type": "token",  "content": "<text>"}
      - {"type": "places", "content": [...]}
      - {"type": "done",   "content": ""}
      - {"type": "error",  "content": "<message>"}
    """
    from config import settings

    session_id = request.session_id

    async def generate() -> AsyncGenerator[str, None]:
        input_state: dict = {
            "messages": [HumanMessage(content=request.message)],
            "session_id": session_id,
            "turn_count": 0,
            "intent": None,
            "location_coords": None,
            "raw_places": None,
            "filtered_places": None,
            "final_response": None,
            "follow_up_context": None,
            "error": None,
        }
        config = _build_config(session_id)

        # Track what we've already emitted so we don't double-send
        llm_streamed = False       # True once we get real on_chat_model_stream tokens
        places_emitted = False     # True once we emit a places event
        response_emitted = False   # True once we emit the final_response as tokens

        try:
            async for event in travel_agent.astream_events(
                input_state, config=config, version="v2"
            ):
                if await req.is_disconnected():
                    break

                event_type = event.get("event", "")

                # ── Real LLM token streaming ──────────────────────────────
                if event_type == "on_chat_model_stream":
                    chunk = event["data"].get("chunk")
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        llm_streamed = True
                        payload = json.dumps({"type": "token", "content": chunk.content})
                        yield payload

                # ── Node chain-end: capture outputs ───────────────────────
                elif event_type == "on_chain_end":
                    output = event["data"].get("output", {})
                    if not isinstance(output, dict):
                        continue

                    # Emit places once we have filtered results
                    if not places_emitted and output.get("filtered_places"):
                        places_emitted = True
                        places_data = [
                            p.to_api_dict(api_key=settings.google_places_api_key)
                            for p in output["filtered_places"]
                        ]
                        payload = json.dumps({"type": "places", "content": places_data})
                        yield payload

                    # Emit final_response as word tokens (mock mode / non-streaming LLMs)
                    if not response_emitted and not llm_streamed and output.get("final_response"):
                        response_emitted = True
                        text: str = output["final_response"]
                        # Stream word-by-word for a realistic typing effect
                        words = text.split(" ")
                        for i, word in enumerate(words):
                            chunk_text = word if i == 0 else f" {word}"
                            payload = json.dumps({"type": "token", "content": chunk_text})
                            yield payload

        except Exception as exc:
            logger.exception("Streaming error")
            payload = json.dumps({"type": "error", "content": str(exc)})
            yield payload
        finally:
            done = json.dumps({"type": "done", "content": ""})
            yield done

    return EventSourceResponse(generate())


# ── GET /session/{session_id} ─────────────────────────────────────────────────

@router.get("/session/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str) -> SessionResponse:
    """Return the full conversation history for a session."""
    if session_id in _deleted_sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    config = _build_config(session_id)
    try:
        state_snapshot = travel_agent.get_state(config)
        state = state_snapshot.values if state_snapshot else {}
    except Exception:
        raise HTTPException(status_code=404, detail="Session not found")

    raw_messages = state.get("messages", [])
    messages = []
    for msg in raw_messages:
        if isinstance(msg, HumanMessage):
            messages.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AIMessage):
            messages.append({"role": "assistant", "content": msg.content})

    return SessionResponse(
        session_id=session_id,
        messages=messages,
        turn_count=state.get("turn_count", 0),
    )


# ── DELETE /session/{session_id} ──────────────────────────────────────────────

@router.delete("/session/{session_id}", response_model=DeleteSessionResponse)
async def delete_session(session_id: str) -> DeleteSessionResponse:
    """Mark a session as cleared (soft delete)."""
    _deleted_sessions.add(session_id)
    logger.info("Session deleted: %s", session_id)
    return DeleteSessionResponse(session_id=session_id, status="cleared")


# ── GET /health ───────────────────────────────────────────────────────────────

@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Return application health and dependency status."""
    from config import settings

    uptime = time.time() - _START_TIME

    deps: dict[str, str] = {}
    if settings.use_mocks:
        deps = {
            "google_places_api": "mocked",
            "google_geocoding_api": "mocked",
            "gemini_api": "mocked",
            "langgraph": "ok",
        }
    else:
        deps = {
            "google_places_api": "configured" if settings.google_places_api_key else "missing_key",
            "google_geocoding_api": "configured" if settings.google_geocoding_api_key else "missing_key",
            "gemini_api": "configured" if settings.gemini_api_key else "missing_key",
            "langgraph": "ok",
        }

    all_ok = all(v not in ("missing_key", "error") for v in deps.values())

    return HealthResponse(
        status="ok" if all_ok else "degraded",
        version=settings.version,
        environment=settings.environment,
        uptime_seconds=round(uptime, 2),
        dependencies=deps,
    )


# ── GET /place/{place_id} ─────────────────────────────────────────────────────

@router.get("/place/{place_id}", response_model=PlaceDetailResponse)
async def get_place(place_id: str) -> PlaceDetailResponse:
    """Fetch detailed information for a specific place by its Google Place ID."""
    try:
        details = await get_place_details(place_id)
    except Exception as exc:
        logger.exception("Place details fetch failed")
        raise HTTPException(status_code=502, detail=f"Google Places API error: {exc}") from exc

    if not details:
        raise HTTPException(status_code=404, detail="Place not found")

    return PlaceDetailResponse(
        place_id=details.get("place_id", place_id),
        name=details.get("name", ""),
        phone=details.get("phone"),
        website=details.get("website"),
        rating=details.get("rating", 0.0),
        is_open=details.get("is_open"),
        weekday_text=details.get("weekday_text", []),
        reviews=details.get("reviews", []),
    )
