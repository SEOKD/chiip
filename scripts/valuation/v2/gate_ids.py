"""감시 종목 id 목록 — 수집 관문(radar/pollers/gate.py)과 같은 기준(valuation universe + earnings_watch extra)"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "radar"))
from pollers import gate  # noqa: E402


def watch():
    return gate.watch_ids()
