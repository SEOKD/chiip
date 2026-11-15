"""SPAC 기저율 재계산·점수 개선 시험 (2026-11-15, ADR-044)"""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "tenbagger"))
import spac_history as sh  # noqa: E402
import spac_score as ss  # noqa: E402

HC = sh.hcfg()
C = ss.cfg()
TODAY = date(2026, 11, 15)
BASE = {"price": 10.0, "trust_per_share": 10.2, "cash": {"trust_left": 0.2, "pipe": 0.05, "fees": 0.02}, "shares": {"공개 주주(환매 후)": 20, "스폰서": 5, "피인수 기존 주주": 50},
        "fairness": {"base": 1.0}, "lockups": []}


def row(**k):
    r = {"px_status": "ok", "close_date": "2021-06-01", "base_date": "2021-06-02", "listing": "active", "last_date": "2026-11-13", "key": "NASDAQ_X",
         "term_r": "-0.5", "r6m": "-0.2", "r12m": "-0.4", "r24m": "-0.6", "max24m": "1.5", "base_px": "12", "fate": "reporting", "fate_date": ""}
    r.update(k)
    return r


class History(unittest.TestCase):
    def test_spac_markers(self):
        self.assertTrue(sh.is_spac({"trust": 1, "red": 2}, []))
        self.assertTrue(sh.is_spac({"red": 3, "bca": 5}, []))                  # 지주회사 구조(신탁 계좌 문구 없음)
        self.assertTrue(sh.is_spac({}, ["RMG Acquisition Corp."]))
        self.assertFalse(sh.is_spac({"red": 20}, ["CARLISLE COMPANIES INC"]))  # 사채 상환 'redemption'만으로는 아니다

    def test_tickers_new_first(self):
        t = "Prior to the Closing, the units were listed under the symbol “CFII”. The common stock began trading on Nasdaq under the symbols “VIEW” and “VIEWW”."
        ticks, ex = sh.tickers_in(t)
        self.assertEqual(ticks[0], "VIEW")
        self.assertNotIn("VIEWW", ticks)
        self.assertEqual(ex, "Nasdaq")

    def test_fate_settle_window(self):
        sub = {"filings": {"recent": {"form": ["8-K", "25-NSE", "10-K"], "filingDate": ["2021-06-05", "2021-06-10", "2026-03-01"], "items": ["2.01,5.01", "", ""]}}}
        self.assertEqual(sh.fate_of(sub, "2021-06-01", "2026-11-15")[0], "reporting")   # 종결 직후 5.01·25는 스팩 정리
        sub = {"filings": {"recent": {"form": ["8-K"], "filingDate": ["2023-04-03"], "items": ["1.03"]}}}
        self.assertEqual(sh.fate_of(sub, "2021-06-01", "2026-11-15"), ("bankrupt", "2023-04-03"))

    def test_lag_and_stale_excluded(self):
        self.assertEqual(sh.usable(row(base_date="2024-01-24"), HC), (False, "기준일 지연"))
        self.assertEqual(sh.usable(row(listing="suspended", max24m="1", term_r="0"), HC), (False, "시세 정지"))
        self.assertTrue(sh.usable(row(), HC)[0])

    def test_terminal_with_delisting_return(self):
        r = row(r24m="", listing="delisted", last_date="2022-12-01", term_r="-0.8", key="NASDAQ_X")
        v, k = sh.horizon(r, "r24m", HC, TODAY)
        self.assertEqual(k, "term")
        self.assertAlmostEqual(v, 0.2 * (1 + HC["delist_ret"]["NASDAQ"]) - 1, places=6)
        v, _ = sh.horizon({**r, "fate": "acquired"}, "r24m", HC, TODAY)
        self.assertAlmostEqual(v, -0.8, places=6)   # 피인수는 보정 없음

    def test_incomplete_window_excluded_both_ways(self):
        r = row(close_date="2025-12-01", base_date="2025-12-02", r24m="", listing="delisted", last_date="2026-05-01")
        self.assertEqual(sh.horizon(r, "r24m", HC, TODAY), (None, "early"))
        f = {"fate": "bankrupt", "fate_date": "2026-03-01", "close_date": "2025-12-01"}
        self.assertIsNone(sh.failed_within(f, "r24m", HC, TODAY))
        self.assertEqual(sh.failed_within({**f, "close_date": "2021-06-01", "fate_date": "2022-03-01"}, "r24m", HC, TODAY), HC["fail_value"])

    def test_ten_dollar_basis(self):
        b = sh.block([row(r12m="-0.5", base_px="12")], [], HC, TODAY, ten=True)
        self.assertAlmostEqual(b["r12m"]["median"], 0.5 * 12 / 10 - 1, places=3)
        b = sh.block([row(base_px="0.01")], [], HC, TODAY, ten=True)   # 분할 이력 오류 의심 원가는 $10 기준에서 뺀다
        self.assertEqual(b["r12m"]["n"], 0)


class Score(unittest.TestCase):
    def test_kor_ncps_assumes_cohort_redemption(self):
        s = {**BASE, "shares": {"공개 주주(환매 전)": 20, "스폰서": 5, "피인수 기존 주주": 50}}
        v, assumed, _ = ss.kor_ncps(s, C, None, 0.9)
        self.assertEqual(assumed, 0.9)
        self.assertAlmostEqual(v, (0.2 * 0.1 - 0.02) * 1000 / (2 + 5), places=3)

    def test_time_pressure(self):
        young = ss.score({**BASE, "ipo_date": "2026-01-01", "as_of": "2026-11-01"}, "S3", True, C, TODAY)
        old = ss.score({**BASE, "ipo_date": "2023-11-01", "as_of": "2026-11-01"}, "S3", True, C, TODAY)
        self.assertEqual(young["factors"]["time"], 10.0)
        self.assertEqual(old["factors"]["time"], 0.0)
        ext = ss.score({**BASE, "ipo_date": "2026-01-01", "as_of": "2026-11-01", "extensions": 3}, "S3", True, C, TODAY)
        self.assertEqual(ext["factors"]["time"], 0.0)

    def test_missing_cap(self):
        r = ss.score(BASE, "S3", True, C, TODAY)
        self.assertLessEqual(r["score"], C["missing_cap"])
        self.assertIn("quality", r["missing"])
        self.assertFalse(r["candidate"])

    def test_psr_cap_and_projection_shrink(self):
        s = {**BASE, "ltm": {"revenue": 0.005, "profitable": False}, "projections": [{"rev": 0.05}], "peer_ev_rev": 50.0}
        r = ss.score(s, "S5", True, C, TODAY)
        self.assertLessEqual(r["factors"]["value"], 2.0)
        self.assertTrue(any("EV/매출" in k for k in r["kills"]))   # 매출 $10M 미만·40배 초과
        self.assertLess(r["factors"]["fundamentals"], 5)

    def test_prerevenue_not_killed(self):
        r = ss.score({**BASE, "ltm": {"revenue": 0, "profitable": False}}, "S5", True, C, TODAY)
        self.assertFalse(any("EV/매출" in k for k in r["kills"]))
        self.assertTrue(any("매출 전" in k for k in r["risks"]))

    def test_vote_below_trust_kill(self):
        r = ss.score({**BASE, "price": 9.0, "redemption": {"pct": 0.8}}, "S4", True, C, TODAY)
        self.assertTrue(any("신탁가 아래" in k for k in r["kills"]))

    def test_attention_has_no_weight(self):
        self.assertEqual(C["weights"]["pre_vote"]["attention"], 0)
        self.assertEqual(C["weights"]["post_close"]["attention"], 0)
        for reg in ("pre_vote", "post_close"):
            self.assertAlmostEqual(sum(C["weights"][reg].values()), 1.0, places=6)


if __name__ == "__main__":
    unittest.main()
