/**
 * Case- and accent-insensitive name fold.
 *
 * Mirrors the backend's `lower(unaccent(...))` membership fold (Feature 069)
 * closely enough for name equality: strip combining diacritics, lowercase, and
 * trim surrounding whitespace. Used to decide whether an alias is the entity's
 * own name ("Primary") on the entity detail page, so the marker agrees with how
 * the application already regards names as equal.
 *
 * This is a display-time comparison helper, not a data operation — it is never
 * persisted or sent to the backend.
 *
 * @param value - The raw name to fold.
 * @returns The folded form (NFD, diacritics removed, lowercased, trimmed).
 */
export function foldName(value: string): string {
  return value
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase()
    .trim();
}
