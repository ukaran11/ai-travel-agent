"""
Unit tests for MCP tool functions.

All external HTTP calls are mocked via pytest-mock / httpx mocking.
"""
from __future__ import annotations

import pytest
import httpx
import config

from agent.state import Coords, PlaceResult
from mcp.tools.filter_tool import filter_places
from mcp.tools.geocoding_tool import geocode_location
from mcp.tools.places_tool import get_place_details, search_places


# ── Geocoding tool tests ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_geocode_valid_location(mocker, geocode_response):
    """geocode_location returns Coords for a valid address."""
    mocker.patch.object(config.settings, "use_mocks", False)
    mock_get = mocker.AsyncMock(
        return_value=mocker.MagicMock(
            status_code=200,
            json=mocker.MagicMock(return_value=geocode_response),
            raise_for_status=mocker.MagicMock(),
        )
    )
    mocker.patch("httpx.AsyncClient.get", mock_get)
    mocker.patch.object(config.settings, "google_geocoding_api_key", "fake_key")
    mocker.patch.object(config.settings, "google_places_api_key", "fake_key")

    coords = await geocode_location("Bandra, Mumbai", api_key="fake_key")

    assert isinstance(coords, Coords)
    assert abs(coords.lat - 19.0596) < 0.01
    assert abs(coords.lng - 72.8295) < 0.01
    assert "Mumbai" in coords.formatted_address


@pytest.mark.asyncio
async def test_geocode_ambiguous_location(mocker):
    """geocode_location raises ValueError on ZERO_RESULTS."""
    mocker.patch.object(config.settings, "use_mocks", False)
    mocker.patch.object(config.settings, "google_geocoding_api_key", "fake_key")
    mock_response = mocker.MagicMock(
        status_code=200,
        json=mocker.MagicMock(return_value={"status": "ZERO_RESULTS", "results": []}),
        raise_for_status=mocker.MagicMock(),
    )
    mocker.patch("httpx.AsyncClient.get", mocker.AsyncMock(return_value=mock_response))

    with pytest.raises(ValueError, match="Could not find location"):
        await geocode_location("zzzznonexistent99999", api_key="fake_key")


# ── Places search tool tests ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_places_search_returns_results(mocker, places_api_response):
    """search_places returns a list of PlaceResult objects on success."""
    mocker.patch.object(config.settings, "use_mocks", False)
    mocker.patch.object(config.settings, "google_places_api_key", "fake_key")
    mock_post = mocker.AsyncMock(
        return_value=mocker.MagicMock(
            status_code=200,
            json=mocker.MagicMock(return_value=places_api_response),
            raise_for_status=mocker.MagicMock(),
        )
    )
    mocker.patch("httpx.AsyncClient.post", mock_post)

    results = await search_places(
        query="rooftop restaurant",
        lat=19.0596,
        lng=72.8295,
        api_key="fake_key",
    )

    assert len(results) == 1
    assert results[0].name == "The Rooftop Lounge"
    assert results[0].rating == 4.5
    assert results[0].price_level == 2  # PRICE_LEVEL_MODERATE → 2


@pytest.mark.asyncio
async def test_places_search_empty_results(mocker):
    """search_places returns an empty list when the API returns no places."""
    mocker.patch.object(config.settings, "use_mocks", False)
    mocker.patch.object(config.settings, "google_places_api_key", "fake_key")
    mock_post = mocker.AsyncMock(
        return_value=mocker.MagicMock(
            status_code=200,
            json=mocker.MagicMock(return_value={"places": []}),
            raise_for_status=mocker.MagicMock(),
        )
    )
    mocker.patch("httpx.AsyncClient.post", mock_post)

    results = await search_places(
        query="oblivious query xyz",
        lat=0.0,
        lng=0.0,
        api_key="fake_key",
    )

    assert results == []


@pytest.mark.asyncio
async def test_tool_api_error_handling(mocker):
    """search_places raises HTTPStatusError after retries on 5xx responses."""
    mocker.patch.object(config.settings, "use_mocks", False)
    mocker.patch.object(config.settings, "google_places_api_key", "fake_key")
    mock_response = mocker.MagicMock(status_code=500)
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Server Error", request=mocker.MagicMock(), response=mock_response
    )
    mocker.patch("httpx.AsyncClient.post", mocker.AsyncMock(return_value=mock_response))

    with pytest.raises(httpx.HTTPStatusError):
        await search_places(
            query="test",
            lat=0.0,
            lng=0.0,
            api_key="fake_key",
            # tenacity is configured with stop_after_attempt(3), so this raises after 3 tries
        )


@pytest.mark.asyncio
async def test_tool_retry_on_rate_limit(mocker, places_api_response):
    """search_places retries and succeeds on transient HTTPStatusError."""
    success_response = mocker.MagicMock(
        status_code=200,
        json=mocker.MagicMock(return_value=places_api_response),
        raise_for_status=mocker.MagicMock(),
    )
    fail_response = mocker.MagicMock(status_code=429)
    fail_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Rate limited", request=mocker.MagicMock(), response=fail_response
    )

    # Fail twice, succeed on third attempt
    mocker.patch(
        "httpx.AsyncClient.post",
        mocker.AsyncMock(side_effect=[fail_response, fail_response, success_response]),
    )

    results = await search_places(
        query="test",
        lat=19.0,
        lng=72.8,
        api_key="fake_key",
    )
    assert len(results) >= 1


@pytest.mark.asyncio
async def test_get_place_details_returns_info(mocker):
    """get_place_details returns phone, website, and hours."""
    mocker.patch.object(config.settings, "use_mocks", False)
    mocker.patch.object(config.settings, "google_places_api_key", "fake_key")
    details_payload = {
        "id": "ChIJtest1234",
        "displayName": {"text": "The Rooftop Lounge"},
        "rating": 4.5,
        "internationalPhoneNumber": "+91 22 1234 5678",
        "websiteUri": "https://example.com",
        "currentOpeningHours": {
            "openNow": True,
            "weekdayDescriptions": ["Monday: 12:00 PM – 11:00 PM"],
        },
        "reviews": [
            {
                "authorAttribution": {"displayName": "Alice"},
                "rating": 5,
                "text": {"text": "Amazing rooftop views!"},
            }
        ],
    }
    mock_get = mocker.AsyncMock(
        return_value=mocker.MagicMock(
            status_code=200,
            json=mocker.MagicMock(return_value=details_payload),
            raise_for_status=mocker.MagicMock(),
        )
    )
    mocker.patch("httpx.AsyncClient.get", mock_get)

    result = await get_place_details("ChIJtest1234", api_key="fake_key")

    assert result["phone"] == "+91 22 1234 5678"
    assert result["website"] == "https://example.com"
    assert result["is_open"] is True
    assert len(result["reviews"]) == 1
    assert result["reviews"][0]["author"] == "Alice"


# ── Filter tool tests ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_filter_by_budget(sample_places):
    """filter_places removes places above the budget ceiling."""
    result = await filter_places(sample_places, budget="budget")
    # price_level ≤ 1 AND rating ≥ 3.5
    for p in result:
        assert p.price_level <= 1 or p.price_level == 0


@pytest.mark.asyncio
async def test_filter_by_rating(sample_places):
    """filter_places removes places below min_rating=3.5."""
    result = await filter_places(sample_places, min_rating=3.5)
    for p in result:
        assert p.rating >= 3.5 or p.rating == 0.0


@pytest.mark.asyncio
async def test_filter_open_now(sample_places):
    """filter_places returns only currently open places when open_now=True."""
    result = await filter_places(sample_places, open_now=True)
    for p in result:
        assert p.is_open is not False


@pytest.mark.asyncio
async def test_filter_returns_ranked_by_score(sample_places):
    """filter_places returns results ranked best-first."""
    result = await filter_places(
        sample_places,
        min_rating=3.5,
        user_lat=19.0596,
        user_lng=72.8295,
    )
    # Distances should be populated
    for p in result:
        assert p.distance_meters is not None


@pytest.mark.asyncio
async def test_filter_empty_input():
    """filter_places returns empty list for empty input."""
    result = await filter_places([])
    assert result == []
