"""CFTC 투자자 포지션(COT) — 주간 수집·지표 (마스터 지시 2026-11-09 "CFTC 포지션 파이프라인을 만들어줘") — 설정 config/cftc.yaml, 모델 없음

수집: CFTC Public Reporting Socrata API(키 불필요) — 계약마다 최근 lookback_weeks주. 금요일 15:30 ET 공표(화요일 기준 포지션).
지표(투자자 유형별): 순포지션(롱 − 숏, 계약), 미결제약정(OI) 대비 %, 주간 변화, 3년 백분위·z점수. 백분위가 extreme_pct 밖이면 '극단'.
출력: knowledge/models/cftc/latest.json {report_date, contracts: {key: {name, oi, groups: {g: {net, pct_oi, chg_w, pctile, z, extreme}}}}, extremes[], errors[]}
      knowledge/models/cftc/history.csv(주·계약·유형별 순포지션 장부)
새 보고 주에 극단이 있으면 inbox 항목(src-cftc) 1건 — Pulse가 집는다. 포지셔닝 극단은 반전의 증거가 아니다(추세 지속 구간에서 자주 틀린다) — 단독 근거로 쓰지 않는다.
사용: py radar/cftc.py            # 수집·계산(run_hourly 하루 1회, 새 주가 없으면 계산만 건너뜀)
      py radar/cftc.py --status   # 요약 표
"""
import csv
import json
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

API = "https://publicreporting.cftc.gov/resource/{id}.json"
DIR = common.ROOT / "knowledge" / "models" / "cftc"
FIELDS = {   # 유형 → (롱 칸, 숏 칸) — 데이터 묶음마다 이름이 다르다(Disaggregated 스왑딜러 숏은 밑줄 두 개가 원 이름)
    "asset_mgr": ("asset_mgr_positions_long", "asset_mgr_positions_short"),
    "lev_money": ("lev_money_positions_long", "lev_money_positions_short"),
    "dealer": ("dealer_positions_long_all", "dealer_positions_short_all"),
    "m_money": ("m_money_positions_long_all", "m_money_positions_short_all"),
    "prod_merc": ("prod_merc_positions_long", "prod_merc_positions_short"),
    "swap": ("swap_positions_long_all", "swap__positions_short_all"),
}


def cfg():
    return common.load_yaml("config/cftc.yaml")


def fetch(ds_id, code, weeks):
    q = {"cftc_contract_market_code": code, "$order": "report_date_as_yyyy_mm_dd DESC", "$limit": weeks}
    rows = json.loads(common.http_get(API.format(id=ds_id) + "?" + urllib.parse.urlencode(q), timeout=40))
    return sorted(rows, key=lambda r: r["report_date_as_yyyy_mm_dd"])


def _f(r, k):
    try:
        return float(r.get(k) or 0)
    except ValueError:
        return 0.0


def stats(rows, group, ext):
    lk, sk = FIELDS[group]
    nets = [_f(r, lk) - _f(r, sk) for r in rows]
    if len(nets) < 10:
        return None
    cur, prev = nets[-1], nets[-2]
    oi = _f(rows[-1], "open_interest_all")
    below = sum(1 for v in nets if v < cur) + 0.5 * sum(1 for v in nets if v == cur)
    pctile = 100 * below / len(nets)
    m = sum(nets) / len(nets)
    sd = (sum((v - m) ** 2 for v in nets) / (len(nets) - 1)) ** 0.5 or 1.0
    return {"net": round(cur), "pct_oi": round(cur / oi * 100, 1) if oi else None, "chg_w": round(cur - prev), "pctile": round(pctile, 1),
            "z": round((cur - m) / sd, 2), "extreme": _ext(cur, pctile, ext), "weeks": len(nets)}


def _ext(net, pctile, ext):
    """백분위 극단 이름 — 순포지션 부호와 함께 읽는다(순숏인데 백분위 상단이면 '3년 중 가장 덜 숏')"""
    if pctile >= ext[1]:
        return "롱 극단(3년 최대 순매수)" if net > 0 else "숏 축소 극단(3년 중 가장 덜 숏)"
    if pctile <= ext[0]:
        return "숏 극단(3년 최대 순매도)" if net < 0 else "롱 축소 극단(3년 중 가장 덜 롱)"
    return None


def run():
    c = cfg()
    out, extremes, errors, hist = {}, [], [], []
    date = None
    for k in c["contracts"]:
        ds = c["datasets"][k["set"]]
        try:
            rows = fetch(ds["id"], k["code"], c["lookback_weeks"])
        except Exception as e:
            errors.append(f"{k['key']}: {type(e).__name__}")
            continue
        if not rows:
            errors.append(f"{k['key']}: 자료 없음")
            continue
        d = rows[-1]["report_date_as_yyyy_mm_dd"][:10]
        date = max(date or d, d)
        groups = {}
        for g in ds["groups"]:
            s = stats(rows, g, c["extreme_pct"])
            if s:
                groups[g] = {**s, "label": ds["groups"][g]}
                hist.append([d, k["key"], g, s["net"], s["pct_oi"], s["pctile"]])
                if s["extreme"] and g in k.get("focus", []):
                    extremes.append(f"{k['name']} {ds['groups'][g]} {s['extreme']}(3년 백분위 {s['pctile']:.0f}, 순 {s['net']:+,}계약, 주간 {s['chg_w']:+,})")
        out[k["key"]] = {"name": k["name"], "date": d, "oi": round(_f(rows[-1], "open_interest_all")), "groups": groups, "focus": k.get("focus", [])}
    DIR.mkdir(parents=True, exist_ok=True)
    prev = json.loads((DIR / "latest.json").read_text(encoding="utf-8")) if (DIR / "latest.json").exists() else {}
    new_week = prev.get("report_date") != date
    (DIR / "latest.json").write_text(json.dumps({"report_date": date, "fetched": common.iso(common.now_kst()), "contracts": out, "extremes": extremes, "errors": errors},
                                                ensure_ascii=False, indent=1), encoding="utf-8")
    if new_week and hist:
        f = DIR / "history.csv"
        have = set()
        if f.exists():
            with f.open(encoding="utf-8", newline="") as fh:
                have = {(r[0], r[1], r[2]) for r in csv.reader(fh)}
        with f.open("a", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            if not have:
                w.writerow(["date", "contract", "group", "net", "pct_oi", "pctile"])
            w.writerows([h for h in hist if tuple(h[:3]) not in have])
    n_in = 0
    if new_week and extremes and prev:   # 첫 실행(기준선)은 알리지 않는다
        it = common.make_item("src-cftc", f"cot-{date}", "https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm",
                              f"[CFTC COT {date}] positioning extremes: " + "; ".join(extremes)[:300], common.iso(common.now_kst()), "포지션 통계", "en",
                              "Commitments of Traders — Tuesday positions released Friday; extremes are context, not reversal signals",
                              extra={"source_class": "포지션", "extremes": extremes})
        n_in = len(common.save_new_items([it]) or [])
    return f"COT {date} · 계약 {len(out)} · 극단 {len(extremes)}" + (" · 새 주" if new_week else "") + (f" · inbox {n_in}" if n_in else "") + (f" · 오류 {errors}" if errors else "")


def status():
    d = json.loads((DIR / "latest.json").read_text(encoding="utf-8"))
    print(f"CFTC COT 기준 {d['report_date']}(화) — 순포지션(계약)·OI 대비·주간 변화·3년 백분위")
    for k, v in d["contracts"].items():
        parts = [f"{g['label']} {g['net']:+,}({g['pct_oi']:+.1f}% OI, 주 {g['chg_w']:+,}, 백분위 {g['pctile']:.0f}{' ' + g['extreme'] if g['extreme'] else ''})"
                 for gk, g in v["groups"].items() if gk in v["focus"]]
        print(f"- {v['name']}: " + " · ".join(parts))
    if d["extremes"]:
        print("극단: " + "; ".join(d["extremes"]))


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if "--status" in argv:
        status()
        return 0
    print(run())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
