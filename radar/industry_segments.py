"""산업 리포트 세그먼트 귀속 장부 (마스터 지시 2026-11-08 — 겸업 회사는 세그먼트별 실적으로, ADR-020)

산업 매출 = 회사마다 '그 산업 사업부' 매출의 합. 설정 config/industry_segments.yaml(풀·회원·근거 등급).
장부 knowledge/models/industries/segments/<YYYYQn>.csv — 풀 × 회사 한 줄(세그먼트 매출·전분기·전년·회사 전체 매출·근거 등급·방법·출처·물량/가격 변화).
사용:
  py radar/industry_segments.py --plan <YYYYQn> <산업>    # 회원별로 무엇을 받아야 하나(Fiscal 세그먼트 지표명·IR·제3자 집계)
  py radar/industry_segments.py --put <YYYYQn> <json>     # [{pool, id, period_end, currency, seg_rev, seg_rev_prev_q, seg_rev_prev_y, company_rev, grade, method, source, vol_chg, price_chg}]
  py radar/industry_segments.py --show <YYYYQn> <산업>
"""
import argparse
import csv
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config" / "industry_segments.yaml"
BASE = ROOT / "knowledge" / "models" / "industries" / "segments"
FIELDS = ["quarter", "pool", "id", "name", "period_end", "currency", "seg_rev", "seg_rev_prev_q", "seg_rev_prev_y", "company_rev",
          "grade", "method", "source", "vol_chg", "price_chg", "note", "at"]


def cfg():
    return yaml.safe_load(CFG.read_text(encoding="utf-8"))


def _f(x):
    try:
        return None if x in (None, "") else float(x)
    except (TypeError, ValueError):
        return None


def cal_quarter(period_end):
    """회계 분기 → 달력 분기: 석 달 중 두 달 이상이 든 분기(말일에서 45일 앞 날짜의 분기). 2026-10-02 끝 → 2026Q3"""
    d = date.fromisoformat(str(period_end)[:10]) - timedelta(days=45)
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


def pools_of(industry, c=None):
    c = c or cfg()
    ip = (c.get("industry_pools") or {}).get(industry)
    return [(p, c["pools"][p]) for p in ip["pools"]] if ip else []


def has_pools(industry, c=None):
    return bool(pools_of(industry, c))


def members(industry, c=None):
    """풀이 정의된 산업의 회원 [{id, name, ticker, korea, pool, share_hint}] — 한 회사가 두 풀에 들면 두 줄"""
    out = []
    for p, meta in pools_of(industry, c):
        for eid, m in meta["members"].items():
            out.append({"id": eid, "name": m["name"], "ticker": m.get("key") or "", "korea": eid in ("co-samsung", "co-skhynix"),
                        "pool": p, "share_hint": float(m.get("share_hint") or 1.0)})
    return out


def path(quarter):
    return BASE / f"{quarter}.csv"


def load(quarter):
    p = path(quarter)
    if not p.exists():
        return {}
    with p.open(encoding="utf-8", newline="") as f:
        return {(r["pool"], r["id"]): r for r in csv.DictReader(f)}


def validate(r, c):
    bad = []
    if r.get("grade") not in c["grades"]:
        bad.append(f"{r.get('id')}: 근거 등급 {r.get('grade')} 없음")
    if r.get("grade") != "U":
        if _f(r.get("seg_rev")) is None:
            bad.append(f"{r.get('id')}: seg_rev 없음")
        if not r.get("source"):
            bad.append(f"{r.get('id')}: 출처 없음")
        if r.get("period_end") and cal_quarter(r["period_end"]) != r.get("quarter"):
            bad.append(f"{r.get('id')}: 기간 {r['period_end']}은 {cal_quarter(r['period_end'])} — {r.get('quarter')}와 다르다")
    s, t = _f(r.get("seg_rev")), _f(r.get("company_rev"))
    if s is not None and t and s > t * 1.001:
        bad.append(f"{r.get('id')}: 세그먼트 매출이 회사 전체보다 크다")
    if r.get("grade") == "E" and not r.get("method"):
        bad.append(f"{r.get('id')}: 추정(E)은 브리지 방법을 적어야 한다")
    return bad


def put(quarter, file, c=None):
    c = c or cfg()
    rows = load(quarter)
    new = json.loads(Path(file).read_text(encoding="utf-8"))
    bad = []
    for r in new:
        r = {**r, "quarter": quarter, "at": datetime.now().isoformat(timespec="minutes")}
        r.setdefault("name", next((m["name"] for p, meta in c["pools"].items() if p == r["pool"] for i, m in meta["members"].items() if i == r["id"]), r["id"]))
        b = validate(r, c)
        if b:
            bad += b
            continue
        rows[(r["pool"], r["id"])] = r
    if bad:
        raise SystemExit("세그먼트 장부 거부 — " + " · ".join(bad))
    BASE.mkdir(parents=True, exist_ok=True)
    with path(quarter).open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, FIELDS, extrasaction="ignore")
        w.writeheader()
        for k in sorted(rows):
            w.writerow(rows[k])
    return len(new)


def exposure_class(share, c=None):
    c = c or cfg()
    e = c["exposure"]
    if share is None:
        return "미확인"
    return "전업" if share >= e["pure"] else "주요 겸업" if share >= e["major"] else "부분 겸업" if share >= e["min_include"] else "제외(노출 미미)"


def ratio(a, b):
    a, b = _f(a), _f(b)
    return a / b - 1 if a is not None and b else None


def rows(quarter, industry, fx=None, c=None):
    """산업 회원별 세그먼트 행 — 합산 여부(aggregate)·노출도·성장률은 여기서 계산한다"""
    c = c or cfg()
    led = load(quarter)
    out = []
    for m in members(industry, c):
        r = led.get((m["pool"], m["id"])) or {}
        g = r.get("grade") or "U"
        seg, tot = _f(r.get("seg_rev")), _f(r.get("company_rev"))
        share = seg / tot if seg is not None and tot else None
        rate = (fx or {}).get((r.get("currency") or "USD").upper())
        out.append({**m, "grade": g, "seg_rev": seg, "company_rev": tot, "share": share, "exposure": exposure_class(share, c) if share is not None else ("전업" if m["share_hint"] >= c["exposure"]["pure"] else "미확인"),
                    "aggregate": g in c["aggregate"] and seg is not None, "seg_yoy": ratio(seg, r.get("seg_rev_prev_y")), "seg_qoq": ratio(seg, r.get("seg_rev_prev_q")),
                    "usd": seg * rate if seg is not None and rate else None, "currency": r.get("currency") or "", "period_end": r.get("period_end") or "",
                    "vol_chg": _f(r.get("vol_chg")), "price_chg": _f(r.get("price_chg")), "method": r.get("method") or m.get("how", ""), "source": r.get("source") or "", "note": r.get("note") or ""})
    return out


def pool_summary(rs, c=None):
    """풀별 합계(달러) · A·B 등급 비중 · 매출 가중 성장"""
    c = c or cfg()
    out = {}
    for r in rs:
        if not r["aggregate"] or r["usd"] is None:
            continue
        p = out.setdefault(r["pool"], {"usd": 0.0, "ab": 0.0, "yoy_w": [], "qoq_w": [], "n": 0})
        p["usd"] += r["usd"]
        p["n"] += 1
        if r["grade"] in ("A", "B"):
            p["ab"] += r["usd"]
        for k in ("yoy", "qoq"):
            if r[f"seg_{k}"] is not None:
                p[f"{k}_w"].append((r[f"seg_{k}"], r["usd"]))
    for p in out.values():
        for k in ("yoy", "qoq"):
            w = sum(x[1] for x in p[f"{k}_w"])
            p[f"{k}_n"] = len(p[f"{k}_w"])   # 성장률을 잰 회사 수(전년 값이 없는 회사는 빠진다)
            p[k] = sum(v * x for v, x in p.pop(f"{k}_w")) / w if w else None
        p["ab_share"] = p["ab"] / p["usd"] if p["usd"] else 0.0
    return out


def plan(quarter, industry, c=None):
    c = c or cfg()
    led = load(quarter)
    out = []
    for m in members(industry, c):
        meta = c["pools"][m["pool"]]["members"][m["id"]]
        out.append({"pool": m["pool"], "id": m["id"], "name": m["name"], "have": (m["pool"], m["id"]) in led,
                    "fiscal": {"companyKey": meta.get("key"), "metrics": meta.get("fiscal")} if meta.get("fiscal") else None, "how": meta.get("how", "")})
    return out


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", nargs=2)
    ap.add_argument("--put", nargs=2)
    ap.add_argument("--show", nargs=2)
    a = ap.parse_args(argv)
    if a.plan:
        for x in plan(*a.plan):
            print(json.dumps(x, ensure_ascii=False))
    elif a.put:
        print(f"[세그먼트 장부] {put(*a.put)}줄")
    elif a.show:
        import industry_quarter as IQ
        rs = rows(a.show[0], a.show[1], IQ.cfg()["fx_usd"])
        for r in rs:
            print(f"{r['pool']:<10} {r['name']:<22} {r['grade']} {r['exposure']:<8} 세그 {r['seg_rev']} 비중 {r['share']}")
        print(json.dumps(pool_summary(rs), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
