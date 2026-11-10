import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

import { useAddEntityChannel, useRemoveEntityChannel } from '../useEntityChannelMutations';

const addMock = vi.fn();
const removeMock = vi.fn();
vi.mock('../../api/channelOwnership', () => ({
  addEntityChannel: (...args: unknown[]) => addMock(...args),
  removeEntityChannel: (...args: unknown[]) => removeMock(...args),
}));

function setup() {
  const client = new QueryClient();
  const spy = vi.spyOn(client, 'invalidateQueries');
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { spy, wrapper };
}

describe('entity-side ownership mutations', () => {
  beforeEach(() => {
    addMock.mockReset();
    removeMock.mockReset();
  });

  it('add: invalidates the entity list and the channel-operators family', async () => {
    addMock.mockResolvedValue({ channel_id: 'UC_x', title: null, in_library: false, provenance: 'manual' });
    const { spy, wrapper } = setup();
    const { result } = renderHook(() => useAddEntityChannel('ent-1'), { wrapper });
    result.current.mutate('UC_x');
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(addMock).toHaveBeenCalledWith('ent-1', 'UC_x');
    expect(spy).toHaveBeenCalledWith({ queryKey: ['entityChannels', 'ent-1'] });
    expect(spy).toHaveBeenCalledWith({ queryKey: ['channel-operators'] });
  });

  it('remove: invalidates the entity list and that channel\'s operators', async () => {
    removeMock.mockResolvedValue(undefined);
    const { spy, wrapper } = setup();
    const { result } = renderHook(() => useRemoveEntityChannel('ent-1'), { wrapper });
    result.current.mutate('UC_chan');
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(removeMock).toHaveBeenCalledWith('ent-1', 'UC_chan');
    expect(spy).toHaveBeenCalledWith({ queryKey: ['entityChannels', 'ent-1'] });
    expect(spy).toHaveBeenCalledWith({ queryKey: ['channel-operators', 'UC_chan'] });
  });
});
