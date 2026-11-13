"""대형 IPO 서류 감지·풀이 (마스터 지시 2026-11-13, ADR-030)"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar"))
from pollers import common  # noqa: E402
from pollers import ipo_watch as W  # noqa: E402

KST = timezone(timedelta(hours=9))
DOC = ("Prospectus\nWe are selling 801,351,354 shares of Class A common stock.\nWe currently estimate that the initial public offering price per share will be between $70.00 and $78.00.\n"
       "In the nine months ended September 30, 2026, our revenue was $33.2\nbillion, representing a year-over-year growth rate of 1,206%.\n"
       "We have purchase commitments with an aggregate committed spend of approximately $900.9 billion, substantially all related to compute.\n"
       "High-bandwidth memory is largely manufactured by SK hynix Inc., Samsung Electronics Co., and Micron Technology, Inc. Each of these is expanding.\n"
       "Shares of our Class A common stock will be entitled to one vote per share.\nSummary Risk Factors\n• If we are unable to secure adequate compute, we may be unable to train competitive models.\n"
       "Goldman Sachs & Co. LLC Morgan Stanley J.P. Morgan\n")
SRC = {"ciks": ["0002130357"], "display_names": ["Anthropic, PBC  (ANT)  (CIK 0002130357)"], "form": "S-1/A", "file_type": "S-1/A",
       "file_date": "2026-11-10", "adsh": "0001628280-26-072484", "_doc": "anthropicpbc-sx1ax2.htm"}
CO = {"id": "us-ant", "name": "Anthropic, PBC", "names": ["Anthropic"], "cik": "2130357", "why": "IPO"}


def probe(cik, form, day, names):
    return {n: n in ("SK hynix", "Samsung", "Micron", "NVIDIA") for n in names}


class TestIpoWatch(unittest.TestCase):
    def test_match_by_cik_and_name(self):
        self.assertEqual(W.match(SRC, [CO])["id"], "us-ant")
        other = {"ciks": ["0000000001"], "display_names": ["OpenAI Group PBC  (CIK 0000000001)"]}
        self.assertEqual(W.match(other, [{"id": "us-openai", "name": "OpenAI", "names": ["OpenAI"], "cik": ""}])["id"], "us-openai")
        self.assertIsNone(W.match({"ciks": ["1"], "display_names": ["Stripes Holdings"]}, [{"id": "s", "name": "Stripe", "names": ["Stripe, Inc"]}]))

    def test_parse_terms_and_numbers(self):
        p = W.parse(DOC)
        self.assertEqual(p["price_range"], "$70.00~$78.00")
        self.assertEqual(p["shares"], "801,351,354")
        self.assertIn("Class A 1표", p["dual_class"])
        self.assertTrue(any("$33.2 billion" in x for x in p["fin"]))   # 줄 중간에서 끊긴 문장을 잇는다
        self.assertTrue(p["risks"][0].startswith("If we are unable"))
        self.assertIn("Goldman Sachs", p["banks"])

    def test_card_reads_doc_and_highlights_korea(self):
        text, d = W.card(CO, "S-1/A", SRC["adsh"], SRC, datetime(2026, 11, 13, tzinfo=KST), {"numbers": {"us-ant": ["old sentence about revenue $1 million total."]}},
                         probe_fn=probe, read_fn=lambda u: (DOC, ""))
        L = text.split("\n")
        self.assertTrue(L[0].startswith("[IPO 서류] Anthropic, PBC — 상장 신청서 수정본(S-1/A)"))
        self.assertLessEqual(len(L), 7)   # 제목 + 핵심 5줄 + 원문
        self.assertIn("🇰🇷 한국 기업 언급: SK hynix, Samsung", text)
        self.assertIn("manufactured by SK hynix", text)
        self.assertIn("$70.00~$78.00", text)
        self.assertIn("이전 판 대비 새 숫자", text)

    def test_card_without_ua_says_why_and_uses_news(self):
        with mock.patch.object(W, "news_titles", lambda co, now, days=3: [("Anthropic sets IPO price range", "src-bbg-direct")]):
            text, d = W.card(CO, "S-1", SRC["adsh"], dict(SRC, form="S-1"), datetime(2026, 11, 13, tzinfo=KST), {},
                             probe_fn=probe, read_fn=lambda u: (None, "원문 미열람 — SEC_USER_AGENT 필요(.env, www.sec.gov 403)"))
        self.assertIn("원문 미열람 — SEC_USER_AGENT 필요", text)
        self.assertIn("보도 기준(원문 미열람): Anthropic sets IPO price range", text)
        self.assertIn("SK hynix", text)   # 전문검색 언급 확인은 원문 없이 된다
        self.assertIsNone(W.detail_message(CO, d))

    def test_detail_message_strips_markdown(self):
        d = {"read": True, "form": "S-1/A", "day": "2026-11-10", "fin_new": ["x"], "fin": ["x"]}
        out = W.detail_message(CO, d, caller=lambda p: "[IPO 상세] **① 사업 개요**")
        self.assertEqual(out, "[IPO 상세] ① 사업 개요")

    def test_poll_once_per_filing_and_skips_exhibits(self):
        states = {}
        exhibit = dict(SRC, file_type="EX-5.1", _doc="exhibit51.htm")
        with mock.patch.object(common, "load_state", lambda n, d=None: states.get(n, d if d is not None else {})), \
                mock.patch.object(common, "save_state", lambda n, v: states.__setitem__(n, v)), \
                mock.patch.object(common, "record_health", lambda *a, **k: None), \
                mock.patch.object(W, "card", lambda *a, **k: ("카드", {"url": "u", "korea": []})), \
                mock.patch.object(W, "ua_notice", lambda st, send: False), \
                mock.patch.object(W, "cfg", lambda: {"companies": [CO], "large_offering_usd": 1e9}):
            items = W.poll(send=False, filings=[(SRC["adsh"], exhibit), (SRC["adsh"], SRC)])
            self.assertEqual(len(items), 1)
            self.assertTrue(items[0]["sec_always"])
            self.assertEqual(W.poll(send=False, filings=[(SRC["adsh"], SRC)]), [])

    def test_ua_notice_once(self):
        sent = []
        import fulltext
        with mock.patch.object(fulltext, "sec_ua", lambda: None):
            st = {}
            with mock.patch.dict(sys.modules, {"notify": mock.Mock(send=lambda m, lvl: sent.append(m))}):
                self.assertTrue(W.ua_notice(st, True))
                self.assertFalse(W.ua_notice(st, True))
        self.assertEqual(len(sent), 1)
        self.assertIn("SEC_USER_AGENT=<이름> <연락 이메일>", sent[0])
        self.assertNotIn("@", sent[0])


if __name__ == "__main__":
    unittest.main()
