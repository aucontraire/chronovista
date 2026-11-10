/**
 * EntityChannelsPanel — states, in-library links, external labelling.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { EntityChannelsPanel } from '../EntityChannelsPanel';

const hookMock = vi.fn();
vi.mock('../../../hooks/useEntityChannels', () => ({
  useEntityChannels: (...args: unknown[]) => hookMock(...args),
}));

const ENTITY = '11111111-1111-4111-8111-111111111111';

function state(overrides: Record<string, unknown> = {}) {
  return { channels: [], isLoading: false, isError: false, error: null, ...overrides };
}

function renderPanel() {
  return render(
    <MemoryRouter>
      <EntityChannelsPanel entityId={ENTITY} />
    </MemoryRouter>
  );
}

describe('EntityChannelsPanel', () => {
  beforeEach(() => hookMock.mockReset());

  it('renders the Operates heading and passes the entity id to the hook', () => {
    hookMock.mockReturnValue(state());
    renderPanel();
    expect(screen.getByRole('heading', { name: 'Operates' })).toBeInTheDocument();
    expect(hookMock).toHaveBeenCalledWith(ENTITY);
  });

  it('shows a loading status', () => {
    hookMock.mockReturnValue(state({ isLoading: true }));
    renderPanel();
    expect(screen.getByRole('status')).toHaveTextContent(/finding channels/i);
  });

  it('shows an error alert', () => {
    hookMock.mockReturnValue(state({ isError: true }));
    renderPanel();
    expect(screen.getByRole('alert')).toHaveTextContent(/couldn't load channels/i);
  });

  it('shows an empty message', () => {
    hookMock.mockReturnValue(state());
    renderPanel();
    expect(screen.getByRole('status')).toHaveTextContent(/no channels are recorded/i);
  });

  it('links in-library channels to the channel page', () => {
    hookMock.mockReturnValue(
      state({ channels: [{ channel_id: 'UC_lib', title: 'Placeholder Channel', in_library: true }] })
    );
    renderPanel();
    expect(screen.getByRole('link', { name: 'Placeholder Channel' })).toHaveAttribute(
      'href',
      '/channels/UC_lib'
    );
    expect(screen.queryByText('external')).not.toBeInTheDocument();
  });

  it('renders external channels as a labelled non-link', () => {
    hookMock.mockReturnValue(
      state({ channels: [{ channel_id: 'UC_ext', title: null, in_library: false }] })
    );
    renderPanel();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
    expect(screen.getByText('UC_ext')).toBeInTheDocument();
    expect(screen.getByText('external')).toBeInTheDocument();
  });
});
