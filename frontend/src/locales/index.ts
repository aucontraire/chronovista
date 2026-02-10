/**
 * Internationalization (i18n) support for Chronovista frontend.
 *
 * This module provides a simple i18n system for externalizing UI strings.
 * Currently supports English (en) as the default locale.
 *
 * @module locales
 */

import enTranslations from './en.json';

/**
 * Available locale codes.
 */
export type LocaleCode = 'en';

/**
 * Translation dictionary structure.
 */
export type Translations = typeof enTranslations;

/**
 * Translation key path for type-safe access.
 * Examples: 'filters.tags.label', 'aria.removeTag'
 */
export type TranslationKey = string;

/**
 * All available translations by locale.
 */
const translations: Record<LocaleCode, Translations> = {
  en: enTranslations,
};

/**
 * Current locale (default: 'en').
 * In a full i18n implementation, this would be managed by state/context.
 */
let currentLocale: LocaleCode = 'en';

/**
 * Get the current locale.
 */
export function getLocale(): LocaleCode {
  return currentLocale;
}

/**
 * Set the current locale.
 */
export function setLocale(locale: LocaleCode): void {
  currentLocale = locale;
}

/**
 * Get a translation string by key path.
 *
 * @param key - Dot-separated key path (e.g., 'filters.tags.label')
 * @param params - Optional parameters for string interpolation
 * @returns Translated string with interpolated parameters
 *
 * @example
 * ```ts
 * t('filters.tags.label') // "Tags"
 * t('aria.removeTag', { tag: 'react' }) // "Remove tag react"
 * t('filters.videoCount.showing', { count: 5 }) // "Showing 5 videos"
 * ```
 */
export function t(key: TranslationKey, params?: Record<string, string | number>): string {
  const keys = key.split('.');
  let value: any = translations[currentLocale];

  // Navigate nested object
  for (const k of keys) {
    if (value && typeof value === 'object' && k in value) {
      value = value[k];
    } else {
      console.warn(`[i18n] Missing translation key: ${key}`);
      return key;
    }
  }

  // Handle pluralization (simple implementation)
  if (params && 'count' in params && typeof value === 'object') {
    const count = params.count;
    const pluralKey = count === 1 ? key : `${key}_plural`;

    // Check if plural form exists
    const pluralKeys = pluralKey.split('.');
    let pluralValue: any = translations[currentLocale];

    for (const k of pluralKeys) {
      if (pluralValue && typeof pluralValue === 'object' && k in pluralValue) {
        pluralValue = pluralValue[k];
      } else {
        // No plural form, use singular
        pluralValue = null;
        break;
      }
    }

    if (typeof pluralValue === 'string') {
      value = pluralValue;
    }
  }

  if (typeof value !== 'string') {
    console.warn(`[i18n] Translation key does not resolve to string: ${key}`);
    return key;
  }

  // Interpolate parameters
  if (params) {
    return value.replace(/\{(\w+)\}/g, (match, paramKey) => {
      return paramKey in params ? String(params[paramKey]) : match;
    });
  }

  return value;
}

/**
 * React hook for translations (for future integration with React context).
 *
 * @example
 * ```tsx
 * const { t } = useTranslations();
 * return <h1>{t('filters.tags.label')}</h1>;
 * ```
 */
export function useTranslations() {
  return {
    t,
    locale: currentLocale,
    setLocale,
  };
}

// Export all translations for direct access if needed
export { enTranslations };
