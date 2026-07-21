/**
 * Recovery for stale lazy-loaded chunks after a redeploy.
 *
 * The app code-splits routes with `React.lazy(() => import(...))`. Vite emits
 * content-hashed chunk filenames, so a rebuild/redeploy replaces every chunk
 * with a new hash and removes the old files. A browser tab still running the
 * *previous* build then tries to import a chunk name that no longer exists on
 * the server, which 404s and surfaces as
 * "Failed to fetch dynamically imported module".
 *
 * Vite dispatches a `vite:preloadError` event when a dynamic import fails. We
 * handle it by reloading the page once, which fetches a fresh `index.html`
 * (served with `Cache-Control: no-cache`) that references the current hashes.
 * A short guard in `sessionStorage` prevents a reload loop if the reload does
 * not resolve the failure (e.g. a genuinely offline network).
 */

const RELOAD_GUARD_KEY = "vite-preload-reloaded-at";
const RELOAD_GUARD_WINDOW_MS = 10_000;

/**
 * Install the `vite:preloadError` handler that reloads once on a failed
 * dynamic import. Safe to call once at app startup.
 */
export function installPreloadErrorReload(): void {
  window.addEventListener("vite:preloadError", (event) => {
    const last = Number(sessionStorage.getItem(RELOAD_GUARD_KEY) ?? "0");
    if (Date.now() - last <= RELOAD_GUARD_WINDOW_MS) {
      // Already reloaded very recently — don't loop; let the error surface.
      return;
    }
    sessionStorage.setItem(RELOAD_GUARD_KEY, String(Date.now()));
    // Prevent Vite from throwing the unhandled error before we reload.
    event.preventDefault();
    window.location.reload();
  });
}
