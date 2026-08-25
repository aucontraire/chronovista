/**
 * Canonical BCP-47 language-code → display-name mapping (frontend).
 *
 * Single source of truth for language display names on the client. This mirrors
 * the backend canonical map in `src/chronovista/models/language_names.py`; there
 * is no cross-language codegen, so a change in one must be reflected in the
 * other. Region-qualified codes carry their region name (`es-MX` →
 * "Spanish (Mexico)").
 *
 * @module constants/languageNames
 */

export const LANGUAGE_NAMES: Record<string, string> = {
  // English variants
  en: 'English',
  'en-US': 'English (United States)',
  'en-GB': 'English (United Kingdom)',
  'en-AU': 'English (Australia)',
  'en-CA': 'English (Canada)',
  'en-IN': 'English (India)',
  // Spanish variants
  es: 'Spanish',
  'es-ES': 'Spanish (Spain)',
  'es-MX': 'Spanish (Mexico)',
  'es-AR': 'Spanish (Argentina)',
  'es-CO': 'Spanish (Colombia)',
  'es-419': 'Spanish (Latin America)',
  // French variants
  fr: 'French',
  'fr-FR': 'French (France)',
  'fr-CA': 'French (Canada)',
  // German variants
  de: 'German',
  'de-DE': 'German (Germany)',
  'de-AT': 'German (Austria)',
  'de-CH': 'German (Switzerland)',
  // Italian
  it: 'Italian',
  'it-IT': 'Italian (Italy)',
  // Portuguese variants
  pt: 'Portuguese',
  'pt-PT': 'Portuguese (Portugal)',
  'pt-BR': 'Portuguese (Brazil)',
  // Chinese variants
  zh: 'Chinese',
  'zh-CN': 'Chinese (Simplified)',
  'zh-TW': 'Chinese (Traditional)',
  'zh-HK': 'Chinese (Hong Kong)',
  // Japanese
  ja: 'Japanese',
  'ja-JP': 'Japanese (Japan)',
  // Korean
  ko: 'Korean',
  'ko-KR': 'Korean (Korea)',
  // Russian
  ru: 'Russian',
  'ru-RU': 'Russian (Russia)',
  // Arabic
  ar: 'Arabic',
  'ar-SA': 'Arabic (Saudi Arabia)',
  'ar-EG': 'Arabic (Egypt)',
  // Hindi
  hi: 'Hindi',
  'hi-IN': 'Hindi (India)',
  // Other major languages
  nl: 'Dutch',
  'nl-NL': 'Dutch (Netherlands)',
  sv: 'Swedish',
  no: 'Norwegian',
  da: 'Danish',
  fi: 'Finnish',
  pl: 'Polish',
  cs: 'Czech',
  hu: 'Hungarian',
  ro: 'Romanian',
  el: 'Greek',
  he: 'Hebrew',
  tr: 'Turkish',
  uk: 'Ukrainian',
  th: 'Thai',
  vi: 'Vietnamese',
  id: 'Indonesian',
  ms: 'Malay',
  tl: 'Tagalog',
  // Indian languages
  bn: 'Bengali',
  gu: 'Gujarati',
  kn: 'Kannada',
  ml: 'Malayalam',
  mr: 'Marathi',
  pa: 'Punjabi',
  ta: 'Tamil',
  te: 'Telugu',
  ur: 'Urdu',
};

/**
 * Human-readable display name for a language code.
 *
 * Tries an exact match (including regional variants), then falls back to the
 * base language name with the region appended (e.g. an unknown `es-CL` →
 * "Spanish (CL)"), and finally returns the code itself if unknown.
 *
 * @param code - BCP-47 language code (base or regional variant)
 * @returns Display name, or the code itself if no mapping exists
 */
export function getLanguageName(code: string): string {
  if (LANGUAGE_NAMES[code]) {
    return LANGUAGE_NAMES[code];
  }
  const parts = code.split('-');
  const baseCode = parts[0] || code;
  if (LANGUAGE_NAMES[baseCode]) {
    const region = parts.length > 1 && parts[1] ? ` (${parts[1]})` : '';
    return `${LANGUAGE_NAMES[baseCode]}${region}`;
  }
  return code;
}
