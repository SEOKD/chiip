"""알파 발굴 엔진 빈 채널 2개(2026-11-15) 오프라인 시험 — 내부자 매수(미 Form 4·한 소유보고)·13F 가치 칸·VIP 쏠림·Fairholme N-PORT. 네트워크는 흉내 낸다"""
import gzip
import io
import json
import sys
import tempfile
import unittest
import zipfile
from datetime import date
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
sys.path.insert(0, str(ROOT / "scripts" / "discovery"))
import guru13f  # noqa: E402
import insider_buys as ib  # noqa: E402
import leads  # noqa: E402
import thirteenf_market as tm  # noqa: E402
import tvsym  # noqa: E402
from pollers import common  # noqa: E402

R = ib.rules()


def form4(issuer_cik="1750735", ticker="XYZ", owners=(("2131880", "Doe Jane", True, False, False, ""),), txs=(("P", "A", "2026-11-12", 1000, 20.0, "Common Stock"),), plan="0"):
    o = "".join(f"""<reportingOwner><reportingOwnerId><rptOwnerCik>{c}</rptOwnerCik><rptOwnerName>{n}</rptOwnerName></reportingOwnerId>
      <reportingOwnerAddress><rptOwnerStreet1>1 MAIN ST</rptOwnerStreet1></reportingOwnerAddress>
      <reportingOwnerRelationship><isDirector>{int(d)}</isDirector><isOfficer>{int(off)}</isOfficer><isTenPercentOwner>{int(ten)}</isTenPercentOwner>
      <isOther>0</isOther><officerTitle>{t}</officerTitle></reportingOwnerRelationship></reportingOwner>""" for c, n, d, off, ten, t in owners)
    t = "".join(f"""<nonDerivativeTransaction><securityTitle><value>{ti}</value></securityTitle><transactionDate><value>{dt}</value></transactionDate>
      <transactionCoding><transactionFormType>4</transactionFormType><transactionCode>{code}</transactionCode></transactionCoding>
      <transactionAmounts><transactionShares><value>{sh}</value></transactionShares><transactionPricePerShare><value>{px}</value></transactionPricePerShare>
      <transactionAcquiredDisposedCode><value>{ad}</value></transactionAcquiredDisposedCode></transactionAmounts></nonDerivativeTransaction>""" for code, ad, dt, sh, px, ti in txs)
    return f"""<?xml version="1.0"?><ownershipDocument><schemaVersion>X0609</schemaVersion><documentType>4</documentType><periodOfReport>2026-11-12</periodOfReport>
      <issuer><issuerCik>{issuer_cik}</issuerCik><issuerName>XYZ Corp</issuerName><issuerTradingSymbol>{ticker}</issuerTradingSymbol></issuer>{o}
      <aff10b5One>{plan}</aff10b5One><nonDerivativeTable>{t}</nonDerivativeTable></ownershipDocument>""".encode()


def buy(**k):
    b = {"m": "us", "id": "A1", "issuer": "100", "ticker": "XYZ", "name": "XYZ Corp", "owners": ["1"], "role": "이사", "ceo": False, "cfo": False, "exec": True,
         "who": "Doe Jane", "title": "", "date": "2026-11-10", "filed": "2026-11-12", "shares": 1000, "value": 50000.0, "price": 50.0, "ccy": "USD",
         "routine": False, "rt": {}, "url": "https://www.sec.gov/x/"}
    b.update(k)
    return b


class TmpLedger:
    """장부 경로를 임시 폴더로 — 실제 장부를 건드리지 않는다"""
    def __enter__(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.saved = (leads.LEADS, leads.EVENTS, leads.PRICES)
        leads.LEADS, leads.EVENTS, leads.PRICES = self.tmp / "leads.csv", self.tmp / "ev.csv", self.tmp / "px.csv"
        return self.tmp

    def __exit__(self, *a):
        leads.LEADS, leads.EVENTS, leads.PRICES = self.saved


class TestForm4(unittest.TestCase):
    def test_parse_and_open_market_buys(self):
        d = ib.parse_form4(form4(txs=(("P", "A", "2026-11-12", 1000, 20.0, "Common Stock"), ("S", "D", "2026-11-12", 10, 21.0, "Common Stock"),
                                      ("P", "A", "2026-11-12", 50, 25.0, "Series A Preferred Stock"), ("A", "A", "2026-11-12", 500, 0, "Common Stock"))))
        self.assertEqual((d["issuer_cik"], d["ticker"], d["plan"]), ("1750735", "XYZ", False))
        self.assertTrue(d["owners"][0]["director"])
        self.assertNotIn("main st", json.dumps(d).lower())   # 주소는 읽지 않는다
        b = ib.open_market_buys(d, R)
        self.assertEqual([(t["code"], t["shares"]) for t in b], [("P", 1000.0)])   # 매도·우선주·부여 제외

    def test_plan_and_units(self):
        self.assertEqual(ib.open_market_buys(ib.parse_form4(form4(plan="true")), R), [])          # 10b5-1 계획 서류
        d = ib.parse_form4(form4(txs=(("P", "A", "2026-11-12", 100, 30.0, "Common Units"), ("P", "A", "2026-11-12", 100, 10.0, "Units"))))
        self.assertEqual([t["title"] for t in ib.open_market_buys(d, R)], ["Common Units"])       # MLP 보통 단위는 넣고 SPAC 유닛은 뺀다

    def test_roles_and_privacy(self):
        o = lambda name, d=False, off=False, ten=False, t="": {"cik": "1", "name": name, "director": d, "officer": off, "ten": ten, "other": False, "title": t}
        self.assertEqual(ib.owner_role([o("Kim A", off=True, t="President and Chief Executive Officer")])[:3], ("CEO", True, False))
        self.assertEqual(ib.owner_role([o("Lee B", off=True, t="EVP & CFO")])[:3], ("CFO", False, True))
        self.assertFalse(ib.owner_role([o("Park C", d=True, t="Former Chief Executive Officer")])[1])
        self.assertEqual(ib.owner_role([o("Smith John", ten=True)])[4], "10% 주주(개인)")              # 임원 아닌 개인 대주주 = 이름 없이
        self.assertEqual(ib.owner_role([o("Acme Capital Partners LP", ten=True)])[4], "Acme Capital Partners LP")
        self.assertEqual(ib.owner_role([o("Doe Jane", d=True)])[4], "Doe Jane")                      # 이사 = 공개 직책자

    def test_ticker_first_symbol(self):
        self.assertEqual(ib.parse_form4(form4(ticker="ABC, ABC.WS"))["ticker"], "ABC")
        self.assertEqual(ib.parse_form4(form4(ticker="NONE"))["ticker"], "")
        self.assertEqual(ib.parse_form4(form4(ticker="NYSE:FLG"))["ticker"], "FLG")   # 거래소 접두(2026-11-15 실측)

    def test_offering_participation_excluded(self):
        x = form4().replace(b"<value>20.0</value>", b'<value>20.0</value><footnoteId id="F1"/>').replace(
            b"</ownershipDocument>", b'<footnotes><footnote id="F1">Shares purchased in the Issuer\'s underwritten public offering at the public offering price.</footnote></footnotes></ownershipDocument>')
        self.assertEqual(ib.open_market_buys(ib.parse_form4(x), R), [])
        y = form4().replace(b"<value>20.0</value>", b'<value>20.0</value><footnoteId id="F1"/>').replace(
            b"</ownershipDocument>", b"<footnotes><footnote id=\"F1\">The price reported is a weighted average price; purchased in multiple transactions.</footnote></footnotes></ownershipDocument>")
        self.assertEqual(len(ib.open_market_buys(ib.parse_form4(y), R)), 1)   # 가중평균 각주는 장내 매수 그대로


class TestRoutineUS(unittest.TestCase):
    """CMP 일상형: 앞선 3년 해마다 같은 달 같은 회사 P·S 거래 → 일상형"""
    def fake(self, years_codes):
        sub = {"filings": {"recent": {"form": [], "reportDate": [], "filingDate": [], "accessionNumber": [], "primaryDocument": []}, "files": []}}
        xml = {}
        for y, code in years_codes.items():
            a = f"0000000000-{y % 100:02d}-000001"
            rc = sub["filings"]["recent"]
            for k, v in (("form", "4"), ("reportDate", f"{y}-11-05"), ("filingDate", f"{y}-11-07"), ("accessionNumber", a), ("primaryDocument", f"xslF345X05/f{y}.xml")):
                rc[k].append(v)
            xml[f"f{y}.xml"] = form4(issuer_cik="100", txs=((code, "A" if code == "P" else "D", f"{y}-11-05", 10, 5.0, "Common Stock"),))
        calls = []

        def get(url):
            calls.append(url)
            if "submissions" in url:
                return json.dumps(sub).encode()
            return xml[url.rsplit("/", 1)[-1]]
        return get, calls

    def test_routine_three_years(self):
        get, _ = self.fake({2023: "P", 2024: "S", 2025: "P"})
        with mock.patch.object(ib, "_get", get):
            rt = ib.routine_us("1", "100", "2026-11-12", R, {}, {})
        self.assertEqual((rt["routine"], rt["same"], rt["verified"], rt["hist"]), (True, 3, 3, True))

    def test_grant_month_is_not_routine(self):
        get, _ = self.fake({2023: "P", 2024: "A", 2025: "P"})   # 2024년 11월은 주식 부여(A)뿐
        with mock.patch.object(ib, "_get", get):
            rt = ib.routine_us("1", "100", "2026-11-12", R, {}, {})
        self.assertFalse(rt["routine"])

    def test_missing_year_skips_documents(self):
        get, calls = self.fake({2023: "P", 2025: "P"})   # 2024년 11월 없음 → 원문을 열지 않고 기회형
        with mock.patch.object(ib, "_get", get):
            rt = ib.routine_us("1", "100", "2026-11-12", R, {}, {})
        self.assertEqual((rt["routine"], rt["same"]), (False, 1))
        self.assertEqual(sum(1 for c in calls if "submissions" not in c), 0)


def kr_zip(rows):
    """DART 원본 XML(소유상황보고서 세부변동내역)을 흉내 낸 zip — 보고자 인적 사항 칸도 넣어 읽지 않는지 본다"""
    tr = "".join(f"""<TR ACOPY="Y"><TU AUNIT="RPT_RSN" AUNITVALUE="{c}" ENG="x">{lab}</TU><TU AUNIT="MDF_DM" AUNITVALUE="{d}">{d[:4]}년</TU>
      <TU AUNIT="STR_KND" AUNITVALUE="1" ENG="Common stock">보통주</TU><TE ACODE="BFR_STK_CNT">1,000</TE><TE ACODE="MDF_STK_CNT">{chg}</TE>
      <TE ACODE="AFR_STK_CNT">2,000</TE><TE ACODE="ACI_AMT2">{px}</TE><TE ACODE="RMK">-</TE><TU AUNIT="TRD_PLN_RD" AUNITVALUE="{plan}">{plan}</TU></TR>"""
                 for c, lab, d, chg, px, plan in rows)
    doc = f"""<DOCUMENT><BODY><P>생년월일 500101 주소 서울시</P><TABLE><TBODY>{tr}<TR><TD>합 계</TD></TR></TBODY></TABLE></BODY></DOCUMENT>"""
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("20261113000001.xml", doc.encode("utf-8"))
    return b.getvalue()


class TestKorea(unittest.TestCase):
    def test_parse_doc_codes_and_plan(self):
        rows = ib.parse_kr_doc(kr_zip([("01", "장내매수(+)", "20261110", "1,749", "5,822", "-"), ("56", "대여(-)", "20261110", "-500", "-", "-"),
                                       ("01", "장내매수(+)", "20261111", "300", "6,000", "20261007")]))
        self.assertEqual([r["code"] for r in rows], ["01", "56", "01"])
        self.assertEqual((rows[0]["date"], rows[0]["chg"], rows[0]["price"], rows[0]["plan"]), ("2026-11-10", 1749.0, 5822.0, ""))
        self.assertEqual(rows[2]["plan"], "20261007")   # 거래계획보고일자 → 미리 알린 매매
        self.assertNotIn("500101", json.dumps(rows))    # 생년월일은 읽지 않는다
        self.assertEqual(ib.parse_kr_doc(b"not zip"), [])

    def test_roles(self):
        es = lambda pos, reg="등기임원", major="-", who="홍길동": {"isu_exctv_ofcps": pos, "isu_exctv_rgist_at": reg, "isu_main_shrholdr": major, "repror": who}
        self.assertEqual(ib.kr_role(es("대표이사 사장"))[:4], ("대표이사", True, False, True))
        self.assertFalse(ib.kr_role(es("부대표"))[1])
        self.assertTrue(ib.kr_role(es("전무(CFO)"))[2])
        self.assertEqual(ib.kr_role(es("-", "-", "10%이상주주", "김개인"))[4], "주요주주(개인)")
        self.assertEqual(ib.kr_role(es("-", "-", "사실상지배주주", "(주)한화"))[4], "(주)한화")

    def test_routine_kr(self):
        docs = {}

        def dart(path, params, key, binary=False, timeout=40):
            if path == "list.json":
                y = params["bgn_de"][:4]
                return {"list": [{"report_nm": ib.KR_REPORT, "flr_nm": "홍 길동", "rcept_no": f"{y}1105000001"}], "total_page": 1}
            docs[params["rcept_no"]] = 1
            y = params["rcept_no"][:4]
            return kr_zip([("01" if y != "2024" else "35", "x", f"{y}1105", "10", "1000", "-")])
        with mock.patch.object(ib, "_dart", dart):
            rt = ib.routine_kr("k", "0001", "홍길동", "2026-11-12", R, {}, {})
        self.assertEqual((rt["routine"], rt["same"], rt["verified"]), (False, 2, 1))   # 2024년 11월은 수증(35) — 장내 거래 아님

    def test_kr_collect_end_to_end(self):
        st = {}
        lst = {"list": [{"report_nm": ib.KR_REPORT, "stock_code": "091700", "corp_code": "0001", "corp_name": "파트론", "corp_cls": "K", "rcept_dt": "20261112",
                         "flr_nm": "김대표", "rcept_no": "20261112000001"},
                        {"report_nm": "[기재정정]" + ib.KR_REPORT, "stock_code": "091700", "corp_code": "0001", "rcept_no": "20261112000002"}], "total_page": 1}

        def dart(path, params, key, binary=False, timeout=40):
            if path == "list.json":
                return lst if "corp_code" not in params else {"list": [], "total_page": 1}
            if path == "elestock.json":
                return {"list": [{"rcept_no": "20261112000001", "rcept_dt": "2026-11-12", "repror": "김대표", "isu_exctv_rgist_at": "등기임원", "isu_exctv_ofcps": "대표이사",
                                  "isu_main_shrholdr": "-", "sp_stock_lmp_irds_cnt": "40,000"}]}
            return kr_zip([("01", "장내매수(+)", "20261114", "40,000", "6,000", "-")])   # 변동일(결제일)이 접수일보다 늦다
        with mock.patch.object(ib, "_dart", dart):
            out, errs = ib.kr_collect(st, R, "k", 1e12, date(2026, 11, 15))
        self.assertEqual(errs, [])
        self.assertEqual(len(out), 1)
        b = out[0]
        self.assertEqual((b["ticker"], b["role"], b["ceo"], b["value"], b["date"], b["board"]), ("091700", "대표이사", True, 240000000, "2026-11-12", "KOSDAQ"))
        self.assertEqual(st["kr"]["queue"], [])


class TestEvaluate(unittest.TestCase):
    def setUp(self):
        self.p = mock.patch.object(tvsym, "sec_table", lambda force=False: {})
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def test_cluster_counts_groups(self):
        bs = [buy(id="A1", owners=["1"], value=600000.0),
              buy(id="A2", owners=["2", "3"], role="CFO", cfo=True, date="2026-11-11", value=500000.0),   # 공동 보고(2·3) = 1명
              buy(id="A3", owners=["3"], date="2026-11-12", value=100.0)]                                  # 3은 A2와 같은 묶음
        rows = ib.evaluate(bs, {"A3"}, R)
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual((r["kind"], r["extra"]["n_buyers"]), ("cluster", 2))
        self.assertEqual(r["strength"], 7.5)   # 6.5 + CFO 0.5(본인 $500K ≥ $250K) + 합계 $1.1M 0.5
        self.assertIn("CFO 포함", r["signal"])
        self.assertEqual(r["tv"], "NASDAQ:XYZ")
        small = [buy(id="S1", owners=["1"]), buy(id="S2", owners=["2"], role="CEO", ceo=True, value=20000.0)]
        self.assertEqual(ib.evaluate(small, {"S2"}, R)[0]["strength"], 6.5)   # CEO 소액 동반 매수는 가점 없음(경보 7.0 아래)

    def test_major_holders_merge_and_routine_late_excluded(self):
        bs = [buy(id="B1", owners=["7"], exec=False, role="10% 주주"), buy(id="B2", owners=["8"], exec=False, role="10% 주주"),
              buy(id="B3", owners=["9"], routine=True), buy(id="B4", owners=["10"], date="2026-09-01", filed="2026-11-12")]
        self.assertEqual(ib.count_groups(bs[:2]), 1)                  # 임원 아닌 10% 주주는 합쳐 1명
        self.assertEqual(ib.evaluate(bs, {"B1", "B2", "B3", "B4"}, R), [])   # 일상형·늦은 제출(72일)은 세지 않는다

    def test_ceo_alone_and_market_mult(self):
        rows = ib.evaluate([buy(id="C1", role="CEO", ceo=True, value=300000.0)], {"C1"}, R)
        self.assertEqual((rows[0]["kind"], rows[0]["strength"]), ("ceo", 6.0))
        kr = [buy(id="K1", m="kr", issuer="0001", ticker="091700", owners=["가"], ccy="KRW", value=2e8),
              buy(id="K2", m="kr", issuer="0001", ticker="091700", owners=["나"], ccy="KRW", value=1e8, board="KOSDAQ")]
        r = ib.evaluate(kr, {"K2"}, R)[0]
        self.assertEqual((r["kind"], r["strength"], r["tv"]), ("cluster", 5.8, "KRX:091700"))   # 5 + (6.5 − 5) × 0.5
        self.assertIn("3.0억 원", r["signal"])
        self.assertEqual(r["extra"]["board"], "KOSDAQ")
        self.assertEqual(ib.evaluate([buy(id="D1")], {"D1"}, R), [])   # 이사 혼자 = 단서 아님

    def test_collect_us_end_to_end(self):
        x1 = form4(issuer_cik="100", owners=(("1", "Doe Jane", True, False, False, ""),), txs=(("P", "A", "2026-11-12", 1000, 20.0, "Common Stock"),))
        x2 = form4(issuer_cik="100", owners=(("2", "Roe Rick", False, True, False, "Chief Executive Officer"),), txs=(("P", "A", "2026-11-13", 20000, 21.0, "Common Stock"),))
        sub_owner = {"filings": {"recent": {"form": [], "reportDate": [], "filingDate": [], "accessionNumber": [], "primaryDocument": []}}}
        sub_iss = {"entityType": "operating", "sic": "3674", "filings": {"recent": {}}}

        def get(url):
            if "CIK0000000100" in url:
                return json.dumps(sub_iss).encode()
            if "submissions" in url:
                return json.dumps(sub_owner).encode()
            return x1 if "a1.xml" in url else x2
        state = {}
        with TmpLedger() as tmp, mock.patch.object(ib, "efts_day", lambda d: [["0001-26-1", "a1.xml", "1", "2026-11-13", 0], ["0002-26-2", "a2.xml", "2", "2026-11-14", 0]] if d == date(2026, 11, 14) else []), \
                mock.patch.object(ib, "_get", get), mock.patch.object(ib, "busy_13f", lambda: False), mock.patch.object(tm, "ua", lambda: "test agent"), \
                mock.patch.object(common, "load_env", lambda: {}), mock.patch.object(common, "load_state", lambda n, d=None: state.setdefault(n, {})), \
                mock.patch.object(common, "save_state", lambda n, v: state.__setitem__(n, v)), mock.patch.object(common, "record_health", lambda *a, **k: None), \
                mock.patch.object(ib, "LATEST", tmp / "latest.json"):
            new, fresh, errors, summary = ib.collect(markets=("us",), days=1, budget_min=1, today=date(2026, 11, 15))
            self.assertEqual(errors, [])
            self.assertEqual(len(fresh), 2)
            self.assertEqual([(x["kind"], x["ticker"], x["strength"]) for x in new], [("cluster", "XYZ", "7.0")])   # 2명 + CEO 0.5(장부는 글자로 적는다)
            self.assertEqual(len(leads.read()), 1)
            self.assertEqual(json.loads((tmp / "latest.json").read_text(encoding="utf-8"))["new_buys"], 2)
            self.assertNotIn("Doe Jane", (tmp / "latest.json").read_text(encoding="utf-8"))   # 요약에는 이름 없이 역할만
            new2, fresh2, _, _ = ib.collect(markets=("us",), days=1, budget_min=1, today=date(2026, 11, 15))   # 같은 서류 다시 = 새 매수 없음
            self.assertEqual((new2, fresh2), ([], []))

    def test_fund_like_issuer(self):
        with mock.patch.object(ib, "_get", lambda url: json.dumps({"entityType": "other", "sic": ""}).encode()):
            self.assertTrue(ib.fund_like("65433", {}, date(2026, 11, 15)))     # 폐쇄형 펀드(MXF 유형)
        with mock.patch.object(ib, "_get", lambda url: json.dumps({"entityType": "other", "sic": "2000"}).encode()):
            self.assertFalse(ib.fund_like("1651717", {}, date(2026, 11, 15)))  # 외국 발행사(NOMD 유형)는 남긴다


class TestThirteenFValue(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = [mock.patch.object(tm, "CACHE", Path(self.tmp.name) / "c"), mock.patch.object(tm, "OUT", Path(self.tmp.name) / "o"),
                  mock.patch.object(tm, "MAP", Path(self.tmp.name) / "o" / "map.json")]
        for x in self.p:
            x.start()

    def tearDown(self):
        for x in self.p:
            x.stop()
        self.tmp.cleanup()

    def test_info_table_keeps_value(self):
        xml = b"""<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
          <infoTable><nameOfIssuer>AAA</nameOfIssuer><cusip>000000AAA</cusip><value>600</value><shrsOrPrnAmt><sshPrnamt>60</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt></infoTable>
          <infoTable><nameOfIssuer>AAA</nameOfIssuer><cusip>000000AAA</cusip><value>400</value><shrsOrPrnAmt><sshPrnamt>40</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt></infoTable>
          <infoTable><nameOfIssuer>BBB</nameOfIssuer><cusip>000000BBB</cusip><value>100</value><shrsOrPrnAmt><sshPrnamt>10</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt><putCall>Call</putCall></infoTable>
        </informationTable>"""
        idx = json.dumps({"directory": {"item": [{"name": "primary_doc.xml"}, {"name": "info.xml"}]}}).encode()
        with mock.patch.object(tm, "get", lambda url, **k: idx if url.endswith("index.json") else xml):
            self.assertEqual(tm.info_table("1", "0001-26-1"), {"000000AAA": [100.0, "AAA", 1000.0]})

    def test_aggregate_reads_old_and_new_cache(self):
        tm.save(2026, 3, "1", {"h": {"AAA000001": [100, "ALPHA"]}})
        tm.save(2026, 4, "1", {"h": {"AAA000001": [150, "ALPHA", 15000.0]}})
        tm.save(2026, 3, "2", {"h": {"AAA000001": [100, "ALPHA", 9000.0]}})
        tm.save(2026, 4, "2", {"h": {"AAA000001": [80, "ALPHA"]}})
        agg, st = tm.aggregate(2026, 4, ["1", "2"])
        a = agg["AAA000001"]
        self.assertEqual((a["holders"], a["increased"], a["decreased"], a["name"]), (2, 1, 1, "ALPHA"))

    def book(self, n, top_val=1e7, etf=False):
        h = {f"{i:08d}X": [100.0, f"STOCK {i}", top_val / (i + 1)] for i in range(n)}
        if etf:
            h["ETF00000X"] = [100.0, "ISHARES TR", top_val * 10]   # 이름 규칙으로 빠지는 ETF
        return h

    def test_vip_band_top10_share_and_gate(self):
        tm.save(2026, 4, "a", {"h": self.book(20, etf=True)})
        tm.save(2026, 4, "b", {"h": self.book(30)})
        tm.save(2026, 4, "c", {"h": self.book(5)})                 # 10종목 미만 — 띠 밖
        tm.save(2026, 4, "d", {"h": self.book(40, top_val=1e6)})    # $10M 미만 — 띠 밖
        tm.save(2026, 4, "e", {"h": {k: v[:2] for k, v in self.book(20).items()}})   # 옛 캐시(가치 칸 없음)
        r = {"crowd_vip_min_filers": 1, "crowd_vip_coverage": 0.5}
        res = tm.vip(2026, 4, ["a", "b", "c", "d", "e"], r, cmap={}, map_fn=lambda cs, m: m)
        self.assertTrue(res["ok"])
        self.assertEqual((res["with_value"], res["managers"]), (4, 2))
        self.assertEqual(res["share"]["00000000X"], 1.0)
        self.assertNotIn("ETF00000X", res["share"])
        self.assertNotIn("00000012X", res["share"])                  # 상위 10 밖
        self.assertEqual(len(res["basket"]), 10)
        gate = tm.vip(2026, 4, ["a", "b", "c", "d", "e"], {"crowd_vip_min_filers": 1, "crowd_vip_coverage": 0.85}, cmap={}, map_fn=lambda cs, m: m)
        self.assertFalse(gate["ok"])                                  # 가치 칸 80% < 85%
        self.assertIn("80%", gate["why"])

    def test_vip_figi_type_excluded_and_ties(self):
        tm.save(2026, 4, "a", {"h": self.book(12)})
        tm.save(2026, 4, "b", {"h": self.book(12)})
        cm = {"00000000X": {"ticker": "QQQ", "type": "ETP"}, "00000001X": {"ticker": "ZZZ", "type": "Common Stock"}, "00000002X": {"ticker": "AAA", "type": "Common Stock"}}
        res = tm.vip(2026, 4, ["a", "b"], {"crowd_vip_min_filers": 1}, cmap=cm, map_fn=lambda cs, m: m)
        self.assertNotIn("00000000X", res["share"])                  # OpenFIGI 종류 ETP는 다시 센다
        self.assertEqual(res["excluded_types"], ["00000000X"])
        self.assertEqual((res["basket"][0]["ticker"], res["basket"][-1]["ticker"]), ("AAA", "ZZZ"))   # 동률은 티커 알파벳순(GS 규칙)


class TestGuruCrowding(unittest.TestCase):
    def setUp(self):
        self.r = guru13f.cfg()[1]

    def agg(self):
        return {"X": {"score": 1.0, "gurus": [], "kind": "new"}, "Y": {"score": 1.0, "gurus": [], "kind": "new"}}

    def test_vip_basis(self):
        a = guru13f.apply_crowding(self.agg(), {"X": 0.20, "Y": 0.05}, self.r, "vip", {"Y"})
        self.assertAlmostEqual(a["X"]["score"], 0.7, 3)               # 상위 10 비율 15% 이상 −0.3
        self.assertFalse(a["X"]["crowd_capped"])
        self.assertEqual((a["Y"]["score"], a["Y"]["crowd_capped"]), (1.0, True))   # VIP 바구니 = 강도 상한

    def test_holders_fallback_unchanged(self):
        a = guru13f.apply_crowding(self.agg(), {"X": 0.45}, self.r)
        self.assertAlmostEqual(a["X"]["score"], 0.4, 3)
        self.assertTrue(a["X"]["crowd_capped"])

    def test_crowding_picks_vip_when_ready(self):
        ok = {"ok": True, "share": {"X": 0.3}, "basket": [{"cusip": "X"}], "quarter": "2026Q4", "managers": 2500, "coverage": 0.97}
        with mock.patch.object(tm, "vip_cached", lambda y, q, r: ok):
            basis, share, basket, info = guru13f.crowding("2026-12-31", self.r)
        self.assertEqual((basis, basket, info["managers"]), ("vip", {"X"}, 2500))
        with mock.patch.object(tm, "vip_cached", lambda y, q, r: {"ok": False, "why": "가치 칸 0%"}), mock.patch.object(guru13f, "crowd_map", lambda rd: {"X": 0.5}):
            basis, share, basket, info = guru13f.crowding("2026-09-30", self.r)
        self.assertEqual((basis, share, info["why"]), ("holders", {"X": 0.5}, "가치 칸 0%"))


class TestNport(unittest.TestCase):
    XML = b"""<edgarSubmission xmlns="http://www.sec.gov/edgar/nport"><formData><genInfo><seriesName>The Fairholme Fund</seriesName><seriesId>S000008484</seriesId>
      <repPdDate>2026-08-31</repPdDate></genInfo><fundInfo><netAssets>1000.0</netAssets></fundInfo><invstOrSecs>
      <invstOrSec><name>FEDERAL NATIONAL MORTGAGE ASSOCIATION</name><title>FNMA 5.10% PFD SERIES E</title><cusip>313586604</cusip><balance>170000</balance><units>NS</units>
        <valUSD>2278000</valUSD><pctVal>2.5</pctVal><assetCat>EP</assetCat><issuerCat>USGSE</issuerCat></invstOrSec>
      <invstOrSec><name>ST. JOE COMPANY (THE)</name><title>JOE COM</title><cusip>790148100</cusip><balance>15073624</balance><units>NS</units>
        <valUSD>900000000</valUSD><pctVal>74.5</pctVal><assetCat>EC</assetCat><issuerCat>CORP</issuerCat></invstOrSec>
      <invstOrSec><name>Federal Home Loan Mortgage Corp</name><title>FMCC PFD</title><cusip>999999999</cusip><balance>100</balance><units>NS</units>
        <valUSD>1</valUSD><pctVal>0.1</pctVal><assetCat>EP</assetCat><issuerCat>USGSE</issuerCat></invstOrSec></invstOrSecs></formData></edgarSubmission>"""

    def test_parse_and_match(self):
        d = guru13f.parse_nport(self.XML)
        self.assertEqual((d["series"], d["period"], d["net_assets"], len(d["rows"])), ("The Fairholme Fund", "2026-08-31", 1000.0, 3))
        secs = [({"id": "gse", "name": "GSE"}, {"ticker": "FNMA", "name": "Federal National Mortgage Association", "cusip6": "313586"}),
                ({"id": "gse", "name": "GSE"}, {"ticker": "FMCC", "name": "Federal Home Loan Mortgage Corp", "cusip6": "313400"})]
        hits = guru13f.nport_hits(d, secs)
        self.assertEqual([h["ticker"] for h in hits], ["FNMA", "FMCC"])   # CUSIP 앞 6자리, 없으면 정규화한 이름

    def test_changes(self):
        r = guru13f.cfg()[1]
        cur = [{"cusip": "A", "pct": 2.5, "balance": 100}, {"cusip": "B", "pct": 1.0, "balance": 130}, {"cusip": "C", "pct": 0.5, "balance": 100}, {"cusip": "D", "pct": 3.0, "balance": 100}]
        prev = [{"cusip": "A", "pct": 1.5, "balance": 100}, {"cusip": "B", "pct": 1.0, "balance": 100}, {"cusip": "C", "pct": 0.5, "balance": 100}]
        out = {h["cusip"]: (why, s) for h, why, s in guru13f.nport_changes(prev, cur, r)}
        self.assertEqual(out["A"], ("순자산 2% 돌파", 6.5))
        self.assertEqual(out["B"], ("+30% 증액", 6.0))
        self.assertEqual(out["D"][0], "새 편입")
        self.assertNotIn("C", out)


class TestRegistryBinding(unittest.TestCase):
    def test_new_params_match_config(self):
        sys.path.insert(0, str(ROOT / "scripts" / "fit"))
        import registry
        reg = registry.load()
        mine = [p for p in reg["params"] if p["id"].startswith(("prm-insider-", "prm-guru-crowd-vip-", "prm-guru-nport-"))]
        self.assertGreaterEqual(len(mine), 20)
        bad = [x for x in registry.check({"params": mine})]
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
