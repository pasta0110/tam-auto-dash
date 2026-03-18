import os
import unittest
from unittest.mock import patch, Mock

import pandas as pd

from data_loader import load_raw_data_with_source, load_raw_data_result
from services.notifiers import build_telegram_notifier, TelegramNotifier, NoopNotifier
from uploader.runtime import build_runtime_config
from services.exception_ops import build_exception_pack


class _FakeSource:
    def __init__(self, order_df=None, delivery_df=None):
        self.order_df = order_df
        self.delivery_df = delivery_df
        self.calls = 0

    def load_csv_with_diagnostics(self, local_path, remote_url):
        self.calls += 1
        diag = {
            "selected_source": "remote",
            "local_path": local_path,
            "remote_url": remote_url,
            "local_error": None,
            "remote_error": None,
        }
        if self.calls == 1:
            return self.order_df, diag
        return self.delivery_df, diag


class _FailingSource:
    def load_csv_with_diagnostics(self, local_path, remote_url):
        return None, {
            "selected_source": None,
            "local_path": local_path,
            "remote_url": remote_url,
            "local_error": "FileNotFoundError: missing",
            "remote_error": "HTTPError: 404",
        }


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

    def test_exception_queue_has_action_columns(self):
        df = pd.DataFrame(
            {
                "주문번호": ["X-002"],
                "주문유형": ["정상"],
                "주문상태": ["배송준비"],
                "배송상태": ["배송중"],
                "등록일": ["2026-03-01"],
                "배송예정일": ["2026-03-02"],
                "배송예정일_DT": pd.to_datetime(["2026-03-02"]),
                "배송사_정제": ["수도권"],
            }
        )
        pack = build_exception_pack(df, {"yesterday": pd.Timestamp("2026-03-10").date(), "m_key": "2026-03"})
        q = pack.get("queue", pd.DataFrame())
        self.assertIn("원인태그", q.columns)
        self.assertIn("권장조치", q.columns)
        self.assertIn("cause_tags", pack)
        self.assertIn("actions", pack)
        self.assertIn("center_sla", pack)
        self.assertIn("capacity_warning", pack)
        self.assertIn("person_reasons", pack)
        self.assertIn("delay_d1", pack.get("kpi", {}))
        self.assertIn("delay_d2", pack.get("kpi", {}))
        self.assertIn("delay_d3p", pack.get("kpi", {}))

    def test_exception_queue_focuses_only_over_standard_lead(self):
        df = pd.DataFrame(
            {
                "주문번호": ["CAP-OK", "CAP-LATE", "ETC-LATE"],
                "주문유형": ["정상", "정상", "정상"],
                "주문상태": ["배송중", "배송중", "배송준비"],
                "배송상태": ["배송중", "배송중", "배송중"],
                "등록일": ["2026-03-10", "2026-03-05", "2026-03-04"],
                "배송예정일": ["2026-03-15", "2026-03-15", "2026-03-15"],
                "배송예정일_DT": pd.to_datetime(["2026-03-15", "2026-03-15", "2026-03-15"]),
                "배송사_정제": ["수도권", "수도권", "대전"],
            }
        )
        # 기준일: 2026-03-12 -> CAP-OK는 수도권 3영업일 이내, 나머지는 기준 초과
        pack = build_exception_pack(df, {"yesterday": pd.Timestamp("2026-03-12").date(), "m_key": "2026-03"})
        q = pack.get("queue", pd.DataFrame())
        self.assertFalse((q["주문번호"] == "CAP-OK").any())
        self.assertTrue((q["주문번호"] == "CAP-LATE").any())
        self.assertTrue((q["주문번호"] == "ETC-LATE").any())

    def test_person_message_reason_inference(self):
        df = pd.DataFrame(
            {
                "주문번호": ["P-001", "P-002"],
                "주문유형": ["정상", "정상"],
                "주문상태": ["배송중", "배송준비"],
                "배송상태": ["배송중", "배송중"],
                "등록일": ["2026-03-01", "2026-03-02"],
                "배송예정일": ["2026-03-15", "2026-03-15"],
                "배송예정일_DT": pd.to_datetime(["2026-03-15", "2026-03-15"]),
                "배송사_정제": ["수도권", "수도권"],
                "수취인": ["홍길동", "홍길동"],
                "주소": ["서울 강남구 테헤란로 1", "서울 강남구 테헤란로 1"],
                "수취인연락처": ["010-1111-2222", "01011112222"],
                "상담메세지": ["고객요청으로 다음주 방문", "고객요청 재방문 일정 조율"],
            }
        )
        pack = build_exception_pack(df, {"yesterday": pd.Timestamp("2026-03-12").date(), "m_key": "2026-03"})
        q = pack.get("queue", pd.DataFrame())
        self.assertIn("지연원인(메세지추정)", q.columns)
        self.assertTrue((q["지연원인(메세지추정)"] == "고객협의").any())
        self.assertTrue((q["원인태그"] == "고객협의").any())

    def test_happycall_priority_action(self):
        df = pd.DataFrame(
            {
                "주문번호": ["H-N", "H-Y"],
                "주문유형": ["정상", "정상"],
                "주문상태": ["배송중", "배송중"],
                "배송상태": ["배송중", "배송중"],
                "등록일": ["2026-03-01", "2026-03-01"],
                "배송예정일": ["2026-03-15", "2026-03-15"],
                "배송예정일_DT": pd.to_datetime(["2026-03-15", "2026-03-15"]),
                "배송사_정제": ["수도권", "수도권"],
                "해피콜": ["N", "Y"],
                "해피콜일자": ["", "2026-03-05"],
            }
        )
        pack = build_exception_pack(df, {"yesterday": pd.Timestamp("2026-03-12").date(), "m_key": "2026-03"})
        q = pack.get("queue", pd.DataFrame())
        self.assertTrue((q.loc[q["주문번호"] == "H-N", "권장조치"] == "해피콜 진행").any())
        self.assertTrue((q.loc[q["주문번호"] == "H-Y", "권장조치"] == "조치없음(고객협의 일정)").any())

    def test_customer_intent_wait_classification(self):
        df = pd.DataFrame(
            {
                "주문번호": ["W-001", "W-002", "W-003"],
                "주문유형": ["정상", "정상", "정상"],
                "주문상태": ["배송중", "배송중", "배송준비"],
                "배송상태": ["배송중", "배송중", "배송중"],
                "등록일": ["2026-03-01", "2026-03-01", "2026-03-01"],
                "배송예정일": ["2026-03-15", "2026-03-15", "2026-03-15"],
                "배송예정일_DT": pd.to_datetime(["2026-03-15", "2026-03-15", "2026-03-15"]),
                "배송사_정제": ["수도권", "수도권", "대전"],
                "수취인": ["김철수", "김철수", "이영희"],
                "주소": ["서울 강남구 역삼동 1", "서울 강남구 역삼동 1", "대전 서구 둔산동 1"],
                "수취인연락처": ["010-1111-2222", "01011112222", "010-3333-4444"],
                "상담메세지": ["컨택하지말라고 함", "조금더 고민해본다고 함", "빠른설치부탁드립니다 | 보류요청"],
            }
        )
        pack = build_exception_pack(df, {"yesterday": pd.Timestamp("2026-03-12").date(), "m_key": "2026-03"})
        q = pack.get("queue", pd.DataFrame())
        matched = q["지연원인(메세지추정)"] == "고객의사 대기"
        self.assertTrue(matched.any())
        self.assertTrue((q.loc[matched, "원인태그"] == "고객의사 대기").all())

    @patch("data_loader._get_source")
    def test_load_raw_data_result_returns_diagnostics(self, mock_get_source):
        mock_get_source.return_value = _FailingSource()
        load_raw_data_result.clear()
        result = load_raw_data_result()
        self.assertFalse(result["ok"])
        self.assertIn("order", result["diagnostics"])
        self.assertIn("delivery", result["diagnostics"])


if __name__ == "__main__":
    unittest.main()
