"""Load repository .env using the Telegram runner's existing precedence rules."""
import os
from pathlib import Path


def load_env(path=None):
    # Resolve from this module, not the terminal's current working directory.
    path = Path(path) if path is not None else Path(__file__).resolve().parents[1] / '.env'
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
