"""
Filter and ranking tool.

Applies budget, rating, and open-now filters to a list of PlaceResult objects,
then ranks survivors by a weighted relevance score.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from agent.state import PlaceResult

logger = logging.getLogger(__name__)

# ── Budget mapping ────────────────────────────────────────────────────────────
# budget string  →  max price_level integer
_BUDGET_CEILING: dict[str, int] = {
    "budget": 1,
    "moderate": 2,
    "expensive": 4,
}


# ── Public tool function ──────────────────────────────────────────────────────

async def filter_places(
    places: List[PlaceResult],
    budget: Optional[str] = None,
    min_rating: float = 3.5,
    open_now: Optional[bool] = None,
    user_lat: Optional[float] = None,
    user_lng: Optional[float] = None,
) -> List[PlaceResult]:
    """
    Filter and rank a list of PlaceResult objects based on user preferences.

    Args:
        places:    Raw list of PlaceResult objects to process.
        budget:    Optional budget level ('budget' | 'moderate' | 'expensive').
        min_rating: Minimum acceptable rating (default 3.5).
        open_now:  If True, only return currently open places.
        user_lat:  User latitude for distance-based ranking.
        user_lng:  User longitude for distance-based ranking.

    Returns:
        Filtered and ranked list of PlaceResult objects (best first).
    """
    if not places:
        return []

    filtered: List[PlaceResult] = []

    for place in places:
        # ── Rating filter ───────────────────────────────────────────────
        if place.rating > 0 and place.rating < min_rating:
            logger.debug("Skipping %r: rating %.1f < %.1f", place.name, place.rating, min_rating)
            continue

        # ── Budget filter ───────────────────────────────────────────────
        if budget:
            ceiling = _BUDGET_CEILING.get(budget.lower(), 4)
            if place.price_level > ceiling and place.price_level != 0:
                logger.debug(
                    "Skipping %r: price_level %d > %d",
                    place.name,
                    place.price_level,
                    ceiling,
                )
                continue

        # ── Open-now filter ─────────────────────────────────────────────
        if open_now is True and place.is_open is False:
            logger.debug("Skipping %r: not currently open", place.name)
            continue

        filtered.append(place)

    # ── Compute distances if user coordinates supplied ───────────────────
    if user_lat is not None and user_lng is not None:
        for place in filtered:
            place.distance_meters = place.calculate_distance(user_lat, user_lng)

    # ── Rank by weighted score ───────────────────────────────────────────
    max_distance = max(
        (p.distance_meters for p in filtered if p.distance_meters is not None),
        default=1.0,
    ) or 1.0

    def score(place: PlaceResult) -> float:
        rating_score = (place.rating / 5.0) if place.rating else 0.3
        if place.distance_meters is not None:
            distance_score = 1.0 - min(place.distance_meters / max_distance, 1.0)
        else:
            distance_score = 0.5
        # Penalise places with very few ratings
        popularity_boost = min(place.total_ratings / 500.0, 0.2)
        return 0.55 * rating_score + 0.35 * distance_score + 0.10 * popularity_boost

    ranked = sorted(filtered, key=score, reverse=True)
    logger.info(
        "filter_places: input=%d after_filter=%d returned=%d",
        len(places),
        len(filtered),
        len(ranked),
    )
    return ranked


# ── Convenience alias used by nodes ──────────────────────────────────────────
filter_and_rank_places = filter_places
