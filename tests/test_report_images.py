"""리포트 이미지·BOM (마스터 지시 2026-11-08, ADR-017) — API를 부르지 않는 단위 시험"""
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "tenbagger"))
import product_images as P  # noqa: E402
import image_check as C  # noqa: E402
import image_view as V  # noqa: E402
import report_html as rh  # noqa: E402

BOM = {"as_of": date.today().isoformat(), "layers_order": "앞→뒤", "items": [
    {"no": i, "part": f"부품{i}", "role": "역할", "supplier": "공급사", "this_company": i == 2, "source": "공시 URL", "confidence": "확인"} for i in range(1, 7)]
    + [{"no": 7, "part": "렌즈", "supplier": "미확인", "source": "", "confidence": "추정"}]}


class TestImages(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._L, self._J, self._I = P.LEDGER, P.JOBS, P.IMG
        P.IMG, P.LEDGER, P.JOBS = self.tmp, self.tmp / "ledger.csv", self.tmp / "jobs.json"
        C.STATE = self.tmp / "approvals.json"
        self.t = {"scope": "company", "id": "x", "kind": "exploded", "n": 1, "name": "트랜시버", "bom": BOM, "dir": self.tmp}

    def tearDown(self):
        P.IMG, P.LEDGER, P.JOBS = self._I, self._L, self._J

    def test_prompt_rules(self):
        p = P.prompt(self.t)
        self.assertIn("No text, no letters, no numbers, no logos", p)
        self.assertNotIn("렌즈", p)          # '추정' 부품은 그리지 않는다
        self.assertEqual(len(P.ordered(BOM)), 6)

    def test_min_six_confirmed(self):
        few = {**BOM, "items": BOM["items"][:5]}
        self.assertLess(len(P.confirmed(few)), P.cfg()["min_confirmed_parts"])

    def test_budget_and_google_cap(self):
        c = P.cfg()
        self.assertTrue(P.budget_ok(self.t, False, c)[0])
        P.log(self.t, "m", "2K", False, 8.95, "ok")
        self.assertEqual(P.budget_ok(self.t, False, c)[1], "over_budget")
        P.log(self.t, "m", "2K", False, 0, "google_cap")
        self.assertEqual(P.month_stopped(), "google_cap")
        P.log({**self.t, "kind": "resume"}, "-", "-", False, 0, "resumed")
        self.assertIsNone(P.month_stopped())

    def test_industry_share(self):
        ti = {**self.t, "scope": "industry"}
        P.log(ti, "m", "2K", False, 3.55, "ok")
        self.assertEqual(P.budget_ok(ti, False)[1], "over_budget_industry")
        self.assertTrue(P.budget_ok(self.t, False)[0])   # 종목 몫은 남아 있다

    def test_402_is_google_cap(self):
        class E(Exception):
            code = 402
            def read(self):
                return b'{"error":{"message":"Your prepayment credits are depleted"}}'
        self.assertEqual(P.classify_error(E())[0], "google_cap")

    def test_usable_needs_visual_and_approval(self):
        (self.tmp / "exploded_1.png").write_bytes(b"x" * 100)
        meta = {"file": "exploded_1.png", "hash": P.key_of(self.t)}
        P.meta_path(self.t).write_text(json.dumps(meta), encoding="utf-8")
        manual = {**P.cfg(), "auto_approve": {"company": False, "industry": False}}
        self.assertEqual(C.usable(self.t, manual)[1], "눈 검수 대기")
        C.visual(P.meta_path(self.t), True, parts=6, order_ok=True)
        self.assertEqual(C.usable(self.t, manual)[1], "마스터 승인 대기")
        self.assertIsNotNone(C.usable(self.t)[0])   # 자동 승인(2026-11-08 마스터 지시)
        C.decide("company", "x", "approved")
        self.assertIsNotNone(C.usable(self.t, manual)[0])

    def test_bom_tables(self):
        b = V.bom_block(BOM, "company")
        html = rh.bom_html(b)
        self.assertIn("이 회사", html)
        self.assertIn("color:var(--mut)", html)   # 추정 행 회색
        ind = {"items": [{"no": 1, "part": "코어 다이", "suppliers": [{"name": "A사", "ticker": "111", "source": "u"}, {"name": "B사", "ticker": "222", "source": "u"}],
                          "chiip_ids": ["kr-a", "kr-b"], "source": "u", "confidence": "확인"},
                         {"no": 2, "part": "본더", "kind": "장비", "suppliers": [], "confidence": "추정"}]}
        bi = V.bom_block(ind, "industry", watch={"kr-a"})
        self.assertEqual(bi["candidates"], ["B사(222) — 코어 다이"])
        self.assertEqual(len(bi["equip"]), 1)

    def test_image_block_render(self):
        rel = self.tmp / "p.png"
        rel.write_bytes(b"\x89PNG")
        orig = rh.ROOT
        rh.ROOT = self.tmp
        try:
            h = rh.image_html({"file": "p.png", "photo": "A", "title": "분해 개념도", "caption": P.cfg()["caption_fixed"],
                               "legend": [[1, "레이저", True]], "callouts": [{"no": 1, "x": 0.5, "y": 0.2, "own": True}]})
        finally:
            rh.ROOT = orig
        self.assertIn("data:image/png;base64", h)
        self.assertIn("사진 A", h)
        self.assertIn("AI 생성 개념도", h)
        self.assertIn("<circle", h)


if __name__ == "__main__":
    unittest.main()
