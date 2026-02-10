/**
 * useOnlineStatus hook for detecting online/offline network status.
 *
 * Implements T084: Offline indicator detection
 *
 * @example
 * ```tsx
 * const isOnline = useOnlineStatus();
 *
 * return (
 *   <div>
 *     {!isOnline && <OfflineBanner />}
 *     <Content />
 *   </div>
 * );
 * ```
 */

import { useState, useEffect } from 'react';

/**
 * Hook that returns the current online/offline status.
 *
 * Listens to browser online/offline events and updates state accordingly.
 * Returns `true` when online, `false` when offline.
 *
 * @returns Current online status
 */
export function useOnlineStatus(): boolean {
  const [isOnline, setIsOnline] = useState(
    typeof navigator !== 'undefined' ? navigator.onLine : true
  );

  useEffect(() => {
    const handleOnline = () => setIsOnline(true);
    const handleOffline = () => setIsOnline(false);

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);

  return isOnline;
}
