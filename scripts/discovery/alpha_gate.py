"""알파 5점 표기 관문 (마스터 지시 2026-11-07 "Portfolio 항목과 Ten-bagger Discovery에서 알파 5점 이상인 종목만 표기하도록 해라")

알파 = knowledge/models/alpha/latest.json total. 티커 → 감시 id는 config/tradingview_symbols.csv·config/portfolio.yaml·종합 명단에서 잇는다.
알파가 없는 종목은 5점 이상이 아니므로 표기하지 않는다(모르면 미확인 — 없는 점수로 통과시키지 않는다).
사용: py scripts/discovery/alpha_gate.py <티커> [티커 …]   → 티커마다 알파와 표기 여부
"""
import csv
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
M = ROOT / "knowledge" / "models"
MIN = 5.0
TICK = re.compile(r"\(([A-Z0-9.\-]{1,12})\)")


def _j(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def table():
    """{티커 대문자: 알파}"""
    alpha = {k: v.get("total") for k, v in (_j(M / "alpha" / "latest.json").get("rows") or {}).items()}
    ids = {}
    f = ROOT / "config" / "tradingview_symbols.csv"
    if f.exists():
        with f.open(encoding="utf-8", newline="") as fh:
            ids.update({r["ticker"].upper(): r["entity_id"] for r in csv.DictReader(fh) if r.get("entity_id") and r.get("ticker")})
    try:
        for h in yaml.safe_load((ROOT / "config" / "portfolio.yaml").read_text(encoding="utf-8")).get("holdings") or []:
            if h.get("ticker"):
                ids[str(h["ticker"]).upper()] = h["id"]
    except (OSError, ValueError, AttributeError):
        pass
    for r in _j(M / "portfolio" / "composite_latest.json").get("rows") or []:
        if r.get("ticker") and r.get("id"):
            ids.setdefault(str(r["ticker"]).upper(), r["id"])
    out = {t: alpha.get(i) for t, i in ids.items()}
    for i, a in alpha.items():   # us-xxx 꼴 id는 티커로도 찾는다
        if i.startswith("us-"):
            out.setdefault(i[3:].upper(), a)
    return out


def alpha_of(ticker, t=None):
    return (t if t is not None else table()).get(str(ticker).upper())


def ok(ticker, t=None):
    a = alpha_of(ticker, t)
    return a is not None and a >= MIN


def ok_name(name, t=None):
    """'회사(TICK)' 꼴 이름 → 표기 여부. 티커를 못 읽으면 표기하지 않는다"""
    m = TICK.search(str(name))
    return bool(m) and ok(m[1], t)


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    t = table()
    print(json.dumps({x: {"alpha": alpha_of(x, t), "show": ok(x, t)} for x in argv}, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
