"""닛케이 산업·상장기업 기사 원천 — 포함·제외 어휘(마스터 지시 2026-11-19)"""
import re
import unittest
from pathlib import Path

import yaml

REG = {s["id"]: s for s in yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "source_registry.yaml").read_text(encoding="utf-8")) if isinstance(s, dict) and "id" in s}


def keep(sid, title):
    s = REG[sid]
    return bool(re.search(s["include_regex"], title, re.I)) and not re.search(s["exclude_regex"], title, re.I)


class Nikkei(unittest.TestCase):
    def test_ja_keeps_industry_and_company(self):
        for t in ["決算:JT、ロシア事業損失で1兆3860億円下方修正 子会社の支配喪失で - 日本経済新聞",
                  "アドバンテスト株価膠着 米アンソロピック「公開価格83ドル」報道好感 - 日本経済新聞",
                  "4〜9月期の純利益、トヨタ2.2兆円で首位 キオクシアなどAI関連が躍進 - 日経ヴェリタス - 日本経済新聞"]:
            self.assertTrue(keep("src-nikkei-main", t), t)

    def test_ja_drops_mirror_jobs_and_columns(self):
        for t in ["京セラ[6971]：保有株式の一部売却 2026年11月19日(適時開示) ：日経会社情報DIGITAL - 日本経済新聞",
                  "【IR（課長～次長クラス）】高成長企業 - 日経転職版",
                  "社説 防衛費の積み上げを - 日本経済新聞",
                  "半導体の新工場 - 日経クロステック"]:
            self.assertFalse(keep("src-nikkei-main", t), t)

    def test_asia(self):
        self.assertTrue(keep("src-nikkei-asia", "Japan's NTT looks to data center business as next profit driver - Nikkei Asia"))
        self.assertFalse(keep("src-nikkei-asia", "Opinion | Why Asia needs a new security order - Nikkei Asia"))


if __name__ == "__main__":
    unittest.main()
