/**
 * FilterPills — required vs excluded entity distinction (Feature 062, FR-030).
 *
 * Entity pills already carry entity-TYPE colour, so colour cannot also carry
 * the required/excluded distinction — two signals competing for one channel.
 * FR-030 therefore requires a non-colour property: a distinct symbol and a
 * distinct textual prefix, surviving greyscale and reaching a screen reader.
 *
 * These tests assert on the DOM text and the symbol rather than on class names,
 * because a class-name assertion would pass even if both pills rendered
 * identically to someone who cannot perceive the colour.
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { FilterPills } from '../../components/FilterPills';

const REQUIRED = {
  type: 'entity' as const,
  value: '11111111-1111-4111-8111-111111111111',
  label: 'Ada Lovelace',
};
const EXCLUDED = {
  type: 'excluded_entity' as const,
  value: '22222222-2222-4222-8222-222222222222',
  label: 'Analytical Engine',
};

function renderPills() {
  return render(
    <FilterPills filters={[REQUIRED, EXCLUDED]} onRemove={() => {}} />
  );
}

describe('FilterPills — entity required/excluded distinction (FR-030)', () => {
  it('announces a distinct human-readable prefix for each', () => {
    const { container } = renderPills();
    const srTexts = Array.from(container.querySelectorAll('span.sr-only')).map(
      (el) => el.textContent?.trim() ?? ''
    );

    expect(srTexts).toContain('Required entity:');
    expect(srTexts).toContain('Excluded entity:');
    // The raw enum slug must not reach a listener.
    expect(srTexts.join(' ')).not.toContain('excluded_entity');
  });

  it('gives each pill a distinct symbol that survives greyscale', () => {
    const { container } = renderPills();
    const pills = Array.from(container.querySelectorAll('[role="listitem"]'));
    expect(pills).toHaveLength(2);

    const symbols = pills.map(
      (pill) => pill.querySelector('[aria-hidden="true"]')?.textContent ?? ''
    );
    expect(symbols[0]).not.toBe('');
    expect(symbols[1]).not.toBe('');
    // Different glyphs, so the distinction does not depend on hue at all.
    expect(symbols[0]).not.toBe(symbols[1]);
  });

  it('distinguishes the remove controls by name, not by position alone', () => {
    renderPills();
    expect(
      screen.getByRole('button', {
        name: 'Remove Required entity filter: Ada Lovelace',
      })
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', {
        name: 'Remove Excluded entity filter: Analytical Engine',
      })
    ).toBeInTheDocument();
  });

  it('remains distinguishable with all colour stripped from the markup', () => {
    // The strongest form of the requirement: remove every class attribute, so
    // no styling of any kind survives, and confirm the two pills are still
    // tellable apart from their text content alone.
    const { container } = renderPills();
    container.querySelectorAll('*').forEach((el) => el.removeAttribute('class'));

    const pills = Array.from(container.querySelectorAll('[role="listitem"]'));
    const [first, second] = pills.map((p) => p.textContent ?? '');

    expect(first).not.toBe(second);
    expect(first).toContain('Required entity');
    expect(second).toContain('Excluded entity');
  });
});
