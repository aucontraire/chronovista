/**
 * EvidenceItem — one VIDEO where the two entities are mentioned together (Feature 114,
 * FR-003/004/007/009). Co-mention only: it never asserts a relationship.
 *
 * The row shows the video's strongest co-mention (its `representative` — minimum separation across
 * the video's co-occurring transcript languages). When the pair also co-occurs in the video's OTHER
 * languages, a native `<details>` expander reveals them — where a surface form that differs by
 * language (a different match, a different false-positive risk) stays visible instead of hidden.
 */

import { Link } from "react-router-dom";

import type {
  EvidenceItem as EvidenceItemData,
  EvidenceVariant,
} from "../../api/graph";
import { formatTimestamp } from "../../utils/formatTimestamp";
import { buildVideoDeepLink } from "../../utils/videoDeepLink";
import { HighlightedText } from "../HighlightedText";

interface EvidenceItemProps {
  item: EvidenceItemData;
}

function separationLabel(variant: EvidenceVariant): string {
  const n = variant.separation_segments;
  if (n <= 0) return "in the same passage";
  const segs = `~${n} ${n === 1 ? "segment" : "segments"} apart`;
  const secs = Math.round(variant.separation_seconds);
  return secs > 0 ? `${segs} (about ${secs}s)` : segs;
}

/** The passages of one (video, language) variant, each a per-passage deep link. Shared by the
 *  representative and every expander row so highlighting + linking behave identically. */
function VariantBody({
  videoId,
  videoTitle,
  variant,
}: {
  videoId: string;
  videoTitle: string;
  variant: EvidenceVariant;
}) {
  const terms = [
    variant.mention_a.mention_text,
    variant.mention_b.mention_text,
  ].filter((t) => t.length > 0);
  return (
    <ul className="mt-2 space-y-2" aria-label="Passages">
      {variant.passages.map((passage) => {
        const href = buildVideoDeepLink(videoId, {
          lang: variant.language_code,
          seg: passage.segment_id,
          t: passage.start_time,
        });
        const stamp = formatTimestamp(passage.start_time);
        return (
          <li key={`${passage.segment_id}-${passage.start_time}`}>
            <p className="text-slate-600" lang={variant.language_code}>
              <HighlightedText text={passage.text} queryTerms={terms} />
            </p>
            <Link
              to={href}
              aria-label={`Open ${videoTitle} at ${stamp} (${variant.language_code})`}
              className="inline-block py-1 font-mono text-xs text-indigo-700 hover:underline focus:outline-none focus:ring-2 focus:ring-indigo-500 rounded"
            >
              {stamp}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

export function EvidenceItem({ item }: EvidenceItemProps) {
  const title = item.video_title ?? "Untitled video";
  const others = item.other_language_variants;

  return (
    <li
      className="rounded-md border border-slate-200 p-3 text-sm"
      data-testid="evidence-item"
    >
      {/* Distinct colour so the video title never blends into the transcript prose below. */}
      <p className="font-semibold text-sky-900">{title}</p>
      <p className="text-xs text-slate-500">
        {item.channel_title ? `${item.channel_title} · ` : ""}
        <span data-testid="evidence-separation">
          {separationLabel(item.representative)}
        </span>
      </p>
      <VariantBody
        videoId={item.video_id}
        videoTitle={title}
        variant={item.representative}
      />

      {others.length > 0 && (
        <details className="mt-3" data-testid="evidence-expander">
          <summary className="cursor-pointer text-xs text-indigo-700 hover:underline focus:outline-none focus:ring-2 focus:ring-indigo-500 rounded">
            also in {others.length} other{" "}
            {others.length === 1 ? "transcript" : "transcripts"} (
            {others.map((v) => v.language_code).join(", ")})
          </summary>
          <ul className="mt-2 space-y-3 border-l-2 border-slate-100 pl-3">
            {others.map((variant) => (
              <li key={variant.language_code}>
                <p className="text-xs text-slate-500">
                  <span className="font-mono uppercase">
                    {variant.language_code}
                  </span>{" "}
                  · {separationLabel(variant)}
                </p>
                <VariantBody
                  videoId={item.video_id}
                  videoTitle={title}
                  variant={variant}
                />
              </li>
            ))}
          </ul>
        </details>
      )}
    </li>
  );
}
