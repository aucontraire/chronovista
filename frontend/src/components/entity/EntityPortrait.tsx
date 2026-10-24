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

import { useId, useState } from "react";
import { entityImageUrl } from "../../api/entityMentions";
import type {
  EntityImageState,
  EntityPropertyValue,
} from "../../api/entityMentions";
import {
  useRemoveEntityImage,
  useSetEntityImageSource,
  useUploadEntityImage,
} from "../../hooks/useEntityImage";

export interface EntityPortraitProps {
  /** UUID of the named entity — used to build the image proxy URL. */
  entityId: string;
  /** The entity's current display name — used as alt text and in the enlarge link's label. */
  canonicalName: string;
  /** The `image` enrichment property block, if any (`enrichment.properties.image`). */
  imageBlock?: EntityPropertyValue;
  /** Manual/Wikidata image state (`entity.image`); `version` is the cache-buster. */
  image?: EntityImageState;
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

const FOCUS_RING =
  "focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2";

function UploadControl({
  entityId,
  hasManual,
  onAnnounce,
}: {
  entityId: string;
  hasManual: boolean;
  onAnnounce: (message: string) => void;
}) {
  const inputId = useId();
  const statusId = useId();
  const upload = useUploadEntityImage(entityId);

  const onChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file)
      upload.mutate(file, {
        onSuccess: () => onAnnounce("Portrait uploaded."),
      });
    e.target.value = "";
  };

  return (
    <div className="mt-2 text-sm">
      <label
        htmlFor={inputId}
        className="block text-slate-600 font-medium mb-1"
      >
        {hasManual ? "Replace portrait" : "Upload portrait"}
      </label>
      <input
        id={inputId}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        onChange={onChange}
        disabled={upload.isPending}
        aria-describedby={statusId}
        className="block w-full text-xs text-slate-600 file:mr-2 file:rounded-md file:border-0 file:bg-slate-100 file:px-2 file:py-1 file:text-slate-700 hover:file:bg-slate-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2"
      />
      <p id={statusId} className="mt-1 text-xs text-slate-500">
        JPEG, PNG or WebP, up to 10 MB.
      </p>
      {upload.isPending ? (
        <p role="status" className="text-xs text-slate-500">
          Uploading portrait...
        </p>
      ) : null}
      {upload.isError ? (
        <p role="alert" className="text-xs text-red-600">
          {upload.error.message || "Upload failed."}
        </p>
      ) : null}
    </div>
  );
}

function SourceToggle({
  entityId,
  source,
  onAnnounce,
}: {
  entityId: string;
  source: EntityImageState["source"];
  onAnnounce: (message: string) => void;
}) {
  const setSource = useSetEntityImageSource(entityId);
  const options: { value: EntityImageState["source"]; label: string }[] = [
    { value: "manual", label: "Your image" },
    { value: "wikidata", label: "Wikidata image" },
  ];

  return (
    <div
      role="group"
      aria-label="Portrait source"
      className="mt-2 flex gap-1 text-xs"
    >
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          aria-pressed={source === o.value}
          disabled={setSource.isPending}
          onClick={() => {
            if (source === o.value) return;
            setSource.mutate(o.value, {
              onSuccess: () => onAnnounce(`Now showing ${o.label}.`),
            });
          }}
          className={`rounded-md border px-2 py-1 ${FOCUS_RING} ${
            source === o.value
              ? "border-indigo-600 bg-indigo-600 text-white"
              : "border-slate-300 bg-white text-slate-700 hover:bg-slate-100"
          }`}
        >
          {o.label}
        </button>
      ))}
      {setSource.isError ? (
        <p role="alert" className="basis-full text-red-600">
          {setSource.error.message || "Could not switch the portrait source."}
        </p>
      ) : null}
    </div>
  );
}

function RemoveControl({
  entityId,
  onAnnounce,
}: {
  entityId: string;
  onAnnounce: (message: string) => void;
}) {
  const remove = useRemoveEntityImage(entityId);
  return (
    <div className="mt-2 text-xs">
      <button
        type="button"
        disabled={remove.isPending}
        onClick={() =>
          remove.mutate(undefined, {
            onSuccess: () => onAnnounce("Your portrait was removed."),
          })
        }
        className={`rounded-md border border-slate-300 bg-white px-2 py-1 text-slate-700 hover:bg-slate-100 ${FOCUS_RING}`}
      >
        Remove portrait
      </button>
      {remove.isError ? (
        <p role="alert" className="mt-1 text-red-600">
          {remove.error.message || "Could not remove the portrait."}
        </p>
      ) : null}
    </div>
  );
}

export function EntityPortrait({
  entityId,
  canonicalName,
  imageBlock,
  image,
}: EntityPortraitProps) {
  const [loadFailed, setLoadFailed] = useState(false);
  const [announcement, setAnnouncement] = useState("");
  const hasImageValue =
    Boolean(imageBlock?.values?.[0]) || Boolean(image?.has_manual);
  const hasImage = hasImageValue && !loadFailed;
  const version = image?.version ?? imageBlock?.set_at;
  const src = hasImage ? entityImageUrl(entityId, version ?? undefined) : "";

  return (
    <div className="w-40 sm:w-48 flex-shrink-0">
      {hasImage ? (
        <a
          href={src}
          target="_blank"
          rel="noopener"
          aria-label={`Open full-size portrait of ${canonicalName}`}
          className={`${SIZE_CLASSES} block rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2`}
        >
          <img
            src={src}
            alt={canonicalName}
            className="w-full h-full rounded-lg object-cover border border-slate-200 hover:opacity-90 transition-opacity"
            onError={() => setLoadFailed(true)}
          />
        </a>
      ) : (
        <PortraitPlaceholder />
      )}
      <UploadControl
        entityId={entityId}
        hasManual={Boolean(image?.has_manual)}
        onAnnounce={setAnnouncement}
      />
      {image?.has_manual && image.has_wikidata ? (
        <SourceToggle
          entityId={entityId}
          source={image.source}
          onAnnounce={setAnnouncement}
        />
      ) : null}
      {image?.has_manual ? (
        <RemoveControl entityId={entityId} onAnnounce={setAnnouncement} />
      ) : null}
      {announcement ? (
        <p role="status" className="sr-only">
          {announcement}
        </p>
      ) : null}
    </div>
  );
}
