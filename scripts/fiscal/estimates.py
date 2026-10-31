"""발표 전 추정 저장과 2순위 보완 (마스터 지시 2026-11-01, config/data_sources.yaml, ADR-014)

company_estimates는 지난 분기의 발표 전 추정을 남기지 않아 서프라이즈 표가 2순위로 내려간다. 발표가 다가온 종목의 Fiscal.ai 추정을 매일 얼려 두고,
빈칸은 Zacks와 Easyconomics가 번갈아 채운다. 값이 바뀔 때만 한 줄 쌓으므로 한 줄의 saved는 그 값이 처음 보인 날이다.
순서: 저장한 Fiscal 값(발표일 전 저장분만) → 2순위 차례 채널 → 다른 2순위 채널.
Easyconomics는 그 회사 실적이 Fiscal.ai 실적과 맞을 때만 쓴다(기준이 다른 EPS·기간이 어긋난 행·깨진 칸을 거른다).
사용: py scripts/fiscal/estimates.py --code [--days 10]                 # execute_code에 넣을 코드
      py scripts/fiscal/estimates.py --put <출력 파일>                  # 저장
      py scripts/fiscal/estimates.py --surprise <id> <surprise.js 출력> [--ec <company_profile 응답>] [--first easyconomics]
      py scripts/fiscal/estimates.py --pick <earnings_est.js 출력> [--ec ...] [--first ...]   # 보완한 JSON을 표준 출력으로
      py scripts/fiscal/estimates.py --street <id> <company_profile 응답> [--first easyconomics]
"""
import argparse
import csv
import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "radar"))
from pollers import common  # noqa: E402

STORE = ROOT / "knowledge" / "models" / "estimates" / "snapshots.csv"
TPL = ROOT / "scripts" / "fiscal" / "templates" / "estimate_snapshot.js"
CAL = ROOT / "knowledge" / "models" / "earnings" / "fiscal_calendar.json"
FIELDS = ["saved", "key", "report_date", "period", "metric", "mean", "source", "basis", "as_of"]
METRIC = {"매출": ("revenue", 1e6), "EPS": ("eps_adjusted", 1), "EBIT": ("ebit_adjusted", 1e6), "EBITDA": ("ebitda_adjusted", 1e6)}
EC_FIELD = {"매출": ("sales_actual", "sales_estimate"), "EPS": ("eps_actual", "eps_estimate")}
ZACKS = "Data provided by Zacks Investment Research, Inc., www.zacksdata.com"
TOL = 0.02       # Easyconomics 실적이 Fiscal.ai 실적과 이 비율 안에 있어야 같은 기준으로 본다
GAP = 0.10       # 2순위 두 채널 추정이 이만큼 벌어지면 알린다


def read_store(path=STORE):
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def upcoming_keys(today, days=10):
    """Fiscal 일정 파일에서 발표가 days일 안에 있는 회사 키"""
    if not CAL.exists():
        return []
    end = (today + timedelta(days=days)).isoformat()
    return sorted({e["key"] for e in json.loads(CAL.read_text(encoding="utf-8")).get("events") or [] if today.isoformat() <= e["date"] <= end})


def code(today, days=10):
    return TPL.read_text(encoding="utf-8").replace("__KEYS__", json.dumps(upcoming_keys(today, days)))


def new_lines(rows, stored, today):
    """직전 저장값과 달라진 칸만 줄로 만든다"""
    last = {(r["key"], r["report_date"], r["metric"]): r for r in stored}
    out = []
    for r in rows:
        for m, c in (r.get("metrics") or {}).items():
            k = (r["key"], r["reportDate"], m)
            p = last.get(k)
            if p and float(p["mean"]) == float(c["mean"]) and p["source"] == str(c.get("source")):
                continue
            out.append({"saved": today, "key": r["key"], "report_date": r["reportDate"], "period": r["period"], "metric": m, "mean": c["mean"],
                        "source": c.get("source"), "basis": c.get("basis"), "as_of": c.get("asOf")})
    return out


def put(path, today=None, store=STORE):
    text = Path(path).read_text(encoding="utf-8")
    data = json.loads(text[text.index("{"):text.rindex("}") + 1])
    lines = new_lines(data.get("rows") or [], read_store(store), today or common.now_kst().date().isoformat())
    store.parent.mkdir(parents=True, exist_ok=True)
    head = not store.exists()
    with store.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if head:
            w.writeheader()
        w.writerows(lines)
    return len(data.get("rows") or []), len(lines), data.get("errors") or []


def frozen(stored, key, report_date, earnings_date):
    """발표일 전에 저장한 마지막 값 {metric: 행}"""
    out = {}
    for r in stored:
        if r["key"] == key and r["report_date"] == report_date and (not earnings_date or r["saved"] < earnings_date):
            out[r["metric"]] = r
    return out


def ec_history(profile):
    """company_profile 응답 → {기간: 행}. 응답을 그대로 저장한 파일과 data 안쪽만 저장한 파일 모두 받는다"""
    p = (profile or {}).get("data") or profile or {}
    return {r.get("period"): r for r in p.get("earnings_history") or []}


def ec_value(row, ec):
    """같은 기간·같은 실적일 때만 Easyconomics 추정을 준다"""
    f = EC_FIELD.get(row["metric"])
    e = ec.get(row["period"])
    if not f or not e or e.get(f[1]) is None or e.get(f[0]) is None or row.get("actual") in (None, 0):
        return None
    return e[f[1]] if abs(e[f[0]] / row["actual"] - 1) <= TOL else None


def fill_rows(rows, key, stored, ec=None, first="zacks"):
    """rows를 고쳐 쓴다. 반환: {'stored': n, 'easyconomics': n, 'zacks': n, 'empty': [...], 'gaps': [...]}"""
    ec = ec or {}
    done = {"stored": 0, "easyconomics": 0, "zacks": 0, "empty": [], "gaps": []}
    for r in rows:
        m = METRIC.get(r.get("metric"))
        if not m or str(r.get("est_src") or "").startswith("fiscal"):
            continue
        z = r["est"] if r.get("est_src") == "zacks" else None
        s = frozen(stored, key, r.get("report_date"), r.get("earnings_date")).get(m[0])
        if s and (r["metric"] == "매출" or s["basis"] == r.get("basis")):
            r.update({"est": round(float(s["mean"]) / m[1], 3), "est_src": f"fiscal:{s['source']}", "est_asof": s["as_of"]})
            done["stored"] += 1
        else:
            e = ec_value(r, ec)
            if z is not None and e is not None and abs(e / z - 1) > GAP:
                done["gaps"].append(f"{r['period']} {r['metric']}: Zacks {z} · Easyconomics {e}")
            if e is not None and (first == "easyconomics" or z is None):
                r.update({"est": round(e, 3), "est_src": "easyconomics", "est_asof": None})
                done["easyconomics"] += 1
            elif z is not None:
                done["zacks"] += 1
            else:
                done["empty"].append(f"{r['period']} {r['metric']}")
                continue
        if z is not None and r["est_src"] != "zacks":
            r["pair"] = {"zacks": z}   # 이익률은 같은 제공처끼리 나누므로 Zacks EBIT 짝을 남긴다
    return done


def apply_surprise(out, stored, ec=None, first="zacks"):
    rows = out.get("rows") or []
    done = fill_rows(rows, out.get("key"), stored, ec, first)
    out["zacks_used"] = any(r.get("est_src") == "zacks" for r in rows)
    out["attribution"] = ZACKS if out["zacks_used"] else None
    return done


def apply_pick(out, stored, ec=None, first="zacks"):
    """earnings_est.js의 reported 칸을 같은 순서로 보완한다"""
    pick = (out.get("pick") or {}).get("reported")
    if not pick:
        return {"stored": 0, "easyconomics": 0, "zacks": 0, "empty": [], "gaps": []}
    actual = out.get("reported_actual") or {}
    rows, name = [], {v[0]: k for k, v in METRIC.items()}
    for fk, label in name.items():
        v = pick.get(fk) or {}
        rows.append({"metric": label, "period": out.get("period"), "report_date": out.get("reported"), "earnings_date": out.get("earningsDate"), "basis": v.get("basis") or actual.get(fk + "_basis"),
                     "actual": (actual.get(fk) / METRIC[label][1]) if actual.get(fk) is not None else None,
                     "est": v["est"] / METRIC[label][1] if v.get("est") is not None else None, "est_src": v.get("src"), "fk": fk})
    done = fill_rows(rows, out.get("key"), stored, ec, first)
    for r in rows:
        if r.get("est") is not None and r["est_src"] != (pick.get(r["fk"]) or {}).get("src"):
            pick[r["fk"]] = {"est": r["est"] * METRIC[r["metric"]][1], "src": r["est_src"], "asOf": r.get("est_asof")}
    out["zacks_used"] = any(v and v.get("src") == "zacks" for p in out["pick"].values() if p for v in p.values())
    out["attribution"] = ZACKS if out["zacks_used"] else None
    return done


def street(ratings, profile, first="zacks", today=None):
    """의견 분포·목표가 — 차례인 채널을 쓰고 빠진 칸은 다른 채널로 채운다. Easyconomics는 강력 매수·강력 매도를 나누지 않는다"""
    p = (profile or {}).get("data") or profile or {}
    ec = {}
    if p.get("analyst_total"):
        ec = {"strong_buy": 0, "buy": p.get("analyst_buy") or 0, "hold": p.get("analyst_hold") or 0, "sell": p.get("analyst_sell") or 0, "strong_sell": 0,
              "as_of": today or common.now_kst().date().isoformat(), "source": "easyconomics"}
    tgt = {k: v for k, v in (("target_mean", p.get("target_price")), ("target_high", p.get("target_price_high")), ("target_low", p.get("target_price_low"))) if v is not None}
    z = dict(ratings or {})
    use = {**z, **ec} if ec and (first == "easyconomics" or not z) else z
    for k, v in tgt.items():
        use.setdefault(k, v)
    return use


def load(path):
    text = Path(path).read_text(encoding="utf-8")
    return json.loads(text[text.index("{"):text.rindex("}") + 1])


def report(done):
    msg = f"저장값 {done['stored']} · Easyconomics {done['easyconomics']} · Zacks {done['zacks']}"
    if done["empty"]:
        msg += f" · 빈칸 {len(done['empty'])}"
    if done["gaps"]:
        msg += " · 2순위 차이 " + "; ".join(done["gaps"])
    return msg


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--code", action="store_true")
    ap.add_argument("--days", type=int, default=10)
    ap.add_argument("--put")
    ap.add_argument("--surprise", nargs=2, metavar=("ID", "FILE"))
    ap.add_argument("--pick")
    ap.add_argument("--street", nargs=2, metavar=("ID", "FILE"))
    ap.add_argument("--ec")
    ap.add_argument("--first", default="zacks", choices=["zacks", "easyconomics"])
    a = ap.parse_args(argv)
    today = common.now_kst().date()
    if a.code:
        print(code(today, a.days))
        return 0
    if a.put:
        n, added, errs = put(a.put)
        print(f"[추정 저장] {n}종목 · 바뀐 값 {added}줄" + (f" · 실패 {errs}" if errs else ""))
        return 0
    ec = ec_history(load(a.ec)) if a.ec else {}
    if a.surprise:
        cid, path = a.surprise
        out = load(path)
        done = apply_surprise(out, read_store(), ec, a.first)
        p = ROOT / "knowledge" / "models" / "companies" / cid / "datapack.json"
        dp = json.loads(p.read_text(encoding="utf-8"))
        dp.setdefault("consensus", {})["surprise"] = out["rows"]
        p.write_text(json.dumps(dp, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[서프라이즈] {cid} {report(done)}" + ("" if a.ec or not done["empty"] else " — 빈칸은 company_profile을 받아 --ec로 다시"))
        return 0
    if a.pick:
        out = load(a.pick)
        done = apply_pick(out, read_store(), ec, a.first)
        print(json.dumps(out, ensure_ascii=False))
        print(f"[실적 est.] {report(done)}", file=sys.stderr)
        return 0
    if a.street:
        cid, path = a.street
        p = ROOT / "knowledge" / "models" / "companies" / cid / "datapack.json"
        dp = json.loads(p.read_text(encoding="utf-8"))
        cons = dp.setdefault("consensus", {})
        cons["ratings"] = street(cons.get("ratings"), load(path), a.first, today.isoformat())
        p.write_text(json.dumps(dp, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[의견 분포] {cid} {cons['ratings'].get('source', 'zacks')}")
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
