"""
API request and response schemas (Pydantic v2).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── Request models ────────────────────────────────────────────────────────────

class UserLocation(BaseModel):
    """Optional GPS coordinates supplied by the client."""
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class ChatRequest(BaseModel):
    """Incoming chat message from the user."""
    message: str = Field(min_length=1, max_length=2000)
    session_id: str = Field(min_length=1, max_length=128)
    location: Optional[UserLocation] = None


# ── Response models ───────────────────────────────────────────────────────────

class PlaceResponse(BaseModel):
    """A single place returned in the chat response."""
    place_id: str
    name: str
    rating: float
    price_level: int
    price_symbol: str
    address: str
    lat: float
    lng: float
    photo_url: str
    is_open: Optional[bool]
    types: List[str]
    total_ratings: int
    distance_meters: Optional[float]
    maps_url: str
    directions_url: str
    phone: Optional[str] = None
    website: Optional[str] = None


class ChatResponse(BaseModel):
    """Response from the chat endpoint."""
    response: str
    places: List[PlaceResponse] = Field(default_factory=list)
    session_id: str
    follow_up: Optional[str] = None
    turn_count: int = 0


class SessionResponse(BaseModel):
    """Full session data returned by GET /session/{session_id}."""
    session_id: str
    messages: List[Dict[str, Any]]
    turn_count: int


class DeleteSessionResponse(BaseModel):
    """Confirmation for session deletion."""
    session_id: str
    status: str = "cleared"


class PlaceDetailResponse(BaseModel):
    """Detailed place info returned by GET /place/{place_id}."""
    place_id: str
    name: str
    phone: Optional[str]
    website: Optional[str]
    rating: float
    is_open: Optional[bool]
    weekday_text: List[str]
    reviews: List[Dict[str, Any]]


class HealthResponse(BaseModel):
    """Health-check response."""
    status: str
    version: str
    environment: str
    uptime_seconds: float
    dependencies: Dict[str, str]
