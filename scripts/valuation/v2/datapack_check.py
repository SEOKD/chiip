"""데이터 묶음 검사기 — 원자료(raw 스냅숏)와 밸류에이션 입력이 같은지 대조한다 (마스터 지시 2026-10-29 "CBRS 리포트의 밸류에이션 과정과
easyconomics로부터 호출한 로우 데이터가 변함 없는지 전 과정을 다시 점검").

2026-10-29 CBRS 점검에서 나온 오류를 규칙으로 만든 것: 가이던스 누락, 어닝콜 톤 오기(레이더는 상향인데 flat), TTM 영업이익 연환산 근사,
투하자본 PBR 역산, 동종사 2곳·TTM 값을 '선행'으로 표기, 희석 주식 출처 없음, 매출(코어)과 이익률(GAAP/비GAAP) 기준 혼재.

각 검사는 통과(1)·경고(0.5)·실패(0). 점수 = 합 ÷ 검사 수 × 10. v2_to_report가 리포트 '데이터 검증' 표로 싣는다.
사용: py scripts/valuation/v2/datapack_check.py <entity_id>
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import multiples  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]


def _near(a, b, tol):
    return a is not None and b is not None and abs(a - b) <= tol * max(abs(b), 1e-9)


def derived_tone(call):
    """실적 변화 레이더 → 톤. 가이던스 상향 또는 톤 +0.5 이상 = up, 가이던스 하향 또는 톤 −0.5 이하 = down"""
    gd, dt = call.get("guidance_direction"), call.get("tone_delta")
    if gd in ("raise",) or (dt is not None and dt >= 0.5):
        return "up"
    if gd in ("cut", "lower") or (dt is not None and dt <= -0.5):
        return "down"
    return "flat" if (gd or dt is not None) else None


FX_PER_USD = {"KRW": (1000, 1800), "JPY": (100, 200), "NOK": (8, 13), "TWD": (25, 40), "EUR": (0.7, 1.2), "GBP": (0.6, 1.0), "CNY": (6, 8.5), "HKD": (7.0, 8.2)}   # 달러당 환율 허용 범위 — 자릿수 오류만 잡는 넓은 띠


def check(p):
    raw, pf, fin, cons = p.get("raw") or {}, p.get("profile") or {}, p.get("financials") or {}, p.get("consensus") or {}
    ez, q = raw.get("fiscal_profile") or raw.get("easyconomics_profile") or {}, raw.get("quarters_gaap") or {}   # 2026-10-30 원천 = Fiscal.ai(ADR-012), 옛 묶음은 easyconomics
    bs = next((v for k, v in sorted(raw.items()) if k.startswith("balance") and isinstance(v, dict)), {})   # balance_<날짜> 또는 balance
    out = []

    def add(name, status, detail):
        out.append({"name": name, "status": status, "detail": detail})

    add("원자료 스냅숏", "통과" if raw.get("retrieved_at") else "실패", f"조회 시각 {raw.get('retrieved_at', '없음')}")
    cover = raw.get("shares_cover_implied")
    add("시가총액 대조", "통과" if _near((pf.get("price") or 0) * (cover or 0), ez.get("market_cap"), 0.01) else "실패",
        f"가격 {pf.get('price')} × 표지 주식 {cover} = {(pf.get('price') or 0) * (cover or 0):.2f} vs 원자료 개요 {ez.get('market_cap')}")
    add("가격 일치", "통과" if _near(pf.get("price"), ez.get("price"), 0.001) else "실패", f"{pf.get('price')} vs {ez.get('price')}")
    # 밸류에이션이 쓰는 기본 주식 수 그대로 시가총액을 잰다(ADR-041 — 위 대조는 원자료 시총 ÷ 가격으로 만든 표지 주식이라 늘 통과했다. IES 분할 뒤 주식 이중 집계를 못 잡았다)
    if pf.get("shares_basic") and ez.get("market_cap") and pf.get("price"):
        gap = pf["price"] * pf["shares_basic"] / ez["market_cap"] - 1
        why = pf.get("share_class_note") or (p.get("dilution") or {}).get("share_class_note")
        add("기본 주식 × 가격 = 원자료 시총", "통과" if abs(gap) <= 0.03 else ("경고" if why else "실패"),
            f"{pf['price']} × {pf['shares_basic']} = {pf['price'] * pf['shares_basic']:.3f} vs {ez['market_cap']}({gap:+.1%})" + (f" — {why}" if why else ""))
    nd_ok = _near(pf.get("cash"), ez.get("total_cash"), 0.01) and _near(pf.get("debt"), ez.get("total_debt"), 0.01)
    detail = f"현금 {pf.get('cash')} vs {ez.get('total_cash')} · 차입(리스 포함) {pf.get('debt')} vs {ez.get('total_debt')}"
    # 개요(Fiscal.ai·옛 easyconomics) 재무상태표가 지난 분기 값이면 더 최신 1차 재무상태표(10-Q·8-K, raw.balance_<날짜>)와 맞는지 본다(2026-10-29 PWR: 8월 채권 발행 반영)
    bs_key = next((k for k in sorted(raw) if k.startswith("balance_") and isinstance(raw[k], dict)), None)
    if not nd_ok and bs_key and ez.get("balance_date") and bs_key[8:].replace("_", "-") > ez["balance_date"]:
        b = raw[bs_key]
        b_cash = b.get("cash", 0) + b.get("st_investments", 0)
        b_debt = b.get("debt_current", 0) + b.get("debt_lt", 0) + b.get("lease_current", 0) + b.get("lease_lt", 0)
        nd_ok = _near(pf.get("cash"), b_cash, 0.01) and _near(pf.get("debt"), b_debt, 0.01)
        detail = f"현금 {pf.get('cash')} vs 재무상태표({bs_key[8:]}) {b_cash:.4f} · 차입 {pf.get('debt')} vs {b_debt:.4f} — 개요({ez['balance_date']})보다 최신 1차 자료"
    add("현금·차입 대조", "통과" if nd_ok else "실패", detail)
    rev4, op4 = q.get("rev") or {}, q.get("op_income") or {}
    add("TTM 매출 = 4분기 합", "통과" if len(rev4) == 4 and _near(fin.get("rev_ttm"), sum(rev4.values()), 0.005) else "실패",
        f"{fin.get('rev_ttm')} vs {sum(rev4.values()):.4f}({len(rev4)}분기)")
    add("TTM 영업이익 = 4분기 합", "통과" if len(op4) == 4 and _near(fin.get("ebit_ttm"), sum(op4.values()), 0.005) else "실패",
        f"{fin.get('ebit_ttm')} vs {sum(op4.values()):.4f}")
    # 같은 datapack에 함께 넣은 분기 원자료(quarters_gaap)는 비GAAP일 때가 있다 — 공시 분기 이력(quarters_hist, Fiscal 표준화 GAAP)과도 맞춘다(ADR-041: SANM +57%, BLOOM +39%)
    qh = [r for r in ((p.get("quarters_hist") or {}).get("q") or []) if r.get("rev")][-4:]
    unit = 1e9 if p.get("unit", "B$") == "B$" else None
    if len(qh) == 4 and unit and all(r.get("op") is not None for r in qh):
        r4, o4 = sum(r["rev"] for r in qh) / unit, sum(r["op"] for r in qh) / unit
        ok = _near(fin.get("rev_ttm"), r4, 0.02) and _near(fin.get("ebit_ttm"), o4, 0.05)
        add("TTM = 공시 분기 이력(GAAP)", "통과" if ok else "실패", f"매출 {fin.get('rev_ttm')} vs {r4:.4f} · 영업이익 {fin.get('ebit_ttm')} vs {o4:.4f}(비GAAP을 GAAP 칸에 넣지 않는다)")
    if bs:
        ic = bs.get("equity", 0) + bs.get("debt_current", 0) + bs.get("debt_lt", 0) + bs.get("lease_current", 0) + bs.get("lease_lt", 0) - bs.get("cash", 0) - bs.get("st_investments", 0) + bs.get("customer_deposits", 0)
        add("투하자본 = 재무상태표", "통과" if _near(fin.get("invested_capital"), ic, 0.02) else "실패", f"{fin.get('invested_capital')} vs 자기자본+차입+리스−현금 {ic:.3f}")
    else:
        add("투하자본 = 재무상태표", "실패", "재무상태표 원자료 없음")
    est = raw.get("estimates_sales_m") or {}
    fy = {}
    for k, v in est.items():
        fy.setdefault(k[:4], 0.0)
        fy[k[:4]] += v / 1000
    bad = [y for y in fy if f"FY{y}" in (cons.get("rev") or {}) and not _near(cons["rev"][f"FY{y}"], fy[y], 0.005)]
    add("연간 컨센서스 = 분기 합", "통과" if fy and not bad else "실패", " · ".join(f"FY{y} {cons.get('rev', {}).get(f'FY{y}')} vs {v:.4f}" for y, v in sorted(fy.items())))
    gd = p.get("guidance") or {}
    add("회사 가이던스 반영", "통과" if gd.get("rev_fy0") and gd.get("source") else ("경고" if not gd.get("rev_fy0") else "실패"),
        gd.get("source", "가이던스 없음 — 회사가 내지 않으면 해당 없음(경고)")[:80])   # 가이던스를 내지 않는 회사(SK하이닉스 등)를 실패로 세던 잡음(ADR-041)
    # 컨센서스 깊이(ADR-041) — 애널리스트 3명 미만·다음 해 범위 없음·범위 밖 평균이면 시나리오 확률이 규칙 기본값으로 떨어진다
    ks = sorted(cons.get("rev") or {})
    nk = ks[1] if len(ks) > 1 else None
    lo, hi, mean = (cons.get("rev_low") or {}).get(nk), (cons.get("rev_high") or {}).get(nk), (cons.get("rev") or {}).get(nk)
    deep = (cons.get("n_analysts") or 0) >= 3 and lo is not None and hi is not None and lo <= (mean or lo) <= hi
    add("컨센서스 깊이(3명 이상·다음 해 범위)", "통과" if deep else "경고", f"애널리스트 {cons.get('n_analysts')}명 · {nk} 범위 {lo}~{hi}, 평균 {mean}")
    dl = p.get("dilution") or {}
    sec_pot = next((v for k, v in sorted((raw.get("sec") or {}).items()) if k.startswith("antidilutive")), None)   # antidilutive_<날짜>
    pot = dl.get("potential_total") if dl.get("potential_total") is not None else sum(dl.get(k) or 0 for k in ("options", "rsu", "warrants", "converts_shares"))
    same_day = dl.get("date") and dl.get("date") == pf.get("shares_date")
    st = "통과" if dl.get("source") and same_day and (sec_pot is None or _near(pot, sec_pot, 0.01)) else ("경고" if dl.get("source") else "실패")
    add("희석 주식(출처·같은 날짜)", st, f"잠재 주식 {pot} vs SEC {sec_pot} · 기본 주식 날짜 {pf.get('shares_date')} / 희석 날짜 {dl.get('date')}")
    call = p.get("call") or {}
    want = derived_tone(call)
    tone = call.get("tone") or want
    add("어닝콜 톤 = 실적 레이더", "통과" if want and tone == want else ("경고" if not want else "실패"),
        f"사용 {tone} · 레이더 기준 {want}(톤 변화 {call.get('tone_delta')}, 가이던스 {call.get('guidance_direction')})")
    peers = p.get("peers") or []
    basis = p.get("peers_basis")
    u = p.get("unit", "B$")
    if u != "B$":   # unit_usd = 그 단위 1개의 달러 값(BKRW = 10억 원 ≈ $0.7M). LOTTEEM이 원당 달러(0.000694)를 적어 10⁹배 작았다(ADR-042)
        ref = FX_PER_USD.get(u[1:])
        uu = float(p.get("unit_usd") or 0)
        fx = 1e9 / uu if uu > 0 else None
        ok_u = bool(ref and fx and ref[0] <= fx <= ref[1])
        add("통화 단위(unit_usd = 단위 1개의 달러 값)", "통과" if ok_u else "실패",
            f"{u} unit_usd {uu:g} → 환율 {fx:,.1f}/$" + ("" if ok_u else f" — 허용 {ref[0]:g}~{ref[1]:g}(1e9 ÷ 달러당 환율로 적는다)" if ref else " — 허용 범위 표(FX_PER_USD)에 통화 추가") if fx else f"{u} unit_usd 없음")
    tgt = (pf.get("price") or 0) * (pf.get("shares_basic") or 0)
    sized = [x for x in peers if (x.get("mcap") or 0) > 0]
    near = sum(1 for x in sized if 0.2 <= x["mcap"] / tgt <= 5) if tgt else 0
    if sized and tgt and p.get("unit", "B$") == "B$":   # 동종 규모(ADR-042 — 12/66곳 동종 중앙 시총이 대상의 5배 초과, 판단 조정으로 메웠다)
        add("동종 규모(절반 이상 시총 0.2~5배)", "통과" if near * 2 >= len(sized) else "경고", f"{near}/{len(sized)}곳이 대상 시총 {tgt:.2f}의 0.2~5배 — 규모가 다르면 판단 조정이 아니라 동종을 바꾼다")
    ok_p = len(peers) >= 4 and basis in ("ttm", "ntm") and p.get("peers_source")
    add("동종사 4곳 이상·기준 표기", "통과" if ok_p else "실패", f"{len(peers)}곳 · 기준 {basis or '미표기'}")
    mult, why = multiples.choose_basis(p)   # Fwd 1Y 이익 멀티플이 기준(마스터 지시 2026-10-30)
    add("기준 멀티플 Fwd 1Y(이익 지표)", "통과" if mult != "ev_sales" else "경고", f"{multiples.BASES[mult]} · {why}")
    mb, rb = cons.get("margin_basis"), cons.get("rev_basis")
    sbc_ok = mb != "non_gaap" or p.get("sbc_pct_rev") is not None
    add("매출·이익률 기준 명시(SBC 처리)", "통과" if mb and rb and sbc_ok else "실패",
        f"매출 {rb or '미표기'} · 이익률 {mb or '미표기'}" + (f" · 비GAAP → SBC {p.get('sbc_pct_rev'):.0%} 차감" if mb == "non_gaap" and p.get("sbc_pct_rev") is not None else ""))
    pts = {"통과": 1.0, "경고": 0.5, "실패": 0.0}
    score = round(sum(pts[c["status"]] for c in out) / len(out) * 10, 1)
    # 자산 구성과 ROIC 재료(ADR-021, 마스터 지시 2026-11-13) — 표시만 하고 점수에는 넣지 않는다(옛 datapack 관문을 막지 않게).
    # 없으면 py scripts/tenbagger/asset_pack.py <id> --write 뒤 10-K 주석으로 항목·내용연수를 채운다
    a = p.get("assets")
    if not a:
        out.append({"name": "자산 구성(assets)", "status": "경고", "detail": "없음 — '자산 구성과 ROIC' 절이 빠진다. py scripts/tenbagger/asset_pack.py <id> --write"})
    else:
        need = [k for k, ok in (("roic", (a.get("roic") or {}).get("capital")), ("quarters", len(a.get("quarters") or []) >= 5), ("ppe", a.get("ppe"))) if not ok]
        out.append({"name": "자산 구성(assets)", "status": "경고" if need else "통과",
                    "detail": (f"빈 칸: {', '.join(need)}" if need else "ROIC·분기 감가·유형자산 있음") + (f" · 미공시 {len(a.get('missing') or [])}건" if a.get("missing") else "")})
    return {"score": score, "checks": out}


def load(entity):
    return json.loads((ROOT / "knowledge" / "models" / "companies" / entity / "datapack.json").read_text(encoding="utf-8"))


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    r = check(load(argv[0]))
    for c in r["checks"]:
        print(f"[{c['status']}] {c['name']} — {c['detail']}")
    print(f"데이터 검증 {r['score']}/10")
    return 0 if r["score"] >= 10 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
