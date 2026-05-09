"""
Pytest configuration and shared fixtures for the travel agent test suite.
"""
from __future__ import annotations

import sys
import os

# Ensure backend/ is on sys.path so all imports resolve correctly
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient

from agent.state import Coords, PlaceResult


# ── Sample data fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def sample_place() -> PlaceResult:
    return PlaceResult(
        place_id="ChIJtest1234",
        name="The Rooftop Lounge",
        rating=4.5,
        price_level=2,
        address="123 Bandra West, Mumbai 400050",
        lat=19.0596,
        lng=72.8295,
        photo_reference="places/ChIJtest1234/photos/PHOTO_REF",
        is_open=True,
        types=["restaurant", "bar"],
        total_ratings=350,
    )


@pytest.fixture
def sample_places(sample_place) -> list[PlaceResult]:
    return [
        sample_place,
        PlaceResult(
            place_id="ChIJtest5678",
            name="Sky Bar & Grill",
            rating=4.2,
            price_level=3,
            address="456 Juhu, Mumbai 400049",
            lat=19.0954,
            lng=72.8265,
            is_open=True,
            types=["restaurant"],
            total_ratings=200,
        ),
        PlaceResult(
            place_id="ChIJtest9999",
            name="Budget Bytes",
            rating=3.8,
            price_level=1,
            address="789 Andheri, Mumbai 400069",
            lat=19.1136,
            lng=72.8697,
            is_open=False,
            types=["restaurant"],
            total_ratings=120,
        ),
        PlaceResult(
            place_id="ChIJtest0001",
            name="Low Rated Spot",
            rating=2.9,
            price_level=1,
            address="101 Mumbai",
            lat=19.05,
            lng=72.82,
            is_open=True,
            types=["restaurant"],
            total_ratings=20,
        ),
    ]


@pytest.fixture
def sample_coords() -> Coords:
    return Coords(lat=19.0596, lng=72.8295, formatted_address="Bandra West, Mumbai")


@pytest.fixture
def geocode_response() -> dict:
    return {
        "status": "OK",
        "results": [
            {
                "formatted_address": "Bandra West, Mumbai, Maharashtra, India",
                "geometry": {
                    "location": {"lat": 19.0596, "lng": 72.8295}
                },
            }
        ],
    }


@pytest.fixture
def places_api_response(sample_place) -> dict:
    return {
        "places": [
            {
                "id": sample_place.place_id,
                "displayName": {"text": sample_place.name},
                "rating": sample_place.rating,
                "priceLevel": "PRICE_LEVEL_MODERATE",
                "formattedAddress": sample_place.address,
                "location": {"latitude": sample_place.lat, "longitude": sample_place.lng},
                "currentOpeningHours": {"openNow": True},
                "types": sample_place.types,
                "userRatingCount": sample_place.total_ratings,
                "photos": [{"name": sample_place.photo_reference}],
            }
        ]
    }


# ── FastAPI test clients ──────────────────────────────────────────────────────

@pytest.fixture
def client():
    """Synchronous test client (for simple request/response tests)."""
    from main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture
async def async_client():
    """Async test client for endpoints that need async."""
    from main import app
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac
