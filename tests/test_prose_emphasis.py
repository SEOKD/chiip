"""본문 글 강조(마스터 지시 2026-11-19 "볼드, 밑줄, 스포트라이트, 색상 등을 더 많이")"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "tenbagger"))
import report_html as rh  # noqa: E402


class TestProse(unittest.TestCase):
    def test_numbers_tags_rates(self):
        h = rh.tp("올라갈 조건: 매출 $240M·Fwd P/E 18.3배, 가동률 81%. 등급은 Neutral, 캐파 미확인.")
        self.assertIn('<b class="num">$240M</b>', h)
        self.assertIn('<b class="num">18.3배</b>', h)
        self.assertIn('<b class="num">81%</b>', h)
        self.assertIn('<span class="tag">올라갈 조건</span>', h)
        self.assertIn('rate-mid rt">Neutral', h)
        self.assertIn('<i class="unk">미확인</i>', h)

    def test_signed_pct_and_bold_untouched(self):
        h = rh.tp("주가 +12%, **핵심 $5B**")
        self.assertIn('<span class="up">+12%</span>', h)
        self.assertNotIn('class="num">12%', h)
        self.assertIn("<b>핵심 $5B</b>", h)   # 이미 굵은 글씨 안 숫자는 다시 감싸지 않는다

    def test_lead_spotlight(self):
        h = rh.tp("실적은 좋아졌고 배수는 내렸다. 3Q 매출은 늘었고 잔고도 늘었다고 회사가 밝혔다.", lead=True)
        self.assertTrue(h.startswith('<span class="spot">실적은 좋아졌고 배수는 내렸다.</span>'))
        self.assertNotIn("spot", rh.tp("짧다. 끝."))   # 뒤 문장이 짧으면 스포트라이트 없음

    def test_tables_and_svg_stay_plain(self):
        self.assertNotIn("num", rh.t("$240M"))


if __name__ == "__main__":
    unittest.main()
