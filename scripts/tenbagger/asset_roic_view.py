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


# ---------- ⑥ 분기 추이와 다음 4개 분기 추정(마스터 지시 2026-11-14) ----------
# "자산 구성은 최근 분기 구성 → 자산별 최근 12개 분기 변화율, ROIC는 최근 12개 분기 추이, 둘 다 다음 4개 분기 추정을 그래프에.
#  추정은 IB 리서치 하우스의 전문 기법, NOPAT은 Fiscal.ai 등 컨센서스"
# 추정 기법(재무상태표 동인 모형 — sell-side 3표 모델의 표준):
#   손익: 컨센서스 분기 매출(consensus.quarters_est, Fiscal.ai) × 컨센서스 EBIT 마진(consensus.ebit_margin, 조정이면 SBC를 뺀다) = EBITA.
#         이미 발표했지만 SEC 공시 데이터(10-Q)에 아직 없는 분기는 Fiscal.ai 표준 재무(quarters_hist)의 실제 매출·영업이익.
#   운전자본: 항목별 회전 일수(DSO·DIO·DPO) — 매출채권·선급·미지급·선수는 매출, 재고·매입채무는 매출원가에 최근 4개 분기 평균 일수를 곱한다
#             (CFA 재무제표 모델링 — 일수가 잔액으로 바로 바뀐다. 매출원가 = 매출 × 최근 4개 분기 원가율).
#   유형자산: 이월 = 기초 + CAPEX − 감가상각. CAPEX = 매출 × 최근 4개 분기 CAPEX 강도, 감가 = 기초 순액 × 최근 4개 분기 분기 감가율
#             (Koller·Goedhart·Wessels 『Valuation』(McKinsey) 재무상태표 추정 — 순 유형자산은 CAPEX·감가로 굴리고, CAPEX 재료가 없으면 순 유형자산 ÷ 매출 유지).
#   영업권·리스 사용권·기타: 인수·새 리스 계약은 공시 전엔 모르므로 유지. 인수 무형: 분기 상각만큼 줄인다.
#   ROIC: TTM NOPAT ÷ 평균 투하자본(이번 분기말과 4개 분기 전 평균, Mauboussin·Callahan 2014 'Calculating ROIC' 평균 자본).
DAYS = 91.25
NWC_ITEMS = {"ar": ("rev", 1), "inv": ("cogs", 1), "prepaid": ("rev", 1), "ap": ("cogs", -1), "accrued": ("rev", -1), "deferred_rev": ("rev", -1)}
NWC_NAMES = {"ar": "매출채권", "inv": "재고자산", "prepaid": "선급·기타 유동자산", "ap": "매입채무", "accrued": "미지급비용", "deferred_rev": "선수수익(계약부채)"}
ASSET_LINES = {"ar": "매출채권", "inv": "재고자산", "ppe": "유형자산", "rou": "리스 사용권자산", "goodwill": "영업권", "intangibles": "무형자산(인수)"}


def _ql(d):
    from datetime import date as _d
    d = _d.fromisoformat(d) if isinstance(d, str) else d
    return f"{(d.month - 1) // 3 + 1}Q{str(d.year)[2:]}"


def cap_of(row):
    """분기말 잔액 → 투하자본 항목(운전자본은 순액)"""
    b = row.get("bal") or {}
    out = {}
    if any(b.get(k) is not None for k in NWC_ITEMS):
        out["nwc"] = sum((b.get(k) or 0) * s for k, (_, s) in NWC_ITEMS.items())
    for k in ("ppe", "rou", "goodwill", "intangibles", "other"):
        if b.get(k) is not None:
            out[k] = b[k]
    return out


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def drivers(a):
    """최근 4개 분기 실적에서 재무상태표 동인 — 일수·강도·감가율"""
    H = a.get("hist") or []
    n = config().get("forecast", {}).get("driver_quarters", 4)   # registry prm-ar-fcst-window
    if len(H) < n + 1:
        return None
    L4 = H[-n:]
    rev4 = sum(x["rev"] or 0 for x in L4)
    cogs_ok = all(x.get("cogs") for x in L4)
    d = {"cogs_ratio": sum(x["cogs"] for x in L4) / rev4 if cogs_ok and rev4 else None, "days": {}}
    for k, (base, _) in NWC_ITEMS.items():
        b = "cogs" if base == "cogs" and cogs_ok else "rev"
        d["days"][k] = _mean([x["bal"].get(k) / x[b] * DAYS if x["bal"].get(k) is not None and x.get(b) else None for x in L4])
        d.setdefault("base", {})[k] = b
    capex = [x.get("capex") for x in L4]
    d["capex_int"] = sum(capex) / rev4 if all(c is not None for c in capex) and rev4 else None
    amort_y = _v((a.get("roic") or {}).get("acq_amort"), 0) or 0.0
    am = [x.get("amort") for x in L4]
    d["amort_q"] = _mean(am) if any(v is not None for v in am) else amort_y / 4
    W = H[-(n + 1):]
    # 감가율은 기초 잔액으로 맞춘다(추정도 기초 잔액에 곱한다 — 평균 잔액으로 맞추고 기초에 곱하면 성장기에 감가가 작게 나왔다, 2026-11-14 점검)
    dep = [(c.get("da") - (c.get("amort") if c.get("amort") is not None else d["amort_q"]), p["bal"]["ppe"], c)
           for p, c in zip(W, W[1:]) if c.get("da") is not None and c["bal"].get("ppe") and p["bal"].get("ppe")]
    d["dep_q"] = sum(x for x, _, _ in dep) / sum(y for _, y, _ in dep) if len(dep) == n else None
    # 이월 잔차 = 실제 변화 − (CAPEX − 감가) — 처분·매각 후 재임차·환율·재분류. 이월식만 쓰면 유형자산이 과대해진다(2026-11-14 점검: AMAT 4개 분기 +13.6%, LTH +7.4%)
    res = [c["bal"]["ppe"] - y - c["capex"] + x for x, y, c in dep if c.get("capex") is not None]
    d["ppe_resid"] = sum(res) / len(res) if len(res) == n else 0.0
    d["ppe_int"] = _mean([x["bal"]["ppe"] / x["rev"] for x in L4 if x["bal"].get("ppe") and x.get("rev")])
    return d


def income_path(dp, H, n=4):
    """다음 n개 분기 손익 — [{q, end, rev, ebita, cogs?, src}], 단위 assets.unit(백만). 실적 발표분(quarters_hist) → 컨센서스 순"""
    from datetime import date, timedelta
    last = date.fromisoformat(H[-1]["end"])
    q_rev = H[-1]["rev"] or 1
    out = []
    for x in (dp.get("quarters_hist") or {}).get("q") or []:   # SEC 10-Q보다 먼저 들어오는 발표 실적(Fiscal.ai 표준 재무)
        e = date.fromisoformat(x["period"])
        if (e - last).days > 20 and x.get("rev") and x.get("op") is not None and len(out) < n:
            out.append({"q": _ql(e), "end": e.isoformat(), "rev": x["rev"] / 1e6, "ebit": x["op"] / 1e6, "cogs": (x.get("cogs") or 0) / 1e6 or None,
                        "src": "발표 실적(Fiscal.ai) · 재무상태표 추정"})
    c = dp.get("consensus") or {}
    qe = c.get("quarters_est") or {}
    fy_rev = c.get("rev") or {}
    m = c.get("ebit_margin") or {}
    sbc = dp.get("sbc_pct_rev") or 0.0
    adj = str(c.get("margin_basis", "")).startswith("non")
    fwd = ((dp.get("forward") or {}).get("ntm") or {})
    keys = sorted(qe)
    if not keys and fy_rev:   # 분기 컨센서스가 없으면 다음 회계연도 매출 ÷ 4
        fy0 = sorted(fy_rev)[0]
        keys = [f"{fy0[2:]}Q{i}" for i in range(1, 5)]
        qe = {k: fy_rev[fy0] / 4 for k in keys}
    scale = 1.0
    if keys:
        v0 = qe[keys[0]]
        scale = 1000.0 if v0 and 0.2 <= v0 * 1000 / q_rev <= 5 else 1.0   # 컨센서스가 십억 단위면 백만으로
    for k in keys:
        if len(out) >= n:
            break
        prev = date.fromisoformat(out[-1]["end"]) if out else last
        e = prev + timedelta(days=91)
        fy = f"FY{k[:4]}"
        mg = m.get(fy) if m.get(fy) is not None else (m[sorted(m)[0]] if m else None)
        src = f"컨센서스 매출 × EBIT 마진 {fy}"
        if mg is None and fwd.get("ebit") and fwd.get("revenue"):
            mg, src = fwd["ebit"] / fwd["revenue"], "컨센서스 매출 × 다음 4개 분기 EBIT 마진(Fiscal.ai)"
        if mg is None:
            break
        if adj:
            mg -= sbc
            src += f"(조정 − 주식보상 {sbc * 100:.1f}%)"
        rev = qe[k] * scale
        # 조정(비 GAAP) 마진은 인수 무형 상각을 이미 뺀 이익 → 그대로 EBITA. GAAP 마진이면 영업이익이라 상각을 forecast에서 되더한다(2026-11-14 점검)
        out.append({"q": _ql(e), "end": e.isoformat(), "rev": rev, **({"ebita": rev * mg} if adj else {"ebit": rev * mg}), "cogs": None, "src": src, "key": k})
    return out


def forecast(a, dp):
    """다음 4개 분기 — 손익(실적 발표분·컨센서스)과 재무상태표 동인으로 굴린 잔액. 행 모양은 hist와 같고 est에 출처"""
    H = a.get("hist") or []
    d = drivers(a)
    if not d:
        return [], None
    inc = income_path(dp, H, config().get("forecast", {}).get("horizon", 4))
    rows, prev = [], H[-1]
    for x in inc:
        rev = x["rev"]
        cogs = x.get("cogs") or (rev * d["cogs_ratio"] if d["cogs_ratio"] else None)
        pb = prev["bal"]
        bal = {}
        for k, (base, _) in NWC_ITEMS.items():
            b = cogs if d["base"][k] == "cogs" else rev
            bal[k] = d["days"][k] / DAYS * b if d["days"].get(k) is not None and b else pb.get(k)
        capex = dep = None
        if pb.get("ppe") is not None and d["capex_int"] is not None and d["dep_q"] is not None:
            capex, dep = d["capex_int"] * rev, d["dep_q"] * pb["ppe"]
            bal["ppe"] = max(0.0, pb["ppe"] + capex - dep + d["ppe_resid"])
        else:
            bal["ppe"] = d["ppe_int"] * rev if d["ppe_int"] else pb.get("ppe")
        for k in ("rou", "goodwill", "other"):
            bal[k] = pb.get(k)
        bal["intangibles"] = None if pb.get("intangibles") is None else max(0.0, pb["intangibles"] - d["amort_q"])
        ebita = x["ebita"] if x.get("ebita") is not None else x["ebit"] + d["amort_q"]
        row = {"q": x["q"], "end": x["end"], "rev": rev, "ebita": ebita, "cogs": cogs, "capex": capex, "dep": dep, "bal": bal, "lease": prev.get("lease"), "est": x["src"]}
        rows.append(row)
        prev = row
    return rows, d


def roic_path(a, rows):
    """TTM ROIC — 4개 분기 NOPAT ÷ 평균 투하자본(이번 분기말·4개 분기 전). rows = hist(+추정) 오래된 분기부터"""
    r = a.get("roic") or {}
    t = r.get("tax_rate", 0.25)
    rate = r.get("lease_rate")
    imp = r.get("impairment_cum") or 0.0
    amort_q = (_v(r.get("acq_amort"), 0) or 0.0) / 4
    keys = [k for k in CAP_NAMES if any(k in cap_of(x) for x in rows)]
    caps = [{k: cap_of(x).get(k) or 0.0 for k in keys} for x in rows]
    out = []
    for i in range(4, len(rows)):
        w = rows[i - 3:i + 1]
        if any(x.get("rev") is None or (x.get("ebita") is None and x.get("ebit") is None) for x in w):
            continue
        rev = sum(x["rev"] for x in w)
        ebita = sum(x["ebita"] if x.get("ebita") is not None else x["ebit"] + (x["amort"] if x.get("amort") is not None else amort_q) for x in w)
        lease = (rows[i]["lease"] + rows[i - 4]["lease"]) / 2 * rate if rate is not None and rows[i].get("lease") is not None and rows[i - 4].get("lease") is not None else 0.0
        nopat = (ebita + lease) * (1 - t)
        cap = {k: (caps[i][k] + caps[i - 4][k]) / 2 for k in keys}
        if "goodwill" in cap:
            cap["goodwill"] += imp
        incl = sum(cap.values())
        excl = sum(v for k, v in cap.items() if k not in ACQUIRED)
        out.append({"q": rows[i]["q"], "est": rows[i].get("est"), "rev": rev, "nopat": nopat, "ic_incl": incl, "ic_excl": excl, "margin": nopat / rev if rev else None,
                    "roic_incl": nopat / incl if incl > 0 else None, "roic_excl": nopat / excl if excl > 0 else None})
    return out


def _r1(v):
    return None if v is None else round(v, 1)


def mix_chart(a, cur, unit):
    """최근 분기 투하자본 구성 — 분기말 잔액(실적 발표 분기, SEC 10-Q·10-K)"""
    H = a.get("hist") or []
    if H:
        cap, lab = cap_of(H[-1]), f"{H[-1]['q']} 분기말"
    else:
        c = (a.get("roic") or {}).get("capital") or {}
        cap, lab = {k: _v(v, 0) for k, v in c.items() if _v(v, 0) is not None}, f"{a.get('as_of', '최근')} 분기말"
    order = ("ppe", "rou", "goodwill", "intangibles", "other", "nwc")
    parts = [{"label": CAP_NAMES[k], "value": round(cap[k], 1), "color": CARD_COLORS[k]} for k in order if k in cap and abs(cap[k]) > 1e-9]
    if not parts:
        return None
    return {"kind": "roic", "title": f"자산 구성 — {lab} 투하자본 {_m(sum(cap.values()), cur, unit)}", "parts": parts, "rates": [], "unit": cur, "unit_suffix": unit,
            "note": "운전자본 = 매출채권 + 재고 + 선급 − 매입채무 − 미지급 − 선수수익(현금 제외)"}


def change_chart(H, F):
    """자산별 최근 12개 분기 변화율(첫 분기 = 0%) + 다음 4개 분기 추정 — 잔액이 큰 자산 5개와 투하자본 합계"""
    if len(H) < 2:
        return None
    rows = H[-12:] + F
    base = rows[0]
    last = H[-1]["bal"]
    cand = [k for k in ASSET_LINES if (base["bal"].get(k) or 0) > 0 and (last.get(k) or 0) > 0]
    cand = sorted(cand, key=lambda k: -last[k])[:5]
    cols = ["c", "a", "b", "d", "e"]
    series = [{"name": ASSET_LINES[k], "color": cols[i], "points": [[x["q"], _r1((x["bal"][k] / base["bal"][k] - 1) * 100) if x["bal"].get(k) is not None else None] for x in rows]}
              for i, k in enumerate(cand)]
    ic0 = sum(cap_of(base).values())
    if ic0 > 0:
        series.append({"name": "투하자본 합계", "color": "f", "dash": True, "points": [[x["q"], _r1((sum(cap_of(x).values()) / ic0 - 1) * 100)] for x in rows]})
    out = {"kind": "line", "title": f"자산별 변화율 — 최근 {len(H[-12:])}개 분기({base['q']} = 0%)" + (f" + 다음 {len(F)}개 분기 추정" if F else ""), "unit": "%", "series": series}
    if F:
        out["est_from"] = F[0]["q"]
    return out


def roic_chart(path, n_hist, wacc):
    """ROIC 추이 — TTM, 최근 12개 분기 + 다음 4개 분기 추정(점선)"""
    act = [x for x in path if not x.get("est")][-12:]
    est = [x for x in path if x.get("est")]
    rows = act + est
    if len(rows) < 2:
        return None
    series = [{"name": "ROIC 영업권·인수 무형 포함", "color": "c", "points": [[x["q"], _r1(x["roic_incl"] * 100) if x["roic_incl"] is not None else None] for x in rows]},
              {"name": "ROIC 영업권·인수 무형 제외", "color": "d", "points": [[x["q"], _r1(x["roic_excl"] * 100) if x["roic_excl"] is not None else None] for x in rows]}]
    if wacc is not None:
        series.append({"name": f"WACC {wacc * 100:.1f}%", "color": "f", "dash": True, "points": [[x["q"], round(wacc * 100, 1)] for x in rows]})
    out = {"kind": "line", "title": f"ROIC 추이 — TTM, 최근 {len(act)}개 분기" + (f" + 다음 {len(est)}개 분기 추정(컨센서스 NOPAT)" if est else ""), "unit": "%", "series": series}
    if est:
        out["est_from"] = est[0]["q"]
    return out


def _ctx(dp, wacc):
    a = (dp or {}).get("assets")
    if not a or a.get("none"):
        return None
    cfg = config()
    cur = (dp.get("currency_symbol") or "$").strip() if dp.get("currency_symbol") else "$"
    unit = str(a.get("unit", "$M")).replace("$", "").strip() or "M"
    H0 = a.get("hist") or []
    if len(H0) >= 9 and all(x.get("rev") is not None and x.get("ebit") is not None for x in H0[-8:]):
        # 두 기간 판(표)도 추이 그림과 같은 분기 이력으로 — 모델이 고친 roic.capital과 SEC 이력이 섞여 같은 TTM에 ROIC가 두 개 나왔다(2026-11-14 점검: LTH 8.27% vs 8.43%)
        r0 = dict(a.get("roic") or {})
        caps = [cap_of(H0[i]) for i in (-1, -5, -9)]
        keys = [k for k in CAP_NAMES if any(k in c for c in caps)]
        r0["capital"] = {k: [c.get(k) or 0.0 for c in caps] for k in keys}
        r0["rev"] = [sum(x["rev"] for x in H0[-4:]), sum(x["rev"] for x in H0[-8:-4])]
        r0["ebit"] = [sum(x["ebit"] for x in H0[-4:]), sum(x["ebit"] for x in H0[-8:-4])]
        r0["periods"] = [f"TTM {H0[-1]['q']}", f"TTM {H0[-5]['q']}"]
        r0["lease_liab"] = [H0[i].get("lease") for i in (-1, -5, -9)]
        a = {**a, "roic": r0}
    rs = roic(a)
    dq = dep_rates(a)
    p1 = rs[0] if rs else None
    H = a.get("hist") or []
    F, drv = forecast(a, dp) if H else ([], None)
    path = roic_path(a, H + F) if H else []
    return {"a": a, "cfg": cfg, "cur": cur, "unit": unit, "M": lambda v: _m(v, cur, unit), "rs": rs, "p1": p1, "p0": rs[1] if len(rs) > 1 else None,
            "lv": lives(a), "dq": dq, "shift": dep_shift(dq, p1["ebit"] if p1 else None, cfg), "capv": cap_version(a, p1, cfg),
            "H": H, "F": F, "drv": drv, "path": path, "wacc": wacc}


# ---------- 절: 자산 구성 ----------
def section(dp, wacc=None):
    """'자산 구성' 절 — 최근 분기 구성 → 자산별 12개 분기 변화율·추정 → 항목별 가치·내용연수·감가 비율. ROIC는 roic_section(마스터 지시 2026-11-14 분리)"""
    X = _ctx(dp, wacc)
    if not X:
        return None
    a, cfg, M, p1, shift, H, F = X["a"], X["cfg"], X["M"], X["p1"], X["shift"], X["H"], X["F"]
    lv, band = X["lv"]
    dq = X["dq"]
    B = []
    head = []
    if H:
        cap = cap_of(H[-1])
        ic = sum(cap.values())
        top = sorted(((k, v) for k, v in cap.items() if v > 0), key=lambda x: -x[1])[:2]
        if ic > 0 and top:
            head.append(f"**{H[-1]['q']} 분기말 투하자본 {M(ic)}** — " + ", ".join(f"{CAP_NAMES[k]} {_p(v / ic, 0)}" for k, v in top))
        if len(H) >= 2:
            b0 = H[-12:][0]
            ch = [(ASSET_LINES[k], H[-1]["bal"][k] / b0["bal"][k] - 1) for k in ASSET_LINES if (b0["bal"].get(k) or 0) > 0 and H[-1]["bal"].get(k)]
            if ch:
                hi = max(ch, key=lambda x: x[1])
                ic0 = sum(cap_of(b0).values())
                head.append(f"최근 {len(H[-12:])}개 분기({b0['q']} → {H[-1]['q']}) 가장 크게 늘어난 자산은 {hi[0]}({_p(hi[1], 0, True)})"
                            + (f", 투하자본 합계 {_p(ic / ic0 - 1, 0, True)}" if ic0 > 0 else ""))
        if F:
            capf = sum(cap_of(F[-1]).values())
            head.append(f"{F[-1]['q']} 추정 투하자본 {M(capf)}({_p(capf / ic - 1, 0, True) if ic > 0 else UNKNOWN}, 컨센서스 매출과 회전 일수·CAPEX 강도 유지 가정)")
    if shift:
        head.append(f"연율 감가 비율({shift['basis']} 기준)은 직전 4분기 {_p(shift['r_old'], 2)} → 최근 4분기 {_p(shift['r_new'], 2)}"
                    + (f", 직전 비율이면 감가상각이 {M(shift['boost'])} 더 컸다(영업이익의 {_p(shift['boost_pct'])})" if shift["boost"] > 0 else ""))
    if head:
        B.append({"type": "hl", "text": ". ".join(head) + "."})
    mc = mix_chart(a, X["cur"], X["unit"])
    if mc:
        B.append({"type": "chart", "chart": mc})
    cc = change_chart(H, F)
    if cc:
        B.append({"type": "chart", "chart": cc})
    if H:
        b0, b4 = H[-12:][0], (H[-5] if len(H) >= 5 else None)
        T = []
        for k, name in list(ASSET_LINES.items())[:2] + [(k, NWC_NAMES[k]) for k in ("prepaid", "ap", "accrued", "deferred_rev")] + list(ASSET_LINES.items())[2:]:
            cur_v = H[-1]["bal"].get(k)
            if cur_v is None:
                continue
            f = F[-1]["bal"].get(k) if F else None
            base = b0["bal"].get(k)
            T.append([name, M(base), M(b4["bal"].get(k)) if b4 else UNKNOWN, M(cur_v), M(f) if F else "—",
                      _p(cur_v / base - 1, 0, True) if base and base > 0 else "비교 불가", _p(f / cur_v - 1, 0, True) if F and f is not None and cur_v > 0 else "—"])
        heads = ["항목", f"{b0['q']}", f"{b4['q']}" if b4 else "1년 전", f"{H[-1]['q']}(최근)", f"{F[-1]['q']} 추정" if F else "추정", f"{len(H[-12:])}개 분기 변화", "다음 4개 분기 변화"]
        B.append({"type": "table", "title": "자산·운전자본 항목별 분기말 잔액 — 최근 12개 분기와 다음 4개 분기 추정", "headers": heads, "rows": T})
        if F and X["drv"]:
            d = X["drv"]
            D = [[NWC_NAMES[k], f"{d['days'][k]:.0f}일", "매출원가" if d["base"][k] == "cogs" else "매출"] for k in NWC_ITEMS if d["days"].get(k) is not None]
            if d["capex_int"] is not None and d["dep_q"] is not None:
                D += [["CAPEX 강도", _p(d["capex_int"], 1), "매출(최근 4개 분기 합)"], ["분기 감가율", _p(d["dep_q"], 2), "기초 유형자산 순액(무형 상각 제외 감가상각)"]]
            elif d["ppe_int"]:
                D.append(["유형자산 ÷ 분기 매출", f"{d['ppe_int']:.2f}배", "CAPEX·감가 재료 없음 — 비율 유지"])
            if d["cogs_ratio"]:
                D.append(["매출원가율", _p(d["cogs_ratio"], 1), "매출(최근 4개 분기)"])
            D.append(["영업권·리스 사용권·기타", "유지", "인수·새 리스는 공시 전 모름"])
            D.append(["인수 무형자산", f"분기 {M(d['amort_q'])} 상각", "최근 4개 분기 평균 상각"])
            B.append({"type": "table", "title": "자산 추정 동인 — 최근 4개 분기 평균(재무상태표 동인 모형)", "headers": ["동인", "값", "곱하는 기준"], "rows": D})
            B.append({"type": "p", "text": "**추정 방법:** 증권사 3표 모델(손익·재무상태표·현금흐름)의 재무상태표 동인 방식이다. 운전자본은 항목별 회전 일수(매출채권·선급·미지급·선수는 매출, "
                                           "재고·매입채무는 매출원가 기준)를 최근 4개 분기 평균으로 두고 컨센서스 매출에 곱한다. 유형자산은 기초 + CAPEX − 감가상각으로 굴린다"
                                           "(Koller·Goedhart·Wessels 『Valuation』 재무상태표 추정). 매출 경로는 ROIC 절의 컨센서스와 같다."})

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
        t = ppe_totals(a, 0)
        if t["accum"] is not None:
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
        if not _has_roic(X):   # ROIC 절이 있으면 감가 비율 그림은 ROIC 그림 뒤로(한눈에 보기: 자산 구성 → 변화율 → ROIC → 감가 비율)
            B.append({"type": "chart", "chart": dep_chart(dq)})
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
    if a.get("missing"):
        B.append({"type": "p", "text": "미공시·미분해: " + " · ".join(a["missing"]) + " — 이 칸은 비우고 나머지로 계산했다."})
    lines = asset_interp(X)
    if lines:
        B += [{"type": "h3", "text": "해석 — 자산이 어디에 쌓이고 있나"}, {"type": "ul", "items": lines}]
    return {"h2": "자산 구성", "blocks": B, "_sources": [a["source"]] if a.get("source") else []}


def _has_roic(X):
    return bool(X["p1"] or X["path"])


def dep_chart(dq):
    return {"kind": "line", "title": f"분기 감가 비율 연율(유형자산 {dq[-1]['basis']} 대비)", "unit": "%",
            "series": [{"name": "연율 감가 비율", "color": "c", "points": [[x["q"], round(x["rate_y"] * 100, 2)] for x in dq[-8:]]}]}


# ---------- 절: ROIC ----------
def roic_section(dp, wacc=None):
    """'ROIC' 절 — 자산 구성 바로 아래(마스터 지시 2026-11-14 "ROIC는 자산 구성 항목 아래로 분리, 최근 12개 분기, 다음 4개 분기 추정, NOPAT은 컨센서스")"""
    X = _ctx(dp, wacc)
    if not X or not _has_roic(X):
        return None
    a, cfg, M, p1, p0, capv, path, F = X["a"], X["cfg"], X["M"], X["p1"], X["p0"], X["capv"], X["path"], X["F"]
    act = [x for x in path if not x.get("est")]
    est = [x for x in path if x.get("est")]
    B, head = [], []
    top = act[-1] if act and act[-1]["roic_incl"] is not None else None   # 추이 그림과 같은 숫자(분기 이력)를 먼저 — 없으면 roic 두 기간 판
    if top:
        head.append(f"**TTM {top['q']} ROIC는 영업권·인수 무형 포함 {_p(top['roic_incl'])}, 제외 {_p(top['roic_excl'])}**"
                    f"(NOPAT 마진 {_p(top['margin'])} × 투하자본 회전율 {top['rev'] / top['ic_incl']:.2f}회)")
    elif p1 and p1["roic_incl"] is not None:
        head.append(f"**{p1['period']} ROIC는 영업권·인수 무형 포함 {_p(p1['roic_incl'])}, 제외 {_p(p1['roic_excl'])}**"
                    f"(NOPAT 마진 {_p(p1['margin'])} × 투하자본 회전율 {p1['rev'] / p1['ic_incl']:.2f}회)")
    if len(act) >= 2 and act[-12:][0]["roic_incl"] is not None and act[-1]["roic_incl"] is not None:
        w = act[-12:]
        hi = max(w, key=lambda x: x["roic_incl"] if x["roic_incl"] is not None else -9)
        head.append(f"최근 {len(w)}개 분기 {w[0]['q']} {_p(w[0]['roic_incl'])} → {w[-1]['q']} {_p(w[-1]['roic_incl'])}(고점 {hi['q']} {_p(hi['roic_incl'])})")
    if est and est[-1]["roic_incl"] is not None:
        head.append(f"컨센서스 NOPAT으로 굴리면 {est[-1]['q']} {_p(est[-1]['roic_incl'])}(제외 {_p(est[-1]['roic_excl'])})"
                    + (f" — WACC {_p(wacc)} 대비 {_pp(est[-1]['roic_incl'] - wacc)}" if wacc is not None else ""))
    if p1 and p0:
        dec = lmdi(p1, p0)
        if dec:
            big = max(dec["parts"], key=lambda x: abs(x[1]))
            head.append(f"1년 변화의 가장 큰 요인은 {big[0]}({_pp(big[1])})")
    if head:
        B.append({"type": "hl", "text": ". ".join(head) + "."})
    rc = roic_chart(path, len(act), wacc)
    if rc:
        B.append({"type": "chart", "chart": rc})
    elif p1:   # 분기 이력(hist)이 없는 옛 datapack — 두 기간 판 한 장(ROIC 포함·제외 vs WACC)
        B.append({"type": "chart", "chart": card(p1, capv, wacc, X["cur"], X["unit"])})
    if path:
        rows = act[-12:] + est
        B.append({"type": "table", "title": "ROIC 추이(TTM)와 다음 4개 분기 추정 — NOPAT ÷ 평균 투하자본(이번 분기말·4개 분기 전)",
                  "headers": ["분기", "구분", "TTM 매출", "TTM NOPAT", "NOPAT 마진", "평균 투하자본", "ROIC 포함", "ROIC 제외"],
                  "rows": [[x["q"], "추정" if x.get("est") else "실적", M(x["rev"]), M(x["nopat"]), _p(x["margin"]), M(x["ic_incl"]), _p(x["roic_incl"]), _p(x["roic_excl"])] for x in rows]})
    if F:
        t = (a.get("roic") or {}).get("tax_rate", 0.25)
        T = [[x["q"], M(x["rev"]), _p(x["ebita"] / x["rev"]) if x["rev"] else UNKNOWN, M(x["ebita"]), M(x["ebita"] * (1 - t)), x["est"]] for x in F]
        B.append({"type": "table", "title": f"다음 4개 분기 NOPAT — 컨센서스(세율 {_p(t, 0)}, 리스 이자 별도)", "headers": ["분기", "매출", "EBITA 마진", "EBITA", "NOPAT(분기)", "근거"], "rows": T})
        B.append({"type": "p", "text": "**추정 방법:** NOPAT은 컨센서스(Fiscal.ai 분기 매출 추정 × 회계연도 EBIT 마진 추정)로 잡고, 조정(비 GAAP) 마진이면 주식보상 몫을 빼서 과거 실적과 같은 기준"
                                       "(영업이익 + 인수 무형 상각)으로 맞췄다. 이미 발표했지만 분기 보고서(10-Q)가 아직 없는 분기는 발표 실적을 쓴다. 투하자본은 자산 구성 절의 재무상태표 동인으로 굴렸다. "
                                       "ROIC는 4개 분기 NOPAT을 이번 분기말과 4개 분기 전 투하자본의 평균으로 나눈다(Mauboussin·Callahan 평균 자본) — 추정 분기의 ROIC에는 이미 나온 실적 분기가 섞여 있다."})

    # ④ ROIC 분해(최근 TTM)
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
    if X["dq"]:
        B.append({"type": "chart", "chart": dep_chart(X["dq"])})   # 한눈에 보기에서 ROIC 그림 뒤(본문 그림은 모두 한눈에 보기로 올라간다)
    lines = roic_interp(X)
    if lines:
        B += [{"type": "h3", "text": "해석 — 무엇이 수익성을 끌어올리고 희석하나"}, {"type": "ul", "items": lines}]
    return {"h2": "ROIC", "blocks": B, "_sources": []}


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
    return {"kind": "roic", "title": f"ROIC({p['period']}) — 투하자본 {_m(p['ic_incl'], cur, unit)}, NOPAT {_m(p['nopat'], cur, unit)}",
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


def asset_interp(X):
    """자산 구성 절 해석 — 어떤 자산이 매출보다 빨리 쌓이나, 감가·내용연수"""
    out, M, H, F, shift, cfg = [], X["M"], X["H"], X["F"], X["shift"], X["cfg"]
    lv, band = X["lv"]
    if len(H) >= 5:
        b0, b1 = H[-12:][0], H[-1]
        n0 = sum(x["rev"] or 0 for x in H[-12:][:4]) if len(H[-12:]) >= 8 else None
        n1 = sum(x["rev"] or 0 for x in H[-4:])
        g = n1 / n0 - 1 if n0 else None
        if g is not None:
            fast = [(ASSET_LINES[k], b1["bal"][k] / b0["bal"][k] - 1) for k in ASSET_LINES if (b0["bal"].get(k) or 0) > 0 and b1["bal"].get(k)]
            over = [x for x in fast if x[1] > g + 0.10]
            out.append(f"같은 기간 4개 분기 매출은 {_p(g, 0, True)}" + (" — 매출보다 빨리 늘어난 자산: " + ", ".join(f"{n} {_p(v, 0, True)}" for n, v in over)
                       + ". 이 자산의 회전율이 떨어지면 ROIC를 희석한다." if over else ". 자산이 매출보다 빨리 쌓이지 않았다 — 회전율이 유지된다."))
    if F and all(x.get("capex") is not None for x in F):
        cx, dp_ = sum(x["capex"] for x in F), sum(x["dep"] for x in F)
        out.append(f"다음 4개 분기 CAPEX {M(cx)} vs 감가상각 {M(dp_)}(최근 4개 분기 CAPEX 강도·감가율 유지) — 유형자산 {H[-1]['q']} {M(H[-1]['bal'].get('ppe'))} → {F[-1]['q']} {M(F[-1]['bal'].get('ppe'))}. "
                   + ("투자가 감가보다 커서 자산이 쌓이는 국면이다." if cx > dp_ else "투자가 감가보다 작아 자산이 줄어드는 국면이다."))
    if shift:
        if shift["flag"]:
            out.append(f"감가 비율 하락으로 최근 4분기 영업이익에 {M(shift['boost'])}({_p(shift['boost_pct'])})가 보태졌을 수 있다 — 내용연수 변경 공시가 없으면 건설중 자산·토지 같은 비상각 자산 몫이 커진 믹스 효과일 가능성이 크다(자체추론).")
        elif shift["rel"] > cfg["dep_rate_shift"]:
            out.append("감가 비율이 올라갔다 — 이익을 보수적으로 잡는 쪽이다(내용연수 단축·짧은 수명 자산 증가).")
    if lv and band and lv[0]["avg"] > band["hi"]:
        out.append("산식 평균 내용연수가 공시 가중 범위 위쪽보다 길다 — 감가상각이 적게 잡히는 쪽이라 이익의 질을 낮춰 본다.")
    return out


def roic_interp(X):
    """ROIC 절 해석 — 희석·부양 항목, 인수 웃돈, 1년 분해, 무형 자본화, 추정 경로"""
    p1, p0, capv, M = X["p1"], X["p0"], X["capv"], X["M"]
    out = []
    if p1:
        out += [x for x in interpret(X["a"], p1, p0, None, capv, [], None, X["cfg"], M)]
    act = [x for x in X["path"] if not x.get("est")]
    est = [x for x in X["path"] if x.get("est")]
    if act and est and act[-1]["roic_incl"] is not None and est[-1]["roic_incl"] is not None:
        dm = (est[-1]["margin"] or 0) - (act[-1]["margin"] or 0)
        dt = est[-1]["rev"] / est[-1]["ic_incl"] - act[-1]["rev"] / act[-1]["ic_incl"] if est[-1]["ic_incl"] and act[-1]["ic_incl"] else None
        out.append(f"추정 경로 {act[-1]['q']} {_p(act[-1]['roic_incl'])} → {est[-1]['q']} {_p(est[-1]['roic_incl'])}: NOPAT 마진 {_pp(dm)}"
                   + (f", 투하자본 회전율 {dt:+.2f}회" if dt is not None else "") + " — 컨센서스 매출·마진이 맞고 회전 일수·CAPEX 강도가 유지된다는 가정이다. 마진 추정이 내려가거나 재고 일수가 늘면 이 경로가 먼저 틀린다.")
    if X["wacc"] is not None and act and act[-1]["roic_incl"] is not None:
        out.append(f"ROIC(포함) − WACC = {_pp(act[-1]['roic_incl'] - X['wacc'])}({act[-1]['q']}) — 양수면 투하자본을 늘릴수록 가치가 쌓인다.")
    return out
