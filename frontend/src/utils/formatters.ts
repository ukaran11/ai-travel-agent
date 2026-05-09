import type { Place } from "../types";

/** Return a star string, e.g. "★★★★☆" for rating 4.2 */
export function formatStars(rating: number): string {
    const full = Math.floor(rating);
    const half = rating - full >= 0.5 ? 1 : 0;
    const empty = 5 - full - half;
    return "★".repeat(full) + (half ? "½" : "") + "☆".repeat(empty);
}

/** Format a distance number (metres) to a readable string. */
export function formatDistance(metres: number | null): string {
    if (metres === null) return "";
    if (metres < 1000) return `${Math.round(metres)} m`;
    return `${(metres / 1000).toFixed(1)} km`;
}

/** Return a human-readable price label from price_level integer. */
export function formatPriceLevel(level: number): string {
    const labels: Record<number, string> = {
        0: "Price unknown",
        1: "₹ Inexpensive",
        2: "₹₹ Moderate",
        3: "₹₹₹ Expensive",
        4: "₹₹₹₹ Very expensive",
    };
    return labels[level] ?? "₹";
}

/** Return open/closed badge text and colour class. */
export function formatOpenStatus(isOpen: boolean | null): {
    text: string;
    colorClass: string;
} {
    if (isOpen === true) return { text: "Open now", colorClass: "text-green-600" };
    if (isOpen === false) return { text: "Closed", colorClass: "text-red-500" };
    return { text: "Hours unknown", colorClass: "text-gray-400" };
}

/** Derive a short type label from the raw types array. */
export function formatPlaceType(types: string[]): string {
    const prioritised = [
        "restaurant", "cafe", "bar", "bakery", "meal_takeaway",
        "tourist_attraction", "museum", "hotel", "lodging",
        "night_club", "spa", "gym",
    ];
    for (const t of prioritised) {
        if (types.includes(t)) return t.replace(/_/g, " ");
    }
    return types[0]?.replace(/_/g, " ") ?? "place";
}

/** Format a timestamp as "HH:MM". */
export function formatTime(date: Date): string {
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

/** Build the Google Places photo URL from the resource name. */
export function buildPhotoUrl(
    photoReference: string,
    apiKey: string,
    maxWidth = 400,
): string {
    if (!photoReference || !apiKey) return "";
    return `https://places.googleapis.com/v1/${photoReference}/media?maxWidthPx=${maxWidth}&key=${apiKey}`;
}

/** Return the first line of an address (street + neighbourhood). */
export function shortAddress(place: Place): string {
    const parts = place.address.split(",");
    return parts.slice(0, 2).join(",").trim();
}
