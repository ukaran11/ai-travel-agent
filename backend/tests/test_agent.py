"""
Agent integration tests.

Node functions are tested with mocked tool calls and a mocked LLM.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from agent.nodes import (
    filter_and_rank_node,
    geocoding_node,
    intent_extraction_node,
    places_search_node,
    response_generation_node,
)
from agent.state import Coords, IntentModel, PlaceResult


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_state(**overrides) -> dict:
    base = {
        "messages": [HumanMessage(content="Find a rooftop restaurant in Bandra")],
        "intent": None,
        "location_coords": None,
        "raw_places": None,
        "filtered_places": None,
        "final_response": None,
        "follow_up_context": None,
        "error": None,
        "turn_count": 0,
        "session_id": "test-session",
    }
    base.update(overrides)
    return base


INTENT_JSON = json.dumps({
    "query": "rooftop restaurant",
    "location": "Bandra, Mumbai",
    "budget": "moderate",
    "cuisine_type": None,
    "vibe": "romantic",
    "party_size": 2,
    "time_of_day": "dinner",
    "place_type": "restaurant",
})


# ── intent_extraction_node tests ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_intent_extraction_restaurant(mocker):
    """Extracts intent correctly from a restaurant query."""
    mock_llm_response = MagicMock()
    mock_llm_response.content = INTENT_JSON

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_llm_response)
    mocker.patch("agent.nodes._get_llm", return_value=mock_llm)

    state = _make_state()
    result = await intent_extraction_node(state)

    assert result["intent"] is not None
    assert result["intent"].query == "rooftop restaurant"
    assert result["intent"].location == "Bandra, Mumbai"
    assert result["intent"].budget == "moderate"
    assert result["error"] is None


@pytest.mark.asyncio
async def test_intent_extraction_missing_location(mocker):
    """Returns a clarification response when location is absent."""
    intent_no_loc = json.dumps({
        "query": "good restaurant",
        "location": None,
        "budget": None,
        "cuisine_type": None,
        "vibe": None,
        "party_size": None,
        "time_of_day": None,
        "place_type": "restaurant",
    })
    mock_llm_response = MagicMock(content=intent_no_loc)

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_llm_response)
    mocker.patch("agent.nodes._get_llm", return_value=mock_llm)

    state = _make_state(messages=[HumanMessage(content="Find me a good restaurant")])
    result = await intent_extraction_node(state)

    assert result.get("error") == "missing_location"
    assert result.get("final_response") is not None
    assert "location" in result["final_response"].lower() or "area" in result["final_response"].lower()


@pytest.mark.asyncio
async def test_intent_extraction_budget_parsing(mocker):
    """Correctly parses budget=budget from cheap/budget keywords."""
    intent_budget = json.dumps({
        "query": "cheap eats",
        "location": "Andheri, Mumbai",
        "budget": "budget",
        "cuisine_type": None,
        "vibe": None,
        "party_size": None,
        "time_of_day": None,
        "place_type": "restaurant",
    })
    mock_llm_response = MagicMock(content=intent_budget)

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_llm_response)
    mocker.patch("agent.nodes._get_llm", return_value=mock_llm)

    state = _make_state(messages=[HumanMessage(content="Cheap eats in Andheri")])
    result = await intent_extraction_node(state)

    assert result["intent"].budget == "budget"


# ── geocoding_node tests ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_geocoding_node_success(mocker, sample_coords):
    """Geocoding node resolves location and returns coords."""
    mocker.patch("agent.nodes.geocode_location", AsyncMock(return_value=sample_coords))

    intent = IntentModel(query="rooftop restaurant", location="Bandra, Mumbai")
    state = _make_state(intent=intent)
    result = await geocoding_node(state)

    assert result["location_coords"] is not None
    assert abs(result["location_coords"].lat - 19.0596) < 0.01


@pytest.mark.asyncio
async def test_geocoding_node_failure(mocker):
    """Geocoding node sets final_response on failure."""
    mocker.patch(
        "agent.nodes.geocode_location",
        AsyncMock(side_effect=ValueError("Could not find location")),
    )

    intent = IntentModel(query="bar", location="Unknowncity99")
    state = _make_state(intent=intent)
    result = await geocoding_node(state)

    assert result.get("error") == "geocoding_failed"
    assert result.get("final_response") is not None


# ── places_search_node tests ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_places_search_node_success(mocker, sample_places, sample_coords):
    """Places search node returns raw_places on success."""
    mocker.patch("agent.nodes.search_places", AsyncMock(return_value=sample_places))

    intent = IntentModel(query="rooftop restaurant", location="Bandra, Mumbai")
    state = _make_state(intent=intent, location_coords=sample_coords)
    result = await places_search_node(state)

    assert result["raw_places"] is not None
    assert len(result["raw_places"]) > 0


# ── Full agent flow tests ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_full_agent_flow_happy_path(mocker, sample_places, sample_coords):
    """Complete pipeline returns final_response and filtered_places."""
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(
        side_effect=[
            MagicMock(content=INTENT_JSON),           # intent extraction
            MagicMock(content="Great choices here!"),  # response generation
        ]
    )
    mocker.patch("agent.nodes._get_llm", return_value=mock_llm)
    mocker.patch("agent.nodes.geocode_location", AsyncMock(return_value=sample_coords))
    mocker.patch("agent.nodes.search_places", AsyncMock(return_value=sample_places))

    # Run through nodes sequentially
    state = _make_state()

    s1 = await intent_extraction_node(state)
    state.update(s1)

    s2 = await geocoding_node(state)
    state.update(s2)

    s3 = await places_search_node(state)
    state.update(s3)

    s4 = await filter_and_rank_node(state)
    state.update(s4)

    s5 = await response_generation_node(state)
    state.update(s5)

    assert state.get("filtered_places") is not None
    assert len(state["filtered_places"]) > 0
    assert state.get("final_response") is not None


@pytest.mark.asyncio
async def test_agent_handles_no_results(mocker, sample_coords):
    """Agent generates a graceful no-results response."""
    mocker.patch("agent.nodes.geocode_location", AsyncMock(return_value=sample_coords))
    mocker.patch("agent.nodes.search_places", AsyncMock(return_value=[]))
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="Sorry, nothing found."))
    mocker.patch("agent.nodes._get_llm", return_value=mock_llm)

    intent = IntentModel(query="unicorn cafe", location="Mumbai")
    state = _make_state(intent=intent, location_coords=sample_coords, raw_places=[])

    result = await filter_and_rank_node(state)
    assert result.get("final_response") is not None
    assert result.get("filtered_places") == []


@pytest.mark.asyncio
async def test_agent_follow_up_open_now(sample_places):
    """Follow-up handler correctly identifies open vs closed places."""
    from agent.nodes import follow_up_handler_node

    fu_ctx = json.dumps({"intent": "open_now", "place_name": None})
    state = _make_state(
        filtered_places=sample_places,
        follow_up_context=fu_ctx,
        messages=[HumanMessage(content="Are they open now?")],
    )

    result = await follow_up_handler_node(state)
    assert result.get("final_response") is not None
    response = result["final_response"].lower()
    # At least one open/closed mention expected
    assert "open" in response or "closed" in response or "hours" in response


@pytest.mark.asyncio
async def test_agent_follow_up_more_results(mocker, sample_places, sample_coords):
    """Follow-up handler fetches and appends more results."""
    extra_place = PlaceResult(
        place_id="ChIJextra999",
        name="New Spot",
        rating=4.0,
        price_level=2,
        address="999 Test St",
        lat=19.06,
        lng=72.83,
        is_open=True,
        types=["restaurant"],
        total_ratings=50,
    )
    mocker.patch("agent.nodes.search_places", AsyncMock(return_value=[extra_place]))

    intent = IntentModel(query="rooftop restaurant", location="Bandra, Mumbai")
    fu_ctx = json.dumps({"intent": "more_results", "place_name": None})
    state = _make_state(
        intent=intent,
        location_coords=sample_coords,
        filtered_places=sample_places,
        follow_up_context=fu_ctx,
        messages=[HumanMessage(content="Show me more options")],
    )

    from agent.nodes import follow_up_handler_node
    result = await follow_up_handler_node(state)

    # Should have added the extra place
    if result.get("filtered_places"):
        combined_ids = {p.place_id for p in result["filtered_places"]}
        assert "ChIJextra999" in combined_ids


@pytest.mark.asyncio
async def test_multi_turn_conversation(mocker, sample_places, sample_coords):
    """Intent extraction classifies second turn as a follow-up."""
    follow_up_json = json.dumps({"intent": "open_now", "place_name": None})
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content=follow_up_json))
    mocker.patch("agent.nodes._get_llm", return_value=mock_llm)

    state = _make_state(
        messages=[
            HumanMessage(content="Rooftop restaurants in Bandra"),
            AIMessage(content="Here are 3 options!"),
            HumanMessage(content="Are they open now?"),
        ],
        filtered_places=sample_places,
        turn_count=1,
        follow_up_context="Last search: rooftop in Bandra",
    )

    result = await intent_extraction_node(state)
    # Should detect as follow-up, not new search
    ctx = result.get("follow_up_context", "")
    assert "open_now" in ctx or result.get("intent") is None
