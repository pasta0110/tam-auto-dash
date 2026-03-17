import os
import unittest
from unittest.mock import patch, Mock

import pandas as pd

from data_loader import load_raw_data_with_source
from services.notifiers import build_telegram_notifier, TelegramNotifier, NoopNotifier
from uploader.runtime import build_runtime_config
from services.exception_ops import build_exception_pack


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

    def test_exception_completed_order_is_excluded(self):
        df = pd.DataFrame(
            {
                "주문번호": ["28-0506955-25-00136", "X-001"],
                "주문유형": ["정상", "정상"],
                "주문상태": ["배송중", "배송중"],
                "배송상태": ["배송중", "배송중"],
                "등록일": ["2026-03-01", "2026-03-01"],
                "배송예정일": ["2026-03-02", "2026-03-02"],
                "배송예정일_DT": pd.to_datetime(["2026-03-02", "2026-03-02"]),
                "배송사_정제": ["수도권", "수도권"],
            }
        )
        pack = build_exception_pack(df, {"yesterday": pd.Timestamp("2026-03-10").date(), "m_key": "2026-03"})
        q = pack.get("queue", pd.DataFrame())
        self.assertFalse((q.get("주문번호", pd.Series(dtype=str)).astype(str) == "28-0506955-25-00136").any())


if __name__ == "__main__":
    unittest.main()
