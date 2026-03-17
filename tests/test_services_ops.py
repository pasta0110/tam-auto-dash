import datetime
import unittest

import pandas as pd

from services.aggregations import aggregate_month_center_counts
from services.data_contract import validate_raw_inputs
from services.prediction_ops import build_tab3_prediction
from services.pipeline_cache import build_expected_meta


class ServiceOpsTests(unittest.TestCase):
    def test_aggregate_month_center_counts(self):
        df = pd.DataFrame(
            {
                "연월_키": ["2026-03", "2026-03", "2026-03"],
                "월일자": pd.to_datetime(["2026-03-01", "2026-03-01", "2026-03-01"]),
                "배송사_정제": ["수도권", "수도권", "대전"],
            }
        )
        out = aggregate_month_center_counts(df)
        self.assertEqual(int(out["완료건수"].sum()), 3)
        self.assertEqual(set(out["지역센터"].tolist()), {"수도권", "대전"})

    def test_validate_raw_inputs_domain(self):
        order_df = pd.DataFrame({"주문번호": ["1"], "상품명": ["매트리스"], "등록일": ["2026-03-01"]})
        delivery_df = pd.DataFrame(
            {
                "주문번호": ["1", "2"],
                "상품명": ["매트리스", "프레임"],
                "배송예정일": ["2026-03-01", "x"],
                "주문유형": ["정상", "미지정코드"],
            }
        )
        errors, warnings = validate_raw_inputs(order_df, delivery_df)
        self.assertTrue(len(errors) >= 0)
        # unknown order type should be at least warning
        self.assertTrue(any(i.code == "delivery_order_type_domain" for i in warnings + errors))

    def test_build_tab3_prediction_has_total(self):
        ana_df = pd.DataFrame(
            {
                "배송예정일_DT": pd.to_datetime(["2026-03-01", "2026-03-02", "2026-03-03"]),
                "연월_키": ["2026-03", "2026-03", "2026-03"],
                "배송사_정제": ["수도권", "수도권", "대전"],
            }
        )
        ctx = {
            "yesterday": datetime.date(2026, 3, 3),
            "m_key": "2026-03",
            "m_start": datetime.date(2026, 3, 1),
            "m_end": datetime.date(2026, 3, 31),
        }
        rows, meta = build_tab3_prediction(ana_df, ctx, ["수도권", "대전"])
        self.assertTrue(len(rows) >= 1)
        self.assertIn("remain_w", meta)
        self.assertEqual(rows[-1]["배송사"], "📌 합계")

    def test_pipeline_meta_schema(self):
        meta = build_expected_meta((100, 200), (300, 400), "oa", "da")
        self.assertIn("schema", meta)
        self.assertEqual(meta["order_sig"], [100, 200])
        self.assertEqual(meta["delivery_sig"], [300, 400])
        self.assertEqual(meta["order_sha256"], "oa")
        self.assertEqual(meta["delivery_sha256"], "da")


if __name__ == "__main__":
    unittest.main()
