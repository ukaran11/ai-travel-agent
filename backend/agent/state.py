"""
State schema for the LangGraph travel agent.
Defines all Pydantic models and the TypedDict state.
"""
from __future__ import annotations

import math
import operator
from typing import Annotated, List, Optional

from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field
from typing_extensions import TypedDict


# ── Domain models ────────────────────────────────────────────────────────────

class IntentModel(BaseModel):
    """Structured intent extracted from a user message."""

    query: str = Field(description="Main search query, e.g. 'rooftop restaurant'")
    location: Optional[str] = Field(None, description="Location string, e.g. 'Bandra, Mumbai'")
    budget: Optional[str] = Field(
        None, description="Budget level: 'budget' | 'moderate' | 'expensive'"
    )
    cuisine_type: Optional[str] = Field(None, description="Cuisine type if mentioned")
    vibe: Optional[str] = Field(
        None, description="Atmosphere: 'romantic' | 'casual' | 'family' | 'business'"
    )
    party_size: Optional[int] = Field(None, description="Number of people")
    time_of_day: Optional[str] = Field(
        None, description="Time preference: 'breakfast' | 'lunch' | 'dinner' | 'evening'"
    )
    place_type: str = Field("restaurant", description="Google Places type to search")


class Coords(BaseModel):
    """Geographic coordinates with a formatted address."""

    lat: float = Field(description="Latitude")
    lng: float = Field(description="Longitude")
    formatted_address: str = Field("", description="Human-readable address")


class PlaceResult(BaseModel):
    """A single place returned from the Google Places API."""

    place_id: str
    name: str
    rating: float = 0.0
    price_level: int = 0          # 0=unknown, 1=inexpensive, 2=moderate, 3=expensive, 4=very_expensive
    address: str = ""
    lat: float = 0.0
    lng: float = 0.0
    photo_reference: Optional[str] = None
    is_open: Optional[bool] = None
    types: List[str] = Field(default_factory=list)
    total_ratings: int = 0
    distance_meters: Optional[float] = None
    phone: Optional[str] = None
    website: Optional[str] = None

    @property
    def maps_url(self) -> str:
        return f"https://www.google.com/maps/place/?q=place_id:{self.place_id}"

    @property
    def directions_url(self) -> str:
        return f"https://www.google.com/maps/dir/?api=1&destination_place_id={self.place_id}"

    @property
    def price_symbol(self) -> str:
        symbols = {0: "", 1: "₹", 2: "₹₹", 3: "₹₹₹", 4: "₹₹₹₹"}
        return symbols.get(self.price_level, "")

    def calculate_distance(self, user_lat: float, user_lng: float) -> float:
        """Return distance in metres using the Haversine formula."""
        R = 6_371_000  # Earth radius (m)
        φ1 = math.radians(self.lat)
        φ2 = math.radians(user_lat)
        Δφ = math.radians(user_lat - self.lat)
        Δλ = math.radians(user_lng - self.lng)
        a = math.sin(Δφ / 2) ** 2 + math.cos(φ1) * math.cos(φ2) * math.sin(Δλ / 2) ** 2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    def to_api_dict(self, api_key: str = "") -> dict:
        """Serialise for the API response, adding computed fields."""
        photo_url = ""
        if self.photo_reference and api_key:
            photo_url = (
                f"https://places.googleapis.com/v1/{self.photo_reference}"
                f"/media?maxWidthPx=400&key={api_key}"
            )
        return {
            "place_id": self.place_id,
            "name": self.name,
            "rating": self.rating,
            "price_level": self.price_level,
            "price_symbol": self.price_symbol,
            "address": self.address,
            "lat": self.lat,
            "lng": self.lng,
            "photo_url": photo_url,
            "is_open": self.is_open,
            "types": self.types,
            "total_ratings": self.total_ratings,
            "distance_meters": self.distance_meters,
            "maps_url": self.maps_url,
            "directions_url": self.directions_url,
            "phone": self.phone,
            "website": self.website,
        }


# ── LangGraph state ───────────────────────────────────────────────────────────

class TravelAgentState(TypedDict):
    """State carried through every node in the travel agent graph."""

    # Accumulated conversation history (operator.add → append-only)
    messages: Annotated[List[BaseMessage], operator.add]

    # Extracted intent for the current turn
    intent: Optional[IntentModel]

    # Resolved coordinates from the geocoding node
    location_coords: Optional[Coords]

    # Raw results from the Places API
    raw_places: Optional[List[PlaceResult]]

    # Filtered + ranked subset
    filtered_places: Optional[List[PlaceResult]]

    # Final human-readable response
    final_response: Optional[str]

    # JSON-encoded follow-up context (intent type, place name, etc.)
    follow_up_context: Optional[str]

    # Error code / message for routing decisions
    error: Optional[str]

    # Incremented on every graph invocation
    turn_count: int

    # Caller-supplied session identifier (= LangGraph thread_id)
    session_id: str
