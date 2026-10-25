"""SuperDeal local multi-channel Telegram worker. Capture all configured channels; recover gaps since monitoring started.

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


def run(channels, *, capture_only=False):
    """Run raw capture independently from the optional publication thread."""
    from telethon import TelegramClient
    from superdeal.telegram_user import TelegramUserSource
    from superdeal_telegram_capture import monitor
    from backend import connect
    backend=connect()
    backend.setup()
    session=os.getenv('TELEGRAM_SESSION','data/telegram_user_fresh')
    Path(session).parent.mkdir(parents=True,exist_ok=True)
    client=TelegramClient(session,int(os.environ['TELEGRAM_API_ID']),
        os.environ['TELEGRAM_API_HASH'],receive_updates=True,catch_up=True,
        sequential_updates=False,auto_reconnect=True)
    reader=TelegramUserSource(os.environ['TELEGRAM_API_ID'],os.environ['TELEGRAM_API_HASH'],
        session=session,client=client)
    try:
        reader.client.loop.run_until_complete(monitor(reader,backend,channels,
            capture_only=capture_only,
            interval=int(os.getenv('SUPERDEAL_TELEGRAM_RECONCILE_SECONDS','20'))))
    finally:
        reader.close()



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--confirm-monitor', action='store_true', help='Start monitoring and local publication')
    parser.add_argument('--capture-only', action='store_true', help='Capture raw messages without EarnKaro, Playwright or LLM calls')
    parser.add_argument('--capture-status', action='store_true', help='Show private MongoDB capture counts and channel scan checkpoints')
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
    if args.capture_status:
        from backend import connect
        backend=connect()
        print('MONGODB_DATABASE',backend.db.name)
        for state in ('CAPTURED','ARCHIVED','RAW_STORED','HANDLED'):
            print('INBOX',state,backend.db.telegram_inbox.count_documents({'state':state}))
        for doc in backend.db.telegram_capture_channels.find({}, {'_id':0,'channel':1,'last_scanned_id':1,'last_received_at':1,'last_reconciled_at':1}):
            print('CHANNEL_STATUS',doc)
        return
    if not args.confirm_monitor:
        parser.error('Monitoring is OFF; use --confirm-monitor to start')
    for key in ('TELEGRAM_API_ID', 'TELEGRAM_API_HASH'):
        if not os.getenv(key):
            parser.error(f'Missing {key} in environment or .env')
    os.environ.setdefault('MONGODB_URI', 'mongodb://127.0.0.1:27017/?replicaSet=rs0')
    os.environ.setdefault('OLLAMA_MODEL', 'mistral:instruct')
    capture_only=args.capture_only or not os.getenv('API_KEY_EARNKARO')
    if capture_only and not args.capture_only:
        print('CAPTURE_ONLY: API_KEY_EARNKARO is missing; raw monitoring continues.',flush=True)
    run(channels,capture_only=capture_only)


if __name__ == '__main__':
    main()
