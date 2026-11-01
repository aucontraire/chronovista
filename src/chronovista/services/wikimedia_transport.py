"""Shared outbound-HTTP transport for the Wikidata / DBpedia / MediaWiki fetch layer.

This is the single component every thin knowledge-source client composes (Feature 102,
Phase B1). It owns everything that was copy-pasted across the five services and drifted:
the outbound identity (User-Agent), the per-request client lifecycle, the request timeout,
the unified rate-limit/backoff policy, the "reached-but-empty" vs "unreachable/error"
distinction, the single chunking helper, and the single MediaWiki continuation helper.

Each thin client keeps only its own endpoint/host, request parameters, and response parsing
(FR-009); it performs no outbound-HTTP scaffolding of its own.

The unreachable/error signal (:class:`WikidataUnavailable`) is an **internal** contract between
this transport and its thin clients (FR-004): the transport raises it, and each client makes a
deliberate absorb-or-propagate decision per the spec's per-service table. Only the Wikidata
client propagates it outward; the others absorb it into their documented fallback value.

Client lifecycle (clarified 2026-10-31): a fresh :class:`httpx.AsyncClient` per request by
default; a caller that owns the event loop may inject one via ``http=`` (then it is reused and
never closed here). A module-level shared client is forbidden — it binds to the loop that
created it and breaks on a second :meth:`WikimediaTransport.run_sync` call (FR-018).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterator, Sequence
from typing import Any, TypeVar

import httpx

from chronovista import __version__

T = TypeVar("T")
R = TypeVar("R")

# The single contact reference every outbound identity carries. Wikimedia's User-Agent policy
# gates request rate on a compliant UA that names a contact URL: a contactless UA is throttled
# to ~10 req/min (429s), a compliant one to ~200 req/min (see ADR-010). This is the one place the
# contact link is written; every service's identity is produced from it (G1).
_CONTACT_URL = "https://github.com/aucontraire/chronovista"

# Unified rate-limit/backoff policy (Decision D6). Single-and-shared across every service
# (FR-003): a Retry-After header is honored but capped, otherwise bounded exponential backoff,
# up to a single maximum number of attempts.
_MAX_ATTEMPTS = (
    3  # total tries (matches the category services' existing _MAX_RETRIES=3)
)
_BACKOFF_BASE = 1.0  # seconds; exponential base for a 429/5xx without Retry-After
_WAIT_CAP = (
    10.0  # seconds; the single cap on any backoff wait (largest existing finite cap)
)

_DEFAULT_CHUNK = (
    50  # the dominant MediaWiki/Wikidata batch size (wbgetentities ceiling)
)
_DEFAULT_TIMEOUT = 8.0


class WikidataUnavailable(Exception):
    """Reached-but-failed or unreachable — the canonical fetch-layer error signal.

    Raised INTERNALLY by :class:`WikimediaTransport` to its thin clients (FR-004) on a transport
    failure, exhausted retries, a non-JSON HTTP 200 body, or a MediaWiki/SPARQL error object inside
    an HTTP 200 body. It is distinct from a *reached-but-empty* result (a confirmed absence, which
    the transport returns as data): a client that confused the two would record a transient server
    error as a verified "nothing found."

    Each thin client absorbs or propagates it per the spec's per-service table; only the Wikidata
    client propagates it outward. The canonical definition lives here and is re-exported from
    ``wikidata_client`` so the existing ``except WikidataUnavailable`` catch sites and their import
    paths are unchanged (FR-011) and there is no circular import — the transport never imports a
    client. The name is kept (not renamed to ``WikimediaUnavailable``) for exactly that reason.
    """


def wikimedia_user_agent(component: str) -> str:
    """Produce the single-sourced outbound User-Agent for a fetch-layer component.

    This is the one site that assembles a User-Agent (G1, FR-002); no thin client builds the
    string itself. The product and version are shared; the contact URL is mandatory (Wikimedia
    policy); the per-``component`` label keeps each service's identity distinct.

    Parameters
    ----------
    component : str
        The per-client subsystem label, e.g. ``"dbpedia/sitelink resolver"``.

    Returns
    -------
    str
        ``chronovista/<version> (<contact-url>; <component>)``.
    """
    return f"chronovista/{__version__} ({_CONTACT_URL}; {component})"


def _norm(title: str) -> str:
    """Normalize a MediaWiki title for matching (``_`` and blanks map identically)."""
    return title.replace("_", " ").strip().lower()


def _merge_page(out: dict[str, dict[str, Any]], key: str, page: dict[str, Any]) -> None:
    """Accumulate one continuation page's object onto the page already stored under ``key``.

    MediaWiki repeats a page object across continuation pages, each carrying a further slice of a
    list-valued property (e.g. ``categories``). Merging concatenates those list slices and keeps
    the first-seen scalar values, so the fully-drained page carries the complete list.
    """
    existing = out.get(key)
    if existing is None:
        out[key] = dict(page)
        return
    for prop, value in page.items():
        prior = existing.get(prop)
        if isinstance(value, list) and isinstance(prior, list):
            existing[prop] = prior + value
        else:
            existing.setdefault(prop, value)


class WikimediaTransport:
    """The single outbound-HTTP transport the five thin knowledge-source clients compose."""

    def __init__(
        self,
        component: str,
        *,
        http: httpx.AsyncClient | None = None,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        """Construct a transport bound to one component identity.

        Parameters
        ----------
        component : str
            The subsystem label baked into this transport's User-Agent (see
            :func:`wikimedia_user_agent`).
        http : httpx.AsyncClient or None, optional
            An injected client. When ``None`` (the default) a fresh client is created per request
            and closed after it. When provided, it is reused and never closed here (the owning
            caller manages its lifetime).
        timeout : float, optional
            Per-request timeout in seconds (default ``8.0``).
        """
        self._component = component
        self._user_agent = wikimedia_user_agent(component)
        self._http = http
        self._timeout = timeout

    def _new_client(self) -> httpx.AsyncClient:
        """Create a per-request client (no shared default headers; the UA is set per request)."""
        return httpx.AsyncClient(timeout=self._timeout)

    @staticmethod
    def _is_retryable(status_code: int) -> bool:
        """True for a transient HTTP status worth retrying (rate limit or server error)."""
        return status_code == 429 or status_code >= 500

    @staticmethod
    def _exponential_wait(attempt: int) -> float:
        """Bounded exponential backoff (base ``1s``), capped — the response-less retry wait.

        Used for a 429/5xx without a Retry-After header AND for a transient transport error
        (timeout/connection reset), where there is no response to read a header from.
        """
        return min(_BACKOFF_BASE * float(2**attempt), _WAIT_CAP)

    def _backoff_wait(self, resp: httpx.Response, attempt: int) -> float:
        """The wait before the next retry: a capped Retry-After, else capped exponential backoff.

        A Retry-After header (seconds) is honored but capped at the unified maximum so a hostile or
        absurd value cannot stall a detached task; absent or unparseable, bounded exponential
        backoff (base ``1s``) is used, also capped.
        """
        retry_after = resp.headers.get("Retry-After")
        if retry_after is not None:
            try:
                return min(float(int(retry_after)), _WAIT_CAP)
            except ValueError:
                pass  # non-integer (e.g. an HTTP-date) -> fall back to exponential
        return self._exponential_wait(attempt)

    async def _run(
        self, perform: Callable[[httpx.AsyncClient], Awaitable[httpx.Response]]
    ) -> dict[str, Any]:
        """Execute one request through the unified retry/backoff + parse/error contract.

        Owns the per-request client lifecycle, the bounded backoff (429/5xx status AND transient
        timeout/connection-reset transport errors), and the unreachable detection. Raises
        :class:`WikidataUnavailable` on exhausted retries, a non-transient transport error, a
        non-JSON HTTP 200 body, a non-object JSON body, or an error object inside a 200 body;
        returns the parsed JSON object otherwise (a reached-but-empty valid result is not an error).
        """
        http = self._http or self._new_client()
        owns = self._http is None
        try:
            for attempt in range(_MAX_ATTEMPTS):
                try:
                    resp = await perform(http)
                except (httpx.TimeoutException, httpx.NetworkError) as exc:
                    # A TRANSIENT transport failure: a timeout, or a connect/read/write network
                    # reset. DBpedia SPARQL — the unreliable one-shot path FR-006's retry exists
                    # to protect — fails mostly this way, not by a 429/5xx status, so it must be
                    # retried under the same bounded policy or the retry barely helps.
                    if attempt < _MAX_ATTEMPTS - 1:
                        await asyncio.sleep(self._exponential_wait(attempt))
                        continue
                    raise WikidataUnavailable(str(exc)) from exc
                except httpx.HTTPError as exc:
                    # A NON-transient httpx error (InvalidURL, UnsupportedProtocol,
                    # TooManyRedirects, DecodingError): retrying is pointless — surface at once.
                    raise WikidataUnavailable(str(exc)) from exc
                if self._is_retryable(resp.status_code) and attempt < _MAX_ATTEMPTS - 1:
                    await asyncio.sleep(self._backoff_wait(resp, attempt))
                    continue
                try:
                    resp.raise_for_status()
                except httpx.HTTPError as exc:
                    raise WikidataUnavailable(str(exc)) from exc
                # A 200 with a non-JSON body (maintenance/CAPTCHA HTML, a truncated body) is a
                # FAILURE, not an absence — translate the ValueError so callers degrade (FR-004).
                try:
                    data: Any = resp.json()
                except ValueError as exc:
                    raise WikidataUnavailable(f"non-JSON response: {exc}") from exc
                if not isinstance(data, dict):
                    raise WikidataUnavailable("non-object JSON response")
                # MediaWiki/SPARQL report many failures (ratelimited, maxlag, bad params) as an
                # HTTP 200 carrying an {"error": ...} body. Treat it as unreachable on every
                # service (D7/FR-005), never as a proven absence that settles the entity forever.
                error = data.get("error")
                if error:
                    code = error.get("code") if isinstance(error, dict) else None
                    raise WikidataUnavailable(f"api error: {code or 'unknown'}")
                return data
            # Unreachable in practice: the final attempt always returns or raises above. Kept so
            # the function provably returns-or-raises on every path.
            raise WikidataUnavailable("retries exhausted")
        finally:
            if owns:
                await http.aclose()

    async def get_json(self, url: str, *, params: dict[str, Any]) -> dict[str, Any]:
        """GET ``url`` with ``params`` and return the parsed JSON object.

        Owns the User-Agent header, the timeout, the unified backoff, and the unreachable-vs-empty
        contract (see :meth:`_run`).

        Parameters
        ----------
        url : str
            The endpoint URL (owned by the thin client).
        params : dict[str, Any]
            Query parameters (owned by the thin client).

        Returns
        -------
        dict[str, Any]
            The parsed JSON object.

        Raises
        ------
        WikidataUnavailable
            On transport failure, exhausted retries, a non-JSON/non-object 200 body, or an
            error object in a 200 body.
        """

        def perform(http: httpx.AsyncClient) -> Awaitable[httpx.Response]:
            return http.get(
                url, params=params, headers={"User-Agent": self._user_agent}
            )

        return await self._run(perform)

    async def post_form(
        self,
        url: str,
        *,
        data: dict[str, str],
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """POST a form body to ``url`` (e.g. DBpedia SPARQL) and return the parsed JSON object.

        Same failure contract as :meth:`get_json`. The transport always sets the User-Agent;
        any ``headers`` the client supplies (e.g. ``Accept``) are merged on top.

        Parameters
        ----------
        url : str
            The endpoint URL (owned by the thin client).
        data : dict[str, str]
            The form fields (owned by the thin client).
        headers : dict[str, str] or None, optional
            Extra request headers merged over the transport-owned User-Agent.

        Returns
        -------
        dict[str, Any]
            The parsed JSON object.

        Raises
        ------
        WikidataUnavailable
            On the same conditions as :meth:`get_json`.
        """
        merged: dict[str, str] = {"User-Agent": self._user_agent}
        if headers:
            merged.update(headers)

        def perform(http: httpx.AsyncClient) -> Awaitable[httpx.Response]:
            return http.post(url, data=data, headers=merged)

        return await self._run(perform)

    @staticmethod
    def chunk(items: Sequence[T], size: int = _DEFAULT_CHUNK) -> Iterator[list[T]]:
        """Yield successive ``size``-length chunks of ``items`` (the single chunking helper).

        Default ``50`` is the dominant batch size; a thin client passes a different ``size`` only
        where an endpoint's own row-cap demands it (documented at that call), never an inline
        ``range(..., N)`` (G-dedup, FR-007).

        Parameters
        ----------
        items : Sequence[T]
            The items to batch.
        size : int, optional
            The maximum chunk length (default ``50``; must be ``>= 1``).

        Yields
        ------
        list[T]
            Each successive chunk, in order.
        """
        if size < 1:
            raise ValueError("chunk size must be >= 1")
        for start in range(0, len(items), size):
            yield list(items[start : start + size])

    async def paginate_mediawiki(
        self,
        url: str,
        *,
        params: dict[str, Any],
        continue_key: str = "clcontinue",
        max_pages: int,
    ) -> dict[str, Any]:
        """Drain a MediaWiki ``query`` across continuation pages (the single continuation helper).

        Follows the ``continue``/``continue_key`` tokens, re-attributes MediaWiki's
        ``normalized``/``redirects`` hops back to the caller's originally-requested titles (the
        v0.104.1 false-zero fix), and merges each page's list-valued props across continuation
        pages. The result is keyed by the caller's *original* input titles.

        Reached means present: a REACHED batch returns an entry for EVERY requested title —
        including a title Wikipedia reports ``missing``/``invalid``, which comes back
        **present-empty** (its page object carries no list-valued prop, so a caller reads it as
        "reached, nothing there"). A title resolving with no categories is likewise present-empty.
        The only page skipped is one whose resolved title maps to no requested original (a genuinely
        unmappable page — defensive). Thus **absence from the result means the batch was UNREACHABLE**
        (this method raised), never a reached-but-settled title — the invariant the operator-facing
        outage reporting relies on (FR-017/SC-007). Exceeding ``max_pages`` raises — an explicit
        incomplete signal, never a silently truncated prefix presented as complete (G3/SC-004).

        Parameters
        ----------
        url : str
            The MediaWiki API endpoint (owned by the thin client).
        params : dict[str, Any]
            The query parameters, including a pipe-joined ``titles`` field. ``continue`` tokens are
            layered on top per page; the caller's params are not mutated.
        continue_key : str, optional
            The continuation token to follow (default ``"clcontinue"`` — the categories/members
            listing token, which is the sole continuation this fetch layer paginates today; a
            caller paginating a different list passes its own). Defaulting it here keeps the token
            literal in exactly one site (G2): no thin client re-names it.
        max_pages : int
            The maximum number of continuation pages before raising incomplete.

        Returns
        -------
        dict[str, Any]
            ``{original_title: merged_page_object}`` for every REACHED title (present, possibly
            empty — a missing/invalid page is present with no list-valued prop).

        Raises
        ------
        WikidataUnavailable
            On a transport/parse failure in any page (via :meth:`get_json`), or when the
            continuation exceeds ``max_pages``.
        """
        titles_param = str(params.get("titles", ""))
        by_norm = {_norm(t): t for t in titles_param.split("|") if t}
        pages_out: dict[str, dict[str, Any]] = {}
        cont: dict[str, str] = {}
        for _ in range(max_pages):
            data = await self.get_json(url, params={**params, **cont})
            query = data.get("query")
            if isinstance(query, dict):
                # Fold MediaWiki's own normalized->redirect hop chain back onto the caller's
                # original input title; 'normalized' before 'redirects' resolves the
                # (input -> canonical -> target) chain in order. Idempotent per page.
                for hop_key in ("normalized", "redirects"):
                    hops = query.get(hop_key)
                    if not isinstance(hops, list):
                        continue
                    for hop in hops:
                        if not isinstance(hop, dict):
                            continue
                        origin = by_norm.get(_norm(str(hop.get("from", ""))))
                        if origin is not None:
                            by_norm[_norm(str(hop.get("to", "")))] = origin
                pages = query.get("pages")
                if isinstance(pages, dict):
                    for page in pages.values():
                        if not isinstance(page, dict):
                            continue
                        original = by_norm.get(_norm(str(page.get("title", ""))))
                        if original is None:
                            # A page that maps to no requested original title (genuinely
                            # unmappable) is skipped — defensive. Every reached request title
                            # otherwise appears, so absence from the result means unreachable.
                            continue
                        # A ``missing``/``invalid`` page is INCLUDED as present-empty: it carries no
                        # list-valued prop (e.g. ``categories``), so it reads as "reached, nothing
                        # there" (settled), distinct from an absent title (unreachable — raised).
                        _merge_page(pages_out, original, page)
            cont_block = data.get("continue")
            if isinstance(cont_block, dict) and continue_key in cont_block:
                cont = {k: str(v) for k, v in cont_block.items()}
                continue
            return pages_out
        raise WikidataUnavailable(
            f"pagination exceeded max_pages={max_pages} (incomplete result)"
        )

    def run_sync(self, coro_factory: Callable[[WikimediaTransport], Awaitable[R]]) -> R:
        """Run an async fetch synchronously, owning a fresh event loop and a per-call client.

        The synchronous entry for Phase B2's all-synchronous scripts (FR-018): it owns its own
        event loop via :func:`asyncio.run` and constructs a per-call client, so it is safe to call
        more than once in a process (each call gets a new loop and client — no dead-loop binding).
        ``coro_factory`` receives a transport bound to that per-call client and may issue several
        awaited requests through it.

        Parameters
        ----------
        coro_factory : Callable[[WikimediaTransport], Awaitable[R]]
            A factory given a transport over the per-call client, returning the awaitable to run.

        Returns
        -------
        R
            Whatever ``coro_factory``'s awaitable resolves to.
        """

        async def _main() -> R:
            async with httpx.AsyncClient(timeout=self._timeout) as http:
                transport = WikimediaTransport(
                    self._component, http=http, timeout=self._timeout
                )
                return await coro_factory(transport)

        return asyncio.run(_main())
