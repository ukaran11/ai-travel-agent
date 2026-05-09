"""
LangGraph agent graph definition.

Compiles the StateGraph with all nodes and conditional routing.
Uses MemorySaver for multi-turn session persistence.
"""
from __future__ import annotations

import logging

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from agent.nodes import (
    filter_and_rank_node,
    follow_up_handler_node,
    geocoding_node,
    intent_extraction_node,
    places_search_node,
    response_generation_node,
)
from agent.state import TravelAgentState

logger = logging.getLogger(__name__)


# ── Routing functions ─────────────────────────────────────────────────────────

def _route_after_intent(state: TravelAgentState) -> str:
    """
    After intent extraction decide the next step:
    - "end"       → missing location or extraction error (early response set)
    - "follow_up" → follow-up question on existing results
    - "geocoding" → fresh search pipeline
    """
    if state.get("final_response"):
        return "end"
    if state.get("follow_up_context") and state.get("filtered_places"):
        return "follow_up"
    return "geocoding"


def _route_after_geocoding(state: TravelAgentState) -> str:
    """After geocoding, check for errors before continuing."""
    if state.get("final_response"):
        return "end"
    return "places_search"


def _route_after_places(state: TravelAgentState) -> str:
    """After places search, check for errors before filtering."""
    if state.get("final_response"):
        return "end"
    return "filter_and_rank"


def _route_after_filter(state: TravelAgentState) -> str:
    """After filtering, always go to response generation."""
    return "response_generation"


# ── Graph builder ─────────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    """Construct and return the compiled LangGraph StateGraph."""
    workflow = StateGraph(TravelAgentState)

    # Register nodes
    workflow.add_node("intent_extraction", intent_extraction_node)
    workflow.add_node("geocoding", geocoding_node)
    workflow.add_node("places_search", places_search_node)
    workflow.add_node("filter_and_rank", filter_and_rank_node)
    workflow.add_node("response_generation", response_generation_node)
    workflow.add_node("follow_up_handler", follow_up_handler_node)

    # Entry point
    workflow.add_edge(START, "intent_extraction")

    # Conditional routing from intent extraction
    workflow.add_conditional_edges(
        "intent_extraction",
        _route_after_intent,
        {
            "end": END,
            "follow_up": "follow_up_handler",
            "geocoding": "geocoding",
        },
    )

    # Conditional routing from geocoding
    workflow.add_conditional_edges(
        "geocoding",
        _route_after_geocoding,
        {
            "end": END,
            "places_search": "places_search",
        },
    )

    # Conditional routing from places search
    workflow.add_conditional_edges(
        "places_search",
        _route_after_places,
        {
            "end": END,
            "filter_and_rank": "filter_and_rank",
        },
    )

    # Linear edges for the rest of the pipeline
    workflow.add_edge("filter_and_rank", "response_generation")
    workflow.add_edge("response_generation", END)
    workflow.add_edge("follow_up_handler", END)

    return workflow


# ── Singleton compiled graph ──────────────────────────────────────────────────
# MemorySaver persists conversation state across invocations within the same process.
_checkpointer = MemorySaver()
_workflow = build_graph()
travel_agent = _workflow.compile(checkpointer=_checkpointer)

logger.info("Travel agent graph compiled successfully")
