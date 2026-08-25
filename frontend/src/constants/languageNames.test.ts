/**
 * Unit tests for the canonical language-name single source of truth.
 *
 * @module constants/languageNames.test
 */

import { describe, it, expect } from 'vitest';
import { LANGUAGE_NAMES, getLanguageName } from './languageNames';

describe('getLanguageName', () => {
  it('returns the base language name', () => {
    expect(getLanguageName('en')).toBe('English');
  });

  it('returns the region-qualified name for a known variant', () => {
    expect(getLanguageName('es-MX')).toBe('Spanish (Mexico)');
  });

  it('falls back to base name + region for an unknown variant', () => {
    expect(getLanguageName('es-CL')).toBe('Spanish (CL)');
  });

  it('returns the code itself when completely unknown', () => {
    expect(getLanguageName('xyz')).toBe('xyz');
  });
});

describe('LANGUAGE_NAMES corrected labels', () => {
  it.each([
    ['es-MX', 'Spanish (Mexico)'],
    ['es-ES', 'Spanish (Spain)'],
    ['ru-RU', 'Russian (Russia)'],
    ['hi-IN', 'Hindi (India)'],
    ['en-IN', 'English (India)'],
  ])('maps %s to the correct country name', (code, expected) => {
    expect(LANGUAGE_NAMES[code]).toBe(expected);
  });

  it('contains none of the previously scrambled labels', () => {
    const wrong = [
      'Spanish (Peru)',
      'Spanish (Portugal)',
      'Russian (Norway)',
      'Hindi (Finland)',
      'English (Finland)',
    ];
    const values = Object.values(LANGUAGE_NAMES);
    for (const label of wrong) {
      expect(values).not.toContain(label);
    }
  });
});
