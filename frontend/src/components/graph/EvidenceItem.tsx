/**
 * EvidenceItem — one VIDEO where the two entities are mentioned together (Features 114/118,
 * FR-003/004/014/014a/021). Co-mention only: it never asserts a relationship.
 *
 * The row lists the video's grouped passages in time order: the first three are visible, the rest
 * unfold in place on request (focus moves to the first revealed one). Each passage leads with its
 * first transcript language and shows the closest co-mention as text; its other co-mention moments
 * are timestamps only, and the same passage in other languages sits behind a native `<details>`.
 */

import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

import type {
  GroupedPassage,
  LanguagePassage,
  MentionRef,
  PassageSegment,
  VideoPassages,
} from "../../api/graph";
import { formatTimestamp } from "../../utils/formatTimestamp";
import { buildVideoDeepLink } from "../../utils/videoDeepLink";

/** Passages visible before the "Show N more passages" fold (FR-014a). */
const VISIBLE_PASSAGES = 3;

interface EvidenceItemProps {
  item: VideoPassages;
}

const linkClass =
  "inline-block py-1 font-mono text-xs text-indigo-700 hover:underline focus:outline-none focus:ring-2 focus:ring-indigo-500 rounded";

function gapLabel(seconds: number): string {
  return `${Math.round(seconds)}s apart`;
}

type Range = [start: number, end: number];

const normalizeText = (t: string): string => t.replace(/\s+/g, " ").trim().toLowerCase();

/**
 * Character ranges of one mention per segment id, taken from its stored offsets, or `null` when the
 * offsets cannot be trusted. Offsets go stale when a later transcript correction changes a
 * segment's text, so the slice they select must still read as `mention_text`.
 */
function rangesFromOffsets(
  mention: MentionRef,
  segments: PassageSegment[],
): Map<number, Range[]> | null {
  const { match_start: ms, match_end: me, segment_id, end_segment_id } = mention;
  if (ms === null || me === null || !Number.isInteger(ms) || !Number.isInteger(me)) return null;
  const startIdx = segments.findIndex((s) => s.segment_id === segment_id);
  const start = segments[startIdx];
  if (start === undefined) return null;

  const out = new Map<number, Range[]>();
  let sliced: string;
  if (end_segment_id === null || end_segment_id === segment_id) {
    if (ms < 0 || me <= ms || me > start.text.length) return null;
    out.set(segment_id, [[ms, me]]);
    sliced = start.text.slice(ms, me);
  } else {
    const endIdx = segments.findIndex((s) => s.segment_id === end_segment_id);
    const end = segments[endIdx];
    if (end === undefined || endIdx <= startIdx) return null;
    if (ms < 0 || ms >= start.text.length || me <= 0 || me > end.text.length) return null;
    const pieces = [start.text.slice(ms)];
    out.set(segment_id, [[ms, start.text.length]]);
    for (const mid of segments.slice(startIdx + 1, endIdx)) {
      pieces.push(mid.text);
      out.set(mid.segment_id, [[0, mid.text.length]]);
    }
    pieces.push(end.text.slice(0, me));
    out.set(end_segment_id, [[0, me]]);
    sliced = pieces.join(" ");
  }
  return normalizeText(sliced) === normalizeText(mention.mention_text) ? out : null;
}

/** Fallback: every case-insensitive occurrence of `mention_text` in each non-context segment. */
function rangesFromTextSearch(
  mention: MentionRef,
  segments: PassageSegment[],
): Map<number, Range[]> {
  const out = new Map<number, Range[]>();
  if (mention.mention_text.length === 0) return out;
  const pattern = new RegExp(mention.mention_text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi");
  for (const segment of segments) {
    if (segment.is_context) continue;
    const found: Range[] = [...segment.text.matchAll(pattern)].map((m) => [
      m.index,
      m.index + m[0].length,
    ]);
    if (found.length > 0) out.set(segment.segment_id, found);
  }
  return out;
}

/** Marked character ranges per segment id for both mentions, merged where they overlap. */
function highlightRanges(
  segments: PassageSegment[],
  mentions: MentionRef[],
): Map<number, Range[]> {
  const all = new Map<number, Range[]>();
  for (const mention of mentions) {
    const ranges =
      rangesFromOffsets(mention, segments) ?? rangesFromTextSearch(mention, segments);
    for (const [id, rs] of ranges) all.set(id, [...(all.get(id) ?? []), ...rs]);
  }
  for (const [id, rs] of all) {
    const sorted = [...rs].sort((a, b) => a[0] - b[0] || a[1] - b[1]);
    const merged: Range[] = [];
    for (const r of sorted) {
      const last = merged[merged.length - 1];
      if (last !== undefined && r[0] <= last[1]) last[1] = Math.max(last[1], r[1]);
      else merged.push([r[0], r[1]]);
    }
    all.set(id, merged);
  }
  return all;
}

const markClass = "bg-yellow-200 text-yellow-900 font-semibold px-0.5 rounded-sm";

function MarkedText({ text, ranges }: { text: string; ranges: Range[] }) {
  const parts: ReactNode[] = [];
  let cursor = 0;
  ranges.forEach(([a, b], i) => {
    if (a > cursor) parts.push(text.slice(cursor, a));
    parts.push(
      <mark key={i} className={markClass}>
        {text.slice(a, b)}
      </mark>,
    );
    cursor = b;
  });
  if (cursor < text.length) parts.push(text.slice(cursor));
  return <>{parts}</>;
}

/** True when transcript segments sit between two shown segments (their text is not shown). */
function isGap(previous: PassageSegment | undefined, segment: PassageSegment): boolean {
  return previous !== undefined && segment.sequence_number - previous.sequence_number > 1;
}

/** The space between two shown segments, or a visible ellipsis when text was skipped between them. */
function SegmentJoin({ skipped }: { skipped: boolean }) {
  if (!skipped) return <> </>;
  return (
    <>
      {" "}
      <span aria-hidden="true" className="text-slate-400">
        {"\u2026"}
      </span>
      <span className="sr-only" lang="en">
        (text omitted)
      </span>{" "}
    </>
  );
}

/** The closest co-mention of one language variant as segments, plus its deep link and other moments. */
function VariantBody({
  videoId,
  videoTitle,
  variant,
}: {
  videoId: string;
  videoTitle: string;
  variant: LanguagePassage;
}) {
  const { closest } = variant;
  const marked = highlightRanges(closest.segments, [closest.mention_a, closest.mention_b]);
  const linkFor = (t: number) =>
    buildVideoDeepLink(videoId, {
      lang: variant.language_code,
      seg: closest.segment_id,
      t,
    });
  const openStamp = formatTimestamp(closest.start_time);
  // The server caps `other_moments`; `co_mention_count` keeps the true total.
  const totalOthers = variant.co_mention_count - 1;
  const unlisted = totalOthers - variant.other_moments.length;

  return (
    <>
      <p className="mt-2 text-slate-800" lang={variant.language_code}>
        {closest.segments.map((segment, i) => (
          <span key={segment.segment_id}>
            {i === 0 ? "" : <SegmentJoin skipped={isGap(closest.segments[i - 1], segment)} />}
            {segment.is_context ? (
              <span className="text-slate-500">
                <span className="sr-only" lang="en">
                  (context){" "}
                </span>
                <MarkedText text={segment.text} ranges={marked.get(segment.segment_id) ?? []} />
              </span>
            ) : (
              <MarkedText text={segment.text} ranges={marked.get(segment.segment_id) ?? []} />
            )}
          </span>
        ))}
      </p>
      <Link
        to={linkFor(closest.start_time)}
        aria-label={`Open at ${openStamp} – ${videoTitle} (${variant.language_code})`}
        className={linkClass}
      >
        Open at {openStamp}
      </Link>

      {variant.other_moments.length > 0 && (
        <details className="mt-1" data-testid="other-moments">
          <summary className="cursor-pointer text-xs text-indigo-700 hover:underline focus:outline-none focus:ring-2 focus:ring-indigo-500 rounded">
            Other moments in this passage ({totalOthers})
          </summary>
          <ul className="mt-1 space-y-1">
            {variant.other_moments.map((moment, index) => {
              const stamp = formatTimestamp(moment.start_time);
              // `start_time` is the earlier mention; the later one is exactly `gap_seconds` after.
              const laterStamp = formatTimestamp(moment.start_time + moment.gap_seconds);
              const bothStamps =
                moment.gap_seconds > 0 && laterStamp !== stamp
                  ? `${stamp} \u2192 ${laterStamp}`
                  : stamp;
              return (
                <li key={`${moment.start_time}-${index}`} className="text-xs text-slate-500">
                  <Link
                    to={linkFor(moment.start_time)}
                    aria-label={`${bothStamps} – ${videoTitle} (${variant.language_code})`}
                    className={linkClass}
                  >
                    {bothStamps}
                  </Link>{" "}
                  · {gapLabel(moment.gap_seconds)}
                </li>
              );
            })}
          </ul>
          {unlisted > 0 && (
            <p className="mt-1 text-xs text-slate-500">and {unlisted} more</p>
          )}
        </details>
      )}
    </>
  );
}

/** Text badge (never colour alone) for a segment that lists several names; nothing is hidden. */
function NameListBadge({ variant }: { variant: LanguagePassage }) {
  if (!variant.name_list) return null;
  return (
    <span className="mt-1 inline-block rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600">
      Several names in one segment
    </span>
  );
}

function PassageRow({
  videoId,
  videoTitle,
  passage,
  position,
  total,
  rowRef,
}: {
  videoId: string;
  videoTitle: string;
  passage: GroupedPassage;
  position: number;
  total: number;
  rowRef?: ((el: HTMLLIElement | null) => void) | undefined;
}) {
  const [lead, ...others] = passage.variants;
  if (lead === undefined) return null;

  return (
    <li
      ref={rowRef}
      tabIndex={-1}
      aria-label={`Passage ${position} of ${total}, ${formatTimestamp(passage.start_time)}–${formatTimestamp(passage.end_time)}`}
      className="rounded border border-slate-100 p-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
      data-testid="evidence-passage"
    >
      <p className="text-xs text-slate-500">
        <span className="font-mono">
          {formatTimestamp(passage.start_time)}–
          {formatTimestamp(passage.end_time)}
        </span>
        {lead.co_mention_count > 1 && ` · ${lead.co_mention_count} co-mentions`}
        {` · closest ${gapLabel(passage.closest_gap_seconds)}`}
      </p>
      <NameListBadge variant={lead} />
      <VariantBody videoId={videoId} videoTitle={videoTitle} variant={lead} />

      {others.length > 0 && (
        <details className="mt-2" data-testid="evidence-expander">
          <summary className="cursor-pointer text-xs text-indigo-700 hover:underline focus:outline-none focus:ring-2 focus:ring-indigo-500 rounded">
            Also in {others.length} other{" "}
            {others.length === 1 ? "transcript" : "transcripts"} (
            {others.map((v) => v.language_code).join(", ")})
          </summary>
          <ul className="mt-2 space-y-3 border-l-2 border-slate-100 pl-3">
            {others.map((variant, index) => (
              // A group may split one language, so the code alone is not unique.
              <li key={`${variant.language_code}-${variant.start_time}-${index}`}>
                <p className="text-xs text-slate-500">
                  <span className="font-mono uppercase">
                    {variant.language_code}
                  </span>{" "}
                  · {gapLabel(variant.closest_gap_seconds)}
                </p>
                <NameListBadge variant={variant} />
                <VariantBody
                  videoId={videoId}
                  videoTitle={videoTitle}
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

export function EvidenceItem({ item }: EvidenceItemProps) {
  const title = item.video_title ?? "Untitled video";
  const [expanded, setExpanded] = useState(false);
  const firstRevealedRef = useRef<HTMLLIElement | null>(null);
  const listId = `passages-${item.video_id}`;
  const folded = item.passages.length - VISIBLE_PASSAGES;

  // Move focus to the first revealed passage so keyboard/screen-reader users land on new content.
  useEffect(() => {
    if (expanded) firstRevealedRef.current?.focus();
  }, [expanded]);

  const visible = expanded
    ? item.passages
    : item.passages.slice(0, VISIBLE_PASSAGES);

  return (
    <li
      className="rounded-md border border-slate-200 p-3 text-sm"
      data-testid="evidence-item"
    >
      {/* Distinct colour so the video title never blends into the transcript prose below. */}
      <h3 className="font-semibold text-sky-900">{title}</h3>
      <p className="text-xs text-slate-500">
        {item.channel_title ? `${item.channel_title} · ` : ""}
        <span data-testid="evidence-separation">
          closest mentions {Math.round(item.closest_gap_seconds)}s apart
        </span>
      </p>

      <ul id={listId} className="mt-2 space-y-2" aria-label={`Passages in ${title}`}>
        {visible.map((passage, i) => (
          <PassageRow
            key={`${passage.start_time}-${passage.end_time}`}
            videoId={item.video_id}
            videoTitle={title}
            passage={passage}
            position={i + 1}
            total={item.passages.length}
            rowRef={
              i === VISIBLE_PASSAGES
                ? (el) => {
                    firstRevealedRef.current = el;
                  }
                : undefined
            }
          />
        ))}
      </ul>

      {folded > 0 && !expanded && (
        <button
          type="button"
          aria-expanded={false}
          aria-controls={listId}
          onClick={() => setExpanded(true)}
          className="mt-2 rounded text-xs text-indigo-700 hover:underline focus:outline-none focus:ring-2 focus:ring-indigo-500"
        >
          Show {folded} more {folded === 1 ? "passage" : "passages"}
        </button>
      )}
    </li>
  );
}
