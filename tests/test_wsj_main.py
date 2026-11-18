"""WSJ 주요 기사 원천(src-wsj-main) — 종목·산업 기사는 남기고 생활·오피니언은 거른다(마스터 지시 2026-11-19)"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar"))
from pollers import common  # noqa: E402


def _src():
    r = common.load_yaml("config/source_registry.yaml")
    r = r if isinstance(r, list) else r.get("sources")
    return next(s for s in r if s.get("id") == "src-wsj-main")


class WsjMain(unittest.TestCase):
    def test_filters(self):
        s = _src()
        inc, exc = re.compile(s["include_regex"], re.I), re.compile(s["exclude_regex"], re.I)
        keep = ["The Pentagon Urgently Needs More Patriot Missiles. It's Running Into a Rayon Problem. - WSJ",
                "Textron Selling Industrial Segment to Kingswood Capital for $1.2 Billion - WSJ",
                "European Chip Stocks Rise After Strong Nvidia Results - WSJ"]
        drop = ["Opinion | Just Another Column - WSJ", "Mansion of the Week: A Malibu Retreat - WSJ"]
        assert all(inc.search(t) and not exc.search(t) for t in keep)
        assert all(exc.search(t) or not inc.search(t) for t in drop)
        assert s["publisher"] == "WSJ" and "robots" in s["terms_note"]
        assert all("site:wsj.com" in q["q"] for q in s["feed_queries"])


if __name__ == "__main__":
    unittest.main()
