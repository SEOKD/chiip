"""애널리스트 토론 — 가상 명칭 제외 (마스터 지시 2026-11-08)"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "tenbagger"))
import debate_view as dv  # noqa: E402

SEATS = dv.SEATS
PANEL = [{"seat": s, "name": f"가상인물{i}", "house": f"가상하우스{i}", "thesis": f"가상인물{i}의 논리", "evidence": ["숫자"], "falsifier": "조건"} for i, s in enumerate(SEATS)]
DB = {"panel": PANEL,
      "rounds": [{"round": "개회", "remarks": [{"seat": s, "text": "개회"} for s in SEATS]},
                 {"round": "반박1", "remarks": [{"seat": s, "to": "Buy", "text": "가상인물1 숫자는 틀렸다"} for s in SEATS[:3]]},
                 {"round": "반박2", "remarks": [{"seat": s, "to": "Sell", "text": "반박"} for s in SEATS[:3]]},
                 {"round": "최종", "remarks": [{"seat": s, "text": "최종"} for s in SEATS]}],
      "final": {"rating": "Buy", "votes": {s: "Buy" for s in SEATS}, "reason": "가상하우스2의 반박이 살아남았다", "dissent": "가상인물4 반대"}}


class TestNoNames(unittest.TestCase):
    def test_names_and_houses_never_rendered(self):
        sec = dv.section({"debate": DB}, {"final": "Buy", "rule": "Buy", "asked": "Buy", "capped": False})
        body = str(sec["blocks"])
        self.assertNotIn("가상인물", body)
        self.assertNotIn("가상하우스", body)
        self.assertIn("Buy 자리", body)            # 발언 속 이름은 자리 이름으로
        table = next(b for b in sec["blocks"] if b.get("type") == "table")
        self.assertNotIn("애널리스트", table["headers"])

    def test_names_not_required(self):
        db = {**DB, "panel": [{k: v for k, v in p.items() if k not in ("name", "house")} for p in PANEL]}
        dv.check(db)


if __name__ == "__main__":
    unittest.main()
