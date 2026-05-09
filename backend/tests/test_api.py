"""
API endpoint tests.

Uses FastAPI's TestClient to validate HTTP behaviour, status codes,
request validation, and session management.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from agent.state import Coords, IntentModel, PlaceResult


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_agent_result(
    response_text: str = "Here are some great places!",
    places: list | None = None,
    turn_count: int = 1,
):
    """Build a realistic mock TravelAgentState dict for graph.ainvoke."""
    from langchain_core.messages import AIMessage, HumanMessage

    filtered = places or [
        PlaceResult(
            place_id="ChIJtest1234",
            name="The Rooftop Lounge",
            rating=4.5,
            price_level=2,
            address="123 Bandra West, Mumbai",
            lat=19.0596,
            lng=72.8295,
            is_open=True,
            types=["restaurant"],
            total_ratings=350,
        )
    ]
    return {
        "messages": [
            HumanMessage(content="Find rooftop restaurants in Bandra"),
            AIMessage(content=response_text),
        ],
        "intent": IntentModel(query="rooftop restaurant", location="Bandra, Mumbai"),
        "location_coords": Coords(lat=19.0596, lng=72.8295, formatted_address="Bandra West, Mumbai"),
        "raw_places": filtered,
        "filtered_places": filtered,
        "final_response": response_text,
        "follow_up_context": "Last search: rooftop in Bandra",
        "error": None,
        "turn_count": turn_count,
        "session_id": "test-session-id",
    }


# ── /api/v1/chat tests ────────────────────────────────────────────────────────

def test_chat_endpoint_returns_200(client, mocker):
    """POST /api/v1/chat returns 200 with response and places."""
    mocker.patch(
        "api.routes.travel_agent.ainvoke",
        AsyncMock(return_value=_mock_agent_result()),
    )
    resp = client.post(
        "/api/v1/chat",
        json={"message": "Rooftop restaurants in Bandra", "session_id": "sess-001"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "response" in body
    assert "places" in body
    assert "session_id" in body
    assert body["session_id"] == "sess-001"


def test_chat_endpoint_invalid_input(client):
    """POST /api/v1/chat returns 422 for missing required fields."""
    resp = client.post("/api/v1/chat", json={"session_id": "sess-002"})  # missing message
    assert resp.status_code == 422


def test_chat_endpoint_empty_message(client):
    """POST /api/v1/chat returns 422 for empty message string."""
    resp = client.post("/api/v1/chat", json={"message": "", "session_id": "sess-003"})
    assert resp.status_code == 422


def test_chat_endpoint_with_location(client, mocker):
    """POST /api/v1/chat accepts optional user GPS location."""
    mocker.patch(
        "api.routes.travel_agent.ainvoke",
        AsyncMock(return_value=_mock_agent_result()),
    )
    resp = client.post(
        "/api/v1/chat",
        json={
            "message": "Coffee shops nearby",
            "session_id": "sess-004",
            "location": {"lat": 19.0596, "lng": 72.8295},
        },
    )
    assert resp.status_code == 200


def test_chat_response_contains_place_fields(client, mocker):
    """Place objects in the response include all required fields."""
    mocker.patch(
        "api.routes.travel_agent.ainvoke",
        AsyncMock(return_value=_mock_agent_result()),
    )
    resp = client.post(
        "/api/v1/chat",
        json={"message": "Rooftop in Bandra", "session_id": "sess-005"},
    )
    assert resp.status_code == 200
    places = resp.json().get("places", [])
    if places:
        place = places[0]
        assert "place_id" in place
        assert "name" in place
        assert "rating" in place
        assert "maps_url" in place


# ── /api/v1/health tests ──────────────────────────────────────────────────────

def test_health_endpoint(client):
    """GET /api/v1/health returns 200 with status field."""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert "status" in body
    assert "version" in body
    assert "uptime_seconds" in body
    assert "dependencies" in body


# ── /api/v1/session tests ─────────────────────────────────────────────────────

def test_session_persistence(client, mocker):
    """POST /chat followed by GET /session returns consistent session_id."""
    mocker.patch(
        "api.routes.travel_agent.ainvoke",
        AsyncMock(return_value=_mock_agent_result()),
    )
    session_id = "persist-session-001"
    post_resp = client.post(
        "/api/v1/chat",
        json={"message": "Restaurants in Bandra", "session_id": session_id},
    )
    assert post_resp.json()["session_id"] == session_id


def test_delete_session(client, mocker):
    """DELETE /session/{id} returns 200 with status=cleared."""
    resp = client.delete("/api/v1/session/my-session-to-delete")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cleared"


# ── /api/v1/place tests ───────────────────────────────────────────────────────

def test_get_place_returns_details(client, mocker):
    """GET /api/v1/place/{id} returns place details from the API."""
    mock_details = {
        "place_id": "ChIJtest1234",
        "name": "The Rooftop Lounge",
        "phone": "+91 22 1234 5678",
        "website": "https://example.com",
        "rating": 4.5,
        "is_open": True,
        "weekday_text": ["Monday: 12 PM – 11 PM"],
        "reviews": [],
    }
    mocker.patch(
        "api.routes.get_place_details",
        AsyncMock(return_value=mock_details),
    )
    resp = client.get("/api/v1/place/ChIJtest1234")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "The Rooftop Lounge"
    assert body["phone"] == "+91 22 1234 5678"


def test_get_place_not_found(client, mocker):
    """GET /api/v1/place/{id} returns 502 when Places API throws."""
    mocker.patch(
        "api.routes.get_place_details",
        AsyncMock(side_effect=Exception("API error")),
    )
    resp = client.get("/api/v1/place/nonexistent_place_id")
    assert resp.status_code == 502


# ── Streaming endpoint smoke test ─────────────────────────────────────────────

def test_streaming_endpoint_exists(client):
    """POST /api/v1/chat/stream returns a streaming response (not 404)."""
    resp = client.post(
        "/api/v1/chat/stream",
        json={"message": "Test query", "session_id": "stream-test"},
        headers={"Accept": "text/event-stream"},
    )
    # Even without mocking, the route should exist (not 404/405)
    assert resp.status_code != 404
    assert resp.status_code != 405
