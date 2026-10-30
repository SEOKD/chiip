"""Chiip Portfolio 시장·섹터 국면 (마스터 지시 2026-10-30 "인덱스와 섹터의 센티멘츠와 펀더멘털의 변화를 감지하고 이를 변화시키는 매크로·마이크로 요인(내러티브 등)을 파악하라.
성장주가 시장금리 상승에 디스카운트가 큰 만큼 금리, 지정학적 요인, 공급망 리스크 등 매크로 요인의 영향도 분석하라")

결정론은 숫자까지, '왜 바뀌었나'는 모델(예약 작업 chiip-portfolio)이 판단한다. 숫자가 없는 원인은 '원인 미확인'.
  지수·금리·변동성·신용·달러·유가  FRED 공개 CSV(키 불필요, config/market_watch.yaml series) → 수준·1·5·20거래일 변화·문턱 경보
  섹터  Fiscal.ai 종목 묶음(sector_pulse.js — 결정론 스크립트가 MCP를 못 불러 '--sector-code → execute_code → --sector-put') → 센티멘트(주가)·펀더멘털(EPS 추정) 사분면
  보유 종목 민감도  DCF 할인율 +50bp 가치 변화(v2 엔진) + 최근 120거래일 나스닥 100·10년물 금리 베타(ohlcv.csv)
출력: knowledge/models/portfolio/market_latest.json · sector_latest.json. radar/portfolio.py가 하루 한 번 부르고, 경보는 '시장 국면' 항목이 된다.
사용: py radar/market_regime.py                  # 스냅숏 출력
      py radar/market_regime.py --sector-code    # execute_code 본문
      py radar/market_regime.py --sector-put <파일>
"""
import csv
import json
import statistics
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

CFG = "config/market_watch.yaml"
DIR = common.ROOT / "knowledge" / "models" / "portfolio"
LATEST = DIR / "market_latest.json"
SECTORS = DIR / "sector_latest.json"
TPL = common.ROOT / "scripts" / "fiscal" / "templates" / "sector_pulse.js"
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv"
HISTORY_DAYS = 420
BETA_DAYS = 120
BETA_MIN = 60


def cfg():
    return common.load_yaml(CFG) or {}


def parse_fred(text):
    out = []
    for line in text.strip().splitlines()[1:]:
        d, _, v = line.partition(",")
        try:
            out.append((d, float(v)))
        except ValueError:
            continue
    return out


def fetch_series(sid, start):
    return parse_fred(common.http_get(FRED, {"id": sid, "cosd": start.isoformat()}, timeout=30).decode("utf-8", "replace"))


def describe(rows, kind):
    """수준과 변화. 금리·스프레드(rate)는 %p 차이, 지수·변동성은 %도 함께"""
    if not rows:
        return None
    last = rows[-1][1]
    back = lambda n: rows[-1 - n][1] if len(rows) > n else None
    out = {"last": last, "as_of": rows[-1][0]}
    for n in (1, 5, 20):
        b = back(n)
        out[f"d{n}"] = last - b if b is not None else None
        if kind != "rate":
            out[f"pct{n}"] = last / b - 1 if b else None
    if kind == "index":
        out["dd"] = last / max(v for _, v in rows[-252:]) - 1
    return out


def check_alerts(m, rules):
    """문턱을 넘은 항목 — 금리는 표기를 bp로"""
    out = []
    for r in rules or []:
        x = (m.get(r["key"]) or {}).get(r["field"])
        if x is None:
            continue
        hit = ("abs" in r and abs(x) >= r["abs"]) or ("ge" in r and x >= r["ge"]) or ("le" in r and x <= r["le"])
        if hit:
            v = x * 100 if "bp" in r["text"] else x
            out.append({"key": r["key"], "field": r["field"], "text": r["text"].format(v=v)})
    return out


# ---------- 섹터 ----------
def sector_code():
    keys = [k for s in (cfg().get("sectors") or {}).values() for k in s["keys"]]
    return TPL.read_text(encoding="utf-8").replace("__KEYS__", json.dumps(sorted(set(keys))))


def _median(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def quadrant(sent, fund, rules):
    s = "미확인" if sent is None else ("강" if sent >= rules["sentiment_up"] else "약" if sent <= rules["sentiment_down"] else "중립")
    f = "미확인" if fund is None else ("상향" if fund >= rules["fundamental_up"] else "하향" if fund <= rules["fundamental_down"] else "중립")
    label = {("강", "상향"): "이익 상향과 주가가 동행", ("약", "상향"): "이익은 오르는데 주가가 빠짐(디레이팅)", ("강", "하향"): "이익은 내려가는데 주가가 오름(기대 선행)",
             ("약", "하향"): "이익과 주가가 함께 약세"}.get((s, f), "뚜렷한 방향 없음")
    return {"sentiment": s, "fundamental": f, "label": label}


def classify(rows, c):
    by = {r["key"]: r for r in rows}
    out = {}
    for sid, s in (c.get("sectors") or {}).items():
        got = [by[k] for k in s["keys"] if k in by]
        if not got:
            out[sid] = {"name": s["name"], "n": 0, "label": "미확인"}
            continue
        sent, fund = _median([r.get("r20") for r in got]), _median([r.get("rev30") for r in got])
        out[sid] = {"name": s["name"], "n": len(got), "r5": _median([r.get("r5") for r in got]), "r20": sent, "r60": _median([r.get("r60") for r in got]),
                    "above50": sum(1 for r in got if r.get("above50")) / len(got), "evs_chg20": _median([r.get("evs_chg20") for r in got]), "dd": _median([r.get("dd") for r in got]),
                    "rev30": fund, **quadrant(sent, fund, c["sector_rules"]), "worst": min(got, key=lambda r: r.get("r20") if r.get("r20") is not None else 9)["key"],
                    "best": max(got, key=lambda r: r.get("r20") if r.get("r20") is not None else -9)["key"]}
    return out


def sector_put(path):
    text = Path(path).read_text(encoding="utf-8")
    data = json.loads(text[text.index("{"):text.rindex("}") + 1])
    c = cfg()
    prev = json.loads(SECTORS.read_text(encoding="utf-8")) if SECTORS.exists() else {}
    cur = classify(data.get("rows") or [], c)
    for sid, s in cur.items():
        old = (prev.get("sectors") or {}).get(sid) or {}
        if old.get("label") and old["label"] != s["label"]:
            s["changed_from"] = old["label"]
    out = {"as_of": common.now_kst().date().isoformat(), "sectors": cur, "rows": data.get("rows") or [], "errors": data.get("errors") or []}
    DIR.mkdir(parents=True, exist_ok=True)
    SECTORS.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


# ---------- 보유 종목 민감도 ----------
def closes(entity):
    p = common.ROOT / "knowledge" / "models" / "companies" / str(entity) / "ohlcv.csv"
    if not p.exists():
        return []
    with p.open(encoding="utf-8") as f:
        return [(r["date"], float(r["c"])) for r in csv.DictReader(line for line in f if not line.startswith("#")) if r.get("c")]


def ols(x, y):
    mx, my = statistics.fmean(x), statistics.fmean(y)
    sxx = sum((a - mx) ** 2 for a in x)
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / sxx if sxx else None


def beta(px, ser, diff=False):
    """주가 일간 수익률의 기울기 — ser가 지수면 수익률, 금리(diff)면 %p 변화 기준. 같은 날만 맞춘다"""
    s = dict(ser)
    ds = [d for d, _ in px if d in s]
    p = dict(px)
    xs, ys = [], []
    for a, b in zip(ds, ds[1:]):
        xs.append(s[b] - s[a] if diff else s[b] / s[a] - 1)
        ys.append(p[b] / p[a] - 1)
    xs, ys = xs[-BETA_DAYS:], ys[-BETA_DAYS:]
    return (ols(xs, ys), len(xs)) if len(xs) >= BETA_MIN else (None, len(xs))


def dcf_rate(entity):
    """할인율 +50bp일 때 DCF 주주가치 변화. 동인이 없으면 None"""
    if not (common.ROOT / "knowledge" / "models" / "companies" / str(entity) / "drivers.yaml").exists():
        return None
    sys.path.insert(0, str(common.ROOT / "scripts" / "valuation" / "v2"))
    import run as v2run
    return v2run.evaluate(entity, draws=200)["rate_50bp"]


def sensitivity(holdings, ndx, us10y):
    out = {}
    for h in holdings:
        px = closes(h.get("id"))
        b_ndx, n = beta(px, ndx) if px else (None, 0)
        b_rate, _ = beta(px, us10y, diff=True) if px else (None, 0)
        row = {"beta_ndx": b_ndx, "per_10bp": b_rate / 10 if b_rate is not None else None, "n": n}
        try:
            r = dcf_rate(h.get("id"))
            row.update({"dcf_50bp": r["chg"], "duration": r["duration"]} if r else {})
        except Exception as exc:
            row["dcf_error"] = type(exc).__name__
        out[h["ticker"]] = row
    return out


# ---------- 스냅숏 ----------
def snapshot(holdings, today=None, fetch=fetch_series):
    c = cfg()
    today = today or common.now_kst().date()
    start = today - timedelta(days=HISTORY_DAYS)
    raw, macro, errors = {}, {}, []
    for key, s in (c.get("series") or {}).items():
        try:
            raw[key] = fetch(s["id"], start)
            macro[key] = {"name": s["name"], **(describe(raw[key], s.get("kind")) or {})}
        except Exception as exc:
            errors.append(f"{s['id']}: {type(exc).__name__}")
    sec = json.loads(SECTORS.read_text(encoding="utf-8")) if SECTORS.exists() else {}
    out = {"as_of": today.isoformat(), "macro": macro, "alerts": check_alerts(macro, c.get("alerts")), "sectors": sec.get("sectors"), "sectors_as_of": sec.get("as_of"),
           "sensitivity": sensitivity(holdings, raw.get("ndx") or [], raw.get("us10y") or []),
           "holdings_sector": {h["ticker"]: next((sid for sid, s in (c.get("sectors") or {}).items() if h.get("sub") in (s.get("sub") or [])), None) for h in holdings},
           "errors": errors}
    DIR.mkdir(parents=True, exist_ok=True)
    LATEST.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def macro_news(days=1):
    """매크로 주제별 제목(9개 매체) — 데일리에만. 사실이 아니라 단서이고, 판단은 모델 몫"""
    import narrative_sources as ns
    rule = (common.load_yaml("config/alert_rules.yaml") or {}).get("telegram_filter") or {}
    pubs = {p.lower() for p in rule.get("allowed_publishers", [])}
    out = {}
    for topic, q in (cfg().get("macro_news") or {}).items():
        try:
            out[topic] = [{"title": x["title"], "url": x["url"], "publisher": x.get("publisher"), "date": x.get("date")}
                          for x in ns.gnews(q, days, 40) if (x.get("publisher") or "").strip().lower() in pubs][:8]
        except Exception as exc:
            out[topic] = [{"title": f"수집 실패: {type(exc).__name__}", "url": None}]
    return out


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if "--sector-code" in argv:
        print(sector_code())
        return 0
    if "--sector-put" in argv:
        out = sector_put(argv[argv.index("--sector-put") + 1])
        for s in out["sectors"].values():
            print(f"{s['name']}: {s['label']}" + (f" (이전: {s['changed_from']})" if s.get("changed_from") else ""))
        return 0
    import portfolio
    out = snapshot(portfolio.holdings())
    print(json.dumps({k: out[k] for k in ("as_of", "alerts", "errors", "sensitivity")}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
