"""
Pre-canned mock responses for all external APIs.

These are used when USE_MOCKS=true in .env so the app runs fully locally
without any real Google or Gemini API keys.
"""
from __future__ import annotations

import json
import re
import random
from typing import Any, Dict, List, Optional

from agent.state import Coords, PlaceResult

# ── Mock places ───────────────────────────────────────────────────────────────

_MOCK_PLACES: List[PlaceResult] = [
    PlaceResult(
        place_id="ChIJmock_001",
        name="The Rooftop Bistro",
        rating=4.6,
        price_level=2,
        address="14 Hill Road, Bandra West, Mumbai 400050",
        lat=19.0596,
        lng=72.8295,
        is_open=True,
        types=["restaurant", "bar"],
        total_ratings=1240,
        phone="+91 22 2641 0000",
        website="https://rooftopbistro.example.com",
        photo_reference=None,
    ),
    PlaceResult(
        place_id="ChIJmock_002",
        name="Café Terraza",
        rating=4.3,
        price_level=1,
        address="22 Linking Road, Bandra West, Mumbai 400050",
        lat=19.0614,
        lng=72.8320,
        is_open=True,
        types=["cafe", "restaurant"],
        total_ratings=870,
        phone="+91 22 2640 1111",
        website="https://cafeterraza.example.com",
        photo_reference=None,
    ),
    PlaceResult(
        place_id="ChIJmock_003",
        name="Spice Garden",
        rating=4.7,
        price_level=3,
        address="8 Carter Road, Bandra West, Mumbai 400050",
        lat=19.0572,
        lng=72.8283,
        is_open=False,
        types=["restaurant"],
        total_ratings=2100,
        phone="+91 22 2645 2222",
        website="https://spicegarden.example.com",
        photo_reference=None,
    ),
    PlaceResult(
        place_id="ChIJmock_004",
        name="The Coastal Kitchen",
        rating=4.4,
        price_level=2,
        address="35 Pali Hill, Bandra West, Mumbai 400050",
        lat=19.0560,
        lng=72.8310,
        is_open=True,
        types=["restaurant", "seafood"],
        total_ratings=650,
        phone="+91 22 2648 3333",
        website="https://coastalkitchen.example.com",
        photo_reference=None,
    ),
    PlaceResult(
        place_id="ChIJmock_005",
        name="Green Leaf Vegan",
        rating=4.2,
        price_level=1,
        address="10 Mount Mary Road, Bandra West, Mumbai 400050",
        lat=19.0540,
        lng=72.8260,
        is_open=True,
        types=["restaurant", "vegan"],
        total_ratings=420,
        phone="+91 22 2641 4444",
        website="https://greenleafvegan.example.com",
        photo_reference=None,
    ),
]


# ── Mock geocoding ────────────────────────────────────────────────────────────

def mock_geocode(location_string: str) -> Coords:
    """Return plausible-ish coords for any location string."""
    # A few well-known cities for slightly better demo experience
    known: Dict[str, tuple] = {
        "mumbai": (19.0760, 72.8777, "Mumbai, Maharashtra, India"),
        "bandra": (19.0596, 72.8295, "Bandra West, Mumbai, Maharashtra, India"),
        "delhi": (28.6139, 77.2090, "New Delhi, Delhi, India"),
        "bangalore": (12.9716, 77.5946, "Bengaluru, Karnataka, India"),
        "bengaluru": (12.9716, 77.5946, "Bengaluru, Karnataka, India"),
        "pune": (18.5204, 73.8567, "Pune, Maharashtra, India"),
        "hyderabad": (17.3850, 78.4867, "Hyderabad, Telangana, India"),
        "london": (51.5074, -0.1278, "London, United Kingdom"),
        "paris": (48.8566, 2.3522, "Paris, France"),
        "new york": (40.7128, -74.0060, "New York, NY, USA"),
    }
    loc_lower = location_string.lower()
    for key, (lat, lng, addr) in known.items():
        if key in loc_lower:
            return Coords(lat=lat, lng=lng, formatted_address=addr)
    # Default fallback with slight random jitter
    return Coords(
        lat=19.0596 + random.uniform(-0.05, 0.05),
        lng=72.8295 + random.uniform(-0.05, 0.05),
        formatted_address=f"{location_string} (approximate)",
    )


# ── Mock LLM ─────────────────────────────────────────────────────────────────

def _make_intent_json(user_message: str) -> str:
    """Generate a plausible intent JSON from the user message (raw user text only)."""
    msg = user_message.lower()
    budget = "moderate"
    # Note: do NOT include "budget" here — it appears in the prompt template itself
    if any(w in msg for w in ("cheap", "affordable", "₹", "inexpensive", "under ₹500", "low cost")):
        budget = "budget"
    elif any(w in msg for w in ("expensive", "fine dining", "luxury", "upscale", "splurge")):
        budget = "expensive"

    place_type = "restaurant"
    if any(w in msg for w in ("cafe", "coffee", "café")):
        place_type = "cafe"
    elif any(w in msg for w in ("bar", "pub", "cocktail", "drink")):
        place_type = "bar"
    elif any(w in msg for w in ("hotel", "stay", "accommodation")):
        place_type = "hotel"

    cuisine = None
    for c in ("italian", "chinese", "indian", "mexican", "thai", "japanese", "french"):
        if c in msg:
            cuisine = c
            break

    vibe = None
    for v in ("romantic", "casual", "family", "rooftop", "outdoor", "cozy", "trendy"):
        if v in msg:
            vibe = v
            break

    # Try to extract location
    location = "Bandra West, Mumbai"
    for loc in ("bandra", "andheri", "juhu", "colaba", "lower parel", "powai",
                "indiranagar", "koramangala", "hauz khas", "south delhi",
                "connaught place", "cp ", "london", "paris", "new york"):
        if loc in msg:
            location = loc.strip().title()
            break

    return json.dumps({
        "query": user_message[:80],
        "location": location,
        "budget": budget,
        "cuisine_type": cuisine,
        "vibe": vibe,
        "party_size": None,
        "time_of_day": None,
        "place_type": place_type,
    }, ensure_ascii=False)


def _make_response_text(places: list, user_query: str) -> str:
    """Generate a friendly natural-language response listing mock places."""
    names = [p["name"] if isinstance(p, dict) else p.name for p in places[:3]]
    intro = f"Here are my top picks for **{user_query}**:\n\n"
    bullets = "\n".join(
        f"**{i+1}. {name}** — a great spot worth checking out!"
        for i, name in enumerate(names)
    )
    outro = (
        "\n\nWould you like more details on any of these? "
        "I can show hours, directions, or suggest alternatives!"
    )
    return intro + bullets + outro


def _make_follow_up_json(user_message: str) -> str:
    """Classify a follow-up message."""
    msg = user_message.lower()
    if any(w in msg for w in ("open", "hours", "closing", "close")):
        intent = "open_now"
    elif any(w in msg for w in ("more", "other", "different", "else", "another")):
        intent = "more_results"
    elif any(w in msg for w in ("detail", "info", "about", "tell me more")):
        intent = "place_details"
    elif any(w in msg for w in ("direction", "how to get", "navigate")):
        intent = "directions"
    elif any(w in msg for w in ("book", "reserv", "table")):
        intent = "book_table"
    else:
        intent = "new_search"
    return json.dumps({"intent": intent, "place_name": None})


class MockMessage:
    """Mimics AIMessage / BaseMessage .content attribute."""
    def __init__(self, content: str):
        self.content = content


def _extract_user_message(prompt_text: str) -> str:
    """
    Pull the actual user message out of the formatted INTENT_EXTRACTION_PROMPT.
    Looks for the 'User message:' sentinel written by INTENT_EXTRACTION_PROMPT.
    Falls back to the full prompt if not found.
    """
    import re as _re
    # Match "User message: <text>\n" or "User follow-up: <text>\n"
    m = _re.search(r"User (?:message|follow-up): (.+?)(?:\n|$)", prompt_text, _re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return prompt_text


class MockLLM:
    """
    A drop-in replacement for ChatGoogleGenerativeAI that returns canned responses.
    Inspects the prompt content to decide what kind of response to produce.
    """

    async def ainvoke(self, messages: list, **kwargs) -> MockMessage:
        # Collect all message content to identify the prompt type
        full_text = ""
        last_human = ""
        for msg in messages:
            if hasattr(msg, "content") and isinstance(msg.content, str):
                full_text += msg.content + "\n"
                last_human = msg.content  # last one wins

        # ── Detect prompt type by key sentinel strings ─────────────────
        # Intent extraction: INTENT_EXTRACTION_PROMPT has "User message: ..."
        if "User message:" in full_text and "JSON object with these exact keys" in full_text:
            user_msg = _extract_user_message(full_text)
            return MockMessage(_make_intent_json(user_msg))

        # Follow-up classification: FOLLOW_UP_PROMPT has "Previous places shown:"
        if "Previous places shown:" in full_text or "Classify the user" in full_text:
            user_msg = _extract_user_message(full_text)
            return MockMessage(_make_follow_up_json(user_msg))

        # Response generation: RESPONSE_GENERATION_PROMPT has "Top recommendations (JSON):"
        if "Top recommendations (JSON):" in full_text or "User's original request:" in full_text:
            try:
                import re as _re
                match = _re.search(r"\[.*?\]", full_text, _re.DOTALL)
                places = json.loads(match.group(0)) if match else []
            except Exception:
                places = []
            # Extract the query from "User's original request: <query>"
            q_match = re.search(r"User's original request: (.+?)(?:\n|$)", full_text)
            query = q_match.group(1).strip() if q_match else "your search"
            return MockMessage(_make_response_text(places, query))

        # No-results prompt
        if "nothing was found" in full_text or "no matches" in full_text:
            return MockMessage(
                "I'm sorry, I couldn't find any places matching your search. "
                "Try broadening your criteria or searching in a different area!"
            )

        # Generic fallback
        return MockMessage(
            "I found some great options for you! Would you like more details on any of them?"
        )
