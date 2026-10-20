"""Manual, offline Telegram message -> SuperDeal MongoDB raw import.

Input JSON: {"channel":"@example", "message_id":"123", "text":"original message"}
Or a list of these objects. No Telegram connection, EarnKaro, Ollama, or processing.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('json_file', type=Path, help='Local JSON file of message(s)')
    parser.add_argument('--dry-run', action='store_true', help='Validate only; do not connect to MongoDB')
    args = parser.parse_args()
    records = json.loads(args.json_file.read_text(encoding='utf-8-sig'))
    if isinstance(records, dict):
        records = [records]
    if not isinstance(records, list) or not records:
        parser.error('Input must be one message object or a nonempty list')
    validated = []
    for i, obj in enumerate(records, 1):
        if not isinstance(obj, dict):
            parser.error(f'Message {i}: expected object')
        channel, message_id, content = obj.get('channel'), obj.get('message_id'), obj.get('text')
        if not isinstance(channel, str) or not channel.strip():
            parser.error(f'Message {i}: channel must be a nonempty string')
        if isinstance(message_id, bool) or not isinstance(message_id, (str, int)) or not str(message_id).strip():
            parser.error(f'Message {i}: message_id must be a nonempty string or integer')
        if not isinstance(content, str) or not content.strip():
            parser.error(f'Message {i}: text must be a nonempty string')
        observed = obj.get('observed_at')
        if observed is not None:
            if not isinstance(observed, str):
                parser.error(f'Message {i}: observed_at must be ISO 8601 string')
            try:
                dt = datetime.fromisoformat(observed.replace('Z', '+00:00'))
            except ValueError:
                parser.error(f'Message {i}: invalid observed_at')
            if dt.tzinfo is None:
                parser.error(f'Message {i}: observed_at needs timezone offset')
            observed = dt.astimezone(timezone.utc)
        validated.append((channel, str(message_id), content, observed))
    print(f'Validated {len(validated)} message(s).')
    if args.dry_run:
        print('DRY RUN: no database writes or external connections')
        return
    root = Path(__file__).resolve().parent
    sys.path.insert(0, str(root / 'superdeal_phase2_full'))
    try:
        from backend import connect
    except ImportError as exc:
        parser.error(f'Missing superdeal_phase2_full backend or dependency: {exc}')
    if not os.getenv('MONGODB_URI'):
        parser.error('Set MONGODB_URI before importing')
    backend = connect()
    backend.setup()
    for channel, message_id, content, observed in validated:
        raw_id = backend.ingest(channel, message_id, content, observed_at=observed)
        print(f'RAW STORED channel={channel} message_id={message_id} raw_id={raw_id}')
    print('Finished. Only raw/PENDING records created. No pipeline processing or monitoring.')


if __name__ == '__main__':
    main()
