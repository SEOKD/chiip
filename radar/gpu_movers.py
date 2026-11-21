"""GPU 렌털료 계열별 변동 성격 판별 — 매일 움직이는 계열을 찾아 그날 값으로 갱신·알림하는 구조
(마스터 지시 2026-11-21 "GPU 렌털비는 일일 데이터 변동이 있는 파이프라인을 찾고 이 값이 매일 변할 경우 업데이트할 수 있는 구조를 만들어라")

배경: 11-10~21 직접 수집 3,315행 중 값이 바뀐 계열은 Silicon Data 지수 6개뿐이었다(정가·선점형·스팟 정가는 전부 그대로).
  그런데 알림은 '값이 바뀌면 무조건'이라 지수가 몇 센트 움직일 때마다 Pulse 보도자료 칸에 올라갔고(소음), 정가가 바뀌는 드문 소식과 섞였다.
구조:
  1) classify(): 계열(제공사·GPU·구성·조건)마다 최근 N일의 하루 마지막 값으로 daily / occasional / sticky / new 판정(config/gpu_rental.yaml)
  2) gate(): daily 계열은 전 관측일 대비·7일 전 대비 문턱을 넘을 때만 알림, 나머지는 바뀌면 알림(정가 변경 = 소식)
  3) stale(): 매일 움직여야 할 원천(expect: daily)이 며칠째 같은 값이면 '정체' — 수집 문제로 올린다(AWS 스팟 공개본처럼 갱신이 멈춘 원천을 잡는다)
  4) knowledge/models/gpu_rental_movers.json에 판정을 남긴다 — 일일 그림(gpu_daily)·주간 점검(gpu_weekly)이 읽는다
결정론 — 모델 없음. 새 일일 원천은 gpu_rental.py 수집 함수 + config 한 줄이면 이 구조를 그대로 탄다.
사용: py radar/gpu_movers.py          # 판정 표
      py radar/gpu_movers.py --json   # 판정 JSON
"""
import csv
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

CFG = common.ROOT / "config" / "gpu_rental.yaml"
LIVE = common.ROOT / "knowledge" / "models" / "gpu_rental.csv"
OUT = common.ROOT / "knowledge" / "models" / "gpu_rental_movers.json"
WB = common.ROOT / "knowledge" / "models" / "gpu_rental_wayback.csv"   # 아카이브·페이지 내장 이력(radar/gpu_daily.py)
DEFAULT = {"classify_days": 14, "min_obs_days": 4, "daily_ratio": 0.3, "stale_days": 5,
           "alert": {"daily_pct": 5.0, "week_pct": 10.0}, "sources": []}


def cfg():
    try:
        import yaml
        c = yaml.safe_load(CFG.read_text(encoding="utf-8")) or {}
    except Exception:
        c = {}
    return {**DEFAULT, **c, "alert": {**DEFAULT["alert"], **(c.get("alert") or {})}}


def expected(c=None):
    """제공사 → 원천 설정(expect·role)"""
    return {s["provider"]: s for s in (c or cfg()).get("sources") or [] if s.get("provider")}


def key(r):
    return (r["provider"], r["gpu"], r["config"], r["term"])


def daily_last(rows):
    """계열 → {날짜: 그날 마지막 값}. 값 없는(문의) 행은 뺀다"""
    out = {}
    for r in rows:
        try:
            v = float(r["usd_per_gpu_hr"])
        except (TypeError, ValueError):
            continue
        out.setdefault(key(r), {})[r["date"]] = v   # 행은 수집 순서 — 같은 날 뒤 값이 이긴다
    return out


def _pct(a, b):
    return (a / b - 1) * 100 if b else None


def classify(daily, today=None, c=None):
    """→ [{key, cls, obs_days, change_days, ratio, last, last_day, prev, dd, w1, last_change}] — 최근 classify_days일 기준"""
    c = c or cfg()
    today = today or common.now_kst().date().isoformat()
    lo = (date.fromisoformat(today) - timedelta(days=int(c["classify_days"]))).isoformat()
    w0 = (date.fromisoformat(today) - timedelta(days=7)).isoformat()
    res = []
    for k, o in daily.items():
        ds = sorted(d for d in o if lo <= d <= today)
        if not ds:
            continue
        vals = [o[d] for d in ds]
        ch = [ds[i] for i in range(1, len(ds)) if abs(vals[i] - vals[i - 1]) >= 0.005]
        n = len(ds)
        ratio = len(ch) / (n - 1) if n > 1 else 0.0
        if n < int(c["min_obs_days"]):
            cls = "new"
        elif ratio >= float(c["daily_ratio"]):
            cls = "daily"
        elif ch:
            cls = "occasional"
        else:
            cls = "sticky"
        before = [d for d in sorted(o) if d <= w0]
        wv = o[before[-1]] if before else None
        allch = [d for d, a, b in zip(sorted(o)[1:], [o[x] for x in sorted(o)], [o[x] for x in sorted(o)[1:]]) if abs(a - b) >= 0.005]
        res.append({"key": list(k), "cls": cls, "obs_days": n, "change_days": len(ch), "ratio": round(ratio, 2),
                    "last": vals[-1], "last_day": ds[-1], "prev": vals[-2] if n > 1 else None,
                    "dd": round(_pct(vals[-1], vals[-2]), 2) if n > 1 and _pct(vals[-1], vals[-2]) is not None else None,
                    "w1": round(_pct(vals[-1], wv), 2) if wv else None, "last_change": allch[-1] if allch else None})
    return sorted(res, key=lambda x: (x["cls"] != "daily", x["key"]))


def gate(info, old, new, c=None):
    """이 계열의 값 변화(old→new, 직전 수집 회차 대비)를 알림으로 올릴지. 나머지(정가)는 바뀌면 올린다.
    daily 계열은 전 관측일 대비(dd)·7일 전 대비(w1)가 문턱을 넘을 때만 — 하루 한 번 제한은 부르는 쪽(gpu_rental.run)이 state로 지킨다"""
    c = c or cfg()
    if abs(new - old) < 0.005:
        return False
    if not info or info.get("cls") != "daily":
        return True
    a = c["alert"]
    return (info.get("dd") is not None and abs(info["dd"]) >= float(a["daily_pct"])) or \
        (info.get("w1") is not None and abs(info["w1"]) >= float(a["week_pct"]))


def stale(res, today=None, c=None):
    """expect: daily 원천 중 GPU 계열이 전부 stale_days일 넘게 같은 값인 원천 → ['Silicon Data 지수 정체 6일(마지막 변화 11/15)']"""
    c = c or cfg()
    today = today or common.now_kst().date().isoformat()
    out = []
    for p, s in expected(c).items():
        if s.get("expect") != "daily":
            continue
        mine = [x for x in res if x["key"][0] == p and x["obs_days"] >= int(c["min_obs_days"])]
        if not mine:
            continue
        lasts = [x["last_change"] for x in mine if x["last_change"]]
        lc = max(lasts) if lasts else None
        days = (date.fromisoformat(today) - date.fromisoformat(lc)).days if lc else int(c["classify_days"]) + 1
        if days > int(c["stale_days"]):
            out.append(f"{p} 정체 {days}일" + (f"(마지막 변화 {lc[5:].replace('-', '/')})" if lc else "(기간 내 변화 없음)"))
    return out


def by_key(res):
    return {tuple(x["key"]): x for x in res}


def wayback(c=None):
    """config sources에 term이 있는 원천(참고선)의 아카이브 과거값 — 새로 붙인 원천도 첫날부터 성격을 잴 수 있게(Flopper 30일치 등)"""
    terms = {p: s["term"] for p, s in expected(c).items() if s.get("term")}
    if not terms or not WB.exists():
        return []
    out = []
    with WB.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r.get("provider") in terms:
                out.append({**r, "term": terms[r["provider"]]})
    return sorted(out, key=lambda r: r["date"])


def build(rows=None, today=None, write=True):
    """→ {as_of, series, daily, stale} — 수집 회차마다 다시 잰다"""
    c = cfg()
    if rows is None:
        rows = list(csv.DictReader(LIVE.open(encoding="utf-8", newline=""))) if LIVE.exists() else []
        rows = wayback(c) + rows   # 아카이브 과거값 먼저 — 같은 날 직접 수집값이 이긴다
        try:   # 내부용 원천(Ornn — git 제외 CSV)
            import gpu_rental
            rows += sorted(gpu_rental.internal_rows(), key=lambda r: r["date"])
        except Exception:
            pass
    res = classify(daily_last(rows), today, c)
    out = {"as_of": common.iso(common.now_kst()), "classify_days": c["classify_days"], "series": res,
           "daily": [x["key"] for x in res if x["cls"] == "daily"], "stale": stale(res, today, c),
           "mismatch": [f"{x['key'][0]} {x['key'][2]} {x['key'][3]} — 기대 sticky인데 매일 바뀜" for x in res
                        if x["cls"] == "daily" and expected(c).get(x["key"][0], {}).get("expect") == "sticky"]}
    if write:
        OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def table(out):
    L = ["| 성격 | 제공사 | GPU | 구성 | 조건 | 관측일 | 바뀐 날 | 지금 $ | 전일 대비 | 1주 | 마지막 변화 |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    name = {"daily": "일일", "occasional": "간헐", "sticky": "고정", "new": "판정 보류"}
    for x in out["series"]:
        if x["cls"] == "sticky":
            continue
        p, g, cf, t = x["key"]
        f = lambda v: "-" if v is None else f"{v:+.1f}%"   # noqa: E731
        L.append(f"| {name[x['cls']]} | {p} | {g} | {cf} | {t} | {x['obs_days']} | {x['change_days']} | {x['last']:.2f} | {f(x['dd'])} | {f(x['w1'])} | {x['last_change'] or '-'} |")
    n = sum(1 for x in out["series"] if x["cls"] == "sticky")
    L.append(f"\n고정(정가) {n}개 계열은 표에서 뺌 · 정체 {', '.join(out['stale']) or '없음'}" + (f" · 기대와 다름 {'; '.join(out['mismatch'])}" if out["mismatch"] else ""))
    return "\n".join(L)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    o = build()
    print(json.dumps(o, ensure_ascii=False, indent=1) if "--json" in sys.argv else table(o))
