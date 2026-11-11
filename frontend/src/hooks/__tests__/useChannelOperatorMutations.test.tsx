import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

import { useAssignChannelOperator, useRemoveChannelOperator } from '../useChannelOperatorMutations';

const assignMock = vi.fn();
const removeMock = vi.fn();
vi.mock('../../api/channelOwnership', () => ({
  assignChannelOperator: (...args: unknown[]) => assignMock(...args),
  removeChannelOperator: (...args: unknown[]) => removeMock(...args),
}));

function setup() {
  const client = new QueryClient();
  const spy = vi.spyOn(client, 'invalidateQueries');
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { spy, wrapper };
}

describe('channel-side ownership mutations', () => {
  beforeEach(() => {
    assignMock.mockReset();
    removeMock.mockReset();
  });

  it('assign: invalidates that channel\'s operators and that entity\'s channels', async () => {
    assignMock.mockResolvedValue({ entity_id: 'ent-1', entity_type: 'person', canonical_name: 'X', provenance: 'manual' });
    const { spy, wrapper } = setup();
    const { result } = renderHook(() => useAssignChannelOperator('UC_chan'), { wrapper });
    result.current.mutate('ent-1');
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(assignMock).toHaveBeenCalledWith('UC_chan', 'ent-1');
    expect(spy).toHaveBeenCalledWith({ queryKey: ['channel-operators', 'UC_chan'] });
    expect(spy).toHaveBeenCalledWith({ queryKey: ['entityChannels', 'ent-1'] });
  });

  it('remove: invalidates that channel\'s operators and that entity\'s channels', async () => {
    removeMock.mockResolvedValue(undefined);
    const { spy, wrapper } = setup();
    const { result } = renderHook(() => useRemoveChannelOperator('UC_chan'), { wrapper });
    result.current.mutate('ent-1');
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(removeMock).toHaveBeenCalledWith('UC_chan', 'ent-1');
    expect(spy).toHaveBeenCalledWith({ queryKey: ['channel-operators', 'UC_chan'] });
    expect(spy).toHaveBeenCalledWith({ queryKey: ['entityChannels', 'ent-1'] });
  });
});
