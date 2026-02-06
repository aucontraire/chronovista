/**
 * Route configuration for Chronovista navigation.
 */

import type React from "react";

import { ChannelIcon, SearchIcon, VideoIcon } from "../components/icons";

/**
 * NavRoute defines a navigable route in the application.
 */
export interface NavRoute {
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
 * Main navigation routes for the application.
 */
export const navRoutes: NavRoute[] = [
  {
    path: "/videos",
    label: "Videos",
    tooltip: "Browse your video library",
    icon: VideoIcon,
  },
  {
    path: "/search",
    label: "Search",
    tooltip: "Search across all content",
    icon: SearchIcon,
  },
  {
    path: "/channels",
    label: "Channels",
    tooltip: "Manage your channel subscriptions",
    icon: ChannelIcon,
  },
];
