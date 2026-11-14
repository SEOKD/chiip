"""알파 발굴 엔진(ADR-043, 2026-11-15 마스터 지시) 오프라인 시험 — 단서 장부·채널 선별·메모 검사·채널 스크린·국장 테마·공시 해석·구루 점수"""
import json
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "discovery"))
sys.path.insert(0, str(ROOT / "radar"))
import channel_screens as cs  # noqa: E402
import channels  # noqa: E402
import kr_theme  # noqa: E402
import leads  # noqa: E402
import memo_check  # noqa: E402

D0 = date(2026, 11, 2)


class TmpLedger:
    """장부 경로를 임시 폴더로 — 실제 장부를 건드리지 않는다"""
    def __enter__(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.saved = (leads.LEADS, leads.EVENTS, leads.PRICES, leads.SCORECARD, leads.OUTD, channels.LATEST, channels.ALERTS, channels.OUTD, channels.FLAGS)
        leads.LEADS, leads.EVENTS, leads.PRICES = self.tmp / "leads.csv", self.tmp / "ev.csv", self.tmp / "px.csv"
        leads.SCORECARD, leads.OUTD = self.tmp / "sc.json", self.tmp
        channels.LATEST, channels.ALERTS, channels.OUTD, channels.FLAGS = self.tmp / "ch.json", self.tmp / "al.json", self.tmp, self.tmp / "flags.json"
        return self.tmp

    def __exit__(self, *a):
        (leads.LEADS, leads.EVENTS, leads.PRICES, leads.SCORECARD, leads.OUTD, channels.LATEST, channels.ALERTS, channels.OUTD, channels.FLAGS) = self.saved


def lead(**k):
    base = {"channel": "activist", "kind": "entry", "market": "us", "ticker": "XYZ", "name": "XYZ Corp", "signal": "시험", "strength": 7.0, "tv": "NASDAQ:XYZ", "date": D0.isoformat()}
    base.update(k)
    return base


class TestLeads(unittest.TestCase):
    def test_add_dedupe_and_validation(self):
        with TmpLedger():
            self.assertEqual(len(leads.add([lead()], today=D0)), 1)
            self.assertEqual(len(leads.add([lead(date=(D0 + timedelta(days=5)).isoformat())], today=D0)), 0)   # 60일 안 같은 단서
            self.assertEqual(len(leads.add([lead(kind="contest")], today=D0)), 1)                               # 종류가 다르면 새 단서
            with self.assertRaises(ValueError):
                leads.add([lead(channel="없는채널")], today=D0)
            with self.assertRaises(ValueError):
                leads.add([lead(market="cn")], today=D0)
            with self.assertRaises(ValueError):
                leads.add([lead(strength=11)], today=D0)

    def test_void_hides_lead(self):
        with TmpLedger():
            r = leads.add([lead()], today=D0)[0]
            leads.event(r["lead_id"], "void", "시험", D0)
            self.assertEqual(leads.recent(30, today=D0), [])
            self.assertEqual(len(leads.read()), 1)   # 장부에는 남는다

    def test_scorecard_forward_excess(self):
        with TmpLedger() as tmp:
            leads.add([lead(price=100, mcap_usd=5e8)], today=D0)
            rows = [{"date": D0.isoformat(), "tv": "AMEX:IWM", "close": "200"},
                    {"date": (D0 + timedelta(days=31)).isoformat(), "tv": "NASDAQ:XYZ", "close": "120"},
                    {"date": (D0 + timedelta(days=31)).isoformat(), "tv": "AMEX:IWM", "close": "210"}]
            leads._append(leads.PRICES, leads.PX_FIELDS, [dict(r, source="t") for r in rows])
            sc = leads.scorecard(today=D0 + timedelta(days=40))
            h = sc["channels"]["activist"]["horizons"]["30"]
            self.assertEqual(h["n"], 1)
            self.assertAlmostEqual(h["median_excess"], 0.20 - 0.05, 4)   # 미국 $10B 미만은 IWM 대비
            self.assertAlmostEqual(h["hit_shrunk"], (1 + 10) / (1 + 20), 3)

    def test_price_specs_includes_bench_first(self):
        with TmpLedger():
            leads.add([lead()], today=D0)
            specs = leads.price_specs(today=D0)
            self.assertIn("NASDAQ:XYZ", specs)
            self.assertEqual(specs[0], "SP:SPX")


class TestChannels(unittest.TestCase):
    def test_confluence_and_flags(self):
        with TmpLedger() as tmp:
            leads.add([lead(), lead(channel="guru", kind="new", strength=6.0)], today=D0)
            leads.add([lead(channel="special", kind="buyback", market="kr", ticker="123456", name="가나다", strength=6.0, tv="KRX:123456"),
                       lead(channel="kr_theme", kind="ignite", market="kr", ticker="123456", name="가나다", strength=6.5, tv="KRX:123456")], today=D0)
            (tmp / "flags.json").write_text(json.dumps({"rows": {"123456": [{"date": D0.isoformat(), "kind": "전환사채권발행", "rcept_no": "1"}]}}), encoding="utf-8")
            rows = channels.triage(today=D0)
            us = next(r for r in rows if r["code"] == "XYZ")
            self.assertEqual(us["score"], 7.8)           # 7.0 + 겹침 0.75(소수 첫째 자리)
            self.assertEqual(us["stage"], "② 채널 선별")
            kr = next(r for r in rows if r["code"] == "123456")
            self.assertAlmostEqual(kr["score"], 5.8)     # 6.5 + 0.75 − 희석 공시 1.5(최고 채널이 special이 아님)
            self.assertTrue(kr["penalty_why"])


class TestMemoCheck(unittest.TestCase):
    GOOD = {"id": "us-xyz", "date": "2026-11-15", "verdict": "focus", "thesis": "t", "edge_type": "analytical", "other_side": "지수 매도",
            "evidence": ["https://a", "https://b"], "consensus_gap": [{"driver": "FY27 매출", "ours": 120, "consensus": 100, "source": "Fiscal.ai"}],
            "price": 10, "scenarios": {"bull": {"value": 20, "p": 0.3}, "base": {"value": 13, "p": 0.5}, "bear": {"value": 7, "p": 0.2}},
            "catalysts": [{"date": "2027-01-10", "what": "실적"}], "premortem": ["a", "b", "c"],
            "kills": [{"metric": "m", "threshold": "t", "deadline": "d", "source": "s"}, {"metric": "m2", "threshold": "t", "deadline": "d", "source": "s"}],
            "implied": {"growth": 0.1, "pctile": 60, "source": "역DCF"}, "red_team": {"verdict": "유지", "answered": True}, "expiry": "2027-11-14"}

    def test_pass(self):
        ok, fails, warns, nums = memo_check.check(dict(self.GOOD))
        self.assertTrue(ok, fails)
        self.assertAlmostEqual(nums["skew"], (0.3 * 10 + 0.5 * 3) / (0.2 * 3), 2)
        self.assertEqual(nums["catalyst_score"], 1.0)

    def test_fail_reasons(self):
        bad = dict(self.GOOD, consensus_gap=[{"driver": "x", "ours": 101, "consensus": 100, "source": "s"}], premortem=["a"],
                   scenarios={"bull": {"value": 11, "p": 0.3}, "base": {"value": 10, "p": 0.4}, "bear": {"value": 7, "p": 0.3}})
        ok, fails, _, _ = memo_check.check(bad)
        self.assertFalse(ok)
        self.assertTrue(any("변이 관점" in f for f in fails))
        self.assertTrue(any("사전 부검" in f for f in fails))
        self.assertTrue(any("상방÷하방" in f for f in fails))

    def test_hold_records_only(self):
        ok, fails, _, _ = memo_check.check(dict(self.GOOD, verdict="hold", premortem=[]))
        self.assertTrue(ok)
        self.assertTrue(fails)


class TestChannelScreens(unittest.TestCase):
    def test_pct_rank_ties(self):
        r = cs.pct_rank({"a": 1, "b": 1, "c": 3, "d": None})
        self.assertEqual(r["a"], r["b"])
        self.assertEqual(r["c"], 1.0)
        self.assertNotIn("d", r)

    def test_neglected_gates(self):
        s = cs.cfg()["screens"]["neglected"]
        row = {"market_cap_basic": 3e8, "AvgValue.Traded_30d": 2e6, "close": 10, "is_primary": True, "price_free_cash_flow_ttm": 8,
               "total_revenue_yoy_growth_ttm": 20, "altman_z_score_ttm": 3, "free_cash_flow_ttm": 1e7, "buyback_yield": 0}
        f, mc, val = cs.features("neglected", row, 1.0, s, "america")
        self.assertIsNone(cs.gates("neglected", row, mc, val, s, "america")[0])
        self.assertEqual(cs.gates("neglected", dict(row, is_primary=False), mc, val, s, "america")[0], "주 상장 아님(2차 상장)")
        self.assertIn("희석", cs.gates("neglected", dict(row, buyback_yield=-25), mc, val, s, "america")[0])
        why, _ = cs.gates("neglected", dict(row, altman_z_score_ttm=0.5, free_cash_flow_ttm=-1), mc, val, s, "america")
        self.assertTrue(why)
        self.assertGreater(f["value"], 0)

    def test_uk_value_in_pence(self):
        s = cs.cfg()["screens"]["neglected"]
        _, _, val = cs.features("neglected", {"market_cap_basic": 1e8, "AvgValue.Traded_30d": 1e8}, 1.27, s, "uk")
        self.assertAlmostEqual(val, 1e8 * 1.27 / 100)

    def test_base_rate_shrink(self):
        br = cs.base_rate(cs.cfg(), "tw")
        self.assertTrue(0.0069 < br["p10x"] < 0.014)


class TestKrTheme(unittest.TestCase):
    def snaps(self, active_days):
        out = []
        for i, n in enumerate(active_days):
            d = (date(2026, 10, 1) + timedelta(days=i)).isoformat()
            rows = [{"code": c, "name": c, "industry": "", "change": 12.0, "value_krw": 5e9, "growth": 30.0, "op_margin": 12.0, "close": 1.0}
                    for c in ["009540", "042660", "010140", "329180"][:n]]
            out.append({"date": d, "rows": rows})
        return out

    def test_ignite_after_quiet(self):
        t = next(x for x in kr_theme.cfg()["themes"] if x["id"] == "shipbuilding")
        lc = kr_theme.cfg()["lifecycle"]
        sn = self.snaps([0] * 12 + [3])
        st = kr_theme.theme_state("shipbuilding", t, sn, {}, lc, sn[-1]["date"])
        self.assertIn("ignite", st["stages"])

    def test_overheat_by_limit_ups(self):
        t = next(x for x in kr_theme.cfg()["themes"] if x["id"] == "shipbuilding")
        lc = kr_theme.cfg()["lifecycle"]
        sn = self.snaps([2] * 5 + [4])
        for r in sn[-1]["rows"][:3]:
            r["change"] = 30.0
        st = kr_theme.theme_state("shipbuilding", t, sn, {}, lc, sn[-1]["date"])
        self.assertIn("overheat", st["stages"])
        self.assertIn("spread", st["stages"])


class TestFilingsParse(unittest.TestCase):
    def setUp(self):
        import discovery_filings as df
        self.df = df

    def test_purpose_ignores_boilerplate(self):
        boiler = ("<transactionPurpose>The Funds acquired the shares for investment purposes. Except as set forth above, none of the Reporting Persons has any present plans "
                  "which relate to or would result in: (a) The acquisition by any person of additional securities; (d) Any change in the present board of directors; "
                  "(j) Any action similar to any of those enumerated above.</transactionPurpose>")
        self.assertEqual(self.df.purpose_score(boiler)[0], 0)
        act = "<transactionPurpose>The Reporting Persons believe the shares are undervalued and intend to engage with the board regarding strategic alternatives, including a sale of the Issuer, and may nominate directors.</transactionPurpose>"
        self.assertGreaterEqual(self.df.purpose_score(act)[0], 4)

    def test_parties_order(self):
        subj, filers = self.df.parties({"display_names": ["Centuri Holdings, Inc.  (CTRI)  (CIK 0001981599)", "ICAHN CARL C  (CIK 0000921669)"]})
        self.assertEqual(subj["tickers"], ["CTRI"])
        self.assertEqual(filers[0]["cik"], "921669")

    def test_name_normalizers(self):
        self.assertEqual(self.df.kr_name("Palliser Capital Master Fund"), "PalliserCapitalMasterFund")
        self.assertIn("Elliott", self.df.jp_name("Ｅｌｌｉｏｔｔ Ｉｎｖｅｓｔｍｅｎｔ"))

    def test_xl_date(self):
        self.assertEqual(self.df._xl_date("46196"), "2026-06-23")
        self.assertEqual(self.df._xl_date("2026/10/03"), "2026-10-03")
        self.assertEqual(self.df._xl_date(""), "")

    def test_tw_buyback_purpose_filter(self):
        rows = [{"公司代號": "1234", "公司名稱": "甲", "主旨 ": "公告本公司董事會決議買回庫藏股", "符合條款": "第35款", "發言日期": "1151113",
                 "說明": "1.董事會決議日期:115/11/13\n2.買回股份目的:維護公司信用及股東權益\n3.買回股份總金額上限(元):1,000,000"},
                {"公司代號": "5678", "公司名稱": "乙", "主旨 ": "公告本公司董事會決議買回庫藏股", "符合條款": "第35款", "發言日期": "1151113",
                 "說明": "2.買回股份目的:轉讓股份予員工"}]
        orig = self.df.common.http_get
        self.df.common.http_get = lambda url, *a, **k: json.dumps(rows if "twse" in url else []).encode()
        try:
            out = self.df.tw_rows()
        finally:
            self.df.common.http_get = orig
        self.assertEqual([r["ticker"] for r in out], ["1234"])
        self.assertEqual(out[0]["date"], "2026-11-13")
        self.assertEqual(out[0]["tv"], "TWSE:1234")


class TestGuruScore(unittest.TestCase):
    XML = b"""<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
      <infoTable><nameOfIssuer>AAA</nameOfIssuer><cusip>000000AAA</cusip><value>600</value><shrsOrPrnAmt><sshPrnamt>60</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt></infoTable>
      <infoTable><nameOfIssuer>BBB</nameOfIssuer><cusip>000000BBB</cusip><value>300</value><shrsOrPrnAmt><sshPrnamt>30</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt></infoTable>
      <infoTable><nameOfIssuer>CCC</nameOfIssuer><cusip>000000CCC</cusip><value>100</value><shrsOrPrnAmt><sshPrnamt>10</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt><putCall>Put</putCall></infoTable>
    </informationTable>"""

    def setUp(self):
        import guru13f
        self.g = guru13f
        self.r = guru13f.cfg()[1]

    def test_parse_excludes_options(self):
        h = self.g.parse_table(self.XML)
        self.assertEqual(set(h), {"000000AAA", "000000BBB"})

    def test_events_new_add_best(self):
        cur = self.g.parse_table(self.XML)
        prev = {"000000AAA": {"sh": 30, "value": 300, "name": "AAA"}}
        w, top5, n, usd = self.g.book_stats(cur)
        ev = self.g.events(cur, prev, {}, w, self.r)
        self.assertEqual(ev["000000AAA"][0][0], "add")     # 30 → 60주(+100%)
        self.assertEqual(ev["000000BBB"][0][0], "new")
        q = self.g.quality({"name": "x"}, top5, n, usd, self.r, date(2026, 11, 15))
        self.assertEqual(q, 1.2)                            # 상위 5 비중 100% → 집중

    def test_consensus_and_crowding(self):
        per = {"a": {"guru": "A", "q": 1.0, "fd": "2026-11-14", "rd": "2026-09-30", "adsh": "1", "cik": "1", "ev": {"X": [("new", 1.0, 1.0, 0.2, 1, None)]}, "name": {"X": "X"}},
               "b": {"guru": "B", "q": 1.0, "fd": "2026-11-13", "rd": "2026-09-30", "adsh": "2", "cik": "2", "ev": {"X": [("new", 1.0, 0.8, 0.1, 2, None)]}, "name": {"X": "X"}}}
        agg = self.g.score_all(per, [], self.r)
        self.assertEqual(agg["X"]["kind"], "cluster")
        self.assertAlmostEqual(agg["X"]["score"], 1.0 + 0.8 + 0.15, 3)
        agg = self.g.apply_crowding(agg, {"X": 0.45}, self.r)
        self.assertAlmostEqual(agg["X"]["score"], 1.95 - 0.6, 3)


if __name__ == "__main__":
    unittest.main()
