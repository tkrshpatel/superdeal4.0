# 24-hour feed pagination

All feed sorts enforce a committed-publication window of 24 hours before pagination. Fresh/24-hour counts remain independent of page size. API pages are bounded to protect request cost; there is no 100-deal total cap. The client fetches the full eligible window in 48-item API pages with offset/as_of, then renders 24 cards at a time with Show more deals. Search, store filters, quick filters and saved-deal filtering use that complete window, including matches beyond the first 100 records.

The as_of snapshot freezes publication eligibility and click-ranking time during fetch; timestamps older than 10 minutes are rejected for continuation. New arrivals appear on the next refresh. Incoming request generations prevent slower older requests from replacing newer sort results. A failed continuation fails the load rather than claiming partial search results are complete.

This design intentionally loads the 24-hour catalog into browser memory while limiting rendered cards. It is suitable for the initial light-traffic release; a substantially larger catalog should move all filter combinations to server-driven cursor queries. Offset pages do not protect against administrators mutating already-published records while paging; do not edit committed publications during a snapshot.

New checks cover 137 records across API batches, UI pages, searches beyond the first 100, failed continuations, and real MongoDB paging across old/future/unpublished/boundary data in all sort modes. Other known validation failures remain recorded in RELEASE_VALIDATION.md. API host, port, .env and production data are unchanged. Main has not been updated by this branch.
