"""
Google Places API (New) tool.

Searches for places using the Places Text Search endpoint and returns
structured PlaceResult objects with retry/back-off on transient errors.
"""
from __future__ import annotations

import logging
import time
from typing import List, Optional

import httpx
from pydantic import BaseModel, Field
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from agent.state import PlaceResult

logger = logging.getLogger(__name__)

PLACES_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
PLACES_DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"

FIELD_MASK_SEARCH = (
    "places.id,places.displayName,places.rating,places.priceLevel,"
    "places.formattedAddress,places.location,places.photos,"
    "places.currentOpeningHours,places.types,places.userRatingCount"
)
FIELD_MASK_DETAILS = (
    "id,displayName,rating,priceLevel,formattedAddress,location,"
    "photos,currentOpeningHours,types,userRatingCount,"
    "internationalPhoneNumber,websiteUri,reviews"
)

# ── Input schema ─────────────────────────────────────────────────────────────

class PlacesSearchInput(BaseModel):
    """Input schema for search_places tool."""

    query: str = Field(description="Search query, e.g. 'rooftop restaurant'")
    lat: float = Field(description="Latitude of search centre")
    lng: float = Field(description="Longitude of search centre")
    radius: int = Field(default=5_000, ge=1, le=50_000, description="Search radius (metres)")
    place_type: str = Field(default="restaurant", description="Google Places type filter")
    max_results: int = Field(default=20, ge=1, le=20, description="Max results (1–20)")


# ── Helper ───────────────────────────────────────────────────────────────────

def _price_level_to_int(price_level_str: str) -> int:
    """Map the Places API (New) price-level enum string to an integer 0–4."""
    mapping = {
        "PRICE_LEVEL_FREE": 0,
        "PRICE_LEVEL_INEXPENSIVE": 1,
        "PRICE_LEVEL_MODERATE": 2,
        "PRICE_LEVEL_EXPENSIVE": 3,
        "PRICE_LEVEL_VERY_EXPENSIVE": 4,
    }
    return mapping.get(price_level_str, 0)


# ── Main tool functions ───────────────────────────────────────────────────────

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(httpx.HTTPStatusError),
    reraise=True,
)
async def search_places(
    query: str,
    lat: float,
    lng: float,
    radius: int = 5_000,
    place_type: str = "restaurant",
    max_results: int = 20,
    api_key: str = "",
) -> List[PlaceResult]:
    """
    Search for places using the Google Places API (New) Text Search endpoint.

    Args:
        query:       Natural-language search query (e.g. 'rooftop bar').
        lat:         Latitude of the search centre.
        lng:         Longitude of the search centre.
        radius:      Search radius in metres (1–50 000, default 5 000).
        place_type:  Optional Google Places type (e.g. 'restaurant', 'cafe').
        max_results: Maximum number of results to return (1–20).
        api_key:     Google Places API key (falls back to config if empty).

    Returns:
        List of PlaceResult objects, ordered by relevance.

    Raises:
        httpx.HTTPStatusError: On 4xx/5xx responses after retries.
    """
    from config import settings  # late import to avoid circular issues in tests

    if settings.use_mocks:
        from mcp.tools.mock_data import _MOCK_PLACES
        logger.info("MOCK search_places query=%r", query)
        return list(_MOCK_PLACES)

    key = api_key or settings.google_places_api_key
    if not key:
        logger.warning("google_places_api_key is not set; returning empty results")
        return []

    t0 = time.perf_counter()
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": key,
        "X-Goog-FieldMask": FIELD_MASK_SEARCH,
    }
    payload: dict = {
        "textQuery": query,
        "maxResultCount": min(max_results, 20),
        "locationBias": {
            "circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": float(radius),
            }
        },
        "rankPreference": "RELEVANCE",
    }
    if place_type and place_type not in ("restaurant",):
        # Only set includedType for non-default types to widen results
        payload["includedType"] = place_type

    logger.info("places.searchText query=%r lat=%.4f lng=%.4f radius=%d", query, lat, lng, radius)

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(PLACES_TEXT_SEARCH_URL, json=payload, headers=headers)
        response.raise_for_status()

    data = response.json()
    places_data = data.get("places", [])
    elapsed = time.perf_counter() - t0

    results: List[PlaceResult] = []
    for place in places_data[:max_results]:
        location = place.get("location", {})
        photo_ref: Optional[str] = None
        if place.get("photos"):
            photo_ref = place["photos"][0].get("name")

        results.append(
            PlaceResult(
                place_id=place.get("id", ""),
                name=place.get("displayName", {}).get("text", ""),
                rating=float(place.get("rating", 0.0)),
                price_level=_price_level_to_int(place.get("priceLevel", "")),
                address=place.get("formattedAddress", ""),
                lat=float(location.get("latitude", 0.0)),
                lng=float(location.get("longitude", 0.0)),
                photo_reference=photo_ref,
                is_open=place.get("currentOpeningHours", {}).get("openNow"),
                types=place.get("types", []),
                total_ratings=int(place.get("userRatingCount", 0)),
            )
        )

    logger.info("places.searchText found=%d elapsed=%.2fs", len(results), elapsed)
    return results


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(httpx.HTTPStatusError),
    reraise=True,
)
async def get_place_details(place_id: str, api_key: str = "") -> dict:
    """
    Fetch detailed information for a specific place by its place_id.

    Args:
        place_id: The Google Place ID (e.g. 'ChIJ...').
        api_key:  Google Places API key (falls back to config if empty).

    Returns:
        Dictionary with phone, website, full opening hours, reviews, etc.

    Raises:
        httpx.HTTPStatusError: On 4xx/5xx responses after retries.
    """
    from config import settings

    if settings.use_mocks:
        from mcp.tools.mock_data import _MOCK_PLACES
        logger.info("MOCK get_place_details place_id=%s", place_id)
        for place in _MOCK_PLACES:
            if place.place_id == place_id:
                return {
                    "place_id": place.place_id,
                    "name": place.name,
                    "phone": place.phone,
                    "website": place.website,
                    "rating": place.rating,
                    "price_level": place.price_level,
                    "address": place.address,
                    "opening_hours": [],
                    "is_open": place.is_open,
                    "maps_link": place.maps_url,
                    "summary": "",
                    "reviews": [],
                }
        return {}

    key = api_key or settings.google_places_api_key
    if not key:
        logger.warning("google_places_api_key is not set; returning empty details")
        return {}

    url = PLACES_DETAILS_URL.format(place_id=place_id)
    headers = {
        "X-Goog-Api-Key": key,
        "X-Goog-FieldMask": FIELD_MASK_DETAILS,
    }

    logger.info("places.details place_id=%s", place_id)

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()

    data = response.json()
    opening_hours = data.get("currentOpeningHours", {})
    reviews = data.get("reviews", [])

    return {
        "place_id": data.get("id", place_id),
        "name": data.get("displayName", {}).get("text", ""),
        "phone": data.get("internationalPhoneNumber"),
        "website": data.get("websiteUri"),
        "rating": data.get("rating", 0.0),
        "is_open": opening_hours.get("openNow"),
        "weekday_text": opening_hours.get("weekdayDescriptions", []),
        "reviews": [
            {
                "author": r.get("authorAttribution", {}).get("displayName", ""),
                "rating": r.get("rating", 0),
                "text": r.get("text", {}).get("text", ""),
            }
            for r in reviews[:3]
        ],
    }
