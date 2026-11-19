"""피터 린치 6분류 (마스터 지시 2026-11-19 "The Peter Lynch Playbook을 Analysis·Pulse·Ten-bagger 종목 분석 알고리즘에 100% 반영")

원전: Peter Lynch & John Rothchild, One Up On Wall Street(1989)·Beating the Street(1993). 마스터가 준 자료는 두 책의 요약 노트다.
플레이북의 뼈대를 코드로 옮긴다.
  ① 크기 먼저(큰 회사는 작게 움직인다) → ② '이야기' 유형으로 6분류 → ③ 분류마다 기대 수익·위험(RISK/REWARD 표)
  ④ 분류마다 점검표와 '팔 때' 규칙(대형우량주는 2배 뒤 10배를 기대하지 않는다, 고성장주를 50%에 팔지 않는다)
  ⑤ 10배 경로가 있는 분류는 고성장주·회생주·경기순환주뿐 → 텐배거 점수 상한(config tenbagger_cap)
  ⑥ 린치 비율 = (EPS 성장% + 배당수익률%) ÷ P/E, PEG(P/E ÷ 성장%)
분류는 '자체추론'이다 — 근거(수치)와 반대 근거를 함께 낸다. 판정 순서: 회생주 → 자산주 → 경기순환주 → 성장 구간(고성장·대형우량·저성장).
금지표: 이 분류는 매매·비중 지시가 아니다. '팔 때' 규칙은 점검 조건으로만 쓴다.

입력(정규화한 dict, from_datapack·from_row가 만든다):
  {"mcap_usd", "growth"(장기 EPS 성장, 소수), "growth_basis", "rev_growth", "industry", "pb", "net_cash_usd", "div_yield", "pe",
   "op_ttm_hist"([오래된 → 최근 TTM 영업이익]), "rev_ttm_hist", "next_eps_up"(다음 해 이익이 지금보다 큰가)}
"""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CATS = ("고성장주", "대형우량주", "저성장주", "경기순환주", "회생주", "자산주")
EN = {"고성장주": "Fast Grower", "대형우량주": "Stalwart", "저성장주": "Slow Grower", "경기순환주": "Cyclical", "회생주": "Turnaround", "자산주": "Asset Play"}

CHECK = {   # 분류별 점검표(OUWS ch.13 '2분 연습'·ch.16 '팔 때') — 자기 말 요약
    "고성장주": {"see": ["성장을 더 이어 갈 자리(새 시장·점포·고객)가 남았나", "P/E가 성장률의 2배를 넘지 않나(PEG)", "성장 속도가 꺾이는 2단계에 들어섰나"],
              "sell": "성장 단계가 끝나거나(확장 여지 소진·동일 매장 성장 둔화) P/E가 성장률의 2배를 크게 넘을 때 — 50% 올랐다고 팔지 않는다(10배 경로를 자른다)"},
    "대형우량주": {"see": ["P/E가 자기 과거 범위의 어디인가", "본업과 무관한 확장(diworsification)이 있나", "장기 성장률이 유지되나", "불황에 얼마나 버텼나"],
               "sell": "30~50% 오르거나 P/E가 과거 범위 위쪽이면 차익을 고민한다 — 2배가 된 뒤 10배를 기대하지 않는다"},
    "저성장주": {"see": ["배당이 꾸준히 올랐나", "배당성향이 감당 가능한가", "점유율을 잃고 있나"],
              "sell": "배당이 끊기거나 점유율을 잃거나 본업 밖으로 확장할 때"},
    "경기순환주": {"see": ["재고·공급과 수요(가격)의 방향", "경쟁사의 증설", "이익 정점에서 P/E가 낮아 보이는 함정", "부채가 바닥을 견딜 수 있나"],
               "sell": "재고가 쌓이고 증설이 시작되고 가격이 꺾일 때 — 정점의 낮은 P/E는 싸다는 뜻이 아니다"},
    "회생주": {"see": ["현금과 부채 — 버틸 수 있나", "무엇으로 돌아서나(원가 절감·사업 매각·신제품)", "회생이 실제 숫자로 나오나"],
             "sell": "회생이 끝나 모두가 아는 회사가 되면 — 기대가 가격에 다 들어간 뒤"},
    "자산주": {"see": ["자산 가치가 가격보다 얼마나 큰가", "자산을 깎는 부채가 있나", "자산을 드러낼 계기(매각·분할·인수)"],
             "sell": "자산 가치가 드러나 가격에 반영되면 — 자산을 깎는 부채·희석이 생기면"},
}


def cfg():
    return yaml.safe_load((ROOT / "config" / "lynch.yaml").read_text(encoding="utf-8"))


def _f(x):
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def size_band(mcap, c):
    if mcap is None:
        return "미확인"
    return "소형" if mcap <= c["size"]["small_usd"] else ("대형" if mcap >= c["size"]["large_usd"] else "중형")


def _drawdown(hist):
    """오래된 → 최근 값 목록의 고점 대비 최대 하락(소수)"""
    peak, dd = None, 0.0
    for v in hist or []:
        if v is None:
            continue
        peak = v if peak is None or v > peak else peak
        if peak and peak > 0:
            dd = max(dd, 1 - v / peak)
    return dd


def classify(x, c=None):
    """→ {"cat", "en", "size", "why": [근거], "against": [반대 근거], "expect", "check", "sell", "tenbagger", "lynch_ratio", "peg"}"""
    c = c or cfg()
    g, mcap = _f(x.get("growth")), _f(x.get("mcap_usd"))
    size = size_band(mcap, c)
    why, against = [], []
    op = [v for v in x.get("op_ttm_hist") or [] if v is not None]
    rev = [v for v in x.get("rev_ttm_hist") or [] if v is not None]
    ind = str(x.get("industry") or "").lower()
    cat = None
    # ① 회생주 — 이익이 무너졌다가(음수 또는 3년 고점 대비 50%↓) 다음 해 회복이 예상될 때
    recent = op[-12:]
    if recent:
        cur, peak = recent[-1], max(recent)
        broken = cur <= 0 or (peak > 0 and cur < peak * (1 - c["turnaround"]["eps_drop"]))
        if broken and x.get("next_eps_up"):
            cat = "회생주"
            why.append(f"TTM 영업이익이 3년 고점 대비 {'음수' if cur <= 0 else f'{1 - cur / peak:.0%} 감소'}이고 다음 해 이익 회복이 컨센서스에 있다")
    # ② 자산주 — P/B 1배 이하 또는 순현금이 시총의 30% 이상, 단 고성장이 아닐 때
    if cat is None and (g is None or g < c["asset_play"]["growth_cap"]):
        pb, nc = _f(x.get("pb")), _f(x.get("net_cash_usd"))
        if pb is not None and 0 < pb <= c["asset_play"]["pb_max"]:
            cat = "자산주"
            why.append(f"P/B {pb:.2f}배 — 장부 자산보다 싸게 거래된다")
        elif nc is not None and mcap and nc / mcap >= c["asset_play"]["net_cash_share"]:
            cat = "자산주"
            why.append(f"순현금이 시가총액의 {nc / mcap:.0%}")
    # ③ 경기순환주 — 업종이 순환 업종이거나 매출이 고점 대비 20% 넘게 빠진 이력
    if cat is None:
        dd = _drawdown(rev)
        cyc_ind = any(k in ind for k in c["cyclical"]["industries"]) or bool(x.get("cyclical_sub"))
        # 적자 → 흑자 이력은 매출도 함께 빠졌을 때만 순환 근거(2026-11-19 — 젊은 회사의 적자 탈출은 성장 이야기다, Bloom)
        neg_cycle = bool(op) and any(v <= 0 for v in op[:-4]) and op[-1] > 0 and dd >= c["cyclical"]["rev_drawdown"] * 0.75
        if cyc_ind or dd >= c["cyclical"]["rev_drawdown"] or neg_cycle:
            cat = "경기순환주"
            if cyc_ind:
                why.append(f"순환 업종({x.get('industry')})")
            if dd >= c["cyclical"]["rev_drawdown"]:
                why.append(f"TTM 매출이 과거 고점 대비 {dd:.0%} 빠진 적이 있다")
            if neg_cycle:
                why.append("영업이익이 적자였다가 흑자로 돌아온 순환 이력")
            if g is not None and g >= c["growth"]["fast_min"]:
                against.append(f"장기 성장률 {g:.0%}로 고성장주 구간 — 순환 위의 성장주일 수 있다")
    # ④ 성장 구간
    if cat is None:
        if g is None:
            return {"cat": "미확인", "en": "Unclassified", "size": size, "why": ["장기 성장률 자료가 없다"], "against": [], "expect": None,
                    "check": [], "sell": "", "tenbagger": None, "lynch_ratio": None, "peg": None}
        if g >= c["growth"]["fast_min"]:
            cat = "고성장주"
            why.append(f"장기 EPS 성장 {g:.0%}({x.get('growth_basis', '컨센서스')}) — 고성장 구간(≥{c['growth']['fast_min']:.0%})")
            if g > c["growth"]["fast_max_credible"]:
                against.append(f"성장 {g:.0%}는 오래 지속되기 어렵다(린치: 50% 성장은 오래 못 간다)")
            if size == "대형":
                against.append("대형주라 10배는 드물다 — 크기가 기대치를 낮춘다")
        elif g >= c["growth"]["slow_max"]:
            cat = "대형우량주" if size != "소형" else "고성장주" if g >= c["growth"]["fast_min"] * 0.8 else "대형우량주"
            why.append(f"장기 EPS 성장 {g:.0%} — 중간 성장 구간({c['growth']['slow_max']:.0%}~{c['growth']['fast_min']:.0%})")
            if size == "소형":
                against.append("소형주인데 성장이 중간이라 우량주보다 '덜 빠른 성장주'에 가깝다")
        else:
            cat = "저성장주"
            why.append(f"장기 EPS 성장 {g:.0%} — 저성장 구간(<{c['growth']['slow_max']:.0%})")
    e = c["expect"][cat]
    pe, dy = _f(x.get("pe")), _f(x.get("div_yield")) or 0.0
    lr = ((g or 0) * 100 + dy * 100) / pe if pe and pe > 0 and g is not None else None
    peg = pe / (g * 100) if pe and pe > 0 and g and g > 0 else None
    return {"cat": cat, "en": EN[cat], "size": size, "why": why, "against": against, "expect": e, "check": CHECK[cat]["see"], "sell": CHECK[cat]["sell"],
            "tenbagger": e["tenbagger"], "lynch_ratio": lr, "peg": peg}


def cap_score(score, res, c=None):
    """텐배거 가능성 점수 상한 — 10배 경로가 없는 분류는 알파 관문(5.0) 아래로. (점수, 사유 또는 None)"""
    c = c or cfg()
    if score is None or not res or res.get("tenbagger") is not False or score <= c["tenbagger_cap"]:
        return score, None
    return c["tenbagger_cap"], f"린치 분류 {res['cat']}({res['en']}) — 10배 경로가 없는 분류라 {c['tenbagger_cap']}로 제한"


# ── 입력 어댑터 ──
def _ttm(q, key):
    out = []
    for i in range(3, len(q)):
        w = [r.get(key) for r in q[i - 3:i + 1]]
        out.append(sum(w) if all(v is not None for v in w) else None)
    return out


def _cagr(d):
    """{'FY2026': v, 'FY2027': v, ...} → (CAGR, 기간 수). 첫 해가 0 이하이면 None"""
    ks = sorted(k for k, v in (d or {}).items() if _f(v) is not None)
    if len(ks) < 2:
        return None, 0
    a, b = d[ks[0]], d[ks[-1]]
    if a <= 0 or b <= 0:
        return None, 0
    n = len(ks) - 1
    return (b / a) ** (1 / n) - 1, n


def from_datapack(dp):
    """Analysis datapack → 정규화 입력"""
    dp = dp or {}
    unit = str(dp.get("unit", "B$"))
    scale = 1e9 if unit.startswith("B") else (1e6 if unit.startswith("M") else 1.0)
    pr = dp.get("profile") or {}
    price, sh = _f(pr.get("price")), _f(pr.get("shares_basic"))
    mcap = price * sh * scale if price and sh else None
    fx = _f(dp.get("usd_per_unit") or (dp.get("fx") or {}).get("usd")) or 1.0
    cons = dp.get("consensus") or {}
    g, n = _cagr(cons.get("eps"))
    basis = f"컨센서스 EPS {n}년 CAGR" if g is not None else None
    rg, rn = _cagr(cons.get("rev"))
    if g is None and rg is not None:
        g, basis = rg, f"컨센서스 매출 {rn}년 CAGR(EPS 없음)"
    q = (dp.get("quarters_hist") or {}).get("q") or []
    eps = cons.get("eps") or {}
    ks = sorted(k for k, v in eps.items() if _f(v) is not None)
    nxt_up = len(ks) >= 2 and eps[ks[1]] > eps[ks[0]] > 0 if ks else False
    mn = dp.get("multiples_now") or {}
    pb = _f(mn.get("pb")) or _f(pr.get("pb"))
    cash, debt = _f(pr.get("cash")), _f(pr.get("debt"))
    ind = str(dp.get("industry") or "")
    return {"mcap_usd": mcap * fx if mcap else None, "growth": g, "growth_basis": basis, "rev_growth": rg, "industry": ind, "cyclical_sub": bool(dp.get("id") and _sub_cyclical(dp["id"])),
            "pb": pb, "net_cash_usd": (cash - debt) * scale * fx if cash is not None and debt is not None else None,
            "div_yield": _f(pr.get("div_yield")), "pe": _f(mn.get("pe_fwd")), "op_ttm_hist": _ttm(q, "op"), "rev_ttm_hist": _ttm(q, "rev"), "next_eps_up": nxt_up}


def _sub_cyclical(eid):
    """config/valuation.yaml universe sub → subsectors.cyclical(메모리·장비·기판 등 True)"""
    try:
        v = yaml.safe_load((ROOT / "config" / "valuation.yaml").read_text(encoding="utf-8")) or {}
    except OSError:
        return None
    sub = next((u.get("sub") for u in v.get("universe") or [] if u.get("id") == eid), None)
    return ((v.get("subsectors") or {}).get(sub) or {}).get("cyclical") if sub else None


def from_fund(f):
    """발굴 펀더멘털 행(knowledge/models/discovery/fundamentals.json) → 정규화 입력. 성장 = 다음 해 EPS ÷ TTM EPS(없으면 매출 성장)"""
    f = f or {}
    et, ef = _f(f.get("eps_ttm")), _f(f.get("eps_fwd"))
    g, basis = (ef / et - 1, "다음 해 EPS ÷ TTM EPS") if et and ef and et > 0 else (_f(f.get("rev_growth")), "TTM 매출 성장(EPS 없음)")
    price = _f(f.get("price"))
    return {"mcap_usd": _f(f.get("mcap_usd")), "growth": g, "growth_basis": basis, "rev_growth": _f(f.get("rev_growth")), "industry": f.get("industry"),
            "pb": _f(f.get("pb")), "net_cash_usd": None, "div_yield": None, "pe": price / ef if price and ef and ef > 0 else None,
            "op_ttm_hist": [et, et] if et is not None and et <= 0 else [], "rev_ttm_hist": [], "next_eps_up": bool(ef and ef > 0 and (et is None or ef > et))}


def for_entity(eid):
    """종목 id → 정규화 입력(Analysis datapack 우선, 없으면 발굴 펀더멘털). 둘 다 없으면 None"""
    import json
    p = ROOT / "knowledge" / "models" / "companies" / eid / "datapack.json"
    x = None
    if p.exists():
        try:
            x = from_datapack(json.loads(p.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            x = None
    if not x or x.get("growth") is None:
        fp = ROOT / "knowledge" / "models" / "discovery" / "fundamentals.json"
        try:
            row = (json.loads(fp.read_text(encoding="utf-8")) or {}).get(eid) if fp.exists() else None
        except (ValueError, OSError):
            row = None
        if row:
            x = from_fund(row)
    if x and _sub_cyclical(eid):
        x["cyclical_sub"] = True   # 밸류에이션 세부 업종이 순환(config/valuation.yaml subsectors.cyclical — 메모리·장비·기판 등)
    return x


# ── 리포트 ──
def _x(v, fmt):
    return "미확인" if v is None else format(v, fmt)


def summary_item(dp):
    r = classify(from_datapack(dp))
    if r["cat"] == "미확인":
        return {"q": "피터 린치라면 어느 분류인가?", "a": "분류 미확인 — " + " ".join(r["why"]), "auto": True}
    e = r["expect"]
    a = (f"**{r['cat']}({r['en']}) · {r['size']}** — 기대 {e['return']}, 하방 {e['down']}, 위험 {e['risk']}. " + " · ".join(r["why"]) + "."
         + (" 10배 경로가 있는 분류다." if r["tenbagger"] else " 10배 경로가 없는 분류라 텐배거 후보로 보지 않는다.")
         + f" 팔 때: {r['sell']}.")
    return {"q": "피터 린치라면 어느 분류인가?", "a": a, "auto": True}


def section(dp):
    x = from_datapack(dp)
    r = classify(x)
    if r["cat"] == "미확인":
        return {"h2": "피터 린치 분류", "blocks": [{"type": "p", "text": "분류 미확인 — " + " ".join(r["why"])}]}
    e = r["expect"]
    B = [{"type": "hl", "text": f"**{r['cat']}({r['en']}), {r['size']}.** 린치 표의 기대 수익 {e['return']}, 하방 {e['down']}, 위험 {e['risk']}. "
                                + ("10배 경로가 있는 분류다(고성장주·회생주·경기순환주)." if r["tenbagger"] else "10배 경로가 없는 분류다 — 기대치를 그 분류에 맞춘다.")},
         {"type": "table", "title": "분류 근거 — 크기 먼저, 다음은 이야기 유형", "headers": ["항목", "값"],
          "rows": [["크기", f"{r['size']}(시가총액 {_x((x['mcap_usd'] or 0) / 1e9 if x['mcap_usd'] else None, ',.1f')}B$)"],
                   ["장기 성장", f"{_x(x['growth'] * 100 if x['growth'] is not None else None, '.1f')}%({x.get('growth_basis') or '미확인'})"],
                   ["린치 비율((성장% + 배당%) ÷ P/E)", _x(r["lynch_ratio"], ".2f") + (" — 2 이상 매력, 1 미만 비싸다" if r["lynch_ratio"] is not None else "")],
                   ["PEG(P/E ÷ 성장%)", _x(r["peg"], ".2f") + (" — 1 적정, 0.5 매우 매력, 2 매우 불리" if r["peg"] is not None else "")],
                   ["근거", " · ".join(r["why"])], ["반대 근거", " · ".join(r["against"]) or "없음"]]},
         {"type": "ul", "items": [f"점검: {s}" for s in r["check"]] + [f"팔 때(점검 조건, 매매 지시 아님): {r['sell']}"]},
         {"type": "p", "text": "분류 = 피터 린치·존 로스차일드 『One Up On Wall Street』(1989)·『Beating the Street』(1993)의 6분류와 위험·보상 표를 숫자 규칙으로 옮긴 자체추론이다(config/lynch.yaml)."}]
    return {"h2": "피터 린치 분류", "blocks": B}


def pulse_line(x):
    """Pulse 알림 한 줄 — 정규화 입력(또는 None)"""
    if not x:
        return None
    r = classify(x)
    if r["cat"] == "미확인":
        return None
    return f"린치 분류: {r['cat']}({r['size']}) — 기대 {r['expect']['return']} · 하방 {r['expect']['down']}" + ("" if r["tenbagger"] else " · 10배 경로 없음")
