from superdeal.runner import check_telegram
from superdeal.worker import WorkerConfig


def test_check_telegram_uses_bot_identity():
    class FakeBot:
        def __init__(self, token):
            self.token = token

        def get_me(self):
            return {"id": 123, "username": "superdeal_bot"}

    config = WorkerConfig("token", ("@deals",))
    result = check_telegram(config, bot_factory=FakeBot)
    assert result == {"ok": True, "bot": {"id": 123, "username": "superdeal_bot"}}


def test_config_defaults_are_safe():
    config = WorkerConfig.from_env()
    assert config.poll_interval >= 0
    assert 1 <= config.batch_limit <= 100
