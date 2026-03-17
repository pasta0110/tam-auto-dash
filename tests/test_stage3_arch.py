import os
import unittest
from unittest.mock import patch, Mock

import pandas as pd

from data_loader import load_raw_data_with_source
from services.notifiers import build_telegram_notifier, TelegramNotifier, NoopNotifier
from uploader.runtime import build_runtime_config


class _FakeSource:
    def __init__(self, order_df=None, delivery_df=None):
        self.order_df = order_df
        self.delivery_df = delivery_df
        self.calls = 0

    def load_csv_prefer_local(self, local_path, remote_url):
        self.calls += 1
        if self.calls == 1:
            return self.order_df, "remote"
        return self.delivery_df, "remote"


class Stage3ArchTests(unittest.TestCase):
    def test_loader_with_source_success(self):
        order_df = pd.DataFrame({"주문번호": ["1"]})
        delivery_df = pd.DataFrame({"주문번호": ["1"]})
        source = _FakeSource(order_df=order_df, delivery_df=delivery_df)
        o, d = load_raw_data_with_source(source)
        self.assertEqual(len(o), 1)
        self.assertEqual(len(d), 1)

    def test_loader_with_source_failure(self):
        source = _FakeSource(order_df=None, delivery_df=pd.DataFrame({"주문번호": ["1"]}))
        with self.assertRaises(RuntimeError):
            load_raw_data_with_source(source)

    def test_notifier_factory(self):
        self.assertIsInstance(build_telegram_notifier("", ""), NoopNotifier)
        self.assertIsInstance(build_telegram_notifier("t", "c"), TelegramNotifier)

    @patch("services.notifiers.requests.post")
    def test_telegram_notifier_send(self, mock_post):
        mock_post.return_value = Mock(status_code=200)
        n = TelegramNotifier("token", "chat")
        self.assertTrue(n.send("hello"))
        self.assertEqual(mock_post.call_count, 1)

    def test_runtime_config_from_env(self):
        with patch.dict(
            os.environ,
            {"TDU_REPO_PATH": "C:\\tmp\\repo", "TDU_GIT_REMOTE": "upstream", "TDU_GIT_BRANCH": "dev"},
            clear=False,
        ):
            cfg = build_runtime_config()
        self.assertTrue(cfg.repo_path.endswith("repo"))
        self.assertEqual(cfg.git_remote, "upstream")
        self.assertEqual(cfg.git_branch, "dev")


if __name__ == "__main__":
    unittest.main()
