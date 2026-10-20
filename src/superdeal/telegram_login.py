"""One-time interactive login for the Telegram MTProto reader."""
from __future__ import annotations
import os
from pathlib import Path
def main() -> None:
    api_id=os.getenv("TELEGRAM_API_ID","").strip(); api_hash=os.getenv("TELEGRAM_API_HASH","").strip(); session=os.getenv("TELEGRAM_SESSION","data/telegram_user").strip()
    if not api_id or not api_hash: raise SystemExit("Set TELEGRAM_API_ID and TELEGRAM_API_HASH first. Get them from Telegram API development tools at my.telegram.org.")
    try: from telethon.sync import TelegramClient
    except ImportError as exc: raise SystemExit("Telethon is not installed. Run: pip install -e .") from exc
    Path(session).parent.mkdir(parents=True,exist_ok=True); client=TelegramClient(session,int(api_id),api_hash)
    try:
        client.start(); me=client.get_me(); username=f"@{me.username}" if getattr(me,"username",None) else "(no username)"
        print(f"Telegram user session ready: {username}"); print(f"Session file: {session}.session")
    finally: client.disconnect()
if __name__=="__main__": main()
