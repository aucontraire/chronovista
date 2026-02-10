/**
 * TopicCombobox Component
 *
 * Implements:
 * - T031: Accessible topic combobox with hierarchical ARIA pattern
 * - T032: Full keyboard navigation (Arrow Up/Down, Enter, Escape, Tab, Home/End, type-ahead)
 * - FR-ACC-001: WCAG 2.1 Level AA compliance
 * - FR-ACC-002: Focus management
 * - FR-ACC-004: Screen reader announcements
 * - FR-ACC-007: Visible focus indicators
 *
 * Features:
 * - Hierarchical ARIA combobox pattern per quickstart.md §4
 * - Indented hierarchical display (16px/32px/48px per depth)
 * - Parent path context display ("Music > Rock Music")
 * - role="combobox", aria-expanded, aria-autocomplete="list"
 * - role="listbox" with role="option" for hierarchical items
 * - aria-activedescendant for keyboard navigation
 * - Full keyboard support including type-ahead search
 * - Multiple topic selection with filter pills
 * - Maximum topic limit validation
 *
 * @see FR-ACC-001: WCAG 2.1 Level AA Compliance
 * @see FR-ACC-002: Focus Management
 * @see FR-ACC-004: Screen Reader Announcements
 * @see FR-ACC-007: Visible Focus Indicators
 */

import { useState, useRef, useEffect, useId } from 'react';
import { useTopics } from '../hooks/useTopics';
import { FILTER_LIMITS } from '../types/filters';
import { filterColors } from '../styles/tokens';
import { isApiError } from '../api/config';
import type { TopicHierarchyItem } from '../types/filters';

interface TopicComboboxProps {
  /** Currently selected topic IDs */
  selectedTopics: string[];
  /** Callback when a topic is selected */
  onTopicSelect: (topicId: string) => void;
  /** Callback when a topic is removed */
  onTopicRemove: (topicId: string) => void;
  /** Maximum number of topics allowed (default: FILTER_LIMITS.MAX_TOPICS) */
  maxTopics?: number;
  /** Optional className for container */
  className?: string;
}

/**
 * TopicCombobox component for selecting video topics with hierarchical display.
 *
 * Provides accessible topic selection with hierarchical navigation, keyboard support,
 * and visual feedback for filter limits. Topics are displayed with indentation based
 * on their depth in the hierarchy.
 *
 * @example
 * ```tsx
 * <TopicCombobox
 *   selectedTopics={['/m/04rlf', '/m/02mscn']}
 *   onTopicSelect={(topicId) => setTopics([...topics, topicId])}
 *   onTopicRemove={(topicId) => setTopics(topics.filter(t => t !== topicId))}
 * />
 * ```
 */
export function TopicCombobox({
  selectedTopics,
  onTopicSelect,
  onTopicRemove,
  maxTopics = FILTER_LIMITS.MAX_TOPICS,
  className = '',
}: TopicComboboxProps) {
  const [searchValue, setSearchValue] = useState('');
  const [isOpen, setIsOpen] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const [typeAheadString, setTypeAheadString] = useState('');
  const [typeAheadTimeout, setTypeAheadTimeout] = useState<NodeJS.Timeout | null>(null);

  const inputRef = useRef<HTMLInputElement>(null);
  const listboxRef = useRef<HTMLUListElement>(null);

  // Unique IDs for ARIA relationships
  const comboboxId = useId();
  const listboxId = useId();
  const labelId = useId();
  const descriptionId = useId();
  const announcementId = useId();

  // Fetch topics with local filtering
  const { topics, isLoading, isError, error, refetch } = useTopics({ search: searchValue });

  // Filter out already selected topics
  const availableTopics = topics.filter(
    topic => !selectedTopics.includes(topic.topic_id)
  );

  // Get selected topic details for display
  const selectedTopicDetails = selectedTopics
    .map(id => topics.find(t => t.topic_id === id))
    .filter((t): t is TopicHierarchyItem => t !== undefined);

  const isMaxReached = selectedTopics.length >= maxTopics;
  const showSuggestions = isOpen && !isMaxReached;

  // Reset highlighted index when topics change
  useEffect(() => {
    setHighlightedIndex(-1);
  }, [availableTopics]);

  // Close dropdown when clicking outside
  useEffect(() => {
    if (!isOpen) return;

    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as Node;
      if (
        inputRef.current &&
        !inputRef.current.contains(target) &&
        listboxRef.current &&
        !listboxRef.current.contains(target)
      ) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen]);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setSearchValue(value);
    setIsOpen(!isMaxReached);
    setHighlightedIndex(-1);
  };

  const handleTopicSelect = (topicId: string) => {
    if (!selectedTopics.includes(topicId) && selectedTopics.length < maxTopics) {
      onTopicSelect(topicId);
      setSearchValue('');
      setIsOpen(false);
      setHighlightedIndex(-1);

      // Return focus to input after selection
      inputRef.current?.focus();
    }
  };

  const handleTopicRemove = (topicId: string) => {
    onTopicRemove(topicId);
    // Return focus to input after removal
    inputRef.current?.focus();
  };

  // Type-ahead search: find next matching topic starting from current position
  const findMatchingTopic = (searchStr: string, startIndex: number): number => {
    const lowerSearch = searchStr.toLowerCase();
    const length = availableTopics.length;

    // Search from startIndex to end
    for (let i = startIndex; i < length; i++) {
      const topic = availableTopics[i];
      if (!topic) continue;
      const fullText = topic.parent_path
        ? `${topic.parent_path} > ${topic.name}`
        : topic.name;
      if (fullText.toLowerCase().startsWith(lowerSearch)) {
        return i;
      }
    }

    // Wrap around: search from beginning to startIndex
    for (let i = 0; i < startIndex; i++) {
      const topic = availableTopics[i];
      if (!topic) continue;
      const fullText = topic.parent_path
        ? `${topic.parent_path} > ${topic.name}`
        : topic.name;
      if (fullText.toLowerCase().startsWith(lowerSearch)) {
        return i;
      }
    }

    return -1;
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    // Handle type-ahead for printable characters
    if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
      // Clear previous timeout
      if (typeAheadTimeout) {
        clearTimeout(typeAheadTimeout);
      }

      const newTypeAhead = typeAheadString + e.key;
      setTypeAheadString(newTypeAhead);

      // Find matching topic
      const matchIndex = findMatchingTopic(
        newTypeAhead,
        highlightedIndex + 1
      );
      if (matchIndex >= 0) {
        setHighlightedIndex(matchIndex);
      }

      // Clear type-ahead string after 1 second
      const timeout = setTimeout(() => {
        setTypeAheadString('');
      }, 1000);
      setTypeAheadTimeout(timeout);

      // Don't prevent default for regular typing in input
      return;
    }

    if (!showSuggestions || availableTopics.length === 0) {
      // Allow Escape to close even if no suggestions
      if (e.key === 'Escape') {
        setIsOpen(false);
        setHighlightedIndex(-1);
      }
      return;
    }

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setHighlightedIndex(prev =>
          prev < availableTopics.length - 1 ? prev + 1 : 0
        );
        break;

      case 'ArrowUp':
        e.preventDefault();
        setHighlightedIndex(prev =>
          prev > 0 ? prev - 1 : availableTopics.length - 1
        );
        break;

      case 'Enter':
        e.preventDefault();
        if (highlightedIndex >= 0 && highlightedIndex < availableTopics.length) {
          const selectedTopic = availableTopics[highlightedIndex];
          if (selectedTopic) {
            handleTopicSelect(selectedTopic.topic_id);
          }
        }
        break;

      case 'Escape':
        e.preventDefault();
        setIsOpen(false);
        setHighlightedIndex(-1);
        break;

      case 'Home':
        if (showSuggestions) {
          e.preventDefault();
          setHighlightedIndex(0);
        }
        break;

      case 'End':
        if (showSuggestions) {
          e.preventDefault();
          setHighlightedIndex(availableTopics.length - 1);
        }
        break;

      case 'Tab':
        // Close dropdown on tab (default behavior will move focus)
        setIsOpen(false);
        setHighlightedIndex(-1);
        break;
    }
  };

  // Scroll highlighted option into view
  useEffect(() => {
    const listbox = listboxRef.current;
    if (isOpen && highlightedIndex >= 0 && listbox) {
      const highlightedOption = listbox.querySelector(
        `[data-index="${highlightedIndex}"]`
      ) as HTMLElement;
      if (highlightedOption) {
        highlightedOption.scrollIntoView({ block: 'nearest' });
      }
    }
  }, [isOpen, highlightedIndex]);

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (typeAheadTimeout) {
        clearTimeout(typeAheadTimeout);
      }
    };
  }, [typeAheadTimeout]);

  // Generate ID for highlighted option (aria-activedescendant)
  const activeDescendantId = highlightedIndex >= 0
    ? `${listboxId}-option-${highlightedIndex}`
    : undefined;

  // Calculate indentation based on depth (16px per level)
  const getIndentation = (depth: number): string => {
    return `${depth * 16}px`;
  };

  // Format topic display with parent path
  const formatTopicDisplay = (topic: TopicHierarchyItem): string => {
    return topic.parent_path
      ? `${topic.parent_path} > ${topic.name}`
      : topic.name;
  };

  return (
    <div className={`space-y-3 ${className}`}>
      {/* Label */}
      <label
        id={labelId}
        htmlFor={comboboxId}
        className="block text-sm font-medium text-gray-900 dark:text-gray-100"
      >
        Topics
        <span className="ml-2 text-xs text-gray-500 dark:text-gray-400">
          ({selectedTopics.length}/{maxTopics})
        </span>
      </label>

      {/* Selected topics display */}
      {selectedTopicDetails.length > 0 && (
        <div
          className="flex flex-wrap gap-2"
          role="list"
          aria-label="Selected topics"
        >
          {selectedTopicDetails.map((topic) => (
            <div
              key={topic.topic_id}
              role="listitem"
              className="inline-flex items-center gap-1.5 px-3 py-2 sm:py-1.5 min-h-[44px] sm:min-h-0 rounded-full text-sm font-medium border"
              style={{
                backgroundColor: filterColors.topic.background,
                color: filterColors.topic.text,
                borderColor: filterColors.topic.border,
              }}
            >
              <span className="max-w-xs truncate" title={formatTopicDisplay(topic)}>
                {topic.name}
              </span>
              <button
                type="button"
                onClick={() => handleTopicRemove(topic.topic_id)}
                aria-label={`Remove topic ${topic.name}`}
                className="inline-flex items-center justify-center min-w-[44px] min-h-[44px] sm:min-w-[24px] sm:min-h-[24px] -my-2 sm:my-0 -me-2 sm:me-0 rounded-full hover:bg-black/10 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
                style={{ color: filterColors.topic.text }}
              >
                <svg
                  className="w-4 h-4 sm:w-3 sm:h-3"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M6 18L18 6M6 6l12 12"
                  />
                </svg>
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Combobox input and dropdown container */}
      <div className="relative">
        <input
          ref={inputRef}
          id={comboboxId}
          type="text"
          role="combobox"
          aria-labelledby={labelId}
          aria-describedby={descriptionId}
          aria-expanded={showSuggestions && availableTopics.length > 0}
          aria-autocomplete="list"
          aria-controls={showSuggestions ? listboxId : undefined}
          aria-activedescendant={activeDescendantId}
          value={searchValue}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          onFocus={() => !isMaxReached && setIsOpen(true)}
          disabled={isMaxReached}
          placeholder={isMaxReached ? 'Maximum topics reached' : 'Type to search topics...'}
          className={`
            w-full px-4 py-2.5 text-base
            border rounded-lg
            bg-white dark:bg-gray-800
            text-gray-900 dark:text-gray-100
            placeholder-gray-500 dark:placeholder-gray-400
            disabled:bg-gray-100 dark:disabled:bg-gray-900
            disabled:cursor-not-allowed
            focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2
            ${isMaxReached ? 'border-gray-300' : 'border-gray-300 dark:border-gray-600'}
          `}
        />

        {/* Loading indicator */}
        {isLoading && searchValue.length > 0 && (
          <div className="absolute right-3 top-1/2 -translate-y-1/2">
            <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" aria-hidden="true" />
          </div>
        )}

        {/* Suggestions listbox with hierarchical display */}
        {showSuggestions && availableTopics.length > 0 && (
          <ul
            ref={listboxRef}
            id={listboxId}
            role="listbox"
            aria-labelledby={labelId}
            className="absolute z-50 left-0 right-0 top-full mt-1 max-h-60 overflow-auto bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg shadow-lg"
          >
          {availableTopics.map((topic, index) => {
            const isHighlighted = index === highlightedIndex;
            const optionId = `${listboxId}-option-${index}`;
            const indentation = getIndentation(topic.depth);

            return (
              <li
                key={topic.topic_id}
                id={optionId}
                role="option"
                aria-selected={isHighlighted}
                data-index={index}
                onClick={() => handleTopicSelect(topic.topic_id)}
                onMouseEnter={() => setHighlightedIndex(index)}
                style={{ paddingLeft: `calc(1rem + ${indentation})` }}
                className={`
                  py-2.5 pr-4 cursor-pointer text-base
                  ${isHighlighted
                    ? 'bg-blue-100 dark:bg-blue-900 text-blue-900 dark:text-blue-100'
                    : 'text-gray-900 dark:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-700'
                  }
                `}
              >
                <div className="flex flex-col">
                  <span className="font-medium">{topic.name}</span>
                  {topic.parent_path && (
                    <span className="text-xs text-gray-600 dark:text-gray-400 mt-0.5">
                      {topic.parent_path}
                    </span>
                  )}
                  <span className="text-xs text-gray-500 dark:text-gray-500 mt-0.5">
                    {topic.video_count} video{topic.video_count !== 1 ? 's' : ''}
                  </span>
                </div>
              </li>
            );
          })}
          </ul>
        )}
      </div>

      {/* Description for screen readers */}
      <p id={descriptionId} className="sr-only">
        Type to search for topics. Topics are organized hierarchically. Use arrow keys to navigate, Enter to select, Escape to close. Type any letter to jump to topics starting with that letter.
        {isMaxReached && ` Maximum of ${maxTopics} topics reached.`}
      </p>

      {/* Error state with retry button */}
      {isError && (
        <div className="p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-700 rounded-lg" role="alert">
          <p className="text-sm text-red-800 dark:text-red-200">
            {isApiError(error) && error.type === 'timeout'
              ? 'Request timed out. Please try again.'
              : 'Error loading topics. Please try again.'}
          </p>
          <button
            type="button"
            onClick={refetch}
            className="mt-2 px-3 py-1 text-sm font-medium text-red-700 dark:text-red-300 hover:text-red-800 dark:hover:text-red-200 border border-red-300 dark:border-red-600 rounded hover:bg-red-100 dark:hover:bg-red-900/40 focus:outline-none focus:ring-2 focus:ring-red-500 transition-colors"
          >
            Retry
          </button>
        </div>
      )}

      {/* No results message */}
      {showSuggestions && availableTopics.length === 0 && !isLoading && !isError && (
        <p className="text-sm text-gray-500 dark:text-gray-400">
          {searchValue
            ? `No topics found matching "${searchValue}"`
            : 'Start typing to search topics'
          }
        </p>
      )}

      {/* Screen reader announcement region */}
      <div
        id={announcementId}
        role="status"
        aria-live="polite"
        aria-atomic="true"
        className="sr-only"
      >
        {showSuggestions && availableTopics.length > 0 &&
          `${availableTopics.length} topic${availableTopics.length === 1 ? '' : 's'} found`
        }
        {selectedTopics.length > 0 &&
          `, ${selectedTopics.length} topic${selectedTopics.length === 1 ? '' : 's'} selected`
        }
        {typeAheadString && `Searching for topics starting with ${typeAheadString}`}
      </div>
    </div>
  );
}
