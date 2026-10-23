/**
 * EntityCategoryTabs — accessible tablist for the entity page's Categories
 * group (Feature 090).
 *
 * Only the active tab's panel is mounted, so a panel's queries fire on first
 * activation rather than on page load. Keyboard conventions follow
 * PlaylistFilterTabs (Left/Right wrap, Home/End, activate on focus move).
 */

import { useId, useRef, useState } from "react";
import type { KeyboardEvent, ReactNode } from "react";

export interface EntityCategoryTabDefinition {
  /** Stable key; used in test ids and ARIA ids. */
  key: string;
  label: string;
  panel: ReactNode;
}

interface EntityCategoryTabsProps {
  /** Tabs in display order; the first is the default. */
  tabs: EntityCategoryTabDefinition[];
}

export function EntityCategoryTabs({ tabs }: EntityCategoryTabsProps) {
  const baseId = useId();
  const [activeKey, setActiveKey] = useState<string | undefined>(tabs[0]?.key);
  const tabRefs = useRef<Record<string, HTMLButtonElement | null>>({});

  const activeTab = tabs.find((t) => t.key === activeKey) ?? tabs[0];
  if (!activeTab) return null;

  const tabId = (key: string) => `${baseId}-tab-${key}`;
  const panelId = (key: string) => `${baseId}-panel-${key}`;

  const activate = (key: string) => {
    setActiveKey(key);
    tabRefs.current[key]?.focus();
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLButtonElement>, index: number) => {
    let next: number | null = null;
    switch (e.key) {
      case "ArrowLeft":
        next = index > 0 ? index - 1 : tabs.length - 1;
        break;
      case "ArrowRight":
        next = index < tabs.length - 1 ? index + 1 : 0;
        break;
      case "Home":
        next = 0;
        break;
      case "End":
        next = tabs.length - 1;
        break;
    }
    if (next === null) return;
    e.preventDefault();
    const target = tabs[next];
    if (target) activate(target.key);
  };

  return (
    <div data-testid="entity-category-tabs">
      <div
        role="tablist"
        aria-label="Category views"
        className="mb-4 flex flex-wrap items-center gap-1 border-b border-gray-200 dark:border-gray-700"
      >
        {tabs.map((tab, index) => {
          const isSelected = tab.key === activeTab.key;
          return (
            <button
              key={tab.key}
              ref={(el) => {
                tabRefs.current[tab.key] = el;
              }}
              type="button"
              role="tab"
              id={tabId(tab.key)}
              aria-selected={isSelected}
              aria-controls={isSelected ? panelId(tab.key) : undefined}
              tabIndex={isSelected ? 0 : -1}
              data-testid={`category-tab-${tab.key}`}
              onClick={() => activate(tab.key)}
              onKeyDown={(e) => handleKeyDown(e, index)}
              className={`relative -mb-px rounded-t-lg border-b-2 px-4 py-2.5 text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1 ${
                isSelected
                  ? "border-blue-600 font-semibold text-blue-600 dark:border-blue-400 dark:text-blue-400"
                  : "border-transparent text-gray-600 hover:bg-gray-50 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-200"
              }`}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      <div
        role="tabpanel"
        id={panelId(activeTab.key)}
        aria-labelledby={tabId(activeTab.key)}
        tabIndex={0}
        data-testid={`category-tabpanel-${activeTab.key}`}
        className="focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
      >
        {activeTab.panel}
      </div>
    </div>
  );
}
