"""Alpha Vantage 데이터 채널 (마스터 지시 2026-11-11 "데이터 채널: Alpha Vantage와 파이프라인을 만들어라")

공식 문서 https://www.alphavantage.co/documentation/ (2026-11-11 확인). 무료 키는 하루 25회(https://www.alphavantage.co/support/) — 프리미엄 표시 함수는 쓰지 않는다.
자리: 2순위 보조 채널(config/data_sources.yaml). Fiscal.ai 칸이 비었을 때만 부른다. 하루 예산 BUDGET을 넘기지 않고, 한도 응답(Note·Information)을 받으면 그날은 멈춘다.
  ① 매일 1회(run_hourly): EARNINGS_CALENDAR(3개월, CSV 1회) → 감시 종목 실적 일정 knowledge/models/alphavantage/earnings_calendar.csv
     일정이 새로 잡히거나 바뀐 감시 종목은 inbox src-alphavantage → Pulse '실적 일정'
  ② 필요할 때(모델·스크립트가 부른다): EARNINGS_CALL_TRANSCRIPT(분기 전사 — Fiscal.ai에 없을 때), EARNINGS_ESTIMATES, EARNINGS, OVERVIEW, INSIDER_TRANSACTIONS
     응답은 radar/state/alphavantage/에 캐시(git 제외 — 전사 원문은 저장소에 두지 않는다), 같은 요청은 7일 동안 다시 부르지 않는다.
키: ALPHA_VANTAGE_API_KEY(D:\\local-only\\secrets\\.env, common.load_env) — 없으면 '키 대기'로 건너뛴다. 키가 든 주소는 출력·오류 메시지에 쓰지 않는다.
사용: py radar/alphavantage.py                                  # ① 실적 일정
      py radar/alphavantage.py --get EARNINGS_ESTIMATES NVDA      # ② 한 함수(JSON 출력)
      py radar/alphavantage.py --transcript NVDA 2026Q3           # ② 어닝콜 전사(요약용, 원문 복제 금지)
      py radar/alphavantage.py --budget                           # 오늘 쓴 호출 수
"""
import csv
import io
import json
import sys
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common, gate  # noqa: E402

API = "https://www.alphavantage.co/query"
SRC = "src-alphavantage"
BUDGET = 24            # 무료 25회 중 1회 여유
CACHE_DAYS = 7
FREE = {"EARNINGS_CALENDAR", "EARNINGS_CALL_TRANSCRIPT", "EARNINGS_ESTIMATES", "EARNINGS", "OVERVIEW", "INSIDER_TRANSACTIONS"}
OUT = common.ROOT / "knowledge" / "models" / "alphavantage"
CACHE = common.ROOT / "radar" / "state" / "alphavantage"


def key():
    return common.load_env().get("ALPHA_VANTAGE_API_KEY")


def budget(now=None):
    now = now or common.now_kst()
    st = common.load_state("alphavantage", {})
    day = now.date().isoformat()
    if st.get("day") != day:
        st = {"day": day, "calls": 0, "limited": False}
    return st


def _call(params, k):
    """한 번 부른다. 예산·한도를 지키고 키가 든 주소는 밖으로 내지 않는다"""
    if params["function"] not in FREE:
        raise SystemExit(f"무료 목록 밖 함수: {params['function']}")
    st = budget()
    if st["limited"] or st["calls"] >= BUDGET:
        raise RuntimeError(f"오늘 예산 소진({st['calls']}/{BUDGET})")
    st["calls"] += 1
    common.save_state("alphavantage", st)
    try:
        body = common.http_get(API + "?" + urllib.parse.urlencode({**params, "apikey": k}), timeout=40).decode("utf-8", "ignore")
    except Exception as e:
        raise RuntimeError(f"요청 실패({type(e).__name__})") from None
    if body.lstrip().startswith("{"):
        d = json.loads(body)
        if "Note" in d or "Information" in d or "Error Message" in d:
            if "Error Message" not in d:
                st["limited"] = True
                common.save_state("alphavantage", st)
            raise RuntimeError("한도·오류 응답: " + str(d.get("Error Message") or d.get("Note") or d.get("Information"))[:120])
    return body


def get(function, symbol=None, k=None, **extra):
    """캐시 우선. JSON 함수는 dict, CSV 함수는 문자열"""
    k = k or key()
    if not k:
        raise RuntimeError("키 대기(ALPHA_VANTAGE_API_KEY) — docs/TODO_MASTER.md")
    params = {"function": function, **({"symbol": symbol} if symbol else {}), **extra}
    name = "_".join(str(v) for v in params.values()).replace("/", "-")
    f = CACHE / f"{name}.txt"
    if f.exists() and time.time() - f.stat().st_mtime < CACHE_DAYS * 86400:
        body = f.read_text(encoding="utf-8")
    else:
        body = _call(params, k)
        CACHE.mkdir(parents=True, exist_ok=True)
        f.write_text(body, encoding="utf-8")
    return json.loads(body) if body.lstrip().startswith("{") else body


def watch_tickers():
    """감시 종목 중 미국 티커 → id"""
    ids = set(gate.watch_ids()) | gate.portfolio_ids()
    out = {}
    with (common.ROOT / "config" / "tradingview_symbols.csv").open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            if r["entity_id"] in ids and r["tv_symbol"].split(":")[0] in ("NASDAQ", "NYSE", "AMEX", "NYSEARCA"):
                out[r["ticker"].upper()] = {"id": r["entity_id"], "name": r["name"]}
    return out


def calendar_rows(text, want):
    return [r for r in csv.DictReader(io.StringIO(text)) if (r.get("symbol") or "").upper() in want]


def run():
    k = key()
    if not k:
        common.record_health("alphavantage", True, "키 대기(ALPHA_VANTAGE_API_KEY)")
        return "키 대기(ALPHA_VANTAGE_API_KEY) — docs/TODO_MASTER.md"
    want = watch_tickers()
    try:
        text = get("EARNINGS_CALENDAR", k=k, horizon="3month")
    except RuntimeError as e:
        common.record_health("alphavantage", False, str(e))
        return f"alphavantage 실패: {e}"
    rows = calendar_rows(text, want)
    OUT.mkdir(parents=True, exist_ok=True)
    old = {}
    p = OUT / "earnings_calendar.csv"
    if p.exists():
        with p.open(encoding="utf-8", newline="") as fh:
            old = {r["symbol"]: r for r in csv.DictReader(fh)}
    fields = ["symbol", "name", "reportDate", "fiscalDateEnding", "estimate", "currency", "timeOfTheDay"]
    with p.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["reportDate"], r["symbol"])))
    items = []
    for r in rows:
        prev = old.get(r["symbol"])
        if old and (not prev or prev["reportDate"] != r["reportDate"]):
            u = want[r["symbol"].upper()]
            what = f"{prev['reportDate']} → {r['reportDate']}" if prev else f"{r['reportDate']} 새로 잡힘"
            items.append(common.make_item(SRC, f"{r['symbol']}:{r['reportDate']}", "https://www.alphavantage.co/documentation/#earnings-calendar",
                                          f"[실적 일정] {u['name']}({r['symbol']}) {what} — 회계분기 {r['fiscalDateEnding']}, EPS 추정 {r.get('estimate') or '미확인'}",
                                          common.iso(common.now_kst()), "일정", "en", "Alpha Vantage EARNINGS_CALENDAR(회사 IR 일정으로 대조 전)",
                                          extra={"entities_matched": [u["id"]], "source_class": "실적 일정"}))
    saved = common.save_new_items(items) if items else []
    common.record_health("alphavantage", True, None)
    return f"alphavantage 실적 일정 {len(rows)}종목 · 변경 알림 {len(saved)}건 · 오늘 호출 {budget()['calls']}/{BUDGET}"


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        if "--budget" in argv:
            st = budget()
            print(f"{st['day']} 호출 {st['calls']}/{BUDGET}" + (" · 한도 응답으로 멈춤" if st["limited"] else ""))
        elif "--get" in argv:
            i = argv.index("--get")
            print(json.dumps(get(argv[i + 1], argv[i + 2] if len(argv) > i + 2 else None), ensure_ascii=False)[:20000])
        elif "--transcript" in argv:
            i = argv.index("--transcript")
            d = get("EARNINGS_CALL_TRANSCRIPT", argv[i + 1], quarter=argv[i + 2])
            print(json.dumps(d, ensure_ascii=False))
        else:
            print(run())
    except RuntimeError as e:
        print(f"alphavantage: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
