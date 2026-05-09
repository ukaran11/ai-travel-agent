"""
MCP-compatible HTTP tool server.

Exposes the four travel-agent tools over HTTP using a JSON-RPC 2.0
envelope, allowing any MCP client to interact with the tools
via the HTTP+SSE transport.

Routes are mounted at /mcp in main.py.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agent.state import PlaceResult
from mcp.tools.filter_tool import filter_places
from mcp.tools.geocoding_tool import geocode_location
from mcp.tools.places_tool import get_place_details, search_places

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mcp", tags=["MCP Tool Server"])


# ── JSON-RPC envelope models ──────────────────────────────────────────────────

class JsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: Optional[str] = None
    method: str
    params: Dict[str, Any] = Field(default_factory=dict)


class JsonRpcResponse(BaseModel):
    jsonrpc: str = "2.0"
    id: Optional[str] = None
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None


# ── Tool registry ─────────────────────────────────────────────────────────────

TOOL_DEFINITIONS = [
    {
        "name": "search_places",
        "description": (
            "Search for places (restaurants, cafes, attractions, etc.) near a "
            "geographic coordinate using the Google Places API."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "lat": {"type": "number", "description": "Latitude"},
                "lng": {"type": "number", "description": "Longitude"},
                "radius": {"type": "integer", "description": "Search radius (metres)", "default": 5000},
                "place_type": {"type": "string", "description": "Google Places type", "default": "restaurant"},
                "max_results": {"type": "integer", "description": "Max results (1–20)", "default": 20},
            },
            "required": ["query", "lat", "lng"],
        },
    },
    {
        "name": "get_place_details",
        "description": "Fetch detailed information (phone, website, reviews, hours) for a Google Place ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "place_id": {"type": "string", "description": "Google Place ID"},
            },
            "required": ["place_id"],
        },
    },
    {
        "name": "geocode_location",
        "description": "Convert a human-readable location string to geographic coordinates (lat/lng).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "location_string": {"type": "string", "description": "Location string, e.g. 'Bandra, Mumbai'"},
            },
            "required": ["location_string"],
        },
    },
    {
        "name": "filter_places",
        "description": "Filter and rank a list of places by budget, rating, and open-now status.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "places": {"type": "array", "description": "List of PlaceResult dicts"},
                "budget": {"type": "string", "description": "budget | moderate | expensive"},
                "min_rating": {"type": "number", "description": "Minimum rating (default 3.5)"},
                "open_now": {"type": "boolean", "description": "Only open places?"},
                "user_lat": {"type": "number"},
                "user_lng": {"type": "number"},
            },
            "required": ["places"],
        },
    },
]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/tools/list")
async def list_tools() -> Dict[str, Any]:
    """Return the list of available MCP tools and their schemas."""
    return {"tools": TOOL_DEFINITIONS}


@router.post("/tools/call", response_model=JsonRpcResponse)
async def call_tool(request: JsonRpcRequest) -> JsonRpcResponse:
    """
    Execute a named tool with the supplied parameters.

    Expects a JSON-RPC 2.0 envelope:
        {"jsonrpc":"2.0","method":"search_places","params":{...},"id":"1"}
    """
    try:
        result = await _dispatch(request.method, request.params)
        return JsonRpcResponse(jsonrpc="2.0", id=request.id, result=result)
    except ValueError as exc:
        logger.warning("Tool call validation error: %s", exc)
        return JsonRpcResponse(
            jsonrpc="2.0",
            id=request.id,
            error={"code": -32602, "message": str(exc)},
        )
    except Exception as exc:
        logger.exception("Tool call failed: method=%s", request.method)
        return JsonRpcResponse(
            jsonrpc="2.0",
            id=request.id,
            error={"code": -32603, "message": f"Internal error: {exc}"},
        )


async def _dispatch(method: str, params: Dict[str, Any]) -> Any:
    """Route a method name to the appropriate tool function."""
    if method == "search_places":
        places = await search_places(**params)
        return [p.model_dump() for p in places]

    if method == "get_place_details":
        place_id = params.get("place_id")
        if not place_id:
            raise ValueError("place_id is required")
        return await get_place_details(place_id)

    if method == "geocode_location":
        location_string = params.get("location_string")
        if not location_string:
            raise ValueError("location_string is required")
        coords = await geocode_location(location_string)
        return coords.model_dump()

    if method == "filter_places":
        raw = params.get("places", [])
        places = [PlaceResult(**p) if isinstance(p, dict) else p for p in raw]
        filtered = await filter_places(
            places=places,
            budget=params.get("budget"),
            min_rating=float(params.get("min_rating", 3.5)),
            open_now=params.get("open_now"),
            user_lat=params.get("user_lat"),
            user_lng=params.get("user_lng"),
        )
        return [p.model_dump() for p in filtered]

    raise HTTPException(status_code=404, detail=f"Unknown tool: {method}")
