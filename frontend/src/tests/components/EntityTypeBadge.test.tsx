/**
 * EntityTypeBadge and EntityName — entity type identity (Feature 062, US4).
 *
 * Two treatments, deliberately:
 *
 * - `EntityTypeBadge` draws the type explicitly, for surfaces where the type
 *   IS the subject: the entities list, the entity detail header.
 * - `EntityName` colours the name and hides the type in screen-reader text,
 *   for dense surfaces where a chip beside every row is noise.
 *
 * Both consume `constants/entityTypes`, so the palette has exactly one
 * definition point (FR-029) and no surface can fork it.
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { EntityTypeBadge } from '../../components/EntityTypeBadge';
import { EntityName } from '../../components/EntityName';
import {
  ENTITY_TYPE_COLORS,
  ENTITY_TYPE_LABELS,
  ENTITY_TYPE_FALLBACK_COLOR,
} from '../../constants/entityTypes';

const ALL_TYPES = [
  'person',
  'organization',
  'place',
  'event',
  'work',
  'technical_term',
  'concept',
  'other',
] as const;

describe('EntityTypeBadge (FR-025, FR-026, FR-027, FR-028)', () => {
  it.each(ALL_TYPES)('renders %s with its established colour and label', (type) => {
    const { container } = render(<EntityTypeBadge entityType={type} />);
    const badge = container.firstElementChild;

    // Colour comes from the shared constant — asserted against the constant
    // itself, so a hardcoded copy anywhere would diverge and fail.
    for (const cls of ENTITY_TYPE_COLORS[type]!.split(' ')) {
      expect(badge).toHaveClass(cls);
    }
    // And the type is ALSO in text, so it survives colour removal (FR-027).
    expect(badge).toHaveTextContent(ENTITY_TYPE_LABELS[type]!);
  });

  it('covers every type the constants define, with no extras', () => {
    // Guards against a ninth type being added to the palette without this
    // suite noticing (FR-026: none added, none changed).
    expect(Object.keys(ENTITY_TYPE_COLORS).sort()).toEqual([...ALL_TYPES].sort());
  });

  it('falls back to the neutral treatment for an unrecognised type (FR-028)', () => {
    const { container } = render(<EntityTypeBadge entityType="not_a_real_type" />);
    const badge = container.firstElementChild;

    for (const cls of ENTITY_TYPE_FALLBACK_COLOR.split(' ')) {
      expect(badge).toHaveClass(cls);
    }
    // Shows the raw value rather than a generic word: that is what the
    // entities list has always done, and it tells a reader what the data
    // actually says instead of hiding it.
    expect(badge).toHaveTextContent('not_a_real_type');
  });

  it('falls back without breaking layout for a missing type', () => {
    const { container } = render(<EntityTypeBadge entityType={null} />);
    const badge = container.firstElementChild;

    expect(badge).toHaveTextContent('Unknown');
    // Layout classes still applied — the badge does not collapse.
    expect(badge).toHaveClass('inline-flex');
  });

  it('offers both sizes in use without changing the colour', () => {
    const { container: small } = render(
      <EntityTypeBadge entityType="person" size="sm" />
    );
    const { container: medium } = render(
      <EntityTypeBadge entityType="person" size="md" />
    );

    expect(small.firstElementChild).toHaveClass('text-xs');
    expect(medium.firstElementChild).toHaveClass('text-sm');
    expect(small.firstElementChild).toHaveClass('text-indigo-700');
    expect(medium.firstElementChild).toHaveClass('text-indigo-700');
  });

  it('identifies the type with all colour stripped (SC-010)', () => {
    // The strongest form: remove every class, and the type must still be
    // readable from text alone.
    const { container } = render(<EntityTypeBadge entityType="technical_term" />);
    container.querySelectorAll('*').forEach((el) => el.removeAttribute('class'));
    expect(container.textContent).toContain('Technical Term');
  });
});

describe('EntityName — the NAME in a type-coloured pill (FR-025, FR-029)', () => {
  it.each(ALL_TYPES)('gives %s the same full pill colours as the badge', (type) => {
    const { container: named } = render(
      <EntityName name="Ada Lovelace" entityType={type} />
    );
    const { container: badged } = render(<EntityTypeBadge entityType={type} />);

    // Background, text AND border all match the badge's — this is the same
    // pill, differing only in what it contains. Asserting the whole triplet is
    // the point: colouring only the text would look like a different element.
    for (const cls of ENTITY_TYPE_COLORS[type]!.split(' ')) {
      expect(named.firstElementChild).toHaveClass(cls);
      expect(badged.firstElementChild).toHaveClass(cls);
    }
    expect(named.firstElementChild).toHaveClass('rounded-full');
  });

  it('puts the NAME in the pill, not the type', () => {
    // The distinction between the legend treatment and the shorthand one.
    const { container } = render(
      <EntityName name="Ada Lovelace" entityType="person" />
    );
    // Clone and strip the visually-hidden node, so this measures what a
    // sighted reader actually sees rather than the DOM's full textContent.
    const clone = container.firstElementChild!.cloneNode(true) as HTMLElement;
    clone.querySelectorAll('.sr-only').forEach((el) => el.remove());

    expect(clone.textContent).toContain('Ada Lovelace');
    expect(clone.textContent).not.toContain('Person');
  });

  it('keeps the type available to screen readers', () => {
    render(<EntityName name="Ada Lovelace" entityType="person" />);
    expect(screen.getByText('Person:')).toHaveClass('sr-only');
    expect(screen.getByText('Ada Lovelace')).toBeInTheDocument();
  });

  it('falls back to the neutral pill for an unrecognised type', () => {
    const { container } = render(
      <EntityName name="Mystery" entityType="not_a_real_type" />
    );
    for (const cls of ENTITY_TYPE_FALLBACK_COLOR.split(' ')) {
      expect(container.firstElementChild).toHaveClass(cls);
    }
  });

  it('shows a mention tally as (N) inside the pill', () => {
    // One convention across the app: the video detail page's entity chips have
    // always shown counts this way, so a reader who learns it there reads it
    // on the videos list too.
    render(<EntityName name="Ada Lovelace" entityType="person" count={13} />);
    expect(screen.getByText('(13)')).toBeInTheDocument();
  });

  it('speaks the tally in full rather than as punctuation', () => {
    // A screen reader reading "open paren thirteen close paren" helps nobody,
    // so the shorthand is aria-hidden and a spoken form sits beside it.
    render(<EntityName name="Ada Lovelace" entityType="person" count={13} />);
    expect(screen.getByText('(13)')).toHaveAttribute('aria-hidden', 'true');
    expect(screen.getByText(', 13 mentions')).toHaveClass('sr-only');
  });

  it('singularises a tally of one', () => {
    render(<EntityName name="Ada Lovelace" entityType="person" count={1} />);
    expect(screen.getByText(', 1 mention')).toBeInTheDocument();
  });

  it('draws no tally when no count is given', () => {
    // The filter-panel pills carry no count; an empty "()" would be noise.
    const { container } = render(
      <EntityName name="Ada Lovelace" entityType="person" />
    );
    expect(container.textContent).not.toContain('(');
  });

  it('renders the same entity identically wherever it appears (SC-009)', () => {
    // Two independent renders of the same entity must be indistinguishable.
    // This is what makes the colour convention learnable: it only teaches
    // anything if it is the same everywhere.
    const { container: first } = render(
      <EntityName name="Israel" entityType="place" />
    );
    const { container: second } = render(
      <EntityName name="Israel" entityType="place" />
    );
    expect(first.firstElementChild?.className).toBe(
      second.firstElementChild?.className
    );
  });
});
