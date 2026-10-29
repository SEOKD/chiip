"""Chiip Ten-bagger Discovery 시험 (마스터 지시 2026-10-29 — 엣지 AI 밸류체인 종목 발굴·관심도·IB식 선별·원문 팔로업)"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
sys.path.insert(0, str(ROOT / "scripts" / "discovery"))

import attention  # noqa: E402
import promote  # noqa: E402
import screen  # noqa: E402
from pollers import tw_disclosure  # noqa: E402


class TestDiscovery(unittest.TestCase):
    def test_universe_has_master_examples(self):
        cands = attention.candidates()
        for cid in ("jp-taiyoyuden", "jp-jxmetals", "co-nittobo", "tw-yageo", "jp-uniontool"):
            self.assertIn(cid, cands)
        self.assertEqual(cands["tw-yageo"]["local"], "國巨")

    def test_screen_scores_and_gates(self):
        c = {"id": "x", "edge": 8}
        fund = {"x": {"rev_growth": 0.30, "n_analysts": 2, "mcap_usd": 1.5e9}}
        att = {"x": {"accel": 2.0, "crowding_pct": 20}}
        comp = screen.components(c, fund, att, {"x": 10.0}, {"min_usd": 1e8, "max_usd": 3e9})
        self.assertEqual(comp["coverage_gap"], 10.0)    # 애널리스트 3명 이하 = 커버리지 공백
        self.assertEqual(comp["size_fit"], 10.0)
        s, missing = screen.score(comp, {"edge": 0.3, "growth": 0.15, "coverage_gap": 0.1, "attention_accel": 0.15, "crowding": -0.1, "valuation": 0.15, "size_fit": 0.15})
        self.assertGreater(s, 6.0)
        self.assertEqual(missing, [])

    def test_attention_accel(self):
        rows = [("2026-10-01", "x", "news_global", "4"), ("2026-10-08", "x", "news_global", "4"), ("2026-10-15", "x", "news_global", "4"),
                ("2026-10-22", "x", "news_global", "4"), ("2026-10-29", "x", "news_global", "14")]
        out = attention.summarize(rows, "2026-10-29")
        self.assertAlmostEqual(out["x"]["accel"], 3.0)   # (14+1)/(4+1)

    def test_tw_disclosure_parsing_and_rules(self):
        self.assertEqual(tw_disclosure.roc_to_iso("1151028", "70003"), "2026-10-28T07:00:03+08:00")
        base = {"source_id": "src-tw-disclosure", "entities_matched": ["tw-emc"]}
        self.assertIsNotNone(promote.match({**base, "title": "台光電(2383) 重大訊息: 公告本公司及子公司董事會通過資本支出預算案"}))
        self.assertIsNone(promote.match({**base, "title": "台光電(2383) 重大訊息: 代子公司台光電子材料(昆山)股份有限公司公告 資金貸與達標準"}))
        self.assertTrue(attention.SELLSIDE_RE.search("台光電(2383) 重大訊息: 本公司受邀參加高盛證券舉辦之線上法人座談會"))


def _tg_page(posts):
    """합성 t.me/s 쪽 — posts = [(글 번호, ISO 시각, 본문)]"""
    blocks = "".join(f'<div class="tgme_widget_message_wrap js-widget_message_wrap"><div class="tgme_widget_message" data-post="ch/{i}">'
                     f'<div class="tgme_widget_message_text js-message_text">{t}</div><a class="tgme_widget_message_date">'
                     f'<time datetime="{ts}" class="time">00:00</time></a></div></div>' for i, ts, t in posts)
    return f"<html><body>{blocks}</body></html>"


class TestAttentionXTelegram(unittest.TestCase):
    """X·텔레그램 관심도 — 회사명 언급 수만(2026-10-29 마스터 허용, ADR-011)"""

    def _ago(self, days):
        from datetime import datetime, timedelta, timezone
        return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")

    def test_aliases_drop_short_ascii_and_match_boundaries(self):
        c = {"name": "ISC", "local": "아이에스시", "ko": ["아이에스시"]}
        self.assertEqual(attention.aliases(c), ["아이에스시"])            # 3자 영문 제외·중복 제거
        p = attention.alias_patterns({"name": "Union Tool", "ko": ["유니온툴"]})
        self.assertTrue(any(x.search("union tool 3Q 수주") for x in p))
        self.assertFalse(any(x.search("ReunionToolkit") for x in p))     # 단어 경계
        self.assertTrue(any(x.search("유니온툴 드릴") for x in p))

    def test_x_query(self):
        q = attention.x_query({"name": "INNIO N.V.", "market": "us", "code": "INIO", "ko": []})
        self.assertEqual(q, '("INNIO N.V." OR $INIO) -is:retweet')

    def test_tg_messages_parse_without_storing(self):
        msgs = attention.tg_messages(_tg_page([(10, "2026-10-29T01:00:00+00:00", "닛토보 T-glass &amp; 증설")]))
        self.assertEqual(msgs[0][0], 10)
        self.assertIn("닛토보 T-glass & 증설", msgs[0][2])

    def test_tg_counts_paginate_until_cutoff(self):
        pages = {"https://t.me/s/ch": _tg_page([(30, self._ago(1), "닛토보 증설"), (31, self._ago(0.5), "Taiyo Yuden MLCC")]),
                 "https://t.me/s/ch?before=30": _tg_page([(20, self._ago(9), "닛토보 옛 글"), (21, self._ago(3), "日東紡 T-glass 닛토보")])}
        cands = {"co-nittobo": {"name": "Nitto Boseki", "local": "日東紡", "ko": ["닛토보"]},
                 "jp-taiyoyuden": {"name": "Taiyo Yuden", "ko": ["다이요유덴"]}}
        with patch.object(attention.time, "sleep"):
            counts, st = attention.tg_counts([{"handle": "ch"}], cands, days=7, fetch=pages.__getitem__)
        self.assertEqual(counts, {"co-nittobo": 2, "jp-taiyoyuden": 1})   # 9일 전 글 제외, 한 글에 별칭 둘이어도 1
        self.assertEqual(st["ch"]["msgs"], 3)

    def test_x_count_parses_new_and_old_fields(self):
        c = {"name": "Nitto Boseki", "ko": []}
        with patch.object(attention.common, "http_get", return_value=b'{"data":[{"post_count":3}],"meta":{"total_post_count":3}}'):
            self.assertEqual(attention.x_count(c, "T"), 3)
        with patch.object(attention.common, "http_get", return_value=b'{"data":[{"tweet_count":2},{"tweet_count":4}],"meta":{}}'):
            self.assertEqual(attention.x_count(c, "T"), 6)
        with patch.object(attention.common, "http_get", side_effect=OSError):
            self.assertIsNone(attention.x_count(c, "T"))

    def test_x_counts_skip_without_key_and_stop_at_cap(self):
        cands = {"a": {"name": "Alpha Corp"}, "b": {"name": "Bravo Corp"}}
        self.assertEqual(attention.x_counts(cands, {}, env={}), ({}, "X 키 없음"))
        state = {}
        with patch.object(attention.common, "load_state", return_value={}), \
             patch.object(attention.common, "save_state", side_effect=lambda k, v: state.update(v)), \
             patch.object(attention, "x_count", return_value=5), patch.object(attention.time, "sleep"):
            out, note = attention.x_counts(cands, {"monthly_cap": 1}, env={"X_BEARER_TOKEN": "T"})
        self.assertEqual(out, {"a": 5})
        self.assertIn("상한", note)
        self.assertEqual(state["requests"], 1)

    def test_config_enables_counts_only(self):
        src = attention.common.load_yaml("config/discovery.yaml")["attention"]["sources"]
        self.assertTrue(src["x"]["enabled"] and src["telegram"]["enabled"])
        self.assertTrue(all(ch.get("verified") for ch in src["telegram"]["channels"]))
        reg = {s["id"]: s for s in attention.common.load_yaml("config/source_registry.yaml")}
        self.assertFalse(reg["src-research-x"]["enabled"])               # 타임라인 본문 수집은 별도 승인 대기(TODO 21-3)


if __name__ == "__main__":
    unittest.main()
