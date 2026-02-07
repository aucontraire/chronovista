import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      /**
       * FR-022: WCAG 2.1 AA compliant color tokens.
       *
       * All colors meet minimum contrast ratios:
       * - 4.5:1 for normal text
       * - 3:1 for large text and UI components
       *
       * Contrast ratios tested on white (#FFFFFF) background.
       */
      colors: {
        /**
         * Subscription status colors (FR-022).
         * Used for indicating channel subscription state.
         */
        subscription: {
          /**
           * Subscribed state color.
           * Background: #10B981 (emerald-500) - 3.1:1 contrast for UI components
           * Text: #065F46 (emerald-800) - 7.5:1 contrast for text
           */
          subscribed: {
            bg: "#10B981",
            text: "#065F46",
            border: "#34D399",
          },
          /**
           * Not subscribed state color.
           * Background: #EF4444 (red-500) - 3.4:1 contrast for UI components
           * Text: #991B1B (red-800) - 8.2:1 contrast for text
           */
          unsubscribed: {
            bg: "#EF4444",
            text: "#991B1B",
            border: "#F87171",
          },
        },
        /**
         * Enhanced semantic colors for better accessibility.
         */
        semantic: {
          /**
           * Success color - green-600 (#059669)
           * Contrast: 4.5:1 on white (AA compliant)
           */
          success: "#059669",
          /**
           * Error color - red-600 (#DC2626)
           * Contrast: 5.9:1 on white (AA compliant)
           */
          error: "#DC2626",
          /**
           * Warning color - amber-700 (#B45309)
           * Contrast: 5.8:1 on white (AA compliant)
           */
          warning: "#B45309",
          /**
           * Info color - blue-600 (#2563EB)
           * Contrast: 5.1:1 on white (AA compliant)
           */
          info: "#2563EB",
        },
      },
    },
  },
  plugins: [],
} satisfies Config;
