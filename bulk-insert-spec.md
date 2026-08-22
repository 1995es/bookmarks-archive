# Business spec: bulk insert of bookmarks

## Problem

A user who wants to import several bookmarks at once has to add them one at a time today, each
through the single-URL form. That's slow when migrating from another tool or dumping a list of
links collected elsewhere.

## User story

As a user, I want to paste a list of URLs and have them all added as bookmarks, so I don't have to
repeat the single-add flow once per link.

## Scope

- Frontend only. The existing `POST /bookmarks` endpoint is reused once per URL — no new backend
  endpoint. See [decision record](#decision-no-dedicated-backend-endpoint) below for why.
- Each URL becomes its own bookmark, created exactly as if the user had pasted it individually into
  the existing single-URL fast path (name derived from host, enrichment scheduled asynchronously —
  no change to that behavior).

## UX flow

1. User opens the bulk-add entry point and gets a text area.
2. User pastes or types URLs, one per line.
3. User confirms (submit). Input is parsed into a list of candidate URLs, blank lines discarded.
4. A spinner (or equivalent in-progress indicator) is shown for the duration of the import — from
   submit until every URL has been attempted.
5. Each URL is submitted to `POST /bookmarks` independently. One URL's failure does not stop or
   delay the others.
6. When all attempts have finished, the spinner clears and the user sees a result summary:
   - how many URLs were added successfully
   - which URLs (if any) failed, so the user can see exactly what to fix and retry — a URL that
     fails is not silently dropped
7. Successfully added bookmarks appear in the list as usual. Their descriptions/tags fill in a few
   seconds later via the existing async enrichment — same as any single-add bookmark, not
   accelerated or batched for this flow.

## Out of scope / explicitly not handled

- **No all-or-nothing guarantee.** This is a best-effort import: valid URLs are added even if
  others in the same paste fail. There is no rollback of partial success.
- **No bulk-specific dedupe.** Two identical URLs in the same paste, or a URL that already exists
  as a bookmark, are each submitted independently to `POST /bookmarks` and handled however that
  endpoint already handles duplicates today (no special bulk-aware detection).
- **No throttling or batching of LLM enrichment.** Enrichment is scheduled per created bookmark
  exactly as it is for a single add; a large paste means a burst of enrichment calls, same as
  submitting that many single adds back to back.
- **No progress-per-URL UI** (e.g. a live checklist ticking off each line) — only a single
  in-progress spinner and a final summary. A more granular progress UI is a possible future
  iteration, not part of this spec.

## Failure reporting

A URL can fail for reasons that already exist in the single-add flow (invalid/malformed URL
rejected by validation, server error, etc.). The summary must surface, per failed URL, enough
information for the user to know what to fix — at minimum the URL itself; the underlying error
message if one is available from the response.

## Decision: no dedicated backend endpoint

Considered adding `POST /bookmarks/bulk` to accept a URL list in one call. Rejected because:

- Enrichment already runs as one independent background task per bookmark regardless of whether
  the request that created it was part of a batch — a bulk endpoint would not reduce or throttle
  LLM calls, which was the main potential win.
- The remaining theoretical advantages of a bulk endpoint (single DB transaction, single HTTP round
  trip, centralized dedupe) don't matter for this project: self-hosted, single user, no auth,
  modest expected paste sizes.

Looping the existing `POST /bookmarks` per URL from the frontend is simpler and reuses
battle-tested validation/creation logic with no new backend surface to maintain.
