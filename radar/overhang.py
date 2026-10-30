"""오버행 리스크 장부 (마스터 지시 2026-10-30 "여기에 오버행 리스크도 추가하라") — 앞으로 시장에 나올 수 있는 물량을 종목별로 적고 크기를 잰다.

종류: 락업 해제·전환사채·ATM·워런트·재매도 등록·내부자 매도 계획(Form 144)·대주주 매각.
모델이 공시에서 읽은 수량을 --put으로 남기면, 여기서 발행 주식 대비 %와 20일 평균 거래량 대비 며칠치인지를 계산한다.
새 증권신고서·Form 144 등 물량 공시는 radar/portfolio.py가 overhang 표시를 붙여 넘긴다.
장부: knowledge/models/portfolio/overhang.csv. 지어내지 않는다 — 수량을 못 찾으면 note에 '수량 미확인'.
사용: py radar/overhang.py --put EROC kind=락업 date=2026-12-07 shares_m=120 note="…" source=<URL>
      py radar/overhang.py                 # 보유 종목 표
"""
import csv
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

BOOK = common.ROOT / "knowledge" / "models" / "portfolio" / "overhang.csv"
FIELDS = ["ticker", "kind", "date", "shares_m", "amount_m", "strike", "status", "note", "source", "as_of"]
FORMS = ("S-1", "S-3", "424B", "144", "F-1", "F-3", "SC 13D", "SCHEDULE 13D")


def is_supply_filing(form, items=""):
    """물량이 늘 수 있는 공시 — 증권신고서·투자설명서·Form 144·대주주 변동·8-K 3.02(증권 발행)"""
    return str(form).startswith(FORMS) or "3.02" in str(items)


def rows():
    if not BOOK.exists():
        return []
    with BOOK.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def put(ticker, pairs, today=None):
    row = {"ticker": ticker.upper(), "status": "열림", "as_of": (today or common.now_kst().date()).isoformat()}
    for p in pairs:
        k, _, v = p.partition("=")
        if k not in FIELDS:
            raise SystemExit(f"모르는 항목: {k} (가능: {', '.join(FIELDS)})")
        row[k] = v
    if not row.get("kind") or not row.get("source"):
        raise SystemExit("kind와 source는 필수")
    keep = [r for r in rows() if not (r["ticker"] == row["ticker"] and r["kind"] == row["kind"] and r.get("date", "") == row.get("date", ""))]
    BOOK.parent.mkdir(parents=True, exist_ok=True)
    with BOOK.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(keep + [row])
    return row


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def shares_and_adv(entity):
    """(발행 주식 백만 주, 20일 평균 거래량 백만 주) — 데이터 묶음·일봉이 없으면 None"""
    base = common.ROOT / "knowledge" / "models" / "companies" / str(entity)
    shares = adv = None
    p = base / "datapack.json"
    if p.exists():
        prof = json.loads(p.read_text(encoding="utf-8")).get("profile") or {}
        shares = (prof.get("shares_basic") or 0) * 1000 or None   # 데이터 묶음 단위는 십억 주
    p = base / "ohlcv.csv"
    if p.exists():
        with p.open(encoding="utf-8") as f:
            vol = [float(r["v"]) for r in csv.DictReader(line for line in f if not line.startswith("#")) if r.get("v")]
        adv = sum(vol[-20:]) / len(vol[-20:]) / 1e6 if vol else None
    return shares, adv


def table(holdings, today=None, cfg=None):
    today = today or common.now_kst().date()
    c = cfg if cfg is not None else (common.load_yaml("config/market_watch.yaml") or {}).get("overhang") or {}
    out, covered = [], set()
    for r in rows():
        h = next((x for x in holdings if x["ticker"] == r["ticker"]), None)
        if not h or r.get("status") == "종료":
            continue
        covered.add(r["ticker"])
        shares, adv = shares_and_adv(h.get("id"))
        qty = _num(r.get("shares_m"))
        d = None
        try:
            d = (date.fromisoformat(r.get("date") or "") - today).days
        except ValueError:
            pass
        pct = qty / shares if qty and shares else None
        out.append({**{k: r.get(k) for k in ("ticker", "kind", "date", "shares_m", "amount_m", "strike", "note", "source")}, "pct_shares": pct, "adv_days": qty / adv if qty and adv else None,
                    "days_to": d, "soon": d is not None and 0 <= d <= c.get("soon_days", 30), "heavy": pct is not None and pct >= c.get("heavy_pct", 0.05)})
    out.sort(key=lambda r: (not r["soon"], r["days_to"] if r["days_to"] is not None else 9999))
    return {"rows": out, "unchecked": sorted(h["ticker"] for h in holdings if h["ticker"] not in covered)}


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if "--put" in argv:
        i = argv.index("--put")
        print(json.dumps(put(argv[i + 1], argv[i + 2:]), ensure_ascii=False))
        return 0
    import portfolio
    print(json.dumps(table(portfolio.holdings()), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
