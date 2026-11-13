"""텐배거(Analysis) 리포트 '자산 구성과 ROIC' 절 (마스터 지시 2026-11-13 "유형·무형자산 세부 항목별 가치를 파악하고 이 요인들이 ROIC에
얼마나 기여하는지 정량화하는 전문 기법 기반 모델링 절. 내용연수와 분기별 감가상각 비율 포함") — 설계 docs/decisions/ADR-021-asset-roic.md

숫자는 여기서 계산한다. 모델은 datapack "assets"에 공시 원자료만 쓴다. 모르는 값은 null로 두고 지어내지 않는다.
datapack에 "assets"가 없으면 이 절은 나오지 않는다(옛 리포트 출력은 그대로).
금액 단위는 assets.unit(보통 "$M"). 배열은 [최근, 1년 전] 또는 [최근, 1년 전, 2년 전](2년 전이 있으면 평균 투하자본을 쓴다).
datapack "assets":
  {"as_of": "3Q26", "unit": "$M", "source": "10-Q 2026-09-30, 10-K 2025",
   "note_periods": ["2025-12-31", "2024-12-31"],         # 유형·무형 주석 기준일(최근, 1년 전) — 분기 보고서가 항목을 안 나누면 연말 주석
   "ppe": [{"name": "토지", "kind": "land", "gross": [431.5, 368.2]},     # kind: land|building|leasehold|equipment|cip|software|other
           {"name": "건물", "kind": "building", "gross": [2107.2, 2174.7], "accum": [null, null], "life": [3, 44]}],   # 항목별 누적상각을 모르면 null
   "ppe_accum": [1930.2, 1736.0],                        # 유형자산 누적상각 합계(항목별이 없을 때)
   "intangibles": [{"name": "상표", "kind": "indefinite|finite|goodwill", "gross": [...], "accum": [...], "life": [5, 10] 또는 null,
                    "acquired": true}],                  # 인수로 생긴 무형이면 true(영업권은 늘 인수)
   "dep_annual": [{"year": 2025, "dep": 292.7, "amort": 1.1}, {"year": 2024, ...}],   # 최근 해부터. 유형 감가상각비·무형 상각비
   "quarters": [{"q": "3Q24", "da": 69.5, "ppe_net": 3095.1, "ppe_gross": null}, ...],   # 오래된 분기부터. da = 감가상각비(무형 상각 포함 가능)
   "da_note": "손익계산서 D&A(무형 상각 연 $1.1M 포함)",
   "roic": {"periods": ["TTM 3Q26", "TTM 3Q25"], "rev": [..2개], "ebit": [..2개], "acq_amort": [..2개], "tax_rate": 0.25,
            "lease_liab": [..2~3개], "lease_rate": 0.0928,          # 운영리스 부채와 가중평균 할인율 → NOPAT에 더할 리스 내재 이자
            "impairment_cum": 0,                                   # 영업권·무형 손상 누계(투하자본에 되더한다)
            "capital": {"nwc": [..], "ppe": [..], "rou": [..], "goodwill": [..], "intangibles": [..], "other": [..]}},   # 분기말 잔액
   "intangible_cap": {"rd": [[2021, 0], ...], "sga": [[2019, 227.7], ...], "note": "..."},   # 선택. 연간, 오래된 해부터
   "life_changes": [{"date": "2025-01-01", "asset": "서버", "old": 5, "new": 5.5, "base": 1000, "effect": 290, "source": "10-K"}]   # 선택. effect를 모르면 base로 추정
  }
계산(ADR-021):
  ① 항목별 총액·누적상각·순액, 1년 변화. 경과율 = 누적상각 ÷ 상각 대상 총액(토지·건설중 제외).
  ② 내용연수 산식(HOLT 자산 수명 = 총유형자산 ÷ 감가상각비): 평균 = 상각 대상 총액 ÷ 연 감가상각, 경과 = 누적 ÷ 연 감가상각, 잔여 = 순 상각 대상 ÷ 연 감가상각.
     공시 범위는 총액 가중 중간값과 대조. 정액법일 때만 근사다.
  ③ 분기 감가 비율 = 분기 감가상각 ÷ 평균 기초·기말 유형자산(총액, 없으면 순액이라고 밝힌다), 연율 ×4. 최근 4분기가 직전 4분기보다 낮으면
     직전 감가율을 썼을 때의 감가상각 − 실제 = 감가 정책·믹스가 이익에 보탠 몫(자체추론).
  ④ ROIC(Mauboussin·Callahan, McKinsey): NOPAT = (EBIT + 인수 무형 상각 + 리스 내재 이자) × (1 − 세율), 투하자본 = 운전자본 + 유형 + 리스 사용권 + 영업권 + 무형 + 기타.
     영업권·인수 무형 포함/제외 두 판. ROIC = NOPAT 마진 × 투하자본 회전율, 항목별 매출 대비 자본·회전율·자본 몫·'빼면 ROIC'.
     1년 변화는 로그 평균 분해(LMDI)로 마진 효과와 항목별 자본 효과(%p)를 정확히 나눈다. 투하자본·NOPAT이 0 이하면 분해하지 않는다(경제적 이익으로 본다).
  ⑤ 무형 자본화 조정판(Damodaran R&D 자본화 + Peters·Taylor 판관비 몫): 정액 상각 자산 = Σ 투자 × (1 − 경과연수/연수),
     조정 NOPAT = NOPAT + 올해 투자 − 지난 투자 상각, 조정 투하자본 = 포함판 + 자산. 가정은 config/asset_roic.yaml(registry prm-ar-*).
"""
import math
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
UNKNOWN = "미확인"
DEPRECIABLE_OFF = ("land", "cip")     # 상각하지 않는 유형자산
CAP_NAMES = {"nwc": "운전자본", "ppe": "유형자산", "rou": "리스 사용권자산", "goodwill": "영업권", "intangibles": "무형자산(인수)", "other": "기타 영업자산"}
ACQUIRED = ("goodwill", "intangibles")


def config():
    return yaml.safe_load((ROOT / "config" / "asset_roic.yaml").read_text(encoding="utf-8"))["asset_roic"]


def _v(a, i):
    return a[i] if isinstance(a, (list, tuple)) and len(a) > i and a[i] is not None else None


def _m(v, cur="$", unit="M"):
    if v is None:
        return UNKNOWN
    return f"−{cur}{abs(v):,.1f}{unit}" if v < 0 else f"{cur}{v:,.1f}{unit}"


def _p(v, d=1, sign=False):
    if v is None:
        return UNKNOWN
    return f"{v * 100:+.{d}f}%" if sign else f"{v * 100:.{d}f}%"


def _pp(v, d=1):
    return UNKNOWN if v is None else f"{v * 100:+.{d}f}%p"


def _y(v):
    return UNKNOWN if v is None else f"{v:.1f}년"


# ---------- ① 항목별 가치 ----------
def items(a):
    rows = []
    for it in a.get("ppe") or []:
        g0, g1 = _v(it.get("gross"), 0), _v(it.get("gross"), 1)
        ac0, ac1 = _v(it.get("accum"), 0), _v(it.get("accum"), 1)
        if it.get("kind") in DEPRECIABLE_OFF:
            ac0 = ac1 = 0.0
        rows.append({"group": "유형", **it, "g": [g0, g1], "ac": [ac0, ac1],
                     "net": [None if g0 is None or ac0 is None else g0 - ac0, None if g1 is None or ac1 is None else g1 - ac1]})
    for it in a.get("intangibles") or []:
        g0, g1 = _v(it.get("gross"), 0), _v(it.get("gross"), 1)
        ac0, ac1 = _v(it.get("accum"), 0) or 0.0, _v(it.get("accum"), 1) or 0.0
        rows.append({"group": "영업권" if it.get("kind") == "goodwill" else "무형", **it, "g": [g0, g1], "ac": [ac0, ac1],
                     "net": [None if g0 is None else g0 - ac0, None if g1 is None else g1 - ac1]})
    return rows


def ppe_totals(a, i):
    """i번째 기준일 유형자산 총액·상각 대상 총액·누적상각·순액"""
    gross = sum(_v(x.get("gross"), i) or 0 for x in a.get("ppe") or [])
    off = sum(_v(x.get("gross"), i) or 0 for x in a.get("ppe") or [] if x.get("kind") in DEPRECIABLE_OFF)
    acc = _v(a.get("ppe_accum"), i)
    if acc is None:
        parts = [_v(x.get("accum"), i) for x in a.get("ppe") or [] if x.get("kind") not in DEPRECIABLE_OFF]
        acc = sum(parts) if parts and all(p is not None for p in parts) else None
    return {"gross": gross, "dep_gross": gross - off, "accum": acc, "net": None if acc is None else gross - acc,
            "land_cip": off, "cip": sum(_v(x.get("gross"), i) or 0 for x in a.get("ppe") or [] if x.get("kind") == "cip")}


# ---------- ② 내용연수 ----------
def lives(a):
    """연도별 산식 내용연수와 공시 범위 가중 중간값"""
    out = []
    for i, d in enumerate((a.get("dep_annual") or [])[:2]):
        t = ppe_totals(a, i)
        dep = d.get("dep")
        if not dep or t["dep_gross"] <= 0:
            continue
        out.append({"year": d["year"], "period": _v(a.get("note_periods"), i) or str(d["year"]), "dep": dep, **t,
                    "avg": t["dep_gross"] / dep, "age": None if t["accum"] is None else t["accum"] / dep,
                    "remain": None if t["accum"] is None else (t["dep_gross"] - t["accum"]) / dep,
                    "elapsed": None if t["accum"] is None else t["accum"] / t["dep_gross"]})
    w = [(_v(x.get("gross"), 0) or 0, x["life"]) for x in a.get("ppe") or [] if x.get("life") and x.get("kind") not in DEPRECIABLE_OFF]
    tot = sum(g for g, _ in w)
    band = None
    if tot > 0:
        band = {"lo": sum(g * l[0] for g, l in w) / tot, "hi": sum(g * l[1] for g, l in w) / tot, "mid": sum(g * (l[0] + l[1]) / 2 for g, l in w) / tot}
    return out, band


# ---------- ③ 분기 감가 비율 ----------
def dep_rates(a):
    qs = a.get("quarters") or []
    rows = []
    for prev, cur in zip(qs, qs[1:]):
        basis = "총액" if cur.get("ppe_gross") is not None and prev.get("ppe_gross") is not None else "순액"
        key = "ppe_gross" if basis == "총액" else "ppe_net"
        if cur.get(key) is None or prev.get(key) is None or not cur.get("da"):
            continue
        base = (cur[key] + prev[key]) / 2
        rows.append({"q": cur["q"], "da": cur["da"], "base": base, "basis": basis, "rate_q": cur["da"] / base, "rate_y": cur["da"] / base * 4})
    return rows


def dep_shift(rows, ebit_ttm, cfg):
    """최근 4분기 vs 직전 4분기 연율 감가율 — 낮아졌으면 직전 감가율로 다시 잰 감가상각과의 차(이익에 보탠 몫)"""
    if len(rows) < 8:
        return None
    new, old = rows[-4:], rows[-8:-4]
    r_new = sum(x["da"] for x in new) / sum(x["base"] for x in new) * 4
    r_old = sum(x["da"] for x in old) / sum(x["base"] for x in old) * 4
    counter = sum(x["base"] * r_old / 4 for x in new)
    boost = counter - sum(x["da"] for x in new)
    rel = r_new / r_old - 1
    return {"r_new": r_new, "r_old": r_old, "rel": rel, "boost": boost, "boost_pct": boost / ebit_ttm if ebit_ttm else None,
            "flag": rel <= -cfg["dep_rate_shift"], "basis": new[-1]["basis"]}


# ---------- ④ ROIC ----------
def _cap(a, i, avg):
    c = (a.get("roic") or {}).get("capital") or {}
    out = {}
    for k in CAP_NAMES:
        if k not in c:
            continue
        x0 = _v(c[k], i)
        x1 = _v(c[k], i + 1)
        out[k] = (x0 + x1) / 2 if avg and x1 is not None and x0 is not None else x0
    return out


def roic(a):
    """[최근, 1년 전] 두 기간의 ROIC 판(영업권·인수 무형 포함/제외)과 항목별 분해"""
    r = a.get("roic") or {}
    c = r.get("capital") or {}
    avg = bool(c) and all(len(v or []) >= 3 and v[2] is not None for v in c.values())   # 2년 전 잔액이 다 있어야 두 기간 모두 평균
    t = r.get("tax_rate", 0.25)
    imp = r.get("impairment_cum") or 0.0
    out = []
    for i in range(2):
        rev, ebit = _v(r.get("rev"), i), _v(r.get("ebit"), i)
        if rev is None or ebit is None:
            continue
        ll = list(r.get("lease_liab") or [])
        rou = ((r.get("capital") or {}).get("rou") or [])
        ll = [x if x is not None else _v(rou, j) for j, x in enumerate(ll + [None] * max(0, len(rou) - len(ll)))]   # 리스 부채를 모르는 시점은 사용권자산으로 대신(크기가 비슷하다)
        lease = None
        if r.get("lease_rate") is not None and _v(ll, i) is not None:
            base = (ll[i] + ll[i + 1]) / 2 if avg and _v(ll, i + 1) is not None else ll[i]
            lease = base * r["lease_rate"]
        ebita = ebit + (_v(r.get("acq_amort"), i) or 0.0) + (lease or 0.0)
        nopat = ebita * (1 - t)
        cap = _cap(a, i, avg)
        if "goodwill" in cap:
            cap["goodwill"] += imp
        incl = sum(cap.values())
        excl = sum(v for k, v in cap.items() if k not in ACQUIRED)
        out.append({"period": _v(r.get("periods"), i) or f"기간 {i}", "rev": rev, "ebit": ebit, "lease_int": lease, "nopat": nopat, "cap": cap,
                    "ic_incl": incl, "ic_excl": excl, "margin": nopat / rev,
                    "roic_incl": nopat / incl if incl > 0 else None, "roic_excl": nopat / excl if excl > 0 else None, "avg": avg})
    return out


def item_rows(p, version="incl"):
    """항목별 매출 대비 자본·회전율·자본 몫·빼면 ROIC"""
    keys = [k for k in p["cap"] if version == "incl" or k not in ACQUIRED]
    ic = sum(p["cap"][k] for k in keys)
    rows = []
    for k in keys:
        x = p["cap"][k]
        rest = ic - x
        rows.append({"k": k, "name": CAP_NAMES[k], "cap": x, "intensity": x / p["rev"], "turn": p["rev"] / x if x > 0 else None,
                     "share": x / ic if ic > 0 else None, "without": p["nopat"] / rest if rest > 0 else None})
    return rows


def _lm(x, y):
    return x if abs(x - y) < 1e-12 else (x - y) / math.log(x / y)


def lmdi(p1, p0, version="incl"):
    """ROIC 변화 = 마진 효과 + Σ 항목 자본 효과. ROIC = 마진 ÷ Σ(항목 자본 ÷ 매출), 로그 평균 분해라 합이 정확히 맞는다"""
    key = "roic_incl" if version == "incl" else "roic_excl"
    keys = [k for k in p1["cap"] if (version == "incl" or k not in ACQUIRED) and k in p0["cap"]]
    c1, c0 = sum(p1["cap"][k] for k in keys) / p1["rev"], sum(p0["cap"][k] for k in keys) / p0["rev"]
    r1, r0 = p1.get(key), p0.get(key)
    if not r1 or not r0 or r1 <= 0 or r0 <= 0 or c1 <= 0 or c0 <= 0 or p1["margin"] <= 0 or p0["margin"] <= 0:
        return None
    L, LC = _lm(r1, r0), _lm(c1, c0)
    parts = [("NOPAT 마진", L * math.log(p1["margin"] / p0["margin"]))]
    for k in keys:
        parts.append((CAP_NAMES[k], -L * (p1["cap"][k] / p1["rev"] - p0["cap"][k] / p0["rev"]) / LC))
    return {"from": r0, "to": r1, "parts": parts}


# ---------- ⑤ 무형 자본화 ----------
def capitalize(hist, life, share=1.0):
    """정액 상각 무형 자산(Damodaran 방식) — hist [[연도, 지출]] 오래된 해부터. 올해 투자는 상각하지 않고, 지난 n년 투자를 1/n씩 상각"""
    if not hist or not life:
        return None
    y = hist[-1][0]
    inv = {yr: v * share for yr, v in hist if v is not None}
    asset = sum(v * max(0.0, 1 - (y - yr) / life) for yr, v in inv.items())
    amort = sum(v / life for yr, v in inv.items() if 1 <= y - yr <= life)
    short = len([yr for yr in inv if y - yr <= life]) < life + 1   # 상각 기간을 다 덮지 못하면 과소 추정
    return {"year": y, "invest": inv.get(y, 0.0), "asset": asset, "amort": amort, "short": short}


def cap_version(a, p, cfg, sga_share=None, sga_life=None):
    ic = a.get("intangible_cap")
    if not ic or not p:
        return None
    k = cfg["intangible_cap"]
    rd = capitalize(ic.get("rd"), k["rd_life"])
    sg = capitalize(ic.get("sga"), sga_life or k["sga_life"], sga_share if sga_share is not None else k["sga_share"])
    parts = [x for x in (rd, sg) if x]
    if not parts:
        return None
    asset = sum(x["asset"] for x in parts)
    delta = sum(x["invest"] - x["amort"] for x in parts)
    nopat = p["nopat"] + delta
    cap = p["ic_incl"] + asset
    return {"asset": asset, "delta": delta, "nopat": nopat, "ic": cap, "roic": nopat / cap if cap > 0 else None, "rd": rd, "sga": sg,
            "short": any(x["short"] for x in parts), "year": parts[0]["year"]}


def life_effects(a, ebit):
    out = []
    for c in a.get("life_changes") or []:
        eff = c.get("effect")
        est = False
        if eff is None and c.get("base") and c.get("old") and c.get("new"):
            eff, est = c["base"] / c["old"] - c["base"] / c["new"], True
        out.append({**c, "effect": eff, "est": est, "pct": eff / ebit if eff is not None and ebit else None})
    return out


# ---------- 절 ----------
def section(dp, wacc=None):
    a = (dp or {}).get("assets")
    if not a or a.get("none"):
        return None
    cfg = config()
    cur = (dp.get("currency_symbol") or "$").strip() if dp.get("currency_symbol") else "$"
    unit = str(a.get("unit", "$M")).replace("$", "").strip() or "M"
    M = lambda v: _m(v, cur, unit)
    B = []
    rs = roic(a)
    lv, band = lives(a)
    dq = dep_rates(a)
    p1 = rs[0] if rs else None
    p0 = rs[1] if len(rs) > 1 else None
    shift = dep_shift(dq, p1["ebit"] if p1 else None, cfg)
    capv = cap_version(a, p1, cfg)

    # 결론 한 줄
    head = []
    if p1 and p1["roic_incl"] is not None:
        head.append(f"**{p1['period']} ROIC는 영업권·인수 무형 포함 {_p(p1['roic_incl'])}, 제외 {_p(p1['roic_excl'])}**"
                    f"(NOPAT 마진 {_p(p1['margin'])} × 투하자본 회전율 {p1['rev'] / p1['ic_incl']:.2f}회)")
        top = max(item_rows(p1), key=lambda x: x["share"] or 0)
        head.append(f"투하자본의 가장 큰 몫은 {top['name']}({_p(top['share'], 0)}, 매출 1달러당 {top['intensity']:.2f}달러)이며, 빼고 재면 ROIC {_p(top['without'])}")
    if p1 and p0:
        dec = lmdi(p1, p0)
        if dec:
            big = max(dec["parts"], key=lambda x: abs(x[1]))
            head.append(f"1년 동안 {_p(dec['from'])} → {_p(dec['to'])}, 가장 큰 요인은 {big[0]}({_pp(big[1])})")
    if shift:
        head.append(f"연율 감가 비율({shift['basis']} 기준)은 직전 4분기 {_p(shift['r_old'], 2)} → 최근 4분기 {_p(shift['r_new'], 2)}"
                    + (f", 직전 비율이면 감가상각이 {M(shift['boost'])} 더 컸다(영업이익의 {_p(shift['boost_pct'])})" if shift["boost"] > 0 else ""))
    if head:
        B.append({"type": "hl", "text": ". ".join(head) + "."})

    # ① 항목별 가치 표
    rows = items(a)
    if rows:
        np0, np1 = (a.get("note_periods") or ["최근", "1년 전"])[:2]
        T = []
        for x in rows:
            life = f"{x['life'][0]:g}~{x['life'][1]:g}년" if x.get("life") else ("비상각" if x.get("kind") in DEPRECIABLE_OFF + ("indefinite", "goodwill") else UNKNOWN)
            ac = "총계만 공시" if x["group"] == "유형" and x["ac"][0] is None else M(x["ac"][0])
            ch = None if x["g"][0] is None or x["g"][1] in (None, 0) else x["g"][0] / x["g"][1] - 1
            T.append([x["group"], x["name"], M(x["g"][0]), ac, M(x["net"][0]) if x["net"][0] is not None else "총계만 공시", M(x["g"][1]), _p(ch, 1, True), life])
        for i, lab in ((0, np0), (1, np1)):
            t = ppe_totals(a, i)
            if t["accum"] is not None and i == 0:
                t1 = ppe_totals(a, 1)
                T.append(["유형 합계", "유형자산", M(t["gross"]), M(t["accum"]), M(t["net"]), M(t1["gross"]),
                          _p(t["gross"] / t1["gross"] - 1 if t1["gross"] else None, 1, True), f"경과율 {_p(t['accum'] / t['dep_gross'], 0)}(상각 대상 기준)"])
        B.append({"type": "table", "title": f"유형·무형자산 항목별 가치({np0} vs {np1})",
                  "headers": ["구분", "항목", f"총액 {np0}", "누적상각", "순액", f"총액 {np1}", "총액 1년 변화", "공시 내용연수"], "rows": T})

    # ② 내용연수
    if lv:
        T = [[x["period"], M(x["dep"]), M(x["dep_gross"]), _y(x["avg"]), _y(x["age"]), _y(x["remain"]), _p(x["elapsed"], 0)] for x in lv]
        B.append({"type": "table", "title": "내용연수 산식(상각 대상 유형자산 = 총액 − 토지 − 건설중)",
                  "headers": ["기준일", "연 감가상각", "상각 대상 총액", "평균 내용연수", "경과 연수", "잔여 연수", "경과율"], "rows": T})
        line = f"산식 평균 내용연수는 {_y(lv[0]['avg'])}"
        if band:
            off = lv[0]["avg"] / band["mid"] - 1
            line += (f"이며, 공시 범위의 총액 가중 중간값 {_y(band['mid'])}(가중 범위 {band['lo']:.1f}~{band['hi']:.1f}년)"
                     + (f"과 {_p(off, 0, True)} 어긋난다 — 범위가 넓거나 상각을 끝낸 자산이 많으면 생기는 차이라 회사별로 원인을 본다" if abs(off) > cfg["life_band"] else "과 가깝다"))
        if len(lv) > 1:
            line += f". 1년 전 {_y(lv[1]['avg'])} → 지금 {_y(lv[0]['avg'])}"
            cip0, cip1 = ppe_totals(a, 0)["cip"], ppe_totals(a, 1)["cip"]
            if cip1 and cip0 / cip1 > 1.5:
                line += f". 건설중인자산이 {M(cip1)} → {M(cip0)}로 늘어 감가상각 없는 자산 몫이 커졌다(순액 기준 감가 비율을 끌어내린다)"
        B.append({"type": "p", "text": line + "."})

    # ③ 분기 감가 비율
    if dq:
        T = [[x["q"], M(x["da"]), M(x["base"]), _p(x["rate_q"], 2), _p(x["rate_y"], 2), _y(1 / x["rate_y"])] for x in dq[-8:]]
        B.append({"type": "table", "title": f"분기 감가 비율(감가상각 ÷ 평균 유형자산 {dq[-1]['basis']})",
                  "headers": ["분기", "감가상각", f"평균 유형자산({dq[-1]['basis']})", "분기 비율", "연율", "연율의 역수"], "rows": T})
        B.append({"type": "chart", "chart": {"kind": "line", "title": f"분기 감가 비율 연율(유형자산 {dq[-1]['basis']} 대비)", "unit": "%",
                                             "series": [{"name": "연율 감가 비율", "color": "c", "points": [[x["q"], round(x["rate_y"] * 100, 2)] for x in dq[-8:]]}]}})
        if a.get("da_note"):
            B.append({"type": "p", "text": f"감가상각 기준: {a['da_note']}."})
        if shift:
            if shift["flag"]:
                txt = (f"**감가율 하락 경고: 연율 {_p(shift['r_old'], 2)} → {_p(shift['r_new'], 2)}({_p(shift['rel'], 0, True)}).** 직전 4분기 비율을 그대로 쓰면 최근 4분기 감가상각이 "
                       f"{M(shift['boost'])} 더 컸다(영업이익의 {_p(shift['boost_pct'])}). 내용연수 연장·상각 끝난 자산 증가·건설중 자산 증가(믹스) 중 무엇인지는 공시 주석으로 가린다(자체추론).")
            else:
                txt = f"최근 4분기 연율 감가 비율 {_p(shift['r_new'], 2)}, 직전 4분기 {_p(shift['r_old'], 2)}({_p(shift['rel'], 0, True)}) — 경고 문턱({_p(-cfg['dep_rate_shift'], 0)}) 안이다."
            B.append({"type": "p", "text": txt})
    le = life_effects(a, p1["ebit"] if p1 else None)
    if le:
        B.append({"type": "table", "title": "내용연수 변경과 이익 효과", "headers": ["시점", "자산", "변경", "연 감가상각 감소(세전)", "영업이익 대비", "근거"],
                  "rows": [[c.get("date", ""), c.get("asset", ""), f"{c.get('old')}년 → {c.get('new')}년", M(c["effect"]) + ("(추정)" if c["est"] else ""), _p(c["pct"]), c.get("source", "")] for c in le]})

    # ④ ROIC 분해
    if p1:
        T = []
        for x in item_rows(p1):
            T.append([x["name"], M(x["cap"]), f"{x['intensity']:.2f}", "음수(자금 원천)" if x["turn"] is None else f"{x['turn']:.2f}회", _p(x["share"], 0), _p(x["without"])])
        B.append({"type": "table", "title": f"투하자본 항목별 회전율과 ROIC 기여({p1['period']}{', 평균 잔액' if p1['avg'] else ', 기말 잔액'})",
                  "headers": ["항목", "투하자본", "매출 1달러당 자본", "회전율(매출 ÷ 항목)", "자본 몫", "이 항목을 빼면 ROIC"], "rows": T})
        V = [["영업권·인수 무형 포함", M(p1["nopat"]), M(p1["ic_incl"]), _p(p1["roic_incl"]), "인수 웃돈까지 낸 돈에 대한 수익률"],
             ["영업권·인수 무형 제외", M(p1["nopat"]), M(p1["ic_excl"]), _p(p1["roic_excl"]), "본업 운영 수익률(동종 비교용)"]]
        if capv:
            k = cfg["intangible_cap"]
            V.append([f"무형 자본화 조정(판관비 {_p(k['sga_share'], 0)}·{k['sga_life']}년, 연구개발 {k['rd_life']}년)", M(capv["nopat"]), M(capv["ic"]), _p(capv["roic"]),
                      "비용으로 처리한 무형 투자를 자산으로 본 판" + (" — 이력이 상각 기간보다 짧아 자산 과소" if capv["short"] else "")])
        if wacc is not None and p1["ic_incl"]:
            V.append(["경제적 이익(포함판)", M(p1["nopat"] - wacc * p1["ic_incl"]), M(p1["ic_incl"]), f"자본비용 {_p(wacc)}", "(ROIC − 자본비용) × 투하자본"])
        B.append({"type": "table", "title": "ROIC 세 가지 판", "headers": ["판", "NOPAT", "투하자본", "ROIC", "무엇을 재나"], "rows": V})
        lease_txt = f" + 리스 내재 이자 {M(p1['lease_int'])}" if p1["lease_int"] else ""
        B.append({"type": "p", "text": f"NOPAT = (영업이익 {M(p1['ebit'])} + 인수 무형 상각{lease_txt}) × (1 − 세율 {_p((a.get('roic') or {}).get('tax_rate', 0.25), 0)}). "
                                       f"리스 사용권자산을 투하자본에 넣었으므로 임차료 속 이자 몫을 영업이익에 되더했다. 현금은 영업에 필요한 몫을 따로 알 수 없어 투하자본에서 뺐다."
                                       + (f" {(a.get('roic') or {})['note']}." if (a.get("roic") or {}).get("note") else "")})
        B.append({"type": "chart", "chart": card(p1, capv, wacc, cur, unit)})   # 한눈에 보기 ROIC 그림은 이 한 장(마스터 지시 2026-11-13)
        if p0:
            dec = lmdi(p1, p0)
            if dec:
                B.append({"type": "table", "title": f"ROIC 1년 변화 분해(포함판, {p0['period']} → {p1['period']})", "headers": ["요인", "ROIC 기여"],
                          "rows": [[n, _pp(v, 2)] for n, v in dec["parts"]] + [["합계", _pp(dec["to"] - dec["from"], 2)]]})
            else:
                B.append({"type": "p", "text": "투하자본 또는 NOPAT이 0 이하라 ROIC 분해는 비교 불가 — 경제적 이익으로 본다."})
        if capv:
            k = cfg["intangible_cap"]
            S = []
            for sh in k["sensitivity"]["sga_share"]:
                for lf in k["sensitivity"]["sga_life"]:
                    v = cap_version(a, p1, cfg, sh, lf)
                    S.append([f"판관비 {_p(sh, 0)}", f"{lf}년", M(v["asset"]), M(v["delta"]), _p(v["roic"])])
            B.append({"type": "table", "title": f"무형 자본화 가정별 ROIC({capv['year']}년 지출 기준, 포함판에 더함)",
                      "headers": ["투자로 보는 몫", "상각 연수", "무형 자산", "NOPAT 조정", "조정 ROIC"], "rows": S})
            if (a.get("intangible_cap") or {}).get("note"):
                B.append({"type": "p", "text": a["intangible_cap"]["note"]})

    if a.get("missing"):
        B.append({"type": "p", "text": "미공시·미분해: " + " · ".join(a["missing"]) + " — 이 칸은 비우고 나머지로 계산했다."})
    # 해석
    lines = interpret(a, p1, p0, shift, capv, lv, band, cfg, M)
    if lines:
        B += [{"type": "h3", "text": "해석 — 무엇이 수익성을 끌어올리고 희석하나"}, {"type": "ul", "items": lines}]
    return {"h2": "자산 구성과 ROIC", "blocks": B, "_sources": [a["source"]] if a.get("source") else []}


CARD_COLORS = {"ppe": "c", "rou": "b", "goodwill": "d", "intangibles": "e", "nwc": "a", "other": "a"}


def card(p, capv, wacc, cur="$", unit="M"):
    """한눈에 보기 ROIC 한 장 — 투하자본 구성(유형·리스·영업권·무형·운전자본) + ROIC 포함·제외(·무형 자본화) vs WACC"""
    order = ("ppe", "rou", "goodwill", "intangibles", "other", "nwc")
    parts = [{"label": CAP_NAMES[k], "value": round(p["cap"][k], 1), "color": CARD_COLORS[k]} for k in order if k in p["cap"] and abs(p["cap"][k]) > 1e-9]
    rates = [{"label": "ROIC 영업권 포함", "value": round(p["roic_incl"] * 100, 1), "color": "c"}] if p["roic_incl"] is not None else []
    if p["roic_excl"] is not None:
        rates.append({"label": "ROIC 영업권 제외", "value": round(p["roic_excl"] * 100, 1), "color": "d"})
    if capv and capv.get("roic") is not None:
        rates.append({"label": "무형 자본화 조정", "value": round(capv["roic"] * 100, 1), "color": "e"})
    return {"kind": "roic", "title": f"자산 구성과 ROIC({p['period']}) — 투하자본 {_m(p['ic_incl'], cur, unit)}, NOPAT {_m(p['nopat'], cur, unit)}",
            "parts": parts, "rates": rates, "wacc": round(wacc * 100, 1) if wacc is not None else None, "unit": cur, "unit_suffix": unit,
            "note": f"NOPAT 마진 {_p(p['margin'])} × 회전율 {p['rev'] / p['ic_incl']:.2f}회" if p["ic_incl"] > 0 else None}


def interpret(a, p1, p0, shift, capv, lv, band, cfg, M):
    out = []
    if not p1:
        return out
    rows = sorted(item_rows(p1), key=lambda x: -(x["share"] or 0))
    lift = [x for x in rows if x["cap"] < 0]
    drag = [x for x in rows if x["cap"] > 0][:2]
    for x in drag:
        out.append(f"{x['name']}: 투하자본의 {_p(x['share'], 0)} — 빼면 ROIC {_p(p1['roic_incl'])} → {_p(x['without'])}. 이 자산의 회전율({x['turn']:.2f}회)이 수익성을 희석하는 주된 자리다.")
    for x in lift:
        out.append(f"{x['name']}: {M(x['cap'])}(음수), 고객 선수금·공급사 외상이 자본을 대신 댄다 — 빼면 ROIC {_p(x['without'])}로 낮아진다. 수익성을 끌어올리는 쪽이다.")
    if p1["roic_excl"] is not None and p1["roic_incl"] is not None:
        out.append(f"영업권·인수 무형을 빼면 ROIC가 {_pp(p1['roic_excl'] - p1['roic_incl'])} 오른다 — 과거 인수에 치른 웃돈이 주주 수익률을 그만큼 낮춘다(본업 수익률은 제외판, 인수까지 포함한 가치 창출은 포함판으로 본다).")
    if p0:
        dec = lmdi(p1, p0)
        if dec:
            pos = [(n, v) for n, v in dec["parts"] if v > 0]
            neg = [(n, v) for n, v in dec["parts"] if v < -0.0005]   # 0.05%p 미만은 말하지 않는다
            if pos:
                n, v = max(pos, key=lambda x: x[1])
                out.append(f"1년 ROIC 개선의 최대 요인은 {n}({_pp(v)})." + (f" 반대로 깎은 최대 요인은 {min(neg, key=lambda x: x[1])[0]}({_pp(min(neg, key=lambda x: x[1])[1])})." if neg else ""))
    if shift:
        if shift["flag"]:
            out.append(f"감가 비율 하락으로 최근 4분기 영업이익에 {M(shift['boost'])}({_p(shift['boost_pct'])})가 보태졌을 수 있다 — 내용연수 변경 공시가 없으면 건설중 자산·토지 같은 비상각 자산 몫이 커진 믹스 효과일 가능성이 크다(자체추론).")
        elif shift["rel"] > cfg["dep_rate_shift"]:
            out.append("감가 비율이 올라갔다 — 이익을 보수적으로 잡는 쪽이다(내용연수 단축·짧은 수명 자산 증가).")
    if lv and band and lv[0]["avg"] > band["hi"]:
        out.append("산식 평균 내용연수가 공시 가중 범위 위쪽보다 길다 — 감가상각이 적게 잡히는 쪽이라 이익의 질을 낮춰 본다.")
    if capv and capv["roic"] is not None and p1["roic_incl"] is not None:
        d = capv["roic"] - p1["roic_incl"]
        out.append(f"비용으로 처리한 무형 투자를 자산으로 보면 ROIC가 {_pp(d)} 움직인다(무형 자산 {M(capv['asset'])}). "
                   + ("투자를 늘리는 중이라 NOPAT이 더 커지는 쪽이다." if capv["delta"] > 0 else "투자 증가가 상각보다 작아 NOPAT 조정이 작다."))
    return out
