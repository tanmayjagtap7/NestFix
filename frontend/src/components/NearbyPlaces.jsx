import { useState } from "react";

const GROUPS = [
  ["schools", "Schools"],
  ["hospitals", "Hospitals"],
  ["transit", "Transit"],
];

function milesBetween(lat1, lng1, lat2, lng2) {
  const toRad = (value) => (value * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLng = toRad(lng2 - lng1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2;
  return 3958.8 * 2 * Math.asin(Math.min(1, Math.sqrt(a)));
}

function coordsFromUrl(url) {
  if (!url) return null;
  const match = String(url).match(/!3d(-?\d+(?:\.\d+)?)!4d(-?\d+(?:\.\d+)?)/);
  if (!match) return null;
  return { lat: Number(match[1]), lng: Number(match[2]) };
}

function readPlace(place, origin) {
  const note = String(place.note || "");
  const ratingMatch = note.match(/rat(?:ed|ing)\s+([0-9]+(?:\.[0-9]+)?)/i);
  const rating = ratingMatch ? Number(ratingMatch[1]) : null;
  const distanceMatch = note.match(/([0-9]+(?:\.[0-9]+)?)\s*mi\b/i);
  let distance = distanceMatch ? Number(distanceMatch[1]) : null;
  if (distance == null && origin?.lat != null && origin?.lng != null) {
    const coords = coordsFromUrl(place.url);
    if (coords) distance = milesBetween(origin.lat, origin.lng, coords.lat, coords.lng);
  }
  const address = note
    .split("·")
    .map((part) => part.trim())
    .find((part) => /\d/.test(part) && !/rat(?:ed|ing)|mi\b/i.test(part));
  return {
    ...place,
    rating: rating && rating > 0 ? rating : null,
    distance,
    address: address ? address.replace(/,?\s*United States$/i, "") : "",
  };
}

function distanceLabel(miles) {
  if (miles == null || Number.isNaN(miles)) return "";
  if (miles < 0.15) return "Nearby";
  return `${miles.toFixed(1)} mi`;
}

export default function NearbyPlaces({ amenities, lat, lng, detailed = false, className = "" }) {
  const origin = lat != null && lng != null ? { lat: Number(lat), lng: Number(lng) } : null;
  const groups = GROUPS.map(([key, label]) => {
    const places = (amenities?.[key] || [])
      .map((place) => readPlace(place, origin))
      .sort((a, b) => (a.distance ?? 999) - (b.distance ?? 999));
    return [label, places];
  }).filter(([, places]) => places.length);

  const [tab, setTab] = useState(groups[0]?.[0] || "Schools");
  if (!groups.length) return null;
  const activeLabel = groups.some(([label]) => label === tab) ? tab : groups[0][0];
  const places = groups.find(([label]) => label === activeLabel)[1];
  const shown = detailed ? places : places.slice(0, 3);

  return (
    <section className={className}>
      <div className="flex gap-1" role="tablist">
        {groups.map(([label]) => (
          <button
            key={label}
            type="button"
            role="tab"
            aria-selected={label === activeLabel}
            className={`nearby-tab rounded-full px-2.5 py-1 text-xs ${label === activeLabel ? "is-active" : ""}`}
            onClick={() => setTab(label)}
          >
            {label}
          </button>
        ))}
      </div>
      <ul className="mt-2">
        {shown.map((place) => (
          <li key={place.name} className="border-b border-sand py-2 last:border-b-0">
            <div className="flex items-start justify-between gap-3">
              {detailed && place.url ? (
                <a className="text-sm font-medium leading-snug hover:underline" href={place.url} target="_blank" rel="noreferrer">
                  {place.name}
                </a>
              ) : (
                <p className="text-sm font-medium leading-snug">{place.name}</p>
              )}
              {distanceLabel(place.distance) && (
                <span className="place-miles shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium">
                  {distanceLabel(place.distance)}
                </span>
              )}
            </div>
            {detailed && place.rating != null && (
              <p className="mt-1 text-xs font-medium text-amber-700">{place.rating.toFixed(1)} / 5</p>
            )}
            {detailed && place.address && <p className="mt-1 text-xs leading-snug text-ink/55">{place.address}</p>}
          </li>
        ))}
      </ul>
    </section>
  );
}
