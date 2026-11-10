"""감시 종목 일간 ±7% 급변 → 원인 사건 찾기 자동 실행 (마스터 지시 2026-11-10 "소프트뱅크 … GEV 주가가 폭락하고 있는데 왜 이걸 안 가져오나")

점검: GEV는 11-04 −9.3%, 11-05 −7.5%였는데 원인 추적이 없었다(금지표: 주가 급등 → 펀더멘털 변화 — 원인 사건을 특정해야 한다).
구조: 결정론 스크립트는 TradingView를 부를 수 없어 Chiip Flow 회차(장초·장마감, docs/tasks/chiip-flow.md)가 한 번 더 부른다.
  ① py radar/move_watch.py --symbols          → 감시 종목 TradingView 심볼 묶음(JSON, 50개씩 — 배치 상한)
  ② 묶음마다 mcp-tv-get-symbol-data-batch(columns ["close","change"]) — 차례로, 병렬 금지 → 응답을 파일로
  ③ py radar/move_watch.py --put <파일>…        → |일간 등락| ≥ 7%인 종목마다 Google News에서 그날 기사 제목 3개를 찾아
     inbox src-price-move('주가 급변', 원인 후보 제목 포함)로 넣는다 → Pulse가 원인 사건을 특정해 판단한다(같은 종목·같은 날 1번).
감시 종목 = gate.watch_ids()(valuation·earnings_watch·실체 보정 always_watch) ∪ 포트폴리오 보유·관심 ∪ 포커스 상위.
"""
import json
import re
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common, gate  # noqa: E402

TH = 7.0
SRC = "src-price-move"
GN = "https://news.google.com/rss/search"


def universe():
    import csv
    ids = set(gate.watch_ids()) | gate.portfolio_ids()
    focus, _ = gate.focus_state()
    ids |= set(focus or [])
    out = {}
    with (common.ROOT / "config" / "tradingview_symbols.csv").open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r["entity_id"] in ids and r["tv_symbol"] not in out:
                out[r["tv_symbol"]] = {"id": r["entity_id"], "name": r["name"], "ticker": r["ticker"]}
    for eid, v in ((common.load_yaml("config/entity_overrides.yaml") or {}).get("tv_symbols") or {}).items():
        if eid in ids:
            out.setdefault(v["symbol"], {"id": eid, "name": v["name"], "ticker": v["ticker"]})
    return out


def causes(name, ticker, n=3):
    q = f'"{name}" OR "{ticker}" (shares OR stock OR 株価 OR 주가) when:1d'
    hl = ("ja", "JP", "JP:ja") if re.fullmatch(r"\d{4}", ticker or "") else ("ko", "KR", "KR:ko") if re.fullmatch(r"\d{6}", ticker or "") else ("en-US", "US", "US:en")
    try:
        x = common.http_get(GN + "?" + urllib.parse.urlencode({"q": q, "hl": hl[0], "gl": hl[1], "ceid": hl[2]}), timeout=20).decode("utf-8", "ignore")
    except Exception:
        return []
    return [re.sub(r"<!\[CDATA\[|\]\]>", "", t).strip() for t in re.findall(r"<item>.*?<title>(.*?)</title>", x, re.S)[:n]]


def put(paths):
    uni = universe()
    st = common.load_state("move_watch", {"seen": []})
    seen = set(st["seen"])
    today = common.now_kst().date().isoformat()
    items, moves = [], []
    for p in paths:
        d = json.loads(Path(p).read_text(encoding="utf-8"))
        data = d.get("data")
        if isinstance(data, dict) and "rows" not in data:   # get-symbol-data-batch: {"data": {심볼: {close, change}}}
            rows = [dict(v, symbol=k) for k, v in data.items()]
        else:
            rows = (data or {}).get("rows") if isinstance(data, dict) else data or d.get("rows") or []
        for r in rows or []:
            sym, ch = r.get("symbol"), r.get("change")
            u = uni.get(sym)
            if not u or ch is None or abs(float(ch)) < TH:
                continue
            moves.append(f"{u['name']} {float(ch):+.1f}%")
            key = f"{sym}:{today}"
            if key in seen:
                continue
            seen.add(key)
            heads = causes(u["name"], u["ticker"])
            items.append(common.make_item(SRC, key, f"https://www.tradingview.com/symbols/{sym.replace(':', '-')}/",
                                          f"[주가 급변] {u['name']}({u['ticker']}) {float(ch):+.1f}% — 원인 사건 확인 필요",
                                          common.iso(common.now_kst()), "속보", "ko",
                                          "원인 후보 기사: " + (" / ".join(heads) if heads else "없음 — 공시·IR·상대방 발언을 직접 확인"),
                                          extra={"entities_matched": [u["id"]], "source_class": "주가 급변", "change_pct": float(ch), "cause_heads": heads}))
    st["seen"] = sorted(seen)[-2000:]
    common.save_state("move_watch", st)
    saved = common.save_new_items(items) if items else []
    return f"급변 {len(moves)}종목({', '.join(moves[:8])}) · 새 원인 추적 {len(saved)}건"


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if "--symbols" in argv:
        syms = sorted(universe())
        print(json.dumps([syms[i:i + 50] for i in range(0, len(syms), 50)]))   # get-symbol-data-batch 한 번에 50개
    elif "--put" in argv:
        print(put(argv[argv.index("--put") + 1:]))
    else:
        print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
