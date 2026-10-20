"""Explicit, one-shot Telegram -> MongoDB raw importer; never starts monitoring.

Usage: python superdeal_telegram_one_shot.py --channel @public_channel --limit 1
Requires TELEGRAM_API_ID, TELEGRAM_API_HASH, MONGODB_URI in environment.
"""
import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def canonical_key(entity, configured):
    """Stable identity: channel ID, not display title or mutable username."""
    entity_id = getattr(entity, 'id', None)
    if entity_id is None:
        raise ValueError('Telegram entity has no numeric ID')
    return f'telegram:{int(entity_id)}'


def ingest_one_shot(reader, backend, configured_channel, limit):
    """Read only explicitly requested messages and store as raw/PENDING."""
    entity = reader._resolve_entity(configured_channel)
    stable_channel = canonical_key(entity, configured_channel)
    # Resolve once and iterate the resolved entity: do not concatenate usernames.
    messages = list(reader.client.iter_messages(entity, limit=limit))
    stored = []
    for message in reversed(messages):
        converted = reader.message_from_event(message, stable_channel)
        if converted is None:
            continue
        observed = datetime.fromisoformat(converted.observed_at.replace('Z', '+00:00'))
        if observed.tzinfo is None:
            raise ValueError('Message timestamp must be timezone-aware')
        raw_id = backend.ingest(stable_channel, converted.message_id, converted.text,
                                observed_at=observed.astimezone(timezone.utc))
        stored.append((converted.message_id, str(raw_id)))
    return stable_channel, stored


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--channel', required=True, help='Exact public @username, URL, or known ID')
    parser.add_argument('--limit', type=int, default=1, help='Maximum messages; default 1, max 10')
    parser.add_argument('--confirm-read', action='store_true', help='Explicitly allow a one-shot Telegram read')
    args = parser.parse_args()
    if not args.confirm_read:
        parser.error('No Telegram connection made. Add --confirm-read to run a one-shot read.')
    if not 1 <= args.limit <= 10:
        parser.error('--limit must be between 1 and 10')
    for key in ('TELEGRAM_API_ID', 'TELEGRAM_API_HASH', 'MONGODB_URI'):
        if not os.environ.get(key):
            parser.error(f'{key} is required')
    root = Path(__file__).resolve().parent
    sys.path.insert(0, str(root / 'src'))
    sys.path.insert(0, str(root / 'superdeal_phase2_full'))
    from superdeal.telegram_user import TelegramUserSource
    from backend import connect
    backend = connect()
    backend.setup()
    reader = TelegramUserSource(os.environ['TELEGRAM_API_ID'], os.environ['TELEGRAM_API_HASH'],
                                session=os.getenv('TELEGRAM_SESSION', 'data/telegram_user_fresh'))
    try:
        channel, stored = ingest_one_shot(reader, backend, args.channel, args.limit)
    finally:
        reader.close()
    print(f'One-shot read complete: channel={channel}, stored={len(stored)}')
    for message_id, raw_id in stored:
        print(f'RAW STORED message_id={message_id} raw_id={raw_id}')
    print('No streaming, no EarnKaro, no Mistral, no publication.')


if __name__ == '__main__':
    main()
