"""실시간 알림 양식 시험 (마스터 지시 2026-10-29 "종목｜내용｜시간 → ☞ 회사 설명(비즈니스 모델·성장동력·내러티브) 3줄 → 핵심 내용 3개")"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))

import notify  # noqa: E402

ITEM = {"title": "Quanta Services raises 2026 outlook after record backlog", "url": "https://example.com/a",
        "published_at": "2026-10-29T21:05:00+09:00", "entities_matched": ["co-quanta-services"],
        "snippet": "Quanta Services raises 2026 outlook after record backlog. Total backlog reached $45.2 billion. "
                   "Revenue rose 57% to $12.0 billion in the third quarter. Data center load growth drove demand. Shares rose 5%."}


class TestAlertFormat(unittest.TestCase):
    def setUp(self):
        self._saved = dict(notify._LINES)
        notify._LINES["prof"] = {}

    def tearDown(self):
        notify._LINES.clear()
        notify._LINES.update(self._saved)

    def test_pulse_gloss(self):
        import pulse_gloss
        t = pulse_gloss.apply("Stargate와 HBM4(이미 풀이), HBM 증설. HBM 재고. EPS는 그대로 https://x.com/HBM")
        self.assertIn("Stargate(오픈AI·오라클·소프트뱅크 AI 데이터센터 사업)", t)
        self.assertIn("HBM4(이미 풀이)", t)
        self.assertEqual(t.count("HBM(고대역폭 메모리)"), 1)
        self.assertIn("https://x.com/HBM", t)
        self.assertNotIn("EPS(", t)
        self.assertEqual(pulse_gloss.unknown("Alphabet(GOOGL) EPS·CapEx·XPU 공급, HBM 증설, BIS(미국 상무부) ZZQ(뜻)"), ["XPU"])

    def test_three_paragraphs(self):
        msg = notify.format_item("P1", ITEM, points=["a", "b", "c", "d"], profile=["모델", "성장", "내러티브"])
        head, prof, pts = msg.split("\n\n")
        self.assertTrue(head.startswith("Quanta Services(PWR)｜<a href="))
        self.assertTrue(head.endswith("21:05"))   # 오늘이 아니면 날짜가 붙는다
        self.assertEqual(prof, "☞ 모델 · 성장 · 내러티브")   # 한 줄로 잇는다(2026-10-30)
        self.assertEqual(pts.splitlines(), ["• a", "• b", "• c"])   # 핵심은 3개까지
        self.assertNotIn("P1", msg)                                  # 등급 코드 비노출 유지

    def test_snippet_fallback_skips_title(self):
        pts = notify.snippet_points(ITEM)
        self.assertEqual(len(pts), 3)
        self.assertFalse(any("raises 2026 outlook" in p for p in pts))   # 제목과 같은 문장은 뺀다
        self.assertEqual(notify.snippet_points({"title": "X", "snippet": ""}), [])   # 없으면 채우지 않는다

    def test_profile_priority(self):
        notify._LINES["prof"] = {"co-quanta-services": {"lines": ["저장1", "저장2", "저장3"], "as_of": notify.common.now_kst().strftime("%Y-%m-%d")}}
        self.assertEqual(notify.company_profile(["co-quanta-services"], ["모델1"]), ["저장1", "저장2", "저장3"])
        notify._LINES["prof"] = {"co-quanta-services": {"lines": ["옛1", "옛2"], "as_of": "2025-01-01"}}   # 30일 지난 설명은 쓰지 않는다
        self.assertEqual(notify.company_profile(["co-quanta-services"], ["모델1", "모델2"]), ["모델1", "모델2"])

    def test_remember_profile_only_when_missing_or_stale(self):
        with tempfile.TemporaryDirectory() as d:
            saved = notify.PROFILES
            notify.PROFILES = Path(d) / "company_profiles.yaml"
            notify.PROFILES.write_text("# 머리말\nprofiles: {}\n", encoding="utf-8")
            orig_load = notify.common.load_yaml
            notify.common.load_yaml = lambda rel: __import__("yaml").safe_load(notify.PROFILES.read_text(encoding="utf-8")) if "company_profiles" in rel else orig_load(rel)
            try:
                self.assertTrue(notify.remember_profile(["us-x"], ["모델", "성장", "내러티브"]))
                self.assertFalse(notify.remember_profile(["us-x"], ["다른1", "다른2", "다른3"]))   # 30일 안에는 바꾸지 않는다
                self.assertFalse(notify.remember_profile(["us-y"], ["한 줄"]))                    # 2줄 미만은 저장하지 않는다
                text = notify.PROFILES.read_text(encoding="utf-8")
                self.assertTrue(text.startswith("# 머리말"))
                self.assertIn("모델", text)
            finally:
                notify.PROFILES = saved
                notify.common.load_yaml = orig_load


class TestAlertLines(unittest.TestCase):
    def test_profile_joins_on_one_line_without_heads(self):
        self.assertEqual(notify.profile_line(["모델: 기기 판매 + 서비스.", "성장: 서비스 매출", "멀티플 근거(시장 해석)"]),
                         "기기 판매 + 서비스 · 서비스 매출 · 멀티플 근거(시장 해석)")

    def test_synergy_only_when_given(self):
        item = {"title": "t", "url": "", "entities_matched": []}
        self.assertIn("• 시너지: AI 에이전트 기능 내재화(추정)", notify.format_item("P1", item, points=["a"], synergy="AI 에이전트 기능 내재화(추정)"))
        self.assertNotIn("시너지", notify.format_item("P1", item, points=["a"]))


if __name__ == "__main__":
    unittest.main()
