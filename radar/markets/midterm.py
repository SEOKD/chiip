"""2026 미국 중간선거 자본시장 반응 — 사건 연구(event study)와 스마트 머니 점수 (마스터 지시 2026-11-03). 판단은 모델 회차

수집: FRED 공개 CSV(--fred, 키 불필요), TradingView 일봉은 모델이 받아 --put. 저장 knowledge/models/midterm2026/.
계산(--compute): 정상 수익률 = 추정 구간(선거 전 약 60거래일)의 시장 모형 r_i = α + β·r_SPY →
  비정상 수익률 AR·누적 CAR(0일 = 11/3부터), 비정상 거래량(추정 구간 평균 대비 배수, 상승일·하락일 분리),
  CMF(종가 위치 × 거래량, 매집·분산), 상대 강도(SPY 대비) → 스마트 머니 점수(가중 z, config/midterm2026.yaml).
  FRED는 0일 직전(11/2) 대비 변화(금리·스프레드는 bp, 그 밖은 %).
사용: py radar/markets/midterm.py --fred · --put <json> · --compute · --status
  --put JSON: {"AMEX:XLK": [["2026-08-03", o, h, l, c, v], …], …}
"""
import csv
import io
import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pollers import common  # noqa: E402

DIR = common.ROOT / "knowledge" / "models" / "midterm2026"
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv"
BP = {"DGS2", "DGS10", "DGS30", "T10Y2Y", "T10Y3M", "T10YIE", "DFII10", "BAMLH0A0HYM2", "BAMLC0A0CM", "BAMLH0A3HYC"}


def cfg():
    return common.load_yaml("config/midterm2026.yaml")


def fred(c=None, get=None):
    c = c or cfg()
    get = get or (lambda sid: common.http_get(FRED, {"id": sid, "cosd": c["estimation"]["start"]}, timeout=30).decode("utf-8", "replace"))
    out, errors = {}, []
    for sid in c["fred"]:
        try:
            rows = list(csv.reader(io.StringIO(get(sid))))[1:]
            out[sid] = {d: float(v) for d, v in rows if v not in ("", ".")}
        except Exception as e:
            errors.append(f"{sid}: {type(e).__name__}")
    DIR.mkdir(parents=True, exist_ok=True)
    (DIR / "fred.json").write_text(json.dumps(out), encoding="utf-8")
    return len(out), errors


def put(path):
    new = json.loads(Path(path).read_text(encoding="utf-8"))
    f = DIR / "ohlcv.json"
    have = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    for sym, bars in new.items():
        m = {b[0][:10]: b for b in have.get(sym, [])}
        m.update({b[0][:10]: [b[0][:10]] + [float(x) for x in b[1:6]] for b in bars})
        have[sym] = [m[d] for d in sorted(m)]
    DIR.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(have), encoding="utf-8")
    return len(new)


def rets(bars):
    return {bars[i][0]: bars[i][4] / bars[i - 1][4] - 1 for i in range(1, len(bars)) if bars[i - 1][4]}


def ols(x, y):
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    sxx = sum((a - mx) ** 2 for a in x)
    b = sum((a - mx) * (c - my) for a, c in zip(x, y)) / sxx if sxx else 1.0
    return my - b * mx, b


def cmf(bars):
    num = den = 0.0
    for _, o, h, l, c, v in bars:
        if h > l:
            num += ((c - l) - (h - c)) / (h - l) * v
            den += v
    return num / den if den else None


def study(data, c=None):
    c = c or cfg()
    est0, est1, ev, end = c["estimation"]["start"], c["estimation"]["end"], c["event_day"], c["window_end"]
    bench = rets(data[c["benchmark"]])
    out = {}
    for sym, bars in data.items():
        r = rets(bars)
        est = [d for d in sorted(r) if est0 <= d <= est1 and d in bench]
        win = [d for d in sorted(r) if ev <= d <= end and d in bench]
        if len(est) < 30 or not win:
            continue
        a, b = ols([bench[d] for d in est], [r[d] for d in est])
        vol = {x[0]: x[5] for x in bars}
        base_v = sum(vol[d] for d in est) / len(est) or None
        ar = {d: r[d] - (a + b * bench[d]) for d in win}
        sd = math.sqrt(sum((r[d] - (a + b * bench[d])) ** 2 for d in est) / (len(est) - 2))
        car = sum(ar.values())
        up = [vol[d] / base_v for d in win if ar[d] > 0] if base_v else []
        dn = [vol[d] / base_v for d in win if ar[d] <= 0] if base_v else []
        wbars = [x for x in bars if ev <= x[0] <= end]
        pre = [x for x in bars if x[0] < ev][-1:] or [None]
        rs = (wbars[-1][4] / pre[0][4]) / (data[c["benchmark"]][-1][4] / [x for x in data[c["benchmark"]] if x[0] < ev][-1][4]) - 1 if pre[0] and wbars else None
        out[sym] = {"beta": b, "car": car, "t": car / (sd * math.sqrt(len(win))) if sd else None, "days": len(win), "path": [[d, round(ar[d], 5)] for d in win],
                    "abvol": sum(vol[d] for d in win) / len(win) / base_v if base_v else None,
                    "abvol_up": sum(up) / len(up) if up else None, "abvol_dn": sum(dn) / len(dn) if dn else None,
                    "cmf": cmf(wbars[-c["smart_money"]["cmf_window"]:]), "rel": rs}
    score(out, c)
    return out


def z(vals):
    xs = [v for v in vals.values() if v is not None]
    if len(xs) < 3:
        return {k: 0.0 for k in vals}
    m = sum(xs) / len(xs)
    s = math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) or 1
    return {k: 0.0 if v is None else (v - m) / s for k, v in vals.items()}


def score(out, c):
    groups = set(c["symbols"]["sector"]) | set(c["symbols"]["industry"])
    pool = {k: v for k, v in out.items() if k in groups}
    w = c["smart_money"]["weights"]
    zs = {key: z({k: v.get(src) for k, v in pool.items()}) for key, src in (("car", "car"), ("abvol_up", "abvol_up"), ("cmf", "cmf"), ("rel_strength", "rel"))}
    for k in pool:
        out[k]["smart"] = sum(w[key] * zs[key][k] for key in w)


def fred_moves(fr, c=None):
    c = c or cfg()
    ev = c["event_day"]
    rows = {}
    for sid, ser in fr.items():
        ds = sorted(ser)
        pre = [d for d in ds if d < ev]
        post = [d for d in ds if ev <= d <= c["window_end"]]
        if not pre or not post:
            continue
        a, b = ser[pre[-1]], ser[post[-1]]
        rows[sid] = {"name": c["fred"][sid], "pre": a, "now": b, "date": post[-1],
                     "chg": (b - a) * 100 if sid in BP else (b / a - 1 if a else None), "unit": "bp" if sid in BP else "%"}
    return rows


def compute():
    c = cfg()
    data = json.loads((DIR / "ohlcv.json").read_text(encoding="utf-8")) if (DIR / "ohlcv.json").exists() else {}
    fr = json.loads((DIR / "fred.json").read_text(encoding="utf-8")) if (DIR / "fred.json").exists() else {}
    res = {"as_of": common.iso(common.now_kst()), "study": study(data, c) if c["benchmark"] in data else {}, "fred": fred_moves(fr, c)}
    (DIR / "latest.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res


def active(today=None):
    today = today or common.now_kst().date()
    return today < date.fromisoformat(cfg()["stop_kst"]) or (today == date.fromisoformat(cfg()["stop_kst"]) and common.now_kst().hour < 12)


def tick_symbols(c=None):
    c = c or cfg()
    t = c["tick"]
    return [c["benchmark"]] + c["symbols"]["sector"] + c["symbols"]["industry"] + t["tone"]


def session_open(now=None):
    """미국 정규장(09:30~16:00 ET) 여부. 관측 기간 11/4~11/13은 표준시(UTC-5)라 KST 23:30~06:00"""
    now = now or common.now_kst()
    et = now - timedelta(hours=14)
    mins = et.hour * 60 + et.minute
    c = cfg()
    return et.weekday() < 5 and c["event_day"] < et.date().isoformat() <= c["window_end"] and 570 <= mins < 960


def regime(quotes, c=None):
    """장중 수급 국면: β 조정 초과 등락 × 상대 거래량 → 유입·유출 상위 3, 위험 선호 톤, 시장 구간"""
    c = c or cfg()
    t = c["tick"]
    beta = {}
    lj = DIR / "latest.json"
    if lj.exists():
        beta = {k: v["beta"] for k, v in json.loads(lj.read_text(encoding="utf-8")).get("study", {}).items()}
    spy = quotes.get(c["benchmark"], {}).get("change") or 0.0
    flow = {}
    for s in c["symbols"]["sector"] + c["symbols"]["industry"]:
        q = quotes.get(s)
        if not q or q.get("change") is None:
            continue
        ex = q["change"] - beta.get(s, 1.0) * spy
        rv = q.get("relative_volume_10d_calc") or 1.0
        flow[s] = round(ex * min(max(rv, 0.3), t["rv_cap"]), 3)
    rank = sorted(flow, key=lambda k: -flow[k])
    ch = lambda s: (quotes.get(s) or {}).get("change") or 0.0
    tone = ch("AMEX:SPHB") - ch("AMEX:USMV") + ch("AMEX:HYG") - ch("AMEX:LQD")
    band = t["spy_band"]
    return {"top": rank[:3], "bottom": rank[-3:][::-1], "flow": flow, "spy": round(spy, 2),
            "spy_zone": max(-3, min(3, int(spy / band))) if band else 0,
            "tone": round(tone, 2), "tone_sign": 1 if tone > t["tone_dead"] else -1 if tone < -t["tone_dead"] else 0,
            "vix": ch("CBOE:VIX"), "tlt": ch("NASDAQ:TLT"), "uup": ch("AMEX:UUP")}


def diff(prev, cur, c=None):
    """바뀐 것만. 상위·하위 진입은 밀려난 종목보다 hyst 이상 클 때만(잡음 방지)"""
    t = (c or cfg())["tick"]
    if not prev:
        return ["개장 첫 관측"]
    out = []
    for side, sign in (("top", 1), ("bottom", -1)):
        new = [s for s in cur[side] if s not in prev[side]]
        gone = [s for s in prev[side] if s not in cur[side]]
        if new and gone:
            worst = min(sign * cur["flow"].get(g, 0) for g in gone)
            new = [s for s in new if sign * cur["flow"][s] - worst >= t["hyst"]]
            if new:
                out.append(f"{'유입' if sign > 0 else '유출'} 상위 진입 {', '.join(new)} / 이탈 {', '.join(gone)}")
    if cur["tone_sign"] != prev["tone_sign"]:
        out.append(f"위험 선호 톤 {prev['tone_sign']:+d}→{cur['tone_sign']:+d} (고베타−저변동+HY−IG {cur['tone']:+.2f}%p)")
    if cur["spy_zone"] != prev["spy_zone"]:
        out.append(f"SPY 구간 이동 {prev['spy']:+.2f}%→{cur['spy']:+.2f}%")
    if abs(cur["vix"] - prev.get("vix", 0)) >= t["vix_jump"]:
        out.append(f"VIX {prev.get('vix', 0):+.1f}%→{cur['vix']:+.1f}%")
    return out


def tick(path):
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    cur = regime(raw.get("data", raw))
    sf = DIR / "tick_state.json"
    prev = json.loads(sf.read_text(encoding="utf-8")) if sf.exists() else None
    if prev and prev.get("day") != (common.now_kst() - timedelta(hours=14)).date().isoformat():
        prev = None
    cur["day"] = (common.now_kst() - timedelta(hours=14)).date().isoformat()
    cur["at"] = common.iso(common.now_kst())
    ch = diff(prev, cur)
    DIR.mkdir(parents=True, exist_ok=True)
    sf.write_text(json.dumps(cur, ensure_ascii=False), encoding="utf-8")
    with (DIR / "tick_log.csv").open("a", encoding="utf-8", newline="") as f:
        csv.writer(f).writerow([cur["at"], cur["spy"], cur["tone"], "|".join(cur["top"]), "|".join(cur["bottom"]), "; ".join(ch)])
    return {"changed": bool(ch), "changes": ch, "prev": prev and {k: prev[k] for k in ("at", "top", "bottom", "spy", "tone")}, "now": cur}


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if "--session" in argv:
        print("장중" if session_open() and active() else "장외")
    elif "--tick-symbols" in argv:
        print(json.dumps(tick_symbols()))
    elif "--tick" in argv:
        print(json.dumps(tick(argv[argv.index("--tick") + 1]), ensure_ascii=False))
    elif "--status" in argv:
        print("관측 중" if active() else "관측 종료(2026-11-14부터 중단)")
    elif "--fred" in argv:
        print(fred())
    elif "--put" in argv:
        print(put(argv[argv.index("--put") + 1]), "종목")
    elif "--compute" in argv:
        r = compute()
        top = sorted(((k, v["smart"]) for k, v in r["study"].items() if "smart" in v), key=lambda kv: -kv[1])
        print("스마트 머니 상위:", [(k, round(s, 2)) for k, s in top[:8]])
        print("하위:", [(k, round(s, 2)) for k, s in top[-5:]])
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
