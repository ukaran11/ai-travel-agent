import { useState } from "react";
import type { Place } from "../types";
import {
    formatDistance,
    formatOpenStatus,
    formatPriceLevel,
    formatStars,
    shortAddress,
} from "../utils/formatters";

interface RecommendationCardProps {
    place: Place;
}

/** Displays a single place recommendation with photo, details, and action buttons. */
export function RecommendationCard({ place }: RecommendationCardProps) {
    const [imgError, setImgError] = useState(false);
    const { text: openText, colorClass } = formatOpenStatus(place.is_open);

    const priceLabel = place.price_symbol || formatPriceLevel(place.price_level).split(" ")[0];

    return (
        <div className="bg-white rounded-2xl shadow-md overflow-hidden border border-gray-100 animate-fade-in hover:shadow-lg transition-shadow duration-200">
            {/* Photo */}
            {place.photo_url && !imgError ? (
                <div className="relative h-40 overflow-hidden">
                    <img
                        src={place.photo_url}
                        alt={place.name}
                        className="w-full h-full object-cover"
                        onError={() => setImgError(true)}
                        loading="lazy"
                    />
                    {/* Price badge */}
                    {priceLabel && (
                        <span className="absolute top-2 right-2 bg-black/60 text-white text-xs font-semibold px-2 py-0.5 rounded-full backdrop-blur-sm">
                            {priceLabel}
                        </span>
                    )}
                </div>
            ) : (
                <div className="h-24 bg-gradient-to-br from-sky-100 to-indigo-100 flex items-center justify-center text-4xl">
                    🍽️
                </div>
            )}

            {/* Details */}
            <div className="p-4">
                {/* Name + rating */}
                <div className="flex items-start justify-between gap-2 mb-1">
                    <h3 className="font-semibold text-gray-900 text-sm leading-tight line-clamp-2">
                        {place.name}
                    </h3>
                    <div className="flex-shrink-0 flex items-center gap-1 bg-amber-50 px-2 py-0.5 rounded-full">
                        <span className="text-amber-500 text-xs">★</span>
                        <span className="text-xs font-semibold text-gray-700">
                            {place.rating.toFixed(1)}
                        </span>
                        <span className="text-[10px] text-gray-400">
                            ({place.total_ratings.toLocaleString()})
                        </span>
                    </div>
                </div>

                {/* Stars */}
                <p className="text-amber-400 text-xs mb-1">{formatStars(place.rating)}</p>

                {/* Price level */}
                <p className="text-xs text-gray-500 mb-2">{formatPriceLevel(place.price_level)}</p>

                {/* Address */}
                <p className="text-xs text-gray-600 mb-1 truncate">📍 {shortAddress(place)}</p>

                {/* Distance + open status */}
                <div className="flex items-center gap-3 mb-3">
                    {place.distance_meters !== null && (
                        <span className="text-xs text-gray-500">
                            🚶 {formatDistance(place.distance_meters)}
                        </span>
                    )}
                    <span className={`text-xs font-medium ${colorClass}`}>{openText}</span>
                </div>

                {/* Action buttons */}
                <div className="flex gap-2">
                    <a
                        href={place.maps_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex-1 text-center text-xs font-medium py-2 px-3 bg-sky-500 text-white rounded-xl hover:bg-sky-600 active:bg-sky-700 transition-colors"
                    >
                        View on Maps
                    </a>
                    <a
                        href={place.directions_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex-1 text-center text-xs font-medium py-2 px-3 border border-sky-500 text-sky-600 rounded-xl hover:bg-sky-50 transition-colors"
                    >
                        Get Directions
                    </a>
                </div>

                {/* Phone / website */}
                {(place.phone || place.website) && (
                    <div className="mt-2 pt-2 border-t border-gray-100 flex gap-3 flex-wrap">
                        {place.phone && (
                            <a
                                href={`tel:${place.phone}`}
                                className="text-[11px] text-sky-600 hover:underline"
                            >
                                📞 {place.phone}
                            </a>
                        )}
                        {place.website && (
                            <a
                                href={place.website}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-[11px] text-sky-600 hover:underline"
                            >
                                🌐 Website
                            </a>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
}
