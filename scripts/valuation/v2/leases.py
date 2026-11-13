"""리스 일관 처리 — 방식 A(리스 자본화, ADR-026, 마스터 지시 2026-11-13 "고쳐라")

v2 엔진은 투하자본(ic0·s2c)과 순차입에 리스를 넣으면서 영업이익(마진)은 임차료를 뺀 GAAP 값을 썼다 — 리스 비용을 두 번 뺀 셈이라
리스가 큰 회사(LTH 리스 부채 $2.8B)는 ROIC가 WACC 아래로 눌리고 성장이 가치를 깎는 것으로 나왔다.
방식 A(Mauboussin·Callahan 2022 ROIC, 자산 구성과 ROIC 절 asset_roic_view와 같은 NOPAT 정의):
  ① 리스 부채 L은 순차입에 넣는다(이미 들어 있으면 그대로) — 지분가치 = EV − 순차입(리스 포함), WACC 부채비중에도 들어간다
  ② 투하자본에는 리스 사용권자산이 들어 있다(datapack 투하자본 = 자기자본 + 차입 + 리스 − 현금, datapack_check 규칙)
  ③ 마진에 리스 내재 이자 L × r ÷ 기준 매출을 더한다(임차료 속 이자 몫을 영업비용에서 빼서 조달비용으로 옮긴다) — 매출에 비례해 자란다고 본다
  ④ r = 공시 가중평균 리스 할인율(datapack leases.rate), 없으면 엔진 세전 차입금리(무위험 + 스프레드). 공시 r이 있으면 WACC의 세전 차입금리도
     일반 차입과 리스를 잔액 가중한 값으로 맞춘다(이자를 되더한 만큼 같은 금리로 할인)
리스 자료가 없거나 0이면 아무것도 바꾸지 않는다(리스가 작은 회사는 영향 없음).
datapack 입력(선택): "leases": {"liab": 2.8084, "rate": 0.0928, "in_debt": false, "source": "10-K 2025 리스 주석"} — 없으면 raw.balance_* 의 lease_current + lease_lt
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEBT_KEYS = ("debt_current", "debt_lt", "loan_current", "loan_lt")
LEASE_KEYS = ("lease_current", "lease_lt", "lease")
ENABLED = True   # 비교·시험용 스위치(False면 방식 A 이전 동작)


def _balance(raw):
    """가장 최근 재무상태표 원자료(raw.balance_YYYY_MM_DD 중 마지막)"""
    keys = sorted(k for k in (raw or {}) if k.startswith("balance") and isinstance(raw[k], dict))
    return raw[keys[-1]] if keys else {}


def info(datapack):
    """{liab, rate(없으면 None), in_debt, nonlease_debt, source} 또는 None"""
    if not datapack:
        return None
    pf = datapack.get("profile") or {}
    ov = datapack.get("leases")
    if ov is False:
        return None
    bs = _balance(datapack.get("raw"))
    liab = (ov or {}).get("liab")
    src = (ov or {}).get("source")
    if liab is None:
        liab = sum(float(bs.get(k) or 0) for k in LEASE_KEYS)
        src = src or "재무상태표 리스 부채(raw.balance)"
    if not liab or liab <= 0:
        return None
    debt = float(pf.get("debt") or 0)
    if ov and ov.get("in_debt") is not None:
        in_debt = bool(ov["in_debt"])
    elif any(k in bs for k in DEBT_KEYS):
        nonlease = sum(float(bs.get(k) or 0) for k in DEBT_KEYS)
        in_debt = abs(debt - (nonlease + liab)) <= abs(debt - nonlease)   # 차입 칸이 리스를 포함한 값에 더 가까운가
    else:
        in_debt = debt >= liab   # 규칙(build_drivers: profile.debt는 리스 포함) — 차입이 리스보다 작으면 빠진 것으로 본다
    return {"liab": float(liab), "rate": (ov or {}).get("rate"), "in_debt": in_debt,
            "nonlease_debt": max(0.0, debt - liab) if in_debt else debt, "source": src}


def load_datapack(entity):
    p = ROOT / "knowledge" / "models" / "companies" / entity / "datapack.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def apply(co, datapack, rf=None, spread=0.015):
    """drivers(co)에 방식 A를 적용한다(제자리 수정, 두 번 적용하지 않음). 반환: co['lease'] 또는 None"""
    if not ENABLED or co.get("lease") or co.get("leases") is False:
        return co.get("lease")
    li = info(datapack)
    if not li or not co.get("rev0"):
        return None
    kd_engine = (rf if rf is not None else 0.045) + spread
    rate = li["rate"] if li["rate"] is not None else kd_engine
    m = co.setdefault("market", {})
    added = 0.0
    if not li["in_debt"]:
        added = li["liab"]
        m["net_debt"] = round(float(m.get("net_debt") or 0) + added, 6)
    interest = li["liab"] * rate
    lease = {**li, "rate_used": rate, "rate_src": "공시 가중평균 할인율" if li["rate"] is not None else f"엔진 세전 차입금리(무위험 + {spread:.1%})",
             "interest": interest, "margin_add": interest / co["rev0"], "net_debt_added": added}
    if li["rate"] is not None and co.get("pretax_kd") is None:
        d = li["nonlease_debt"]
        co["pretax_kd"] = (d * kd_engine + li["liab"] * rate) / (d + li["liab"])
        lease["pretax_kd"] = co["pretax_kd"]
    co["lease"] = lease
    return lease


def line(lease, unit="B$"):
    """리포트·카드용 한 줄"""
    if not lease:
        return None
    return (f"리스 자본화(방식 A): 리스 부채 {lease['liab']:.2f}{unit}를 순차입에 포함"
            + (f"(+{lease['net_debt_added']:.2f}{unit})" if lease["net_debt_added"] else "")
            + f", 리스 내재 이자 {lease['interest']:.3f}{unit}(금리 {lease['rate_used']:.2%}, {lease['rate_src']}) = 매출의 {lease['margin_add']:.1%}를 영업 마진에 되더함")
