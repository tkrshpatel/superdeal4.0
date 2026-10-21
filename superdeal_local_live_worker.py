"""SuperDeal local multi-channel Telegram worker. New messages only; no backfill/retries.

Run from the repository root. API and Vite are separate processes.
"""
from __future__ import annotations

import argparse
import asyncio
import concurrent.futures
import threading
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'superdeal_phase2_full'))


def load_env():
    path = ROOT / '.env'
    if not path.is_file():
        return
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"\'')


def parse_channels(value):
    """Parse a single TELEGRAM_CHANNELS setting, reject duplicates and invalid names."""
    channels = [x.strip() for x in value.split(',')]
    if not channels or any(not x or '\n' in x or '\r' in x for x in channels):
        raise ValueError('TELEGRAM_CHANNELS must be a nonempty comma-separated list on one line')
    if len(set(x.casefold() for x in channels)) != len(channels):
        raise ValueError('Duplicate TELEGRAM_CHANNELS entries')
    return channels


def ingest_message(backend, channel, msg_id, text, observed_at):
    """Durably save a Telegram event before scheduling expensive processing."""
    raw_id = backend.ingest(channel, str(msg_id), text, observed_at=observed_at)
    status = backend.db.pipeline_status.find_one({'raw_id': raw_id}, {'status': 1}) or {}
    return status.get('status', 'UNKNOWN'), raw_id


def process_message(backend, channel, msg_id, raw_id):
    """Run a claimed PENDING message; never automatically retry FAILED ones."""
    try:
        published = backend.process(raw_id)
        status = backend.db.pipeline_status.find_one({'raw_id': raw_id}, {'status': 1}) or {}
        print(
            f'PROCESSED channel={channel} id={msg_id} raw_id={raw_id} '
            f'status={status.get("status", "UNKNOWN")} products={published}',
            flush=True,
        )
    except Exception as exc:
        print(f'PROCESSING_ERROR channel={channel} id={msg_id} type={type(exc).__name__}', file=sys.stderr, flush=True)


# Backward-compatible entry point for callers that intentionally process synchronously.
def handle_message(backend, channel, msg_id, text, observed_at):
    state, raw_id = ingest_message(backend, channel, msg_id, text, observed_at)
    if state == 'PENDING':
        process_message(backend, channel, msg_id, raw_id)
        state = (backend.db.pipeline_status.find_one({'raw_id': raw_id}, {'status': 1}) or {}).get('status', 'UNKNOWN')
    return state, str(raw_id)


def run(channels):
    """Construct Telethon's sync client outside an active asyncio event loop."""
    from telethon import events
    from superdeal.telegram_user import TelegramUserSource
    from backend import connect

    backend = connect()
    backend.setup()
    reader = TelegramUserSource(
        os.environ['TELEGRAM_API_ID'], os.environ['TELEGRAM_API_HASH'],
        session=os.getenv('TELEGRAM_SESSION', 'data/telegram_user_fresh'),
    )
    try:
        resolved = []
        errors = []
        ids = set()
        for configured in channels:
            try:
                entity = reader._resolve_entity(configured)
                entity_id = int(entity.id)
                if entity_id in ids:
                    raise ValueError('Duplicate resolved Telegram channel')
                ids.add(entity_id)
                resolved.append((configured, entity, f'telegram:{entity_id}'))
            except Exception as exc:
                errors.append((configured, type(exc).__name__))
        if errors:
            for configured, kind in errors:
                print(f'CHANNEL_ERROR channel={configured} type={kind}', file=sys.stderr)
            raise RuntimeError('Not starting: all configured Telegram channels must resolve')

        # A single Telethon connection listens to all channels. Telegram event
        # chat IDs may be marked (-100...) while entity IDs are unmarked.
        from telethon import utils
        channel_by_peer = {int(utils.get_peer_id(entity)): stable for _, entity, stable in resolved}
        entities = [entity for _, entity, _ in resolved]

        # A dedicated, bounded processing thread keeps costly merchant browsing
        # and local LLM calls off Telegram's message-receiving path.
        processing_pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=1, thread_name_prefix='superdeal-processing'
        )
        processing_futures = set()
        processing_lock = threading.Lock()

        def schedule_processing(channel, msg_id, raw_id):
            future = processing_pool.submit(process_message, backend, channel, msg_id, raw_id)
            with processing_lock:
                processing_futures.add(future)
            def on_done(done):
                with processing_lock:
                    processing_futures.discard(done)
            future.add_done_callback(on_done)

        @reader.client.on(events.NewMessage(chats=entities))
        async def on_new_message(event):
            print(
                f"EVENT_RECEIVED chat_id={event.chat_id} "
                f"message_id={event.message.id}",
                flush=True
            )
            stable = channel_by_peer.get(int(event.chat_id or 0))
            if not stable:
                print('WORKER_WARNING unmatched Telegram chat ID', file=sys.stderr, flush=True)
                return
            converted = reader.message_from_event(event, stable)
            if converted is None:
                return  # Ignore nontext messages.
            try:
                state, raw_id = await asyncio.to_thread(
                    ingest_message, backend, stable, converted.message_id,
                    converted.text, event.message.date,
                )
                print(f'STORED channel={stable} id={converted.message_id} raw_id={raw_id} status={state}', flush=True)
                if state == 'PENDING':
                    schedule_processing(stable, converted.message_id, raw_id)
            except Exception as exc:
                # Never print message bodies, affiliate URLs, or provider responses.
                print(f'WORKER_ERROR channel={stable} id={converted.message_id} type={type(exc).__name__}', file=sys.stderr, flush=True)

        for configured, _, stable in resolved:
            print(f'LISTENING {configured} ({stable})', flush=True)
        print('MONITORING new messages only; Ctrl+C to stop; local publication enabled', flush=True)
        reader.client.run_until_disconnected()
    finally:
        reader.close()
        # Drain accepted work on a normal shutdown. Never discard queued
        # jobs: the system intentionally has no automatic retry mechanism.
        print('STOPPING Telegram listener; finishing queued processing...', flush=True)
        processing_pool.shutdown(wait=True)
        print('ALL_QUEUED_PROCESSING_FINISHED', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--confirm-monitor', action='store_true', help='Start monitoring and local publication')
    parser.add_argument('--check-config', action='store_true', help='Show configured channels without connecting to Telegram')
    args = parser.parse_args()
    load_env()
    try:
        channels = parse_channels(os.getenv('TELEGRAM_CHANNELS', ''))
    except ValueError as exc:
        parser.error(str(exc))
    if args.check_config:
        for channel in channels:
            print('CONFIGURED', channel)
        return
    if not args.confirm_monitor:
        parser.error('Monitoring is OFF; use --confirm-monitor to start')
    for key in ('TELEGRAM_API_ID', 'TELEGRAM_API_HASH', 'API_KEY_EARNKARO'):
        if not os.getenv(key):
            parser.error(f'Missing {key} in environment or .env')
    os.environ.setdefault('MONGODB_URI', 'mongodb://127.0.0.1:27017/?replicaSet=rs0')
    os.environ.setdefault('OLLAMA_MODEL', 'mistral:instruct')
    run(channels)


if __name__ == '__main__':
    main()
