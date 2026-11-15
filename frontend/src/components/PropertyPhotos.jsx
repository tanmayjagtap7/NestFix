import { useEffect, useState } from "react";
import { getPropertyPhotos } from "../api";

function listingPhotos(listing) {
  const urls = [];
  const many = Array.isArray(listing?.image_urls) ? listing.image_urls : [];
  many.forEach((url) => {
    if (typeof url === "string" && url.startsWith("http") && !urls.includes(url)) urls.push(url);
  });
  if (typeof listing?.image_url === "string" && listing.image_url.startsWith("http") && !urls.includes(listing.image_url)) {
    urls.unshift(listing.image_url);
  }
  return urls.map((url, index) => ({ url, caption: index === 0 ? "Photo of the home" : "Another photo of the home" }));
}

export default function PropertyPhotos({ optionId, listing, compact = false }) {
  const [photos, setPhotos] = useState(() => listingPhotos(listing));
  const [pending, setPending] = useState(false);
  const [active, setActive] = useState(0);

  useEffect(() => {
    const ready = listingPhotos(listing);
    if (ready.length || !optionId) {
      setPhotos(ready);
      setPending(false);
      return undefined;
    }
    let stop = false;
    let timer;
    const load = () => {
      getPropertyPhotos(optionId)
        .then((data) => {
          if (stop) return;
          const next = (data.photos || []).filter((photo) => photo && typeof photo.url === "string");
          setPhotos(next);
          const still = Boolean(data.pending) && next.length === 0;
          setPending(still);
          if (still) timer = setTimeout(load, 4000);
        })
        .catch(() => {
          if (!stop) setPending(false);
        });
    };
    load();
    return () => {
      stop = true;
      clearTimeout(timer);
    };
  }, [optionId, listing]);

  if (!photos.length) {
    if (!pending) return null;
    return <p className={`text-sm text-ink/60 ${compact ? "py-6 text-center" : "px-2 py-8 text-center"}`}>Loading photos of this home.</p>;
  }

  const current = photos[Math.min(active, photos.length - 1)];
  return (
    <figure className={compact ? "" : "overflow-hidden"}>
      <img
        src={current.url}
        alt={current.caption || "Photo of this home"}
        className={`w-full object-cover ${compact ? "h-56" : "h-80"} bg-sand`}
      />
      <figcaption className="px-1 pt-2 text-xs text-ink/60">{current.caption}</figcaption>
      {photos.length > 1 && (
        <div className="mt-2 flex gap-2 overflow-x-auto">
          {photos.map((photo, index) => (
            <button
              key={photo.url}
              type="button"
              className={`h-14 w-20 shrink-0 overflow-hidden rounded-lg border ${index === active ? "border-clay" : "border-sand"}`}
              onClick={() => setActive(index)}
              aria-label={photo.caption || "Photo"}
            >
              <img src={photo.url} alt="" className="h-full w-full object-cover" />
            </button>
          ))}
        </div>
      )}
    </figure>
  );
}
