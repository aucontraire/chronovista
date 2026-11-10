/**
 * EntityChannelsPanel — states, in-library links, external labelling.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

import { EntityChannelsPanel } from '../EntityChannelsPanel';

const hookMock = vi.fn();
vi.mock('../../../hooks/useEntityChannels', () => ({
  useEntityChannels: (...args: unknown[]) => hookMock(...args),
}));

const addMutate = vi.fn();
const removeMutate = vi.fn();
let addState: Record<string, unknown> = {};
vi.mock('../../../hooks/useEntityChannelMutations', () => ({
  useRemoveEntityChannel: () => ({
    mutate: removeMutate,
    isPending: false,
    isError: false,
    error: null,
  }),
  useAddEntityChannel: () => ({
    mutate: addMutate,
    isPending: false,
    isError: false,
    error: null,
    reset: vi.fn(),
    ...addState,
  }),
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
  beforeEach(() => {
    hookMock.mockReset();
    addMutate.mockReset();
    removeMutate.mockReset();
    addState = {};
  });

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
      state({ channels: [{ channel_id: 'UC_lib', title: 'Placeholder Channel', in_library: true, provenance: 'wikidata' }] })
    );
    renderPanel();
    expect(screen.getByRole('link', { name: 'Placeholder Channel' })).toHaveAttribute(
      'href',
      '/channels/UC_lib'
    );
    expect(screen.queryByText('not in library')).not.toBeInTheDocument();
  });

  it('links external channels out to YouTube with a not-in-library marker', () => {
    hookMock.mockReturnValue(
      state({ channels: [{ channel_id: 'UC_ext', title: null, in_library: false, provenance: 'manual' }] })
    );
    renderPanel();
    const link = screen.getByRole('link', { name: /UC_ext/ });
    expect(link).toHaveAttribute('href', 'https://www.youtube.com/channel/UC_ext');
    expect(link).toHaveAttribute('rel', expect.stringContaining('noreferrer'));
    expect(screen.getByText('not in library')).toBeInTheDocument();
  });

  it('renders a provenance badge for each source', () => {
    hookMock.mockReturnValue(
      state({
        channels: [
          { channel_id: 'UC_a', title: 'A', in_library: true, provenance: 'wikidata' },
          { channel_id: 'UC_b', title: 'B', in_library: true, provenance: 'manual' },
        ],
      })
    );
    renderPanel();
    expect(screen.getByText('per Wikidata')).toBeInTheDocument();
    expect(screen.getByText('you added')).toBeInTheDocument();
  });

  it('submits the trimmed ref and clears the input on success', async () => {
    hookMock.mockReturnValue(state());
    addMutate.mockImplementation((_ref: string, opts?: { onSuccess?: () => void }) => opts?.onSuccess?.());
    renderPanel();
    const input = screen.getByLabelText(/add a channel/i);
    await userEvent.type(input, '  UC_new  ');
    await userEvent.click(screen.getByRole('button', { name: 'Add channel' }));
    expect(addMutate).toHaveBeenCalledWith('UC_new', expect.any(Object));
    expect(input).toHaveValue('');
  });

  it('shows the server reason on 409', () => {
    hookMock.mockReturnValue(state());
    addState = { isError: true, error: { status: 409, detail: 'Already recorded from Wikidata' } };
    renderPanel();
    expect(screen.getByRole('alert')).toHaveTextContent('Already recorded from Wikidata');
  });

  it('shows format guidance on 422', () => {
    hookMock.mockReturnValue(state());
    addState = { isError: true, error: { status: 422 } };
    renderPanel();
    expect(screen.getByRole('alert')).toHaveTextContent(
      'Enter a channel ID (UC…) or a youtube.com/channel/… URL'
    );
  });

  it('offers remove only on manual rows and calls it with the channel id', async () => {
    hookMock.mockReturnValue(
      state({
        channels: [
          { channel_id: 'UC_a', title: 'Wiki Chan', in_library: true, provenance: 'wikidata' },
          { channel_id: 'UC_b', title: 'Manual Chan', in_library: true, provenance: 'manual' },
        ],
      })
    );
    renderPanel();
    expect(screen.getAllByRole('button', { name: /^remove/i })).toHaveLength(1);
    expect(screen.queryByRole('button', { name: /remove wiki chan/i })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /remove manual chan/i }));
    expect(removeMutate).toHaveBeenCalledWith('UC_b');
  });
});
