"""SPAC 비대칭 점수 3단계 (마스터 지시 2026-11-04 "3단계 진행", 설계 knowledge/methods/spac_discovery_design.md 3·4절)
— 2026-11-15 개선(ADR-044, 조사 D 근거: Klausner·Ohlrogge·Ruan 2022, Gahng·Ritter·Zhang 2023 RFS, Blankespoor 외 2022, Leal 외 2026, Ritter 표 12·15c·18d)

입력은 spac_report.py와 같은 datapack "spac"(knowledge/models/companies/<id>/datapack.json, 금액 B$·주식 백만 주)과 장부(spac_watch 단계·spac_theme 테마).
요인을 0~10으로 재고 단계별 가중으로 합친다. 연구 후보 지표이지 매수 권유가 아니다(목표주가·등급 없음).
  ① 바닥    환매 전(주총 전)만 — 다음 환매 시점(next_redemption.date 또는 deadline)까지의 신탁가 대비 하방 d = 신탁가×(1+신탁 금리×t)/주가 − 1.
            d ≥ 0 → 10, d ≤ −30% → 0. 환매 시점이 1년 넘게 멀면 5 상한. 연 수익 d/t ≥ 국채 − 1%p이고 1년 안이면 '바닥 인정'.
            환매 시점을 모르면 예전처럼 프리미엄 p = 주가/주당 신탁가 − 1로(p ≤ 0 → 10, p ≥ 0.30 → 0)
  ② 희석    KOR 주당 순현금(Klausner·Ohlrogge 정의) = (남은 신탁 − 수수료 − 워런트 시가) / (환매 뒤 공개주 + 스폰서주) — 피인수 주주 주식은 분모에 넣지 않는다.
            환매 전 지분표면 환매율을 같은 분기 중앙값(Ritter 표 12)으로 가정한다. 합병 뒤 가치와 기울기 약 1(KOR 1.04~1.16) → 점수 = NCPS($), 0~10
  ③ 질      5 + 기대 1년 시장 조정 수익 차(10%p = 1점): 환매율 − 분기 중앙값(β −0.35, GRZ −0.49 축소), 스폰서 상급(KOR 차 55%p의 절반)·업종 전문(GRZ +0.139의 절반)·
            스폰서 이전 합병 성과(절반 축소), 주관사 순위(GRZ 점당 +0.05), PIPE 질(보통주 $10 이상·비계열 +0.5점, 구조화·없음 −0.5점)
  ④ 시간    상장 → 계약(종결 뒤는 종결) 개월 m: 10×(1 − ln(m/12)/ln 3)(12개월 10, 36개월 0), 연장 표결 3회면 0. 늦은 거래(18개월 초과·연장 1회 이상)는
            보호 조항(FPA·make-whole·희석 방지·스폰서 언아웃·스폰서 보호예수)마다 +1, 최대 +3(Leal 외 2026). GRZ 표 7: log-개월당 1년 −0.54
  ⑤ 펀더멘털 LTM 매출·흑자(GRZ 표 6, 1년 시장 조정: $1억 이상·흑자 −16.1% … 미만·적자 −43.5%, 평균 −30.6% 대비 차), 매출 $1천만 미만은 Ritter IPO 비교(−52.3%) 절반 더 감점,
            EV $5억 미만 −0.5점(약한 사전값)
  ⑥ 가치    EV = 주가 × 전체 주식 − 합병 뒤 순현금. 선행 매출 = LTM × (1 + λ·전망 성장), λ 0.35(Blankespoor 외 2022: 실현 41% / 전망 116%) — 2024-07-01 뒤 전망은 λ를 따로 둔다.
            LTM이 없으면 예전처럼 전망 첫 해 × (1 − projection_haircut). 배수 비율 r = (EV/선행 매출) / 동종 EV/매출 → 5 − 5·log2(r).
            EV/LTM 매출 40배 초과면 2 상한, 20~40배는 4 상한(Ritter 표 18d). 전망이 없으면 공정성 의견 중간값(5 상한)
  ⑦ 사업 엣지 datapack spac.edge(0~10, Chiip 렌즈). 없으면 테마 일치 5, 불일치 3 — Chiip 표본에서 테마 일치가 낫지 않아 가중을 낮췄다
  ⑧ 오버행  overhang_days 안에 풀리는 보호예수 주식 / 유통 주식 → 10·(1 − min(1, 비율/3))
  ⑨ 관심    가중 0 — 위험 표시만(합병 전 프리미엄이 클수록 뒤가 나쁘다, GRZ −0.184; 낮은 유통은 양방향 변동성)
킬 조건: 계약 해지·최소 현금 미달·재매각 대량 등록(flags), 환매 95% 이상인데 외부 자금(PIPE·FPA·기타) 없음, 주총(환매 마감) 뒤 신탁가 아래(Jenkinson·Sousa 2011),
         매출 $1천만 미만(0 초과)인데 EV/매출 40배 초과, 구조화 자금(전환·ELOC) 한도가 유통의 50% 초과
빈칸 상한: 가중 합의 40% 넘게 빈칸이면 5.9 상한(빈칸을 중립 5로 채워 부풀리지 않는다 — 발굴 엔진 ADR-043과 같은 원칙)
사용: py scripts/tenbagger/spac_score.py <회사 id> [--price <현재가>]     → 한 종목
      py scripts/tenbagger/spac_score.py --all                            → datapack에 spac이 있는 모든 종목 → knowledge/models/spac/scores.csv, candidates.json
      py scripts/tenbagger/spac_score.py --needs                          → 테마가 맞은 S2+ 스팩 중 datapack이 없는 것(모델이 서류로 채울 목록)
      py scripts/tenbagger/spac_score.py --fill-ipo                       → datapack 스팩의 IPO 날짜(EDGAR 424B4)를 knowledge/models/spac/ipo_dates.json에(네트워크)
"""
import csv
import json
import math
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
COMP = ROOT / "knowledge" / "models" / "companies"
DIR = ROOT / "knowledge" / "models" / "spac"
IPO_DATES = DIR / "ipo_dates.json"
PRE_STAGES = ("S2", "S3", "S4")


def cfg():
    return yaml.safe_load((ROOT / "config" / "spac.yaml").read_text(encoding="utf-8"))["score"]


def lin(x, lo, hi):
    """x가 lo면 10, hi면 0(선형, 밖은 자름)"""
    return max(0.0, min(10.0, 10 * (hi - x) / (hi - lo)))


def clip(x):
    return max(0.0, min(10.0, x))


def net_cash(s):
    c = s.get("cash") or {}
    return (c.get("trust_left") or 0) + (c.get("pipe") or 0) + (c.get("other") or 0) - (c.get("fees") or 0) + (c.get("target_cash") or 0) - (c.get("debt") or 0)


def total_shares(s, price=None):
    n = sum((s.get("shares") or {}).values())
    for w in s.get("warrants") or []:   # 행사가 아래 주가면 행사될 것으로 본다(희석 보수적)
        if price is None or price >= (w.get("strike") or 1e9):
            n += w.get("count") or 0
    return n


def _d(v):
    try:
        return date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


def quarter(d):
    return f"{d.year}Q{(d.month - 1) // 3 + 1}" if d else None


def red_ref(c, d):
    """같은 분기 환매율 중앙값(Ritter 표 12) — 없는 분기는 가장 가까운 앞 분기, 그것도 없으면 기본값"""
    tab = c.get("redemption_ref_by_q") or {}
    qd = quarter(d)
    if qd in tab:
        return tab[qd], qd
    prev = sorted(k for k in tab if qd and k <= qd)
    return (tab[prev[-1]], prev[-1]) if prev else (c["ncps_redemption_ref"], "기본")


def kor_ncps(s, c, red=None, ref=None):
    """KOR 주당 순현금 → (값, 가정 환매율 또는 None, 메모). 공개·스폰서 행을 지분표 이름으로 가린다. 못 가리면 None"""
    pub = spon = 0.0
    pre = found = False
    for k, v in (s.get("shares") or {}).items():
        if re.search(r"공개|public", k, re.I):
            pub += v or 0
            found = True
            pre = pre or bool(re.search(r"환매 전|pre-?redemption|before redemption", k, re.I))
        elif re.search(r"스폰서|초기 주주|sponsor|founder", k, re.I):
            spon += v or 0
    if not found or not spon:
        return None, None, "지분표에서 공개주·스폰서주를 가리지 못함"
    cash = (s.get("cash") or {}).get("trust_left") or 0
    assumed = None
    if pre:
        r = red if red is not None else (ref if ref is not None else c["ncps_redemption_ref"])
        assumed = None if red is not None else r
        pub, cash = pub * (1 - r), cash * (1 - r)
    wl = sum((w.get("count") or 0) * (w.get("price") or 0) for w in s.get("warrants") or []) / 1000
    no_wp = any(w.get("price") is None for w in s.get("warrants") or [])
    v = (cash - ((s.get("cash") or {}).get("fees") or 0) - wl) * 1000 / (pub + spon)
    return v, assumed, ("워런트 시가 미확인 — 부채 0으로 계산(낙관)" if no_wp else "")


def months_between(a, b):
    return max(0.0, (b - a).days / 30.4375)


def factors(s, stage, theme_ok, c, today=None, ctx=None):
    today = today or date.today()
    ctx = ctx or {}
    price = s.get("price")
    tps = s.get("trust_per_share") or 10.0
    red = (s.get("redemption") or {}).get("pct")
    redeemed = red is not None or "가결" in str(s.get("status") or "")
    pre = stage in PRE_STAGES and not redeemed   # 환매가 끝나면(주총 가결) 신탁가 바닥이 사라진다
    out, notes, risks = {}, [], []
    prem = price / tps - 1 if price and tps else None
    asof = _d(s.get("as_of")) or today

    # ① 바닥 — 다음 환매 시점까지
    if pre and price:
        ev_date = _d((s.get("next_redemption") or {}).get("date")) or _d(s.get("deadline"))
        if ev_date and ev_date > asof:
            t = max((ev_date - asof).days / 365.25, 1 / 365.25)
            tps_ev = ((s.get("next_redemption") or {}).get("tps") or tps * (1 + c["trust_yield"] * t))
            dn = tps_ev / price - 1
            out["floor"] = lin(-dn, 0.0, 0.30)
            if t > c["floor_far_years"]:
                out["floor"] = min(out["floor"], c["floor_far_cap"])
                notes.append(f"다음 환매 시점 {ev_date}까지 {t:.1f}년 — 바닥이 멀다(5 상한)")
            elif dn / t >= c["tbill"] - 0.01:
                notes.append(f"바닥 인정(환매 시점 {ev_date}, 신탁가 대비 {dn:+.1%} · 연 {dn / t:+.1%} ≥ 국채 {c['tbill']:.2%} − 1%p)")
        elif prem is not None:
            out["floor"] = lin(prem, 0.0, 0.30)
            if prem <= c["floor_premium_max"]:
                notes.append(f"바닥 인정(프리미엄 {prem:+.1%} — 주총 전 환매권, 환매 시점 미확인)")

    # ② 희석 — KOR 주당 순현금
    ref, refq = red_ref(c, _d(ctx.get("close_date")) or asof)
    ncps, assumed, memo = kor_ncps(s, c, red, ref)
    n = total_shares(s, price)
    nc = net_cash(s)
    ncps_post = nc * 1000 / n if n else None
    if ncps is not None and ncps > c["ncps_max_sane"]:
        notes.append(f"KOR 주당 순현금 ${ncps:.2f} — 단위 확인 필요(버림)")
        ncps = None
    if ncps_post is not None and ncps_post > c["ncps_max_sane"]:
        notes.append(f"합병 뒤 주당 순현금 ${ncps_post:.2f} — 단위 확인 필요(버림)")
        ncps_post = None
    if ncps is not None:
        out["dilution"] = clip(ncps)
        notes.append(f"KOR 주당 순현금 ${ncps:.2f}" + (f"(환매 {assumed:.0%} 가정 — {refq} 중앙값)" if assumed is not None else "") + (f" · {memo}" if memo else ""))
    elif ncps_post is not None:
        out["dilution"] = clip(ncps_post)
        notes.append(f"주당 순현금(합병 뒤 전체 주식 기준) ${ncps_post:.2f} — {memo}")

    # ③ 질
    pts = c["pts_per_return"]
    q, qin = 0.0, []
    if red is not None:
        q += -c["redemption_beta"] * (red - ref) * pts
        qin.append(f"환매 {red:.0%} vs {refq} 중앙값 {ref:.0%}")
    sp = s.get("sponsor") or {}
    if sp.get("hq") is not None:
        q += (c["sponsor_hq_gap"] / 2) * (1 if sp["hq"] else -1) * pts
        qin.append("상급 스폰서" if sp["hq"] else "비상급 스폰서")
    if sp.get("expert"):
        q += c["sponsor_expert"] * pts
        qin.append("업종 전문 스폰서")
    if sp.get("prior_median_12m") is not None:
        q += max(-2.0, min(2.0, c["sponsor_prior_shrink"] * (sp["prior_median_12m"] - c["sponsor_prior_base"]) * pts))
        qin.append(f"스폰서 이전 합병 12개월 중앙값 {sp['prior_median_12m']:+.0%}")
    if s.get("uw_rank") is not None:
        q += c["uw_beta"] * (s["uw_rank"] - c["uw_center"]) * pts
        qin.append(f"주관사 순위 {s['uw_rank']}")
        if s["uw_rank"] < 6:
            risks.append(f"하위 주관사(순위 {s['uw_rank']} < 6 — Ritter 표 11a IPO 3년 시장 조정 −89.1%)")
    pt = s.get("pipe_terms") or {}
    if pt.get("type"):
        good = pt["type"] == "common" and (pt.get("price") or 0) >= 10 and not pt.get("affiliated")
        bad = pt["type"] in ("convert", "preferred", "eloc", "none")
        q += c["pipe_quality_pts"] * (1 if good else (-1 if bad else 0))
        qin.append(f"PIPE {pt['type']}")
    if qin:
        out["quality"] = clip(5 + q)
        notes.append("질: " + ", ".join(qin))

    # ④ 시간 압박
    ipo = _d(s.get("ipo_date")) or _d(ctx.get("ipo_date"))
    ext = s.get("extensions") if s.get("extensions") is not None else ctx.get("extensions")
    ext = int(ext) if str(ext or "").strip().isdigit() else None
    if ipo:
        end = _d(ctx.get("close_date")) if stage in ("S5", "S6") and ctx.get("close_date") else max(asof, _d(s.get("da_date")) or _d(ctx.get("da_date")) or asof)
        m = max(1.0, months_between(ipo, end))
        tsc = lin(math.log(max(m, c["time_full_months"]) / c["time_full_months"]), 0.0, math.log(c["time_zero_months"] / c["time_full_months"]))
        if ext is not None:
            tsc = min(tsc, 10 * (1 - min(ext, c["time_ext_zero"]) / c["time_ext_zero"]))
        late = m > c["late_months"] or (ext or 0) >= 1
        ncl = len([k for k in s.get("clauses") or [] if k])
        if late and ncl:
            tsc = clip(tsc + min(c["late_clause_cap"], ncl * c["late_clause_pts"]))
        out["time"] = tsc
        notes.append(f"상장 → {'종결' if stage in ('S5', 'S6') else '지금'} {m:.0f}개월" + (f"·연장 {ext}회" if ext is not None else "") +
                     f"(GRZ 1년 {c['time_beta'] * math.log(max(m, 1) / 12):+.0%} 상당)" + (f", 늦은 거래 보호 조항 {ncl}개" if late and ncl else ""))

    # ⑤ 펀더멘털
    ltm = s.get("ltm") or {}
    r0 = ltm.get("revenue")
    ev = price * n / 1000 - nc if price and n else None
    if r0 is not None:
        cells = c["fund_cells"]
        prof = ltm.get("profitable")
        if r0 >= 0.1:
            cell = cells["big_profit"] if prof else cells["big"]
        else:
            cell = cells["small"] if prof else cells["small_loss"]
        d = cell - c["fund_mean"] + (c["fund_prerev_extra"] if r0 < c["prerev_sales_b"] else 0)
        f = 5 + d * pts
        if ev is not None and ev < c["fund_small_ev_b"]:
            f += c["fund_small_ev_pts"]
        out["fundamentals"] = clip(f)
        notes.append(f"LTM 매출 ${r0 * 1000:.0f}M·{'흑자' if prof else ('적자' if prof is False else '손익 미확인')}(GRZ 표 6 칸 {cell:+.1%})")

    # ⑥ 가치
    proj = s.get("projections") or []
    p1 = proj[0].get("rev") if proj and proj[0].get("rev") else None
    regime = _d(s.get("da_date")) or _d(ctx.get("da_date")) or asof
    lam = c["proj_growth_shrink_post2024"] if regime and regime >= _d(c["proj_regime_date"]) else c["proj_growth_shrink"]
    rev = None
    if p1 and r0 and r0 > 0:
        rev = r0 * (1 + lam * (p1 / r0 - 1))
        how = f"LTM × (1 + {lam}·전망 성장 {p1 / r0 - 1:+.0%})"
    elif p1:
        rev = p1 * (1 - c["projection_haircut"])
        how = f"전망 첫 해 × {1 - c['projection_haircut']:.0%}(LTM 없음)"
    if ev is not None and rev and s.get("peer_ev_rev"):
        r = (ev / rev) / s["peer_ev_rev"]
        out["value"] = clip(5 - 5 * math.log2(max(r, 1e-6)))
        notes.append(f"EV/선행 매출 {ev / rev:.1f}배 vs 동종 {s['peer_ev_rev']:.1f}배 — 선행 매출 = {how}")
    elif price and (s.get("fairness") or {}).get("base") and n:
        fv = s["fairness"]["base"] * 1000 / n   # 공정성 의견 중간값(지분가치 B$)을 주당으로
        r = price / fv
        out["value"] = min(c["fairness_value_cap"], clip(5 - 5 * math.log2(max(r, 1e-6))))
        notes.append(f"공정성 의견 중간값 주당 ${fv:.2f} 대비 주가 {r:.2f}배(경영진 측 평가 — {c['fairness_value_cap']:.0f} 상한)")
    psr = ev / r0 if ev is not None and r0 and r0 > 0 else None
    if psr is not None and "value" in out:
        for lim, cap in c["psr_cap"]:
            if psr > lim:
                out["value"] = min(out["value"], cap)
                notes.append(f"EV/LTM 매출 {psr:.0f}배 > {lim} — 가치 {cap:.0f} 상한(Ritter 표 18d)")
                break
    if r0 == 0:
        risks.append("매출 전(LTM 0) — 가치 점수 없음, 펀더멘털 최저 칸")

    # ⑦ 사업 엣지
    out["edge"] = float(s.get("edge")) if s.get("edge") is not None else (5.0 if theme_ok else 3.0)

    # ⑧ 오버행
    flt = sum(v or 0 for k, v in (s.get("shares") or {}).items() if re.search(r"공개|public", k, re.I) and not re.search(r"환매 전", k)) + ((s.get("shares") or {}).get("PIPE") or 0)
    if not flt:
        flt = ((s.get("shares") or {}).get("공개 주주(환매 후)") or 0) + ((s.get("shares") or {}).get("PIPE") or 0)
    cut = (today + timedelta(days=c["overhang_days"])).isoformat()
    lock = sum(x.get("shares") or 0 for x in s.get("lockups") or [] if str(x.get("date", "9999")) <= cut)
    if flt:
        out["overhang"] = 10 * (1 - min(1.0, (lock / flt) / 3))
        if lock:
            notes.append(f"{c['overhang_days']}일 안 보호예수 해제 {lock:.0f}백만 주 = 유통의 {lock / flt:.1f}배")

    # ⑨ 관심 — 위험 표시만(가중 0)
    out["attention"] = 5.0 if red is None or prem is None else clip(5 + 10 * prem * (1 if red < 0.9 else -1))
    if prem is not None and prem > 0.10:
        risks.append(f"합병 전 프리미엄 {prem:+.0%} — 프리미엄이 클수록 뒤가 나쁘다(GRZ −0.184)")
    if red is not None and red >= 0.9:
        risks.append(f"환매 {red:.0%} — 유통이 작아 양방향 변동성(기대 수익 요인 아님)")

    # 킬 조건
    kills = []
    cs = s.get("cash") or {}
    if red is not None and red >= 0.95 and not ((cs.get("pipe") or 0) + (cs.get("other") or 0) + (cs.get("fpa") or 0)):
        kills.append("환매 95% 이상·외부 자금 없음")
    if stage == "S4" and redeemed and price and price < tps * (1 - c["vote_below_tol"]):
        kills.append(f"주총 뒤 신탁가 아래(주가 ${price:.2f} < 신탁 ${tps:.2f})")
    if r0 and 0 < r0 < c["prerev_sales_b"] and psr and psr > c["psr_kill"]:
        kills.append(f"매출 $10M 미만·EV/매출 {psr:.0f}배")
    st = s.get("structured_shares")
    if st and flt and st / flt > c["structured_kill"]:
        kills.append(f"구조화 자금 한도 = 유통의 {st / flt:.0%}")
    for k in s.get("flags") or []:
        if k in ("계약 해지", "재매각 대량 등록", "최소 현금 미달"):
            kills.append(k)
    return out, {"premium": None if prem is None else round(prem, 4), "ncps_kor": None if ncps is None else round(ncps, 2),
                 "net_cash_ps": None if ncps_post is None else round(ncps_post, 2), "ev_b": None if ev is None else round(ev, 3),
                 "total_shares_m": round(n, 1), "psr_ltm": None if psr is None else round(psr, 1)}, notes, kills, risks


def score(s, stage, theme_ok, c=None, today=None, ctx=None):
    c = c or cfg()
    f, nums, notes, kills, risks = factors(s, stage, theme_ok, c, today, ctx)
    redeemed = (s.get("redemption") or {}).get("pct") is not None or "가결" in str(s.get("status") or "")
    regime = "pre_vote" if stage in PRE_STAGES and not redeemed else "post_close"
    w_all = {k: v for k, v in c["weights"][regime].items() if v}
    w = {k: v for k, v in w_all.items() if k in f}
    tot = sum(w.values())
    val = round(sum(f[k] * v for k, v in w.items()) / tot, 1) if tot else None
    missing = [k for k in w_all if k not in f]
    miss_share = 1 - tot / sum(w_all.values()) if w_all else 0
    if val is not None and miss_share > c["missing_weight_max"]:
        val = min(val, c["missing_cap"])
        notes.append(f"빈칸 {', '.join(missing)}(가중 {miss_share:.0%}) — {c['missing_cap']} 상한")
    if kills:
        val = min(val or 0.0, c["kill_cap"])
    return {"score": val, "factors": {k: round(v, 1) for k, v in f.items()}, "missing": missing, "regime": regime,
            "numbers": nums, "notes": notes, "risks": risks, "kills": kills, "stage": stage, "base_rate": base_rate_line(c, stage),
            "candidate": bool(val is not None and val >= c["candidate_min"] and not kills and theme_ok)}


def base_rate_line(c, stage="S5"):
    """기저율 한 줄 — 종결 뒤는 Chiip 표본(knowledge/models/spac/base_rates.json headline, 생존 편향 보정)과 Ritter 표 15c, 주총 전은 스팩 기간 기저율도.
    base_rates.json이 없으면 config score.base_rate(옛 4단계 값)"""
    ext = c.get("external_base_rate") or {}
    p = DIR / "base_rates.json"
    h = {}
    if p.exists():
        try:
            h = json.loads(p.read_text(encoding="utf-8")).get("headline") or {}
        except (OSError, ValueError):
            h = {}
    if h.get("r24m_median") is not None:
        pct = lambda v: "미확인" if v is None else f"{v:+.0%}"   # noqa: E731
        sh = lambda v: "미확인" if v is None else f"{v:.0%}"     # noqa: E731
        line = (f"스팩 종결 뒤 기저율(Chiip 2021~2025 종결 {h['n']}건 + 시세 없는 파산·상장폐지 {h['n_fail']}건, 생존 편향 보정): 12개월 중앙값 {pct(h['r12m_median'])}, "
                f"24개월 {pct(h['r24m_median'])}($10 기준 {pct(h.get('r24m_median_10'))}), −50% 이하 {sh(h['lt_minus50_24m'])}, −90% 이하 {sh(h['lt_minus90_24m'])}, "
                f"24개월 안 3배 {sh(h['ge3x_24m'])}·10배 {sh(h['ge10x_24m'])}(꼬리 하한)")
    else:
        b = c.get("base_rate") or {}
        if not b:
            return None
        line = (f"스팩 종결 뒤 기저율(2021~2025 표본 {b['n']}건, 생존 편향으로 낙관 쪽): 24개월 수익 중앙값 {b['r24m_median']:+.0%}, "
                f"−50% 이하 {b['lt_minus50_24m']:.0%}, 2배 도달 {b['ge2x_24m']:.0%}, 3배 {b['ge3x_24m']:.0%}, 10배 {b['ge10x_24m']:.0%}")
    if ext.get("post_close"):
        line += f" · 외부: {ext['post_close']}"
    if stage in PRE_STAGES and ext.get("pre_vote"):
        line = f"주총 전: {ext['pre_vote']} · " + line
    return line


def ledger():
    reg, th = {}, {}
    for name, store in (("registry.csv", reg), ("themes.csv", th)):
        p = DIR / name
        if p.exists():
            with p.open(encoding="utf-8", newline="") as f:
                store.update({r["cik"]: r for r in csv.DictReader(f)})
    return reg, th


def transitions():
    p = DIR / "transitions.csv"
    if not p.exists():
        return {}
    out = {}
    with p.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            out.setdefault(r["cik"], []).append(r)
    return out


def ctx_of(d, r, tr=None, ipo=None):
    """장부·단계 이력·IPO 날짜 캐시에서 시간 요인 재료 — IPO일(424B4), 계약일(S2 전환), 종결일(S5), 연장 횟수"""
    tr = transitions() if tr is None else tr
    ipo = (json.loads(IPO_DATES.read_text(encoding="utf-8")) if IPO_DATES.exists() else {}) if ipo is None else ipo
    ciks = [x for x in [r.get("cik")] + [str(k) for k in d.get("ciks") or []] if x]
    rows = [t for k in ciks for t in tr.get(k, [])]
    first = lambda st: min((t["filed"] for t in rows if t["to"] == st and t.get("filed")), default=None)   # noqa: E731
    ipo_d = min([ipo[k] for k in ciks if ipo.get(k)] + ([first("S0")] if first("S0") else []), default=None)
    return {"ipo_date": ipo_d, "da_date": first("S2"), "close_date": first("S5") or (r.get("stage_date") if r.get("stage") == "S5" else None),
            "extensions": r.get("extensions")}


def spac_packs():
    for p in COMP.glob("*/datapack.json"):
        d = json.loads(p.read_text(encoding="utf-8"))
        if d.get("spac"):
            yield p.parent.name, d


def lookup(d, reg, th):
    """datapack → 장부 행(티커·이름으로 맞춘다)"""
    tk = {str(d.get("ticker") or "").upper(), str((d.get("spac") or {}).get("new_ticker") or "").upper()} - {""}
    for cik, r in reg.items():
        if tk & {x.upper() for x in (r.get("tickers") or "").split(",") if x} or (d.get("name") and d["name"].lower() in r["name"].lower()):
            return r, th.get(cik) or {}
    return {}, {}


def run_all(prices=None):
    c = cfg()
    reg, th = ledger()
    tr = transitions()
    ipo = json.loads(IPO_DATES.read_text(encoding="utf-8")) if IPO_DATES.exists() else {}
    rows, cands = [], []
    for cid, d in spac_packs():
        s = dict(d["spac"])
        if prices and d.get("ticker") in prices:
            s["price"] = prices[d["ticker"]]
        r, t = lookup(d, reg, th)
        stage = r.get("stage") or s.get("stage") or "S4"
        res = score(s, stage, bool(t.get("theme")) or bool(s.get("theme")), c, ctx=ctx_of(d, r, tr, ipo))
        row = {"id": cid, "ticker": d.get("ticker"), "target": s.get("target"), "stage": stage, "theme": t.get("theme") or s.get("theme") or "", **res}
        rows.append(row)
        if res["candidate"]:
            cands.append(row)
    DIR.mkdir(parents=True, exist_ok=True)
    keys = ("floor", "dilution", "quality", "time", "fundamentals", "value", "edge", "overhang", "attention")
    with (DIR / "scores.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "ticker", "target", "stage", "theme", "score", *keys, "premium", "ncps_kor", "net_cash_ps", "missing", "kills"])
        for x in rows:
            fa, nu = x["factors"], x["numbers"]
            w.writerow([x["id"], x["ticker"], x["target"], x["stage"], x["theme"], x["score"], *[fa.get(k, "") for k in keys],
                        nu["premium"], nu["ncps_kor"], nu["net_cash_ps"], "|".join(x["missing"]), "|".join(x["kills"])])
    (DIR / "candidates.json").write_text(json.dumps({"as_of": date.today().isoformat(), "min": c["candidate_min"], "candidates": cands,
                                                     "note": "연구 후보 지표 — 매수 권유가 아님"}, ensure_ascii=False, indent=1), encoding="utf-8")
    return rows


def needs():
    """테마가 맞은 확정 계약 이후 스팩 중 datapack spac이 없는 것"""
    reg, th = ledger()
    have = set()
    for _, d in spac_packs():
        r, _ = lookup(d, reg, th)
        if r:
            have.add(r["cik"])
        have.update(str(k) for k in d.get("ciks") or [])   # 같은 거래의 다른 장부 행(스팩·합병 지주사)
    stages = set((yaml.safe_load((ROOT / "config" / "spac.yaml").read_text(encoding="utf-8")) or {}).get("alert_stages") or [])
    return [{"cik": k, "name": r["name"], "tickers": r["tickers"], "stage": r["stage"], "theme": th[k]["theme"], "url": r["url"]}
            for k, r in reg.items() if r["stage"] in stages and th.get(k, {}).get("theme") and k not in have]


def fill_ipo():
    """datapack 스팩의 IPO 날짜 = EDGAR 제출 목록의 첫 424B4·424B1(스팩 IPO 투자설명서) — 시간 압박 요인 재료. 프로젝트 User-Agent, 요청 사이 0.25초"""
    import time
    sys.path.insert(0, str(ROOT / "radar"))
    from pollers import common, sec_filings   # noqa: E402
    reg, th = ledger()
    have = json.loads(IPO_DATES.read_text(encoding="utf-8")) if IPO_DATES.exists() else {}
    for _, d in spac_packs():
        r, _ = lookup(d, reg, th)
        for k in [x for x in [r.get("cik")] + [str(x) for x in d.get("ciks") or []] if x]:
            if k in have:
                continue
            time.sleep(0.25)
            try:
                sub = json.loads(common.http_get(f"https://data.sec.gov/submissions/CIK{int(k):010d}.json", headers={"User-Agent": sec_filings._ua()}, timeout=40))
            except Exception:
                continue
            rec = (sub.get("filings") or {}).get("recent") or {}
            ds = [dt for f, dt in zip(rec.get("form") or [], rec.get("filingDate") or []) if f in ("424B4", "424B1")]
            if ds:
                have[k] = min(ds)
    IPO_DATES.write_text(json.dumps(dict(sorted(have.items())), ensure_ascii=False, indent=1), encoding="utf-8")
    return have


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if "--needs" in argv:
        print(json.dumps(needs(), ensure_ascii=False, indent=1))
    elif "--fill-ipo" in argv:
        print(json.dumps(fill_ipo(), ensure_ascii=False))
    elif "--all" in argv:
        for x in run_all():
            print(f"{x['ticker']} {x['target']} [{x['stage']}·{x['theme'] or '테마 없음'}] 점수 {x['score']} {x['factors']} {'후보' if x['candidate'] else ''} {x['kills'] or ''}")
    else:
        cid = argv[0]
        d = json.loads((COMP / cid / "datapack.json").read_text(encoding="utf-8"))
        s = dict(d["spac"])
        if "--price" in argv:
            s["price"] = float(argv[argv.index("--price") + 1])
        reg, th = ledger()
        r, t = lookup(d, reg, th)
        print(json.dumps(score(s, r.get("stage") or "S4", bool(t.get("theme")), ctx=ctx_of(d, r)), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
