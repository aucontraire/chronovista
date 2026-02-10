/**
 * ClassificationSection component displays video classification metadata.
 *
 * Features:
 * - T038: Organized subsections for tags, category, and topics
 * - T039: Clickable tag links that navigate to filtered video lists
 * - T040: URL encoding for special characters in tags (C++, music & arts, etc.)
 * - T041: Hover styling to indicate tags are clickable
 * - T042: Browser back button returns to video detail after tag navigation
 * - T064: Clickable topic links to navigate to filtered video lists
 * - T065: Multiple topics as individually clickable elements
 * - T066: Topic display with parent path context ("Arts > Music > Pop Music")
 * - T067: "Classification & Context" section header
 * - T068: Playlists subsection with clickable playlist links
 * - T069: Graceful empty state for all subsections (FR-006, FR-032)
 * - T070: Labeled subsections for Tags, Categories, Topics, Playlists
 * - FR-ACC-003: WCAG AA compliant color contrast (7.0:1+ ratio)
 *
 * Accessibility:
 * - Semantic HTML with proper heading hierarchy
 * - Labeled subsections with descriptive headings
 * - Link elements for keyboard navigation
 * - Visible focus indicators
 * - Empty state messaging
 */

import { Link } from "react-router-dom";
import { filterColors } from "../styles/tokens";
import type { TopicSummary } from "../types/video";
import type { VideoPlaylistMembership } from "../types/playlist";

/**
 * Props for ClassificationSection component.
 */
export interface ClassificationSectionProps {
  /** Array of tag strings */
  tags: string[];
  /** YouTube category ID (may be null) */
  categoryId: string | null;
  /** Human-readable category name (may be null) */
  categoryName: string | null;
  /** Array of topic summaries with hierarchy */
  topics: TopicSummary[];
  /** Array of playlists containing this video (T068) */
  playlists?: VideoPlaylistMembership[];
}

/**
 * Renders a subsection with a label and content.
 */
function Subsection({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <h4 className="text-sm font-medium text-gray-700 mb-2">{label}</h4>
      {children}
    </div>
  );
}

/**
 * ClassificationSection component.
 *
 * Displays tags, category, topics, and playlists in organized subsections.
 * All elements are clickable and navigate to filtered video lists or playlist details.
 *
 * @param props - Component props
 * @returns Classification section UI
 */
export function ClassificationSection({
  tags,
  categoryId,
  categoryName,
  topics,
  playlists = [],
}: ClassificationSectionProps) {
  return (
    <section
      aria-labelledby="classification-heading"
      className="bg-white rounded-xl shadow-md border border-gray-100 p-6 lg:p-8 space-y-6"
    >
      {/* T067: Section Header */}
      <h3 id="classification-heading" className="text-lg font-semibold text-gray-900">
        Classification & Context
      </h3>

      {/* T070: Tags Subsection - T038, T039, T040, T041 */}
      <Subsection label="Tags">
        {tags.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {tags.map((tag) => (
              <Link
                key={tag}
                to={`/videos?tag=${encodeURIComponent(tag)}`}
                className="px-3 py-1 text-sm font-medium rounded-full transition-all duration-200 hover:underline hover:brightness-95 focus:outline-none focus:ring-2 focus:ring-offset-2"
                style={{
                  backgroundColor: filterColors.tag.background,
                  color: filterColors.tag.text,
                  borderWidth: "1px",
                  borderStyle: "solid",
                  borderColor: filterColors.tag.border,
                  // T041: Hover styling uses filter for brightness shift
                  // Cursor: pointer is implicit for Link elements
                }}
                aria-label={`Filter videos by tag: ${tag}`}
              >
                {tag}
              </Link>
            ))}
          </div>
        ) : (
          <span className="text-gray-400 text-sm">None</span>
        )}
      </Subsection>

      {/* T070: Category Subsection - T038 */}
      <Subsection label="Category">
        {categoryName && categoryId ? (
          <Link
            to={`/videos?category=${encodeURIComponent(categoryId)}`}
            className="inline-flex px-3 py-1 text-sm font-medium rounded-full transition-all duration-200 hover:underline hover:brightness-95 focus:outline-none focus:ring-2 focus:ring-offset-2"
            style={{
              backgroundColor: filterColors.category.background,
              color: filterColors.category.text,
              borderWidth: "1px",
              borderStyle: "solid",
              borderColor: filterColors.category.border,
            }}
            aria-label={`Filter videos by category: ${categoryName}`}
          >
            {categoryName}
          </Link>
        ) : (
          <span className="text-gray-400 text-sm">None</span>
        )}
      </Subsection>

      {/* T070: Topics Subsection - T038, T064, T065, T066 */}
      <Subsection label="Topics">
        {topics.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {topics.map((topic) => (
              <Link
                key={topic.topic_id}
                to={`/videos?topic_id=${encodeURIComponent(topic.topic_id)}`}
                className="px-3 py-1 text-sm font-medium rounded-full transition-all duration-200 hover:underline hover:brightness-95 focus:outline-none focus:ring-2 focus:ring-offset-2"
                style={{
                  backgroundColor: filterColors.topic.background,
                  color: filterColors.topic.text,
                  borderWidth: "1px",
                  borderStyle: "solid",
                  borderColor: filterColors.topic.border,
                }}
                aria-label={`Filter videos by topic: ${topic.name}${topic.parent_path ? ` (${topic.parent_path})` : ""}`}
              >
                {topic.parent_path ? `${topic.parent_path} > ${topic.name}` : topic.name}
              </Link>
            ))}
          </div>
        ) : (
          <span className="text-gray-400 text-sm">None</span>
        )}
      </Subsection>

      {/* T068, T070: Playlists Subsection - NEW */}
      <Subsection label="Playlists">
        {playlists.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {playlists.map((playlist) => (
              <Link
                key={playlist.playlist_id}
                to={`/playlists/${playlist.playlist_id}`}
                className="px-3 py-1 text-sm font-medium rounded-full transition-all duration-200 hover:underline hover:brightness-95 focus:outline-none focus:ring-2 focus:ring-offset-2"
                style={{
                  backgroundColor: filterColors.playlist.background,
                  color: filterColors.playlist.text,
                  borderWidth: "1px",
                  borderStyle: "solid",
                  borderColor: filterColors.playlist.border,
                }}
                aria-label={`View playlist: ${playlist.title}`}
              >
                {playlist.title}
              </Link>
            ))}
          </div>
        ) : (
          <span className="text-gray-400 text-sm">None</span>
        )}
      </Subsection>
    </section>
  );
}
