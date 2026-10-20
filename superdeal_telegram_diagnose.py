"""One-shot Telegram message diagnostics; does not print message contents or write to DB."""
import argparse
import os
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--channel', required=True)
    parser.add_argument('--limit', type=int, default=10)
    parser.add_argument('--confirm-read', action='store_true')
    args = parser.parse_args()
    if not args.confirm_read:
        parser.error('Add --confirm-read to authorize a single Telegram read')
    if not 1 <= args.limit <= 20:
        parser.error('--limit must be 1 through 20')
    for name in ('TELEGRAM_API_ID', 'TELEGRAM_API_HASH'):
        if not os.getenv(name):
            parser.error(f'{name} is required')
    sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))
    from superdeal.telegram_user import TelegramUserSource
    reader = TelegramUserSource(
        os.environ['TELEGRAM_API_ID'], os.environ['TELEGRAM_API_HASH'],
        session=os.getenv('TELEGRAM_SESSION', 'data/telegram_user_fresh'))
    try:
        entity = reader._resolve_entity(args.channel)
        messages = list(reader.client.iter_messages(entity, limit=args.limit))
        text_count = sum(bool(str(getattr(m, 'raw_text', None) or getattr(m, 'text', None) or '').strip()) for m in messages)
        print('Resolved channel ID:', getattr(entity, 'id', 'unknown'))
        print('Messages returned by Telegram:', len(messages))
        print('Messages containing text:', text_count)
        print('Messages without text:', len(messages) - text_count)
        print('No message text, credentials, or session data printed.')
        print('No MongoDB writes, monitoring, EarnKaro, Mistral, or publication.')
    finally:
        reader.close()


if __name__ == '__main__':
    main()
