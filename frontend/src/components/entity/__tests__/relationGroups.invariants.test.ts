/**
 * Invariants of the FORWARD relation grouping (Feature 087).
 *
 * This pins the frontend forward-display grouping (`../relationGroups.ts`) against the two rules it
 * must share with the backend inverse grouping: the synonym union (membership = member_of + part_of)
 * and the attribute-field exclusions. It imports ONLY the frontend module — it is not a cross-process
 * parity check. The backend inverse grouping has its own invariant test
 * (tests/unit/services/test_relation_groups.py), and the two definitions intentionally differ in
 * keys and labels (forward vs inverse), so a single shared literal is not expected.
 */

import { describe, it, expect } from 'vitest';

import { RELATION_GROUPS, relationGroupForField } from '../relationGroups';

describe('forward relationGroups invariants', () => {
  it('unions exactly member_of and part_of under membership', () => {
    const membership = RELATION_GROUPS.find((g) => g.key === 'membership');
    expect(membership).toBeDefined();
    expect([...(membership?.fields ?? [])].sort()).toEqual(['member_of', 'part_of']);
  });

  it('encodes the expected forward group keys', () => {
    expect(RELATION_GROUPS.map((g) => g.key).sort()).toEqual(
      [
        'child', 'employment', 'father', 'founder', 'membership',
        'mother', 'sibling', 'significant_person', 'spouse',
      ].sort()
    );
    expect(relationGroupForField('employer')?.key).toBe('employment');
  });

  it('excludes attribute fields', () => {
    for (const field of ['country', 'place_of_birth', 'place_of_death']) {
      expect(relationGroupForField(field)).toBeUndefined();
    }
  });

  it('gives every group a specific label and a Wikidata-attributed phrasing', () => {
    for (const group of RELATION_GROUPS) {
      expect(group.label.length).toBeGreaterThan(0);
      expect(group.attribution).toMatch(/Wikidata/);
      expect(`${group.label} ${group.attribution}`).not.toMatch(
        /related to|connected with/i
      );
    }
  });
});
