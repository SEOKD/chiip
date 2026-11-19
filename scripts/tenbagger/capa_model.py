"""생산능력(캐파) 추정 모델 (마스터 지시 2026-11-19 "캐파를 추정할 때 생산시설별 면적과 판매량 등 여러 재무 지표와 경영진 콜 발언,
IB 리서치 하우스 추정치를 종합해 캐파를 모델링을 통해 추정해 시각물로 나타내라. 캐파는 기업과 업계가 쓰는 단위를 써라.")

회사가 캐파를 공시하지 않을 때만 쓴다(capacity.current.nameplate가 숫자면 공시값이 우선). 숫자는 여기서 계산하고, 모델은 datapack
capacity.estimate에 방법별 원자료만 쓴다. 모든 결과는 '추정'으로 표시하고 공시 캐파처럼 쓰지 않는다.

datapack capacity.estimate:
  {"unit": "$M 매출/년",                      # 회사·업계가 쓰는 캐파 단위(웨이퍼/월·MW/년·대/년·크루 …). 부품처럼 품목이 수천 개면 '매출 상당액'
   "unit_basis": "왜 이 단위인가 한 줄",
   "output": {"value": 785.6, "label": "TTM 매출", "source": "출처"},   # 같은 단위의 현재 산출(판매량·출하·매출) — 가동률 = 산출 ÷ 캐파
   "methods": [
     {"kind": "자산회전", "base": {"value": 81.9, "label": "순유형자산 $M(3Q26)"},
      "factor": {"lo": 11.2, "mid": 11.7, "hi": 12.5, "label": "과거 최고 매출 ÷ 순유형자산(배)"}, "basis": "근거", "source": "출처"},
     {"kind": "면적", "base": {"value": 1.2, "label": "제조 면적(백만 sq ft)"}, "factor": {"lo": .., "mid": .., "hi": .., "label": "면적당 최대 산출"}, ...},
     {"kind": "판매·가동률", "base": {"value": 785.6, "label": "TTM 매출"}, "factor": {"lo": 1/0.9, "mid": 1/0.8, "hi": 1/0.7, "label": "1 ÷ 가동률"}, ...},
     {"kind": "경영진", "bound": "하한" | "상한" | None, "value": 924 또는 {"lo","mid","hi"}, "basis": "콜 발언 요지(자기 말)", "source": "콜 날짜"},
     {"kind": "IB", "value": 1000 또는 "미확인", "basis": "하우스·날짜·요지", "source": "출처"}]}
  base × factor(lo·mid·hi) 또는 value(숫자나 lo·mid·hi). "미확인"은 표에만 남고 계산에서 빠진다.
결합: 점 추정 방법의 가중 평균(가중치 = WEIGHTS, 방법에 weight를 쓰면 그 값) → 경영진 하한·상한으로 자른다.
범위 = 점 추정들의 lo 최솟값~hi 최댓값(하한·상한 반영). 방법 간 차이(최대÷최소)가 1.5배를 넘으면 '방법 간 차이 큼'.
시설별 배분: 생산시설의 면적 × 제조 사용 비율(capacity_basis의 'NN%' 또는 mfg_share)로 결합 캐파를 나눈다 — 배분은 추정이다.
"""
import re

UNKNOWN = "미확인"
WEIGHTS = {"경영진": 1.0, "IB": 0.8, "판매·가동률": 0.7, "자산회전": 0.6, "면적": 0.5}
KINDS = tuple(WEIGHTS)
SPREAD_WARN = 1.5


def _num(x):
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def _trip(m):
    """방법 하나 → (lo, mid, hi) 또는 None"""
    v = m.get("value")
    if isinstance(v, dict):
        t = tuple(_num(v.get(k)) for k in ("lo", "mid", "hi"))
    elif _num(v) is not None:
        t = (_num(v),) * 3
    elif isinstance(m.get("base"), dict) and isinstance(m.get("factor"), dict):
        b = _num(m["base"].get("value"))
        f = tuple(_num(m["factor"].get(k)) for k in ("lo", "mid", "hi"))
        t = tuple(b * x if b is not None and x is not None else None for x in f)
    else:
        return None
    if t[1] is None:
        return None
    lo, mid, hi = (t[0] if t[0] is not None else t[1]), t[1], (t[2] if t[2] is not None else t[1])
    return min(lo, mid), mid, max(hi, mid)


def check(est):
    if not est:
        return
    if not est.get("unit") or not est.get("methods"):
        raise ValueError("capacity.estimate에 unit·methods가 필요하다(capa_model.py 맨 위)")
    for m in est["methods"]:
        if m.get("kind") not in KINDS or not m.get("source") or not m.get("basis"):
            raise ValueError(f"capacity.estimate 방법 {m.get('kind')}: kind({KINDS})·basis·source가 필요하다")
        if m.get("value") != UNKNOWN and _trip(m) is None:
            raise ValueError(f"capacity.estimate 방법 {m['kind']}: value(숫자·lo/mid/hi) 또는 base×factor, 모르면 '미확인'")
    if not any(_trip(m) for m in est["methods"] if not m.get("bound")):
        raise ValueError("capacity.estimate: 점 추정 방법이 하나 이상 있어야 한다(경영진 하한·상한만으로는 추정하지 않는다)")


def estimate(cap):
    """결합 추정 — {"lo","mid","hi","unit","rows","use","spread_warn","bounds"} 또는 None"""
    est = (cap or {}).get("estimate")
    if not est:
        return None
    rows, pts, lows, highs = [], [], [], []
    for m in est["methods"]:
        t = _trip(m) if m.get("value") != UNKNOWN else None
        rows.append({**m, "t": t})
        if t is None:
            continue
        if m.get("bound") == "하한":
            lows.append(t[1])
        elif m.get("bound") == "상한":
            highs.append(t[1])
        else:
            pts.append((t, float(m.get("weight", WEIGHTS[m["kind"]]))))
    if not pts:
        return None
    w = sum(x for _, x in pts)
    mid = sum(t[1] * x for t, x in pts) / w
    lo, hi = min(t[0] for t, _ in pts), max(t[2] for t, _ in pts)
    floor, cap_ = (max(lows) if lows else None), (min(highs) if highs else None)
    if floor is not None:
        mid, lo, hi = max(mid, floor), max(lo, floor), max(hi, floor)
    if cap_ is not None:
        mid, lo, hi = min(mid, cap_), min(lo, cap_), min(hi, cap_)
    mids = [t[1] for t, _ in pts]
    out = _num((est.get("output") or {}).get("value"))
    return {"lo": lo, "mid": mid, "hi": hi, "unit": est["unit"], "rows": rows, "floor": floor, "ceiling": cap_,
            "spread_warn": len(mids) > 1 and max(mids) / min(mids) > SPREAD_WARN,
            "use": out / mid if out and mid else None, "use_range": (out / hi, out / lo) if out and lo and hi else None, "output": est.get("output")}


_PCT = re.compile(r"(\d{1,3})\s*%")


def mfg_share(f):
    s = _num(f.get("mfg_share"))
    if s is not None:
        return s
    m = _PCT.search(str(f.get("capacity_basis") or ""))
    return int(m.group(1)) / 100 if m and "제조" in str(f.get("capacity_basis")) else 1.0


def allocate(e, facilities, is_production):
    """결합 캐파를 생산시설 면적 × 제조 사용 비율로 나눈다 → [(시설, 배분 mid, 비중)]"""
    items = [f for f in (facilities or {}).get("items") or [] if (f.get("area") or {}).get("value") and is_production(f)]
    wts = [(f, f["area"]["value"] * mfg_share(f)) for f in items]
    tot = sum(x for _, x in wts)
    if not tot:
        return []
    return sorted(((f, e["mid"] * x / tot, x / tot) for f, x in wts), key=lambda r: -r[1])


def _f(v):
    return UNKNOWN if v is None else (f"{v:,.0f}" if abs(v) >= 100 else f"{v:,.1f}")


def headline(e):
    t = f"**추정 캐파 {_f(e['mid'])} {e['unit']}(범위 {_f(e['lo'])}~{_f(e['hi'])})**"
    if e["use"] is not None:
        t += f" — {e['output'].get('label', '현재 산출')} 기준 가동률 약 {e['use']:.0%}"
        if e["use_range"]:
            t += f"({e['use_range'][0]:.0%}~{e['use_range'][1]:.0%})"
    t += ". 회사가 캐파를 공시하지 않아 여러 방법을 합친 추정이다."
    if e["spread_warn"]:
        t += " 방법 간 차이가 커 확신도는 낮다."
    return t


def table(e):
    rows = []
    for r in e["rows"]:
        t = r["t"]
        how = (f"{r['base'].get('label', '')} {_f(_num(r['base'].get('value')))} × {r['factor'].get('label', '')} {_f(_num(r['factor'].get('mid')))}"
               if isinstance(r.get("base"), dict) and isinstance(r.get("factor"), dict) else (r.get("bound") or "직접 값"))
        val = UNKNOWN if t is None else (f"{_f(t[1])}" + (f" ({_f(t[0])}~{_f(t[2])})" if t[0] != t[2] else ""))
        rows.append([r["kind"] + (f"({r['bound']})" if r.get("bound") else ""), val, how, r.get("basis", ""), r.get("source", "")])
    return {"type": "table", "title": f"캐파 추정 — 방법별({e['unit']}, 결합 = 점 추정 가중 평균, 경영진 하한·상한으로 자름)",
            "headers": ["방법", "추정", "계산", "근거", "출처"], "rows": rows}


def chart(e):
    """방법별 추정과 결합값, 현재 산출 — 한 단위 한 축(가로 막대)"""
    col = {"경영진": "d", "IB": "e", "판매·가동률": "c", "자산회전": "c", "면적": "c"}
    rows = [{"label": f"{r['kind']}" + (f"({r['bound']})" if r.get("bound") else ""), "bars": [{"name": r["kind"], "color": col.get(r["kind"], "c"), "value": round(r["t"][1], 1)}]}
            for r in e["rows"] if r["t"]]
    rows.append({"label": "결합 추정", "bars": [{"name": "결합 추정", "color": "a", "value": round(e["mid"], 1)}]})
    if _num((e["output"] or {}).get("value")):
        rows.append({"label": e["output"].get("label", "현재 산출"), "bars": [{"name": "현재 산출", "color": "b", "value": round(e["output"]["value"], 1)}]})
    use = f" · 가동률 약 {e['use']:.0%}" if e["use"] is not None else ""
    return {"kind": "hbars", "w": 480, "label_w": 150, "unit": "",
            "title": f"추정 캐파({e['unit']}) — 결합 {_f(e['mid'])}(범위 {_f(e['lo'])}~{_f(e['hi'])}){use}", "rows": rows}


def site_chart(e, facilities, is_production):
    al = allocate(e, facilities, is_production)
    if len(al) < 2:
        return None
    return {"kind": "hbars", "w": 480, "label_w": 160, "unit": "",
            "title": f"생산시설별 추정 캐파({e['unit']}, 큰 순) — 결합 추정을 면적 × 제조 사용 비율로 배분",
            "rows": [{"label": f["name"], "bars": [{"name": "추정 캐파", "color": "c", "value": round(v, 1)}]} for f, v, _ in al]}
