/**
 * EntityPortrait — the entity's portrait image shown in the entity detail
 * page header, to the left of the name/description/action controls.
 *
 * Renders the image fetched from the entity image proxy (`entityImageUrl`)
 * when an `image` enrichment property is present, with a click-to-enlarge
 * link that opens the full-size image in a new tab. Falls back to a neutral
 * placeholder — at the same size, so the header layout never shifts — when
 * there is no image property, or the image fails to load. The proxy serves
 * the same full-resolution image at this URL, so no separate endpoint is
 * needed for the enlarged view.
 */

import { useState } from "react";
import { entityImageUrl } from "../../api/entityMentions";
import type { EntityPropertyValue } from "../../api/entityMentions";

export interface EntityPortraitProps {
  /** UUID of the named entity — used to build the image proxy URL. */
  entityId: string;
  /** The entity's current display name — used as alt text and in the enlarge link's label. */
  canonicalName: string;
  /** The `image` enrichment property block, if any (`enrichment.properties.image`). */
  imageBlock?: EntityPropertyValue;
}

/** Shared size classes so the image and its placeholder always match. */
const SIZE_CLASSES = "w-40 h-40 sm:w-48 sm:h-48";

function PortraitPlaceholder() {
  return (
    <div
      className={`${SIZE_CLASSES} flex-shrink-0 flex items-center justify-center rounded-lg border border-slate-200 bg-slate-100 text-slate-300`}
      role="img"
      aria-label="No portrait available"
    >
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 24 24"
        fill="currentColor"
        className="w-16 h-16 sm:w-20 sm:h-20"
        aria-hidden="true"
      >
        <path
          fillRule="evenodd"
          d="M18.685 19.097A9.723 9.723 0 0 0 21.75 12c0-5.385-4.365-9.75-9.75-9.75S2.25 6.615 2.25 12a9.723 9.723 0 0 0 3.065 7.097A9.716 9.716 0 0 0 12 21.75a9.716 9.716 0 0 0 6.685-2.653Zm-12.54-1.285A7.486 7.486 0 0 1 12 15a7.486 7.486 0 0 1 5.855 2.812A8.224 8.224 0 0 1 12 20.25a8.224 8.224 0 0 1-5.855-2.438ZM15.75 9a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0Z"
          clipRule="evenodd"
        />
      </svg>
    </div>
  );
}

export function EntityPortrait({ entityId, canonicalName, imageBlock }: EntityPortraitProps) {
  const [loadFailed, setLoadFailed] = useState(false);
  const hasImageValue = Boolean(imageBlock?.values?.[0]);
  const hasImage = hasImageValue && !loadFailed;

  if (!hasImage) {
    return <PortraitPlaceholder />;
  }

  const src = entityImageUrl(entityId, imageBlock?.set_at);

  return (
    <a
      href={src}
      target="_blank"
      rel="noopener"
      aria-label={`Open full-size portrait of ${canonicalName}`}
      className={`${SIZE_CLASSES} flex-shrink-0 block rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2`}
    >
      <img
        src={src}
        alt={canonicalName}
        className="w-full h-full rounded-lg object-cover border border-slate-200 hover:opacity-90 transition-opacity"
        onError={() => setLoadFailed(true)}
      />
    </a>
  );
}
