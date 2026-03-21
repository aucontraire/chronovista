/**
 * Route configuration for Chronovista navigation.
 */

import type React from "react";

import {
  BatchCorrectionsIcon,
  ChartBarIcon,
  ChannelIcon,
  ClockIcon,
  EntityIcon,
  PlaylistIcon,
  SearchIcon,
  SetupIcon,
  SettingsIcon,
  TranscriptsIcon,
  VideoIcon,
} from "../components/icons";

/**
 * NavRoute defines a navigable route in the application.
 */
export interface NavRoute {
  /** Discriminant tag for the discriminated union */
  kind: "route";
  /** URL path for this route */
  path: string;
  /** Display label for navigation */
  label: string;
  /** Tooltip text for accessibility */
  tooltip: string;
  /** Icon component for this route */
  icon: React.FC<React.SVGProps<SVGSVGElement>>;
}

/**
 * NavGroupRoute defines a collapsible group of child routes in the sidebar.
 */
export interface NavGroupRoute {
  /** Discriminant tag for the discriminated union */
  kind: "group";
  /** Display label for the group header */
  label: string;
  /** Tooltip text shown in compact (icon-only) mode */
  tooltip: string;
  /** Icon component for the group header */
  icon: React.FC<React.SVGProps<SVGSVGElement>>;
  /** Child navigation routes within this group */
  children: NavRoute[];
  /** Whether the group starts expanded (before localStorage overrides) */
  defaultExpanded: boolean;
  /** localStorage key for persisting expand/collapse state */
  storageKey: string;
}

/**
 * NavSeparator defines a visual divider between navigation sections.
 */
export interface NavSeparator {
  /** Discriminant tag for the discriminated union */
  kind: "separator";
}

/**
 * Union type for top-level navigation entries.
 */
export type NavEntry = NavRoute | NavGroupRoute | NavSeparator;

/**
 * Main navigation entries for the application sidebar.
 */
export const navRoutes: NavEntry[] = [
  {
    kind: "route",
    path: "/videos",
    label: "Videos",
    tooltip: "Browse your video library",
    icon: VideoIcon,
  },
  {
    kind: "group",
    label: "Transcripts",
    tooltip: "Transcripts",
    icon: TranscriptsIcon,
    defaultExpanded: true,
    storageKey: "chronovista.sidebar.transcriptsExpanded",
    children: [
      {
        kind: "route",
        path: "/corrections/batch",
        label: "Find & Replace",
        tooltip: "Batch find and replace across all transcripts",
        icon: BatchCorrectionsIcon,
      },
      {
        kind: "route",
        path: "/corrections/batch/history",
        label: "Batch History",
        tooltip: "View batch correction history",
        icon: ClockIcon,
      },
      {
        kind: "route",
        path: "/corrections/diff-analysis",
        label: "ASR Error Patterns",
        tooltip: "Analyse ASR error patterns across transcripts",
        icon: ChartBarIcon,
      },
    ],
  },
  {
    kind: "route",
    path: "/channels",
    label: "Channels",
    tooltip: "Manage your channel subscriptions",
    icon: ChannelIcon,
  },
  {
    kind: "route",
    path: "/playlists",
    label: "Playlists",
    tooltip: "Browse your playlists",
    icon: PlaylistIcon,
  },
  {
    kind: "route",
    path: "/entities",
    label: "Entities",
    tooltip: "Browse named entities",
    icon: EntityIcon,
  },
  {
    kind: "route",
    path: "/search",
    label: "Search",
    tooltip: "Search across all content",
    icon: SearchIcon,
  },
  {
    kind: "separator",
  },
  {
    kind: "route",
    path: "/onboarding",
    label: "Setup",
    tooltip: "Data onboarding pipeline — import and enrich your YouTube data",
    icon: SetupIcon,
  },
  {
    kind: "route",
    path: "/settings",
    label: "Settings",
    tooltip: "Application settings and preferences",
    icon: SettingsIcon,
  },
];
