"""백테스트 일봉 원천 관문 (ADR-016 §2-3, config/backtest.yaml price_source·price_candidates)

새 원천은 약관·robots를 확인하고 마스터가 승인해야 쓴다(CLAUDE.md 약관 준수, 새 원천 승인). price_source가 비어 있으면
load()는 PriceSourceNotApproved를 낸다 — 백테스트는 재무(frames)만으로 돌 수 있는 단계까지만 간다.
어댑터 규약: monthly(ticker, start, end) → [(YYYY-MM-DD 월말, 수정 종가)].
"""
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "knowledge" / "models" / "backtest" / "prices"


class PriceSourceNotApproved(RuntimeError):
    pass


def cfg():
    return yaml.safe_load((ROOT / "config" / "backtest.yaml").read_text(encoding="utf-8"))


def status():
    c = cfg()
    return c.get("price_source"), c.get("price_candidates") or {}


def _tiingo(ticker, start, end):
    """Tiingo EOD(승인 후에만). 키는 common.load_env()의 TIINGO_API_KEY — 출력·커밋 금지. 무료 등급은 저장 금지라 유료 등급에서만 캐시"""
    import json
    import urllib.request
    sys.path.insert(0, str(ROOT / "radar"))
    from pollers import common
    key = common.load_env().get("TIINGO_API_KEY")
    if not key:
        raise PriceSourceNotApproved("TIINGO_API_KEY 없음 — 마스터가 D:\\local-only\\secrets\\.env에 넣어야 한다")
    q = f"https://api.tiingo.com/tiingo/daily/{ticker}/prices?startDate={start}&endDate={end}&resampleFreq=monthly"
    req = urllib.request.Request(q, headers={"Authorization": f"Token {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        rows = json.loads(r.read().decode("utf-8"))
    return [(x["date"][:10], float(x["adjClose"])) for x in rows if x.get("adjClose") is not None]


ADAPTERS = {"tiingo": _tiingo}


def monthly(ticker, start, end):
    src, cand = status()
    if not src:
        raise PriceSourceNotApproved("일봉 대량 원천 승인 대기 — config/backtest.yaml price_candidates 참고")
    if (cand.get(src) or {}).get("status") not in ("승인", "approved"):
        raise PriceSourceNotApproved(f"{src}는 승인 상태가 아니다({(cand.get(src) or {}).get('status')})")
    return ADAPTERS[src](ticker, start, end)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    s, c = status()
    print(f"[일봉 원천] 사용 중: {s or '없음(승인 대기)'}")
    for k, v in c.items():
        print(f"- {k}: {v.get('status')} — {v.get('why')}")
