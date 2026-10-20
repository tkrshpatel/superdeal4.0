import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location('one_shot', Path(__file__).with_name('superdeal_telegram_one_shot.py'))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_stable_channel_and_idempotent_input():
    class Reader:
        def __init__(self):
            self.entity = SimpleNamespace(id=123, username='Deals')
            self.client = self
        def _resolve_entity(self, value):
            assert value == '@Deals'
            return self.entity
        def iter_messages(self, entity, limit):
            assert entity is self.entity and limit == 2
            return [SimpleNamespace(id=2), SimpleNamespace(id=1)]
        def message_from_event(self, message, configured):
            return SimpleNamespace(message_id=str(message.id), text='Original text', observed_at='2026-10-18T00:00:00+00:00')
    class Backend:
        def __init__(self): self.rows = []
        def ingest(self, channel, message_id, text, observed_at):
            self.rows.append((channel, message_id, text, observed_at))
            return message_id
    backend = Backend()
    channel, stored = mod.ingest_one_shot(Reader(), backend, '@Deals', 2)
    assert channel == 'telegram:123'
    assert stored == [('1', '1'), ('2', '2')]
    assert all(row[0] == 'telegram:123' and row[2] == 'Original text' for row in backend.rows)
    assert all(row[3].tzinfo == timezone.utc for row in backend.rows)
