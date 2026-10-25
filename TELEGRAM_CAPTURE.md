# Telegram capture

Run only one instance per Telegram session file. Existing .env settings remain authoritative; process environment variables override .env, as before. No API host/port settings change.

## Modes

Normal: python superdeal_local_live_worker.py --confirm-monitor
Raw only: python superdeal_local_live_worker.py --confirm-monitor --capture-only
Configuration: python superdeal_local_live_worker.py --check-config
Private Mongo capture status: python superdeal_local_live_worker.py --capture-status

TELEGRAM_CHANNELS is the explicit comma-separated list of monitored channels. This does not automatically join new channels or monitor every chat on the account. Each configured channel must be accessible to the authenticated user. Failed channels log CHANNEL_ERROR and retry independently while healthy channels continue. LISTENING confirms successful resolution. Numeric IDs, public usernames/URLs and Telegram Web links are supported.

TELEGRAM_API_ID, TELEGRAM_API_HASH and TELEGRAM_SESSION select the account/session. Missing EarnKaro credentials selects capture-only mode; it does not disable raw capture. Never share API hashes, session files, full .env files or message payloads publicly.

SUPERDEAL_TELEGRAM_RECONCILE_SECONDS optionally controls per-channel gap scans (default 20 seconds, minimum 5). A slow or failed scan affects that channel, not the others.

## Storage and processing

telegram_inbox stores original text/captions, media type, album ID, dates and Telegram's serialized message payload, even for posts without text. This records media metadata/references, not downloaded binary photo/video files. Duplicate events use a stable unique key. Edits are separate archived revisions and do not republish existing deals.

telegram_capture_channels records per-channel durable scan cursors and receive/reconciliation times. On FIRST registration the cursor starts at the channel's latest message: old history is not imported. Subsequent runs recover messages AFTER that saved cursor, including gaps caused by outages. Scans have no 100-message total limit. The cursor advances only after durable storage; a direct live event never advances it.

The pipeline reads the Mongo inbox in a separate thread. EarnKaro, Playwright, LLM and publication failures cannot remove captured raw messages. Pending work remains in Mongo across restarts; already FAILED/PUBLISHED/PROCESSING jobs are not retried. Capture-only retains text posts as CAPTURED for later processing.

No original event monitoring system can promise messages deleted by Telegram before recovery. Edits during a prolonged shutdown may also be unavailable as separate revisions. Mongo must be reachable for durable writes; per-channel scans recover original messages after it returns. Monitor CHANNEL_ERROR/CAPTURE_ERROR and last_reconciled_at. This change does not replay historical deal publications.

## Local verification

Compare the configured list against LISTENING and MONITORING active counts. Check each channel's last_reconciled_at using --capture-status. Compare telegram_inbox channel/message_id to the missing Telegram post. Inbox existence and deal publication are different checks: a captured message can legitimately have no published deal.

Do not run the previous runner and this version simultaneously with the same session. Stop the old runner before switching branches.
