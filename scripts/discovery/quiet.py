"""조용한 매집형 상승(quiet compounder) 발굴 — Chiip Ten-bagger·Pulse (마스터 지시 2026-10-29 "FormFactor와 Nova Ltd 같은 엣지 있는 중소형
종목들도 반드시 관측해야 한다. 아직 수급과 관심도가 제한적이지만 기관 자금이 유입되면서 조용하면서 꾸준히 상승하는 종목을 잘 발굴해야 한다")

요소 다섯 개를 시가총액 구간 안 백분위로 바꿔 가중 합(0~10). 구간에 비교 대상이 5개 미만이면 전체 유니버스 백분위.
 ① trend 꾸준한 상승
    일봉(knowledge/models/companies/<id>/ohlcv.csv)이 있으면:
      정보 이산성 ID = sign(R) × (%하락일 − %상승일), 12개월 중 마지막 1개월 제외 — 낮을수록 작은 상승이 꾸준히 쌓였다
        (Da, Gurun & Warachka 2014, RFS "Frog in the Pan": 꾸준한 정보는 주의를 덜 끌어 모멘텀이 더 오래간다)
      12-1개월 수익률(Jegadeesh & Titman 1993, JF) · 126일 로그 가격 추세의 R²(부호 포함) · 126일 최대 낙폭
    없으면 회사 개요 값: 가격/200일선 · 50일선/200일선 · 52주 고점 근접도(George & Hwang 2004, JF — 52주 고점 근처 종목의 모멘텀 지속)
 ② accumulation 기관 매집 — FINRA 주간 공개 자료(scripts/tenbagger/flow.py fetch_weekly): 장외 거래 중 ATS(다크풀·기관 블록) 비중의
    최근 4주 − 직전 8주 변화(+면 기관 체결 증가), 리테일 도매 체결사 비중(낮을수록 기관 주도). 13F는 분기 지연이라 다음 단계
 ③ neglect 관심 부족 — 투자자 원천 언급 수(radar/attention.py) 하위, 애널리스트 수 적음(Arbel & Strebel 1983 '소외주 효과'), 리테일 비중 낮음
 ④ fundamental 실적 확인 — 최근 4분기 EPS 서프라이즈 상회 횟수·평균(Bernard & Thomas 1989 실적 발표 후 표류), 매출 성장, 선행 ÷ 후행 EPS
 ⑤ edge 병목 — config/discovery.yaml 후보 edge(없으면 중립)
관문(조용한 '상승'이 아님): 가격 < 200일선, 또는 126일 최대 낙폭 > 35%, 또는 52주 고점 대비 −30% 밑 → watch에서 뺀다(점수는 남긴다).
쏠림: 관심이 이미 상위면 neglect가 낮아 순위가 자연히 내려간다(크라우딩 감점과 같은 방향).
설정 config/discovery.yaml quiet 절(가중치 = 등록부 prm-quiet-w-* 사전값, 단계적 고도화 scripts/fit/stepwise.py로 피팅).
출력 knowledge/models/discovery/quiet_latest.json(순위·요소·관문·watch) · outputs/discovery/quiet_<YYYYMMDD>.md.
watch = 관문 통과 + 점수 ≥ watch_min 상위 top_n — Pulse 알파 산정 대기열과 SEC 공시 수집 대상에 들어간다. 연구 후보 순위이지 매수 권유가 아니다.
사용: py scripts/discovery/quiet.py [--no-finra]
"""
import csv
import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "tenbagger"))
DISC = ROOT / "knowledge" / "models" / "discovery"
OUTD = ROOT / "outputs" / "discovery"
LATEST = DISC / "quiet_latest.json"
DEFAULT = {"weights": {"trend": 0.30, "accumulation": 0.20, "neglect": 0.15, "fundamental": 0.25, "edge": 0.10},
           "gates": {"max_drawdown": 0.35, "min_to_high": 0.70}, "watch_min": 6.0, "top_n": 15, "finra_top": 40, "min_band_n": 5}


def cfg():
    d = yaml.safe_load((ROOT / "config" / "discovery.yaml").read_text(encoding="utf-8")) or {}
    q = d.get("quiet") or {}
    return {**DEFAULT, **q, "weights": {**DEFAULT["weights"], **(q.get("weights") or {})}, "gates": {**DEFAULT["gates"], **(q.get("gates") or {})}}


# ---------- 일봉 지표 ----------
def load_bars(cid):
    p = ROOT / "knowledge" / "models" / "companies" / cid / "ohlcv.csv"
    if not p.exists():
        return []
    with p.open(encoding="utf-8", newline="") as f:
        return [{"date": r["date"], "c": float(r["c"]), "v": float(r.get("v") or 0)} for r in csv.DictReader(f) if r.get("c")]


def info_discreteness(closes, skip=21, n=252):
    """Da·Gurun·Warachka(2014) ID — 형성 기간(12개월, 마지막 1개월 제외)의 sign(누적 수익률) × (%하락일 − %상승일)"""
    win = closes[-(n + 1):-skip] if len(closes) > n else closes[:-skip] if len(closes) > skip + 20 else []
    if len(win) < 60:
        return None, None
    rets = [b / a - 1 for a, b in zip(win, win[1:]) if a > 0]
    pret = win[-1] / win[0] - 1
    pos = sum(1 for r in rets if r > 0) / len(rets)
    neg = sum(1 for r in rets if r < 0) / len(rets)
    return (1 if pret > 0 else -1 if pret < 0 else 0) * (neg - pos), pret


def trend_r2(closes, n=126):
    """로그 가격 ~ 시간 회귀의 R² × sign(기울기) — 1에 가까울수록 곧게 오른다"""
    ys = [math.log(c) for c in closes[-n:] if c > 0]
    if len(ys) < 40:
        return None
    xs = list(range(len(ys)))
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    syy = sum((y - my) ** 2 for y in ys)
    if not sxx or not syy:
        return None
    return math.copysign(sxy * sxy / (sxx * syy), sxy)


def max_drawdown(closes, n=126):
    peak, mdd = None, 0.0
    for c in closes[-n:]:
        peak = c if peak is None or c > peak else peak
        mdd = max(mdd, 1 - c / peak) if peak else mdd
    return mdd if closes else None


# ---------- 요소 ----------
def trend_features(f, bars):
    closes = [b["c"] for b in bars]
    out = {"basis": "일봉" if len(closes) >= 120 else "개요"}
    if out["basis"] == "일봉":
        idv, pret = info_discreteness(closes)
        out.update(id=idv, mom_12_1=pret, r2=trend_r2(closes), mdd=max_drawdown(closes), last=closes[-1],
                   ma200=sum(closes[-200:]) / min(200, len(closes)), high=max(closes[-252:]))
    else:
        out.update(last=f.get("price"), ma200=f.get("ma200"), ma50=f.get("ma50"), high=f.get("high_52w"), low=f.get("low_52w"))
    last, ma200, high = out.get("last"), out.get("ma200"), out.get("high")
    out["p_ma200"] = (last / ma200 - 1) if last and ma200 else None
    out["ma50_200"] = (f.get("ma50") / f.get("ma200") - 1) if f.get("ma50") and f.get("ma200") else None
    out["to_high"] = (last / high) if last and high else None
    return out


def trend_value(t):
    """꾸준한 상승의 한 숫자(클수록 좋음). 일봉: −ID·R²·12-1·고점 근접의 평균 / 개요: 200일선 위·골든크로스·고점 근접의 평균"""
    parts = []
    if t["basis"] == "일봉":
        if t.get("id") is not None and (t.get("mom_12_1") or 0) > 0:
            parts.append(-t["id"])                       # ID −1(매일 조금씩 상승) ~ +1
        if t.get("r2") is not None:
            parts.append(t["r2"])
        if t.get("mom_12_1") is not None:
            parts.append(max(-1.0, min(1.0, t["mom_12_1"])))
    else:
        if t.get("p_ma200") is not None:
            parts.append(max(-1.0, min(1.0, 3 * t["p_ma200"])))
        if t.get("ma50_200") is not None:
            parts.append(max(-1.0, min(1.0, 5 * t["ma50_200"])))
    if t.get("to_high") is not None:
        parts.append(2 * t["to_high"] - 1)               # 52주 고점 = +1, 고점의 절반 = 0
    return sum(parts) / len(parts) if parts else None


def accumulation_features(weekly):
    """FINRA 주간 {주: {ats, otc, retail}} → (ATS 비중 변화 최근 4주 − 직전 8주, 리테일 도매 비중 최근 4주)"""
    wks = sorted(weekly or {})
    def share(ws, key):
        tot = sum((weekly[w]["ats"] + weekly[w]["otc"]) for w in ws)
        return sum(weekly[w][key] for w in ws) / tot if tot else None
    if len(wks) < 6:
        return {"ats_shift": None, "retail_share": share(wks[-4:], "retail") if wks else None, "weeks": len(wks)}
    rec, prev = wks[-4:], wks[-12:-4]
    a1, a0 = share(rec, "ats"), share(prev, "ats")
    return {"ats_shift": (a1 - a0) if a1 is not None and a0 is not None else None, "retail_share": share(rec, "retail"), "weeks": len(wks)}


def accumulation_value(a):
    parts = []
    if a.get("ats_shift") is not None:
        parts.append(max(-1.0, min(1.0, 10 * a["ats_shift"])))     # ATS 비중 +10%p = +1
    if a.get("retail_share") is not None:
        parts.append(1 - 2 * min(1.0, a["retail_share"] / 0.5))     # 리테일 0% = +1, 25% = 0, 50%+ = −1
    return sum(parts) / len(parts) if parts else None


def neglect_value(f, att, acc):
    """클수록 덜 알려짐: 투자자 언급(로그) 낮음·애널리스트 적음·리테일 비중 낮음 — 원값을 부호 바꿔 백분위에 넘긴다"""
    parts = []
    inv = (att or {}).get("investor")
    if inv is not None:
        parts.append(-math.log1p(inv))
    if f.get("n_analysts") is not None:
        parts.append(-math.log1p(f["n_analysts"]))
    if acc.get("retail_share") is not None:
        parts.append(-acc["retail_share"] * 5)
    return sum(parts) / len(parts) if parts else None


def fundamental_value(f):
    parts = []
    s = [x for x in (f.get("surprises") or []) if x is not None]
    if s:
        parts.append(sum(1 for x in s if x > 0) / len(s) * 2 - 1)    # 4분기 모두 상회 = +1
        parts.append(max(-1.0, min(1.0, (sum(s) / len(s)) / 20)))   # 평균 +20% = +1
    if f.get("rev_growth") is not None:
        parts.append(max(-1.0, min(1.0, f["rev_growth"] / 0.5)))
    if f.get("eps_fwd") and f.get("eps_ttm") and f["eps_ttm"] > 0:
        parts.append(max(-1.0, min(1.0, (f["eps_fwd"] / f["eps_ttm"] - 1) / 0.5)))
    return sum(parts) / len(parts) if parts else None


def pct(pool, v):
    if v is None or len(pool) < 2:
        return None
    below = sum(1 for x in pool if x < v)
    eq = sum(1 for x in pool if x == v)
    return (below + 0.5 * eq) / len(pool)


def gate(t, c):
    if all(t.get(k) is None for k in ("p_ma200", "mdd", "to_high")):
        return ["추세 자료 없음"]   # 모르는 것을 '상승'으로 치지 않는다 — 다음 일요일 개요 갱신(가격·200일선·52주 고점) 뒤 판정
    why = []
    if t.get("p_ma200") is not None and t["p_ma200"] < 0:
        why.append("200일선 아래")
    if t.get("mdd") is not None and t["mdd"] > c["gates"]["max_drawdown"]:
        why.append(f"126일 낙폭 {t['mdd']:.0%}")
    if t.get("to_high") is not None and t["to_high"] < c["gates"]["min_to_high"]:
        why.append(f"52주 고점의 {t['to_high']:.0%}")
    return why


def score_rows(rows, c):
    """rows: [{id, band, raw:{trend,accumulation,neglect,fundamental,edge}}] → 같은 rows에 comp·score·missing"""
    keys = list(c["weights"])
    for r in rows:
        peers = [x for x in rows if x["band"] == r["band"]] if r["band"] else []
        if len(peers) < int(c["min_band_n"]):
            peers = rows
        r["comp"], tot, wsum, r["missing"] = {}, 0.0, 0.0, []
        for k in keys:
            p = pct([x["raw"][k] for x in peers if x["raw"].get(k) is not None], r["raw"].get(k))
            if p is None:
                r["missing"].append(k)
                p = 0.5
            r["comp"][k] = round(10 * p, 1)
            tot += c["weights"][k] * p
            wsum += c["weights"][k]
        r["score"] = round(10 * tot / wsum, 2) if wsum else None
    return rows


def run(today=None, use_finra=True):
    import bands
    today = today or date.today()
    c = cfg()
    uni, fund = bands.universe(), bands.load_fund()
    att = (json.loads((DISC / "attention_latest.json").read_text(encoding="utf-8")) if (DISC / "attention_latest.json").exists() else {}).get("rows") or {}
    edges, bcfg = bands.edges(), bands.cfg()
    rows = []
    for cid, u in uni.items():
        f = fund.get(cid) or {}
        if not f and not load_bars(cid):
            continue
        t = trend_features(f, load_bars(cid))
        e = edges.get(cid)
        b = bands.band_of(f.get("mcap_usd"), bcfg.get("list") or bcfg.get("bands") or []) if f.get("mcap_usd") else None
        rows.append({"id": cid, "name": u.get("name"), "code": u.get("code"), "market": u.get("market"), "band": (b or {}).get("id"),
                     "band_label": (b or {}).get("label"), "trend": t, "acc": {}, "att": att.get(cid) or {}, "f": f,
                     "raw": {"trend": trend_value(t), "accumulation": None, "neglect": None, "fundamental": fundamental_value(f),
                             "edge": float(e) if e is not None else None}})
    # 1차 점수(매집 제외) → 상위 미국 종목만 FINRA 주간 자료를 받아 매집·리테일 비중을 더한다(요청 수 제한)
    for r in rows:
        r["raw"]["neglect"] = neglect_value(r["f"], r["att"], r["acc"])
    score_rows(rows, c)
    if use_finra:
        import flow
        # 기관 매집은 추세보다 먼저 올 수 있다 — 관문과 무관하게 점수 상위 미국 종목 + 마스터 지정 관측 종목
        aw = set(c.get("always_watch") or [])
        us = [r for r in sorted(rows, key=lambda r: (r["id"] not in aw, -(r["score"] or 0))) if r["market"] == "us"][: int(c["finra_top"])]
        start = (today - timedelta(days=100)).isoformat()
        for r in us:
            tk = bands.ticker_of(r)[0]
            try:
                r["acc"] = accumulation_features(flow.fetch_weekly(tk, start, today.isoformat()))
            except Exception as exc:
                r["acc"] = {"error": f"{type(exc).__name__}"}
            r["raw"]["accumulation"] = accumulation_value(r["acc"])
            r["raw"]["neglect"] = neglect_value(r["f"], r["att"], r["acc"])
        score_rows(rows, c)
    for r in rows:
        r["gate"] = gate(r["trend"], c)
    rows.sort(key=lambda r: (bool(r["gate"]), -(r["score"] or 0)))   # 관문 통과(지금 조용히 오르는 중)부터, 그 안에서 점수순
    watch = [r["id"] for r in rows if not r["gate"] and (r["score"] or 0) >= float(c["watch_min"])][: int(c["top_n"])]
    for cid in c.get("always_watch") or []:   # 마스터 지정 관측 종목 — 점수와 무관하게 관측
        if cid not in watch:
            watch.append(cid)
    DISC.mkdir(parents=True, exist_ok=True)
    LATEST.write_text(json.dumps({"date": today.isoformat(), "weights": c["weights"], "watch": watch,
                                  "rows": [{k: r[k] for k in ("id", "name", "code", "band", "score", "comp", "missing", "gate")} |
                                           {"trend_basis": r["trend"]["basis"], "acc": r["acc"]} for r in rows]},
                                 ensure_ascii=False, indent=1), encoding="utf-8")
    path = write_report(today, rows, watch, c)
    return rows, watch, path


def write_report(today, rows, watch, c):
    OUTD.mkdir(parents=True, exist_ok=True)
    f = lambda v: "-" if v is None else f"{v:.1f}"
    L = [f"# Chiip Ten-bagger Discovery — 조용한 매집형 상승 {today.isoformat()}", "",
         f"대상 {len(rows)}종목 · 관문 통과 {sum(1 for r in rows if not r['gate'])} · watch {len(watch)} · 가중치 "
         + " · ".join(f"{k} {v}" for k, v in c["weights"].items()), "",
         "관문 통과 종목(200일선 위·126일 낙폭 35% 이하·52주 고점의 70% 이상)을 먼저, 그 안에서 점수순. 관문 미통과는 아래에 이유와 함께.", "",
         "| 순위 | 종목 | 구간 | 점수 | 꾸준한 상승 | 기관 매집 | 관심 부족 | 실적 확인 | 엣지 | 추세 근거 | 관문 | 빠진 자료 |", "|" + "---|" * 12]
    for i, r in enumerate(rows[:40], 1):
        cp = r["comp"]
        L.append(f"| {i} | {r['name']}({str(r['code']).split('.')[0]}) | {r.get('band_label') or r.get('band') or '-'} | **{f(r['score'])}** | {f(cp.get('trend'))} | "
                 f"{f(cp.get('accumulation'))} | {f(cp.get('neglect'))} | {f(cp.get('fundamental'))} | {f(cp.get('edge'))} | {r['trend']['basis']} | "
                 f"{', '.join(r['gate']) or '통과'} | {', '.join(r['missing']) or '-'} |")
    L += ["", "## watch(Pulse 알파 산정·SEC 공시 관측)"] + [f"- {cid}" for cid in watch] + \
         ["", "요소 점수는 시가총액 구간 안 백분위(0~10). 연구 후보 순위이지 매수 권유가 아님."]
    p = OUTD / f"quiet_{today.strftime('%Y%m%d')}.md"
    p.write_text("\n".join(L), encoding="utf-8")
    return p


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    rows, watch, path = run(use_finra="--no-finra" not in argv)
    print(f"[조용한 상승] {path.relative_to(ROOT).as_posix()} · {len(rows)}종목 · watch {len(watch)} · 상위: "
          + ", ".join(f"{r['name']} {r['score']}" for r in rows[:5]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
