"""
Google Geocoding API tool.

Converts a human-readable location string into geographic coordinates,
handling ambiguous or unrecognised addresses gracefully.
"""
from __future__ import annotations

import logging
import time

import httpx
from pydantic import BaseModel, Field
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from agent.state import Coords

logger = logging.getLogger(__name__)

GEOCODING_URL = "https://maps.googleapis.com/maps/api/geocode/json"


# ── Input schema ─────────────────────────────────────────────────────────────

class GeocodingInput(BaseModel):
    """Input schema for geocode_location tool."""

    location_string: str = Field(
        description="Human-readable location, e.g. 'Bandra, Mumbai' or 'Connaught Place, Delhi'"
    )


# ── Main tool function ────────────────────────────────────────────────────────

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(httpx.HTTPStatusError),
    reraise=True,
)
async def geocode_location(location_string: str, api_key: str = "") -> Coords:
    """
    Convert a location string to geographic coordinates using the Google Geocoding API.

    When USE_MOCKS=true in config, returns pre-canned coordinates without any
    network call.

    Args:
        location_string: Human-readable location (e.g. 'Bandra, Mumbai').
        api_key:         Google Geocoding API key (falls back to config if empty).

    Returns:
        Coords object with lat, lng and formatted_address.

    Raises:
        ValueError:             If the location cannot be resolved.
        httpx.HTTPStatusError:  On 4xx/5xx API responses after retries.
    """
    from config import settings  # late import avoids circular deps in tests

    if settings.use_mocks:
        from mcp.tools.mock_data import mock_geocode
        logger.info("MOCK geocode location=%r", location_string)
        return mock_geocode(location_string)

    key = api_key or settings.google_geocoding_api_key or settings.google_places_api_key
    if not key:
        logger.warning("No geocoding API key set; using fallback stub")
        raise ValueError(f"No API key configured for geocoding '{location_string}'")

    t0 = time.perf_counter()
    params = {"address": location_string, "key": key}

    logger.info("geocode location=%r", location_string)

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(GEOCODING_URL, params=params)
        response.raise_for_status()

    data = response.json()
    status = data.get("status")
    elapsed = time.perf_counter() - t0

    if status == "ZERO_RESULTS":
        raise ValueError(f"Could not find location: '{location_string}'")

    if status != "OK":
        raise ValueError(f"Geocoding API error: {status} for '{location_string}'")

    result = data["results"][0]
    loc = result["geometry"]["location"]

    coords = Coords(
        lat=loc["lat"],
        lng=loc["lng"],
        formatted_address=result.get("formatted_address", location_string),
    )

    logger.info(
        "geocode resolved=%r lat=%.4f lng=%.4f elapsed=%.2fs",
        coords.formatted_address,
        coords.lat,
        coords.lng,
        elapsed,
    )
    return coords
