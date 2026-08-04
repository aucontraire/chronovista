/**
 * CooccurringPanel — appears-with panel states and behaviour (Feature 062, US3).
 *
 * Covers the four states FR-036/FR-038 require to be distinct (loading, empty,
 * scope-restricted empty, error), the reveal-more bound (FR-023/FR-023a), and
 * the address scheme the panel hands to the videos list (FR-022, FR-024a).
 *
 * Kept under `src/tests/` so it is typechecked.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { CooccurringPanel } from '../../components/entity/CooccurringPanel';

const hookMock = vi.fn();
vi.mock('../../hooks/useCooccurringEntities', async () => {
  const actual = await vi.importActual<
    typeof import('../../hooks/useCooccurringEntities')
  >('../../hooks/useCooccurringEntities');
  return {
    ...actual,
    useCooccurringEntities: (...args: unknown[]) => hookMock(...args),
  };
});

const SUBJECT = '11111111-1111-4111-8111-111111111111';
const PARTNER = '22222222-2222-4222-8222-222222222222';

function partner(overrides: Record<string, unknown> = {}) {
  return {
    entity_id: PARTNER,
    entity_type: 'organization',
    canonical_name: 'Analytical Engine',
    shared_video_count: 261,
    ...overrides,
  };
}

function state(overrides: Record<string, unknown> = {}) {
  return {
    partners: [],
    isLoading: false,
    isError: false,
    error: null,
    ...overrides,
  };
}

function renderPanel(props: Record<string, unknown> = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <CooccurringPanel entityId={SUBJECT} {...props} />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('CooccurringPanel (Feature 062, US3)', () => {
  beforeEach(() => {
    hookMock.mockReset();
  });

  describe('states are distinct (FR-036, FR-038)', () => {
    it('shows a loading state that is neither empty nor error', () => {
      hookMock.mockReturnValue(state({ isLoading: true }));
      renderPanel();

      expect(screen.getByTestId('cooccurring-loading')).toBeInTheDocument();
      expect(screen.queryByTestId('cooccurring-empty')).not.toBeInTheDocument();
      expect(screen.queryByTestId('cooccurring-error')).not.toBeInTheDocument();
    });

    it('renders a clean empty state, not an error (FR-024)', () => {
      hookMock.mockReturnValue(state({ partners: [] }));
      renderPanel();

      expect(screen.getByTestId('cooccurring-empty')).toBeInTheDocument();
      expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    });

    it('distinguishes an empty result under a restricted scope (FR-024d)', () => {
      // "Nothing co-occurs" and "nothing co-occurs UNDER THIS SCOPE" are
      // different facts and suggest different actions.
      hookMock.mockReturnValue(state({ partners: [] }));
      renderPanel({ minEvidence: 'transcript' });

      expect(screen.getByText(/Transcript-only is active/)).toBeInTheDocument();
      expect(screen.getByText(/may reveal connections/)).toBeInTheDocument();
    });

    it('does not mention the scope when none is active', () => {
      hookMock.mockReturnValue(state({ partners: [] }));
      renderPanel();

      expect(screen.queryByText(/Transcript-only is active/)).not.toBeInTheDocument();
    });

    it('degrades to a panel-level error, leaving the page usable (FR-038)', () => {
      hookMock.mockReturnValue(state({ isError: true, error: new Error('boom') }));
      renderPanel();

      const error = screen.getByTestId('cooccurring-error');
      expect(error).toBeInTheDocument();
      expect(error).toHaveTextContent(/rest of this page is unaffected/i);
      // The panel still renders its own heading — it has not taken the page
      // down with it.
      expect(screen.getByText('Appears with')).toBeInTheDocument();
    });
  });

  describe('partner rows', () => {
    it('shows each partner name, type-coloured, with its shared-video count', () => {
      hookMock.mockReturnValue(state({ partners: [partner()] }));
      const { container } = renderPanel();

      expect(screen.getByText('Analytical Engine')).toBeInTheDocument();
      expect(screen.getByText('261 videos')).toBeInTheDocument();

      // The type is carried by the NAME's colour, not a separate chip — a chip
      // beside every row made the panel busy. The type still reaches screen
      // readers through visually-hidden text.
      expect(screen.getByText('Organization:')).toHaveClass('sr-only');
      const name = container.querySelector('.text-violet-700');
      expect(name).not.toBeNull();
      expect(name).toHaveTextContent('Analytical Engine');
    });

    it('singularises a count of one', () => {
      hookMock.mockReturnValue(
        state({ partners: [partner({ shared_video_count: 1 })] })
      );
      renderPanel();

      expect(screen.getByText('1 video')).toBeInTheDocument();
    });
  });

  describe('address scheme (FR-022, FR-024a)', () => {
    it('links to the two-entity intersection using repeated entity_id keys', () => {
      hookMock.mockReturnValue(state({ partners: [partner()] }));
      renderPanel();

      const href = screen.getByRole('link').getAttribute('href') ?? '';
      const params = new URLSearchParams(href.split('?')[1]);
      // Both entities present, as repeated keys — the same scheme the videos
      // list reads, not a parallel one.
      expect(params.getAll('entity_id')).toEqual([SUBJECT, PARTNER]);
    });

    it('targets /videos, not the root', () => {
      // The root is an index route that redirects with
      // `<Navigate to="/videos" replace />`, and that redirect carries NO
      // query string. Linking to `/?entity_id=…` therefore lands on an
      // unfiltered videos page with every parameter silently dropped — the
      // href looks correct on hover and the destination is wrong.
      //
      // This assertion exists because the params-only test above passed
      // while the feature was broken: it checked what the link carried and
      // never checked where it pointed.
      hookMock.mockReturnValue(state({ partners: [partner()] }));
      renderPanel();

      const href = screen.getByRole('link').getAttribute('href') ?? '';
      expect(href.split('?')[0]).toBe('/videos');
    });

    it('carries the active evidence scope forward', () => {
      // Otherwise the panel computes under one definition and the page it
      // opens computes under another, and the counts disagree.
      hookMock.mockReturnValue(state({ partners: [partner()] }));
      renderPanel({ minEvidence: 'transcript' });

      const href = screen.getByRole('link').getAttribute('href') ?? '';
      expect(new URLSearchParams(href.split('?')[1]).get('min_evidence')).toBe(
        'transcript'
      );
    });

    it('omits the scope parameter when none is active', () => {
      hookMock.mockReturnValue(state({ partners: [partner()] }));
      renderPanel();

      const href = screen.getByRole('link').getAttribute('href') ?? '';
      expect(new URLSearchParams(href.split('?')[1]).has('min_evidence')).toBe(
        false
      );
    });
  });

  describe('reveal more (FR-023, FR-023a)', () => {
    it('offers reveal-more only when the list filled the requested bound', () => {
      // Fewer partners than requested means there is nothing further to show.
      hookMock.mockReturnValue(state({ partners: [partner()] }));
      renderPanel();

      expect(
        screen.queryByRole('button', { name: 'Show more' })
      ).not.toBeInTheDocument();
    });

    it('requests a further tranche of the same size when revealed', async () => {
      const user = userEvent.setup();
      const full = Array.from({ length: 12 }, (_, i) =>
        partner({ entity_id: `p${i}`, canonical_name: `Partner ${i}` })
      );
      hookMock.mockReturnValue(state({ partners: full }));
      renderPanel();

      await user.click(screen.getByRole('button', { name: 'Show more' }));

      await waitFor(() => {
        // Second positional argument is the limit.
        const limits = hookMock.mock.calls.map((call) => call[1]);
        expect(limits).toContain(24);
      });
    });

    it('passes the subject id and scope through to the hook', () => {
      hookMock.mockReturnValue(state({ partners: [] }));
      renderPanel({ minEvidence: 'transcript' });

      expect(hookMock).toHaveBeenCalledWith(SUBJECT, 12, 'transcript');
    });
  });
});
