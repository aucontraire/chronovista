"""Shared entity→category coverage logic (Feature 084).

One implementation of "give this entity its Wikipedia categories", invoked by the two
orchestrations FR-003 requires it to serve — never a parallel pipeline:

1. the on-approval enrichment seam (``EntityEnrichmentService._store_categories``), per entity,
   **add-only**; and
2. the backfill batch (``scripts/utilities/backfill_entity_categories.py``), which **adds** for the
   ~1,441 uncategorized entities and **replaces** the existing ~373's DBpedia categories with the
   Wikipedia namespace.

Title resolution, the fetch wiring, the upsert+assign, and the incremental global-size fill all
live here so neither caller re-implements them. The batch drives the *same* fetch service with many
titles at once (rate-efficiency, FR-014) and reuses :func:`resolve_article_title` and
:func:`store_categories_for_entity` directly; the single-entity caller uses :func:`categorize_entity`.

Name-free: article titles and category names are runtime data, never embedded in source.
"""

from __future__ import annotations

import datetime
import urllib.parse
import uuid
from collections.abc import Callable
from typing import Any

import httpx
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.repositories.entity_category_repository import EntityCategoryRepository
from chronovista.repositories.wikipedia_category_repository import (
    WikipediaCategoryRepository,
)
from chronovista.services.category_size import CategorySizeService
from chronovista.services.dbpedia_resolver import DbpediaResolver
from chronovista.services.entity_category_fetch import EntityCategoryFetchService
from chronovista.services.wikidata_client import WikidataClient, WikidataUnavailable

#: Every assignment this feature writes carries this source — one uniform namespace (FR-007).
WIKIPEDIA_SOURCE = "wikipedia"

_DBPEDIA_RESOURCE_MARKER = "/resource/"
_CATEGORY_PREFIX = "Category:"


def _norm(name: str) -> str:
    """Normalize a category name for de-duplication (``_``/blanks and case fold together)."""
    return name.replace("_", " ").strip().lower()


#: A per-language fetch-service factory — injectable so tests can supply a MockTransport-backed
#: service per language. The default constructs one bound to that language's Wikipedia.
FetchServiceFactory = Callable[[str], EntityCategoryFetchService]


def default_fetch_factory(language: str) -> EntityCategoryFetchService:
    """Default factory: a category-fetch service bound to ``language``'s Wikipedia."""
    return EntityCategoryFetchService(language=language)


def title_from_dbpedia_iri(iri: str) -> str | None:
    """Derive the Wikipedia article title from a DBpedia resource IRI, or ``None``.

    Inverse of :meth:`DbpediaResolver._resource_iri`: take the segment after ``/resource/`` and
    URL-unquote it. Underscores are left as the article's own; the fetch service normalizes
    ``_``/blanks when matching, so ``A_B`` and ``A B`` resolve identically.

    Parameters
    ----------
    iri : str
        A DBpedia resource IRI, e.g. ``http://dbpedia.org/resource/Example_Title``.

    Returns
    -------
    str | None
        The decoded article title, or ``None`` if ``iri`` is empty or not a resource IRI.
    """
    if not iri or _DBPEDIA_RESOURCE_MARKER not in iri:
        return None
    tail = iri.split(_DBPEDIA_RESOURCE_MARKER, 1)[1]
    if not tail:
        return None
    return urllib.parse.unquote(tail) or None


async def resolve_article_title(
    external_ids: dict[str, Any],
    qid: str | None,
    resolver: DbpediaResolver,
) -> str | None:
    """Resolve an entity's Wikipedia article title (FR-002).

    Prefer the stored DBpedia IRI (``external_ids['dbpedia']['id']`` — the ~1,250 case); otherwise
    resolve the QID via :meth:`DbpediaResolver.resolve` (owl:sameAs, then the enwiki-sitelink
    fallback — the ~191 case) and derive the title from the resulting IRI. Returns ``None`` when
    neither yields a title, so the caller skips-and-reports the entity rather than failing it
    (SC-006). Never raises — ``DbpediaResolver.resolve`` is itself degradation-safe.

    Parameters
    ----------
    external_ids : dict[str, Any]
        The entity's ``external_ids`` JSONB bag.
    qid : str | None
        The entity's Wikidata QID, if grounded.
    resolver : DbpediaResolver
        The QID→IRI resolver (injectable for tests).

    Returns
    -------
    str | None
        The resolved article title, or ``None`` if unresolvable.
    """
    dbpedia = external_ids.get("dbpedia") if isinstance(external_ids, dict) else None
    iri = dbpedia.get("id") if isinstance(dbpedia, dict) else None
    if isinstance(iri, str) and iri:
        title = title_from_dbpedia_iri(iri)
        if title:
            return title
    if qid:
        link = await resolver.resolve(qid)
        if link is not None:
            return title_from_dbpedia_iri(link[0])
    return None


async def store_categories_for_entity(
    session: AsyncSession,
    entity_id: uuid.UUID,
    category_names: list[str],
    *,
    cat_repo: WikipediaCategoryRepository,
    assign_repo: EntityCategoryRepository,
    size_service: CategorySizeService | None = None,
    sizes: dict[str, int] | None = None,
    replace: bool,
    source: str = WIKIPEDIA_SOURCE,
) -> None:
    """Upsert ``category_names`` and assign them to ``entity_id`` (optionally replacing first).

    The one write path shared by both orchestrations.

    - ``replace=False`` (add-only): the 1,441 and the on-approval seam. ``add`` is
      ON CONFLICT DO NOTHING, so an already-assigned pair is a no-op (idempotent, FR-008).
    - ``replace=True`` (the 373 rewrite): remove the entity's existing assignments first, then add
      the Wikipedia set — the DBpedia→Wikipedia transition (FR-005).

    **Safety invariant:** a replace is *never* allowed to leave an entity with no categories. If
    ``replace`` is requested with an empty ``category_names`` (a fetch that found nothing, or a
    title that resolved to zero non-hidden categories), this is a no-op — the existing assignments
    are **kept**, not deleted-to-empty. This makes the destructive "delete then add nothing" data
    loss structurally impossible regardless of caller; the batch additionally skips-and-reports
    such an entity so its DBpedia categories are left intact for a later run.

    Global sizes are filled incrementally — only categories still missing a size (FR-005). The
    source of the sizes is chosen to keep network **out of the caller's transaction** where it
    matters:

    - ``sizes`` given (the batch): pre-fetched once for the whole run, off any transaction, and
      applied here with no network — so the batch's write transaction holds no network call.
    - ``size_service`` given, ``sizes`` omitted (the on-approval seam): sizes for the still-missing
      categories are fetched inline (one entity, a brief call).
    - neither given: sizes are left NULL for a later run.

    The caller commits.
    """
    if replace and not category_names:
        return  # never delete an entity's categories down to nothing
    if replace:
        await assign_repo.delete_for_entity(session, entity_id)

    name_to_id: dict[str, uuid.UUID] = {}
    for name in dict.fromkeys(category_names):
        cat = await cat_repo.upsert(session, name)
        name_to_id[name] = cat.id
    for category_id in name_to_id.values():
        await assign_repo.add(session, entity_id, category_id, source)

    distinct = list(name_to_id)
    if not distinct:
        return
    to_fill = await cat_repo.names_without_global_size(session, distinct)
    if not to_fill:
        return
    resolved_sizes = sizes
    if resolved_sizes is None:
        if size_service is None:
            return  # no size source this call — leave NULL, a later run fills it
        resolved_sizes = await size_service.sizes_for(to_fill)
    fetched_at = datetime.datetime.now(datetime.UTC)
    for name in to_fill:
        size = resolved_sizes.get(name)
        if size is not None:
            await cat_repo.set_global_size(session, name_to_id[name], size, fetched_at)


async def categorize_entity(
    session: AsyncSession,
    entity_id: uuid.UUID,
    qid: str | None,
    external_ids: dict[str, Any],
    *,
    fetch_service: EntityCategoryFetchService,
    resolver: DbpediaResolver,
    cat_repo: WikipediaCategoryRepository,
    assign_repo: EntityCategoryRepository,
    size_service: CategorySizeService,
    replace: bool = False,
) -> str | None:
    """Resolve → fetch → store one entity's categories; the single-entity composite (FR-003).

    Used by the on-approval seam (one entity, ``replace=False``). The batch reuses the same
    building blocks (:func:`resolve_article_title`, :func:`store_categories_for_entity`) but batches
    the fetch across many entities for rate-efficiency.

    Returns the resolved article title, or ``None`` if the entity was skipped — either because no
    article resolved (SC-006) or because the fetch omitted the title (a failure; the entity is left
    as-is and retried on a later run, FR-008). A title that exists with zero non-hidden categories
    is *not* a skip: it is stored as processed-zero (add-only) / left intact (replace, via the
    safety invariant).
    """
    title = await resolve_article_title(external_ids, qid, resolver)
    if title is None:
        return None
    fetched = await fetch_service.categories_for_titles([title])
    names = fetched.get(title)
    if names is None:
        return None  # fetch omitted this title (failure) — leave as-is, retry later
    await store_categories_for_entity(
        session,
        entity_id,
        names,
        cat_repo=cat_repo,
        assign_repo=assign_repo,
        size_service=size_service,
        replace=replace,
    )
    return title


# ---------------------------------------------------------------------------
# Feature 100 — foreign-language category cross-walk
# ---------------------------------------------------------------------------


class EntityCrosswalkResult(BaseModel):
    """Outcome of cross-walking one foreign-only entity's categories to English (Feature 100).

    ``english_categories`` is the de-duplicated UNION of English category names recovered across
    every foreign language the entity has (FR-005); ``source_langs_by_category`` records, per
    English name, which language(s) it came from (capture/audit, FR-010); ``dropped_count`` is the
    number of foreign categories with no English equivalent (reporting, SC-002). An empty
    ``english_categories`` means "recovered zero" — eligible but nothing cross-walked (not an error).
    """

    english_categories: list[str] = Field(default_factory=list)
    source_langs_by_category: dict[str, list[str]] = Field(default_factory=dict)
    dropped_count: int = 0
    languages: list[str] = Field(default_factory=list)


async def crosswalk_foreign_categories(
    foreign_categories_by_lang: dict[str, list[str]],
    *,
    fetch_factory: FetchServiceFactory,
    wikidata_client: WikidataClient,
) -> EntityCrosswalkResult:
    """Cross-walk foreign categories to their English equivalents, unioned across languages (FR-004/5/6).

    For each language, resolve its category titles to their own Wikidata items
    (``wikibase_item``); then one batched sitelink fetch maps those items to the English
    ``Category:`` title (``enwiki`` sitelink). Per-category inclusion: a category with no Wikidata
    item, or whose item has no ``enwiki`` sitelink, is dropped (counted) — never raises.
    """
    # Hop 1 (per language): foreign category title -> its Wikidata QID.
    lang_cat_qids: list[tuple[str, str]] = []
    dropped = 0
    for lang, titles in foreign_categories_by_lang.items():
        if not titles:
            continue
        try:
            mapping = await fetch_factory(lang).wikibase_items_for_categories(titles)
        except httpx.HTTPError:
            # Degrade on a transport failure only — a language's lookup failing drops its
            # categories, not the whole entity. A logic error is NOT swallowed (it should surface).
            mapping = {}
        for title in titles:
            qid = mapping.get(title)
            if qid:
                lang_cat_qids.append((lang, qid))
            else:
                dropped += 1  # no Wikidata item -> no English equivalent (FR-006)

    # Hop 2 (one batched call): category QID -> English Category title via its enwiki sitelink.
    cat_qids = list(dict.fromkeys(qid for _, qid in lang_cat_qids))
    try:
        sitelinks = await wikidata_client.fetch_sitelinks(cat_qids) if cat_qids else {}
    except WikidataUnavailable:
        sitelinks = {}  # degrade: no cross-walk this run, retry later (FR-014)

    result = EntityCrosswalkResult(languages=sorted(foreign_categories_by_lang))
    seen: dict[str, str] = {}
    for lang, qid in lang_cat_qids:
        enwiki_title = (sitelinks.get(qid) or {}).get("enwiki")
        if not enwiki_title:
            dropped += 1  # item exists but has no English category (FR-006)
            continue
        name = (
            enwiki_title[len(_CATEGORY_PREFIX) :]
            if enwiki_title.startswith(_CATEGORY_PREFIX)
            else enwiki_title
        )
        if not name:
            dropped += 1
            continue
        key = _norm(name)
        canonical = seen.get(key)
        if canonical is None:
            seen[key] = name
            result.english_categories.append(name)
            result.source_langs_by_category[name] = [lang]
        elif lang not in result.source_langs_by_category[canonical]:
            result.source_langs_by_category[canonical].append(lang)
    result.dropped_count = dropped
    return result


async def resolve_and_crosswalk_entity(
    qid: str,
    *,
    wikidata_client: WikidataClient,
    fetch_factory: FetchServiceFactory = default_fetch_factory,
) -> EntityCrosswalkResult | None:
    """Cross-walk one grounded, foreign-only entity (Feature 100). All network, NO database.

    This is the per-entity primitive shared by the enrichment seam (US1) and the backfill (US2).
    Resolves the entity's foreign articles from its QID (sitelinks), fetches each foreign article's
    non-hidden categories, and cross-walks them (:func:`crosswalk_foreign_categories`). Keeping it
    DB-free means no session is ever held across this network work (FR-012, the 094 deadlock lesson);
    the caller performs the single ``store_categories_for_entity`` write afterward.

    Returns ``None`` when the entity is NOT eligible — it has an English Wikipedia article (out of
    scope, FR-001) or no foreign article at all. Otherwise returns an :class:`EntityCrosswalkResult`,
    which may have an empty ``english_categories`` ("recovered zero"). Degrades on knowledge-base
    failure (returns ``None``) rather than raising.
    """
    try:
        sitelinks = await wikidata_client.fetch_sitelinks([qid])
    except WikidataUnavailable:
        return None  # knowledge base unreachable — leave as-is, retry later (FR-014)
    wikis = sitelinks.get(qid) or {}
    if "enwiki" in wikis:
        return None  # has an English article -> out of scope (FR-001)
    foreign = {
        # Wikimedia dbnames use "_" where the host subdomain uses "-" (e.g. zh_yuewiki ->
        # zh-yue.wikipedia.org, be_x_oldwiki -> be-x-old...); without the swap the host 404s and
        # that language silently contributes nothing (FR-005 under-recovery).
        dbname[: -len("wiki")].replace("_", "-"): title
        for dbname, title in wikis.items()
        if dbname.endswith("wiki") and dbname != "enwiki"
    }
    if not foreign:
        return None  # grounded but no foreign article -> nothing to recover

    categories_by_lang: dict[str, list[str]] = {}
    for language, article in foreign.items():
        fetched = await fetch_factory(language).categories_for_titles([article])
        cats = fetched.get(article) or []
        if cats:
            categories_by_lang[language] = cats

    return await crosswalk_foreign_categories(
        categories_by_lang,
        fetch_factory=fetch_factory,
        wikidata_client=wikidata_client,
    )
