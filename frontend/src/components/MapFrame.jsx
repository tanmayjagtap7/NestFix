export default function MapFrame({ address, lat, lng, className = "h-52" }) {
  const hasPoint = Number.isFinite(Number(lat)) && Number.isFinite(Number(lng));
  const src = hasPoint
    ? `https://www.openstreetmap.org/export/embed.html?bbox=${Number(lng) - 0.018}%2C${Number(lat) - 0.012}%2C${Number(lng) + 0.018}%2C${Number(lat) + 0.012}&layer=mapnik&marker=${lat}%2C${lng}`
    : `https://maps.google.com/maps?q=${encodeURIComponent(address || "")}&z=15&output=embed`;
  const openHref = hasPoint
    ? `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lng}#map=16/${lat}/${lng}`
    : `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(address || "")}`;

  return (
    <div className="overflow-hidden rounded-2xl border border-sand bg-sand/40">
      <iframe title={address ? `Map of ${address}` : "Map"} src={src} className={`w-full ${className}`} loading="lazy" />
      <a className="block px-3 py-2 text-xs underline" href={openHref} target="_blank" rel="noreferrer">
        Open this location
      </a>
    </div>
  );
}
