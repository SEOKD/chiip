"""텐배거 리포트 양식 3 (마스터 지시 2026-10-31 — 구매 등급·대시보드·한눈에 보기·본론 순서 개편)

순서: 제목 → Chiip View → 대시보드 → 한 장 요약 → 한눈에 보기(그림 번호 없음) → 내러티브 → 포트폴리오 → 수주·파이프라인 → 해자 →
      약세 논리 및 셀온 조건 → 어닝콜 변화 → 밸류에이션 → 수급 → 체크리스트.
모델은 JSON에 title·subtitle·date·ticker·company·biz·verdict(view·alpha)·summary·sections(판단 시나리오·반대 검증·킬 조건(또는 셀온 조건)·체크리스트)만 쓴다.
숫자·순서·그래프는 이 파일이 만든다. 모르는 절이 있으면 멈춘다 — 본론 순서가 고정이기 때문이다.

datapack 새 재료(없으면 --merge가 멈춘다, 옛 리포트 정정은 --legacy):
  "moat": {"summary": "한 줄", "items": [{"kind": MOAT_KINDS 중 하나, "verdict": "강함|보통|약함|해당 없음", "claim": "무엇이 해자인가",
            "evidence": "1차 자료 숫자", "quant": "ASP·캐파·시점 숫자(선택)", "falsifier": "깨지는 조건"}…]}   # 세 종류 모두, 해당이 없으면 verdict 해당 없음 + claim에 이유
  "multiple_view": {"adj": -0.2, "why": "사이클·실행 할인 등 IB식 판단 한 줄"}   # 조정폭은 config/tenbagger.yaml multiple_select.judge_cap 안에서
  "guidance": {"next": {"period": "4Q26", "rev": 285, "rev_cons": 285, "eps": 0.95, "eps_cons": 1.0, "unit": "$M"}}   # 같은 기간 회사 가이던스 vs 컨센서스, 없는 지표는 뺀다
  "consensus": {"ratings": {"strong_buy": 6, "buy": 0, "hold": 5, "sell": 0, "strong_sell": 0, "as_of": "2026-10-20"}}   # Fiscal.ai company_analyst_ratings
  "next_event": {"date": "2027-02-03", "tag": "4Q26 실적(예상)"}   # 어닝·오퍼링·인베스터데이 중 가장 가까운 것
  "terms": {"Triton": "CPO 광 시험 장비"}   # 이 리포트의 제품명·정책명 풀이
JSON '판단 시나리오' 절의 scenario 차트: cases마다 {"name", "prob", "eps" 또는 "ebitda", "why", "color"} — 멀티플·주가는 엔진이 정한다.
"""
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import flow  # noqa: E402
import levels  # noqa: E402
import narrative_view  # noqa: E402

MOAT_KINDS = ("공급 병목에 따른 구조적 ASP 상승", "기술 혁신에 따른 구조적 ASP 상승", "선제 CAPEX에 따른 Q 사이클")
RATINGS = ("Strong Buy", "Buy", "Neutral", "Sell", "Strong Sell")
ANALYST = (("strong_buy", "Strong Buy"), ("buy", "Buy"), ("hold", "Neutral"), ("sell", "Sell"), ("strong_sell", "Strong Sell"))
MODEL_SECTIONS = ("판단 시나리오", "반대 검증", "킬 조건", "셀온 조건", "체크리스트", "재발행 기록", "정정 기록")
BANNED = ("DCF ÷ 시가총액", "주주가치 ÷ 시가총액", "배수 사다리", "컨빅션")
SHORT_TITLES = {"콜 변화": "어닝콜 변화별 주주가치 영향", "최근 4개 분기 주가": "최근 4개 분기 주가 변화 분석", "일별 거래량": "일별 거래량 분해", "기관 자금": "기관 자금 흐름"}


def config():
    return yaml.safe_load((ROOT / "config" / "tenbagger.yaml").read_text(encoding="utf-8"))


def rating(up, rr, dcf_up, cfg):
    """구매 등급(마스터 지시 2026-10-31) — 확률 가중 업사이드·손익비·DCF 교차 확인으로 규칙이 고른다. 모델이 고르지 않는다. 개인 포지션을 읽지 않는다"""
    r = cfg["rating"]
    if up >= r["strong_buy"]["upside"] and rr >= r["strong_buy"]["rr"] and dcf_up >= r["strong_buy"]["dcf_min"]:
        return "Strong Buy"
    if up >= r["buy"]["upside"] and rr >= r["buy"]["rr"] and dcf_up >= r["buy"]["dcf_min"]:
        return "Buy"
    if up >= r["neutral"]["upside"]:
        return "Neutral"
    return "Sell" if up >= r["sell"]["upside"] else "Strong Sell"


def reward_risk(price, bull, bear):
    """손익비 = 강세까지 오를 폭 ÷ 약세까지 내릴 폭"""
    return (bull - price) / (price - bear) if price > bear else None


def scenario_build(d, dp, mm, sel, shares):
    """모델이 쓴 cases(EPS·확률·이유)에 엔진이 고른 멀티플을 곱한다. 주가 = 멀티플 × EPS, EBITDA 지표면 (멀티플 × EBITDA − 순차입) ÷ 주식 수"""
    sec = next((s for s in d.get("sections") or [] if s.get("h2", "").startswith("판단 시나리오")), None)
    block = next((b for b in (sec or {}).get("blocks") or [] if (b.get("chart") or {}).get("kind") == "scenario"), None)
    if not block:
        raise SystemExit("리포트 JSON에 '판단 시나리오' 절의 scenario 차트가 없다")
    c = block["chart"]
    price = float(dp["profile"]["price"])
    net_debt = (dp["profile"].get("debt") or 0) - (dp["profile"].get("cash") or 0)
    if abs(sum(float(k.get("prob") or 0) for k in c["cases"]) - 1) > 0.01:
        raise SystemExit("판단 시나리오 확률 합이 1이 아니다")
    spread = config()["multiple_select"]["spread"]
    ev_metric = sel["basis"] != "pe_fwd"
    for k in c["cases"]:
        name = k["name"]
        m = sel["value"] * (1 + spread[{"약세": "bear", "강세": "bull"}.get(name, "base")])
        if ev_metric:
            if k.get("ebitda") is None:
                raise SystemExit(f"시나리오 {name}: 주요 지표가 EBITDA라 ebitda가 필요하다")
            k["value"] = round((m * float(k["ebitda"]) - net_debt) / shares, 2)
        else:
            if k.get("eps") is None:
                raise SystemExit(f"시나리오 {name}: eps가 필요하다")
            k["value"] = round(m * float(k["eps"]), 2)
        k["multiple"] = round(m, 1)
    c.update({"current": price, "unit": "$", "title": "밸류에이션 주가 시나리오"})
    cases = {k["name"]: k for k in c["cases"]}
    for need in ("약세", "기본", "강세"):
        if need not in cases:
            raise SystemExit(f"판단 시나리오에 {need}가 없다")
    weighted = sum(float(k["prob"]) * k["value"] for k in c["cases"])
    return {"chart": c, "price": price, "bull": cases["강세"]["value"], "base": cases["기본"]["value"], "bear": cases["약세"]["value"], "weighted": weighted,
            "upside": weighted / price - 1, "downside": cases["약세"]["value"] / price - 1, "bull_up": cases["강세"]["value"] / price - 1,
            "rr": reward_risk(price, cases["강세"]["value"], cases["약세"]["value"]) or 0.0, "cases": c["cases"], "metric_name": "EBITDA" if ev_metric else "EPS"}


def rr_chart(s):
    """업사이드·주가별 손익비 — 약세와 강세 사이 가격마다 손익비, 현재가를 한 줄 끼운다"""
    bear, bull, price = s["bear"], s["bull"], s["price"]
    prices = [bear + (bull - bear) * i / 8 for i in range(1, 8)]
    near = (bull - bear) / 16
    prices = sorted([p for p in prices if abs(p - price) > near] + ([price] if bear < price < bull else []))
    rows = []
    for p in prices:
        rr = reward_risk(p, bull, bear)
        v = round(rr * 100)
        name, col = ("손익비 300% 이상", "d") if v >= 300 else (("손익비 100~300%", "c") if v >= 100 else ("손익비 100% 미만", "b"))
        label = f"${p:,.2f} 현재" if p == price else f"${p:,.0f}"
        rows.append({"label": f"{label} · 가중 {s['weighted'] / p - 1:+.0%}", "bars": [{"name": name, "color": col, "value": v}]})
    return {"kind": "hbars", "w": 480, "label_w": 170, "title": "업사이드·주가별 손익비", "unit": "%", "rows": rows}


def _at(rows, idx):
    return rows[idx] if -len(rows) <= idx < len(rows) else None


def actest_chart(dp):
    """분기 매출·EPS 실적 vs 컨센서스 — 지난 4개 분기는 실적과 발표 직전 추정, 앞으로 3개 분기는 컨센서스만"""
    cons = dp.get("consensus") or {}
    rows = cons.get("surprise") or []
    panels = []
    for metric, name, scale in (("매출", "매출($M)", 1.0), ("EPS", "EPS($)", 1.0)):
        past = sorted((r for r in rows if r.get("metric") == metric), key=lambda r: r["period"])[-4:]
        cats = [r["period"] for r in past]
        act = [r.get("actual") for r in past]
        est = [r.get("est") for r in past]
        if metric == "매출":
            fut = sorted((k, v * 1000) for k, v in (cons.get("quarters_est") or {}).items())
        else:
            fut = sorted((r["period"], r["to"]) for r in ((cons.get("revisions") or {}).get("rows") or []) if r.get("metric") == "EPS")
            fut = sorted({**dict(fut), **(cons.get("eps_quarters_est") or {})}.items())   # Fiscal.ai 분기 추정이 있으면 그것을 먼저
        for k, v in [x for x in fut if x[0] not in cats][:3]:
            cats.append(k)
            act.append(None)
            est.append(round(v * scale, 3))
        panels.append({"name": name, "categories": cats, "actual": act, "est": est})
    return {"kind": "actest", "title": "분기 매출·EPS 실적과 컨센서스", "panels": panels}


def price_charts(entity):
    """일봉·주봉·월봉 — 봉마다 가장 많이 쓰는 기법 두 가지(이동평균선·피보나치 되돌림)로 지지선과 저항선을 가른다(마스터 지시 2026-10-31)"""
    daily = flow.load_ohlcv(entity)
    if len(daily) < 60:
        return []
    monthly = flow.load_monthly(entity)
    z = levels.zones(daily, None, monthly=monthly)
    price, sw = z["price"], z["swings"]
    series = (("일봉", daily, 120, sw["일봉"], (50, 200), "일"), ("주봉", levels.resample(daily, "W"), 78, sw["주봉"], (20, 50), "주"),
              ("월봉", levels.merge_monthly(monthly, daily) if monthly else levels.resample(daily, "M"), 60, sw["월봉"], (12, 24), "개월"))
    out = []
    for title, bars, tail, s, mas, unit in series:
        view = bars[-tail:]
        lines, hl = [], []
        for n, col in zip(mas, ("c", "e")):
            pts = [[bars[i]["date"], sum(x["c"] for x in bars[i - n + 1:i + 1]) / n] for i in range(n - 1, len(bars))]
            if pts:
                lines.append({"name": f"{n}{unit}선", "color": col, "points": pts[-tail:]})
                last = pts[-1][1]
                hl.append({"y": last, "tag": f"{n}{unit}선", "kind": "ma"})
        for name, v in (s.get("ret") or {}).items():
            hl.append({"y": v, "tag": f"피보 {name}", "kind": "fib"})
        lo, hi = min(b["l"] for b in view), max(b["h"] for b in view)
        fmt = (lambda v: f"{v:,.2f}") if price < 100 else (lambda v: f"{v:,.0f}")
        keep = [h for h in hl if lo * 0.9 <= h["y"] <= hi * 1.1]
        sup = sorted((h for h in keep if h["y"] < price), key=lambda h: -h["y"])[:3]
        res = sorted((h for h in keep if h["y"] >= price), key=lambda h: h["y"])[:3]
        marks = [{"y": h["y"], "label": f"지지 {fmt(h['y'])}", "color": "d"} for h in sup] + [{"y": h["y"], "label": f"저항 {fmt(h['y'])}", "color": "b"} for h in res]
        legend = [{"name": x["name"], "color": x["color"]} for x in lines] + [{"name": "지지", "color": "d"}, {"name": "저항", "color": "b"}]
        out.append({"kind": "candle", "w": 480, "title": title, "unit": "$", "bars": [[x["date"], x["o"], x["h"], x["l"], x["c"]] for x in view], "lines": lines, "hlines": marks, "legend": legend,
                    "levels": {"support": [[h["tag"], h["y"]] for h in sup], "resistance": [[h["tag"], h["y"]] for h in res]}})
    return out


def price_stats(entity, price):
    """(52주 고점 대비, 1년 변화) — 일봉 종가 기준"""
    px = flow.load_ohlcv(entity)
    if not px:
        return None, None
    last = px[-252:]
    high = max(b["c"] for b in last)
    return price / high - 1, price / last[0]["c"] - 1


def _money_m(v, unit="$M"):
    return f"${v:,.0f}M" if unit == "$M" else f"{v}"


def dashboard(dp, s, mm, alpha, grade, mcap, unit, entity):
    """대시보드 8칸(마스터 지시 2026-10-31): 주가·시가총액·업사이드·구매등급·멀티플·가이던스·알파·이벤트"""
    prof, cons = dp["profile"], dp.get("consensus") or {}
    from_high, yr = price_stats(entity, s["price"])
    ev = mcap + (prof.get("debt") or 0) - (prof.get("cash") or 0)
    money = lambda x: f"${x:,.2f}B" if unit == "B$" else f"{x:,.1f} {unit}"
    tiles = [{"k": "주가", "v": f"${s['price']:,.2f}", "sub": f"고점 대비 {from_high:+.0%} · 1년 {yr:+.0%}" if from_high is not None else "미확인", "tone": "red" if (from_high or 0) < -0.3 else ""},
             {"k": "시가총액", "v": money(mcap), "sub": f"EV {money(ev)}"},
             {"k": "업사이드", "v": f"{s['upside']:+.0%}", "sub": f"다운사이드 {s['downside']:+.0%} · 손익비 {s['rr'] * 100:.0f}%", "tone": "red" if s["upside"] > 0 else "blue"}]
    ra = cons.get("ratings") or {}
    counts = " · ".join(f"{name} {ra.get(k, 0)}" for k, name in ANALYST)
    tiles.append({"k": "구매등급", "v": grade, "sub": f"애널리스트 {sum(ra.get(k, 0) for k, _ in ANALYST)}명: {counts}" if ra else "애널리스트 등급 미확인",
                  "tone": "red" if "Buy" in grade else ("blue" if "Sell" in grade else "")})
    tiles.append({"k": "멀티플", "v": f"{mm['label_short']} {mm['current']:.1f}배", "sub": f"동종 중앙값 {mm['peer_p50']:.1f}배"})
    g = (dp.get("guidance") or {}).get("next") or {}
    if g:
        head = " · ".join(x for x in (f"${g['rev']:,.0f}M" if g.get("rev") is not None else "", f"${g['eps']:.2f}" if g.get("eps") is not None else "") if x)
        vs = " · ".join(x for x in (f"${g['rev_cons']:,.0f}M" if g.get("rev_cons") is not None else "", f"${g['eps_cons']:.2f}" if g.get("eps_cons") is not None else "") if x)
        tiles.append({"k": f"가이던스 {g.get('period', '')}".strip(), "v": head, "sub": f"컨센서스 {vs}" if vs else "컨센서스 미확인"})
    else:
        tiles.append({"k": "가이던스", "v": "없음", "sub": "회사가 숫자를 내지 않았다"})
    tiles.append({"k": "알파", "v": f"{alpha}/10", "sub": "텐배거 가능성 점수"})
    ne = dp.get("next_event") or {}
    tiles.append({"k": "이벤트", "v": str(ne.get("tag") or "미확인"), "sub": str(ne.get("date") or "")})
    return tiles


def moat_section(dp):
    m = dp.get("moat") or {}
    have = {x.get("kind"): x for x in m.get("items") or []}
    miss = [k for k in MOAT_KINDS if not (have.get(k) or {}).get("claim")]
    if miss:
        raise SystemExit(f"datapack moat에 {miss}가 없다 — 해당이 없으면 verdict '해당 없음'과 claim에 이유(report_layout.py 맨 위)")
    B = [{"type": "hl", "text": m["summary"]}] if m.get("summary") else []
    B.append({"type": "boxes", "items": [{"title": x["kind"], "tag": x.get("verdict"), "lines": [["해자", x.get("claim")], ["근거", x.get("evidence")], ["숫자", x.get("quant")], ["깨지는 조건", x.get("falsifier")]]}
                                         for x in m["items"]]})
    return {"h2": "해자", "blocks": B}


def _pick(blocks, *prefix, typ=None):
    return next((b for b in blocks if (typ is None or b.get("type") == typ) and any(str(b.get("title") or (b.get("chart") or {}).get("title") or "").startswith(p) for p in prefix)), None)


def earnings_blocks(esec):
    """어닝콜 변화 — 표와 해석만, 그래프는 한눈에 보기로"""
    B = (esec or {}).get("blocks") or []
    out = [b for b in (_pick(B, "직전 콜 대비", typ="table"), _pick(B, "실적 vs 컨센서스", typ="table"), _pick(B, "사건별 EPS 리비전", typ="table"), _pick(B, "컨센서스 리비전", typ="table")) if b]
    for b in out:
        b["title"] = str(b["title"]).split(" — ")[0].split(" (")[0]
    read = next((b for b in B if b.get("type") == "p" and str(b.get("text")).startswith("**해석:**")), None)
    return out + ([read] if read else [])


def gallery(price, actest, ev_chart, s, esec, mm, flow_sec, sec):
    """한눈에 보기 순서(마스터 지시 2026-10-31): 차트 → 실적 → EPS 리비전 → 주가 시나리오 → 손익비 → 어닝콜 → 주가 분해 → 멀티플 프리미엄 → 합리적 멀티플 → 거래량·자금 → 몬테카를로"""
    E = [b for b in (esec or {}).get("blocks") or [] if b.get("type") == "chart"]
    get = lambda blocks, key: next((dict(b["chart"]) for b in blocks if key in str((b.get("chart") or {}).get("title"))), None)
    out = list(price) + [actest]
    rev = next((dict(b["chart"]) for b in E if b["chart"].get("kind") == "revision"), None)
    if rev:
        rev["title"] = "EPS 리비전"
        out.append(rev)
    out += [s["chart"], rr_chart(s)]
    call = get(E, "콜 변화")
    if call:
        call["title"] = SHORT_TITLES["콜 변화"]
        out.append(call)
    dec = get(E, "최근 4개 분기 주가")
    if dec:
        dec["title"] = SHORT_TITLES["최근 4개 분기 주가"]
        out.append(dec)
    prem = get(E, "멀티플 프리미엄")
    if prem:
        want = "EV/EBITDA" if mm["basis"] != "pe_fwd" else "P/E"
        idx = [i for i, c in enumerate(prem["categories"]) if want in c]
        series = [{**x, "values": [x["values"][i] for i in idx]} for x in prem["series"]]
        prem.update({"title": "멀티플 프리미엄", "categories": [prem["categories"][i] for i in idx], "series": [x for x in series if any(v is not None for v in x["values"])]})
        out.append(prem)
    if ev_chart:
        out.append(ev_chart)
    F = [b for b in (flow_sec or {}).get("blocks") or [] if b.get("type") == "chart"]
    for key, name in (("일별 거래량", SHORT_TITLES["일별 거래량"]), ("기관 자금", SHORT_TITLES["기관 자금"])):
        c = get(F, key)
        if c:
            c["title"] = name
            out.append(c)
    mc = get(sec.get("blocks") or [], "몬테카를로")
    if mc:
        mc["title"] = "몬테카를로"
        mc["categories"] = [f"{(float(x) - 1) * 100:+.0f}%" for x in mc["categories"]]
        mc["conclusion"] = [x for x in mc.get("conclusion") or [] if x.startswith("해석")]
        out.append(mc)
    return [c for c in out if c]


def rational_chart(view):
    """합리적 멀티플 — Fwd 1Y만(마스터 지시 2026-10-31)"""
    n = view["label"]
    bars = [{"label": "현재", "bars": [{"name": n, "color": "e", "value": round(view["current"], 1)}]}]
    if view.get("history"):
        bars.append({"label": "자기 과거 중앙", "bars": [{"name": n, "color": "a", "value": round(view["history"]["p50"], 1)}]})
    bars.append({"label": "동종 중앙", "bars": [{"name": n, "color": "b", "value": round(view["peer_range"]["p50"], 1)}]})
    if view.get("rational"):
        bars.append({"label": "합리적 멀티플", "bars": [{"name": n, "color": "d", "value": round(view["rational"]["p50"], 1)}]})
    return {"kind": "hbars", "w": 480, "label_w": 130, "title": "합리적 멀티플", "unit": "배", "rows": bars}


def valuation_section(s, sel, mm, r, co, sec, name, decision_line):
    """밸류에이션 — 계산은 엔진이 체계적으로, 글은 짧게(마스터 지시 2026-10-31)"""
    mcap = r["mcap"]
    base, bull, bear = r["scenarios"]["base"], r["scenarios"]["bull"], r["scenarios"]["bear"]
    B = [{"type": "hl", "text": f"**확률 가중 ${s['weighted']:,.0f}, 업사이드 {s['upside']:+.0%}.** 강세 ${s['bull']:,.0f}({s['bull_up']:+.0%}), 약세 ${s['bear']:,.0f}({s['downside']:+.0%}). "
                                f"DCF 기준 업사이드는 기본 {base['v0'] - 1:+.0%}, 강세 {bull['v0'] - 1:+.0%}, 약세 {bear['v0'] - 1:+.0%}다(WACC {r['coc']['wacc']:.1%})."}]
    B.append({"type": "table", "title": "주가 시나리오", "headers": ["시나리오", "확률", "멀티플", s["metric_name"], "주가", "업사이드", "근거"],
              "rows": [[k["name"], f"{k['prob']:.0%}", f"{k['multiple']:.1f}배", (f"${k['eps']:.2f}" if k.get("eps") is not None else f"${k['ebitda']:,.2f}B"), f"${k['value']:,.0f}", f"{k['value'] / s['price'] - 1:+.0%}", k.get("why", "")] for k in s["cases"]]})
    B.append({"type": "table", "title": f"멀티플 선정 — {sel['label']}", "headers": ["단계", "조정", "근거"], "rows": sel["rows"]})
    peers = [[x["ticker"]] + [("-" if x.get(k) is None else f"{x[k]:.1f}") for k in sel["keys"]] + [f"{x['growth']:.0%}", f"{x['ebit_margin']:.0%}", "-" if x.get("roic") is None else f"{x['roic']:.0%}"] for x in mm["peers"]]
    B.append({"type": "table", "title": "동종 레인지", "headers": ["회사"] + sel["labels"] + ["성장", "영업이익률", "ROIC"], "rows": peers + [[f"**{name}**"] + [f"{v:.1f}" for v in sel["now"]] + ["", "", ""]]})
    grid = _pick(sec.get("blocks") or [], "민감도", typ="table")
    if grid:
        B.append({"type": "table", "title": "민감도 — DCF 업사이드(장기 이익률 × 매출÷투하자본)", "headers": grid["headers"],
                  "rows": [[r0[0]] + [("-" if c == "-" else f"{float(c) - 1:+.0%}") for c in r0[1:]] for r0 in grid["rows"]]})
    u = r["upside"]
    tail = f"몬테카를로 중앙값 업사이드 {u['v0_p50'] - 1:+.0%}"
    if u.get("implied_cagr") is not None:
        tail = f"지금 주가가 요구하는 5년 매출 CAGR {u['implied_cagr']:.0%}, 기본 시나리오 {u['base_cagr']:.0%}. " + tail
    B.append({"type": "p", "text": tail + "."})
    if decision_line:
        B.append({"type": "hl", "text": decision_line})
    return {"h2": "밸류에이션", "blocks": B}


def flow_blocks(flow_sec, price_list):
    B = [b for b in (flow_sec or {}).get("blocks") or [] if b.get("type") != "chart" and not str(b.get("text", "")).startswith("**읽는 법")]
    rows = []
    for c in price_list:
        lv = c.get("levels") or {}
        rows.append([c["title"], " · ".join(f"{t} ${v:,.2f}" for t, v in lv.get("support") or []) or "-", " · ".join(f"{t} ${v:,.2f}" for t, v in lv.get("resistance") or []) or "-"])
    if rows:
        B.append({"type": "table", "title": "지지선·저항선", "headers": ["봉", "지지", "저항"], "rows": rows})
    return B


def unglossed(d, dp):
    """풀이 없는 전문 약자 — 금융 용어(plain_ok)·티커가 아니면 report_glossary.yaml 또는 datapack terms에 넣게 한다. 대문자 약자만 잡는다(제품명은 모델이 terms에 쓴다)"""
    g = yaml.safe_load((ROOT / "config" / "report_glossary.yaml").read_text(encoding="utf-8"))
    known = set(g["terms"]) | set(g.get("no_gloss") or {}) | set(g.get("plain_ok") or []) | set(dp.get("terms") or {})
    tick = {str(p.get("ticker")) for p in dp.get("peers") or []} | {str(d.get("ticker"))}
    text = []

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k not in ("sources", "gallery", "bars", "points"):
                    walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
        elif isinstance(o, str):
            text.append(re.sub(r"https?://\S+", "", o))
    walk({k: d.get(k) for k in ("verdict", "summary", "sections")})
    found = set(re.findall(r"(?<![A-Za-z0-9/&.\-])[A-Z][A-Z0-9]{2,6}(?![A-Za-z0-9\-])", " ".join(text)))
    return sorted(x for x in found if x not in known and x not in tick and not re.fullmatch(r"\d?Q\d+|FY\d+|CY\d+|[A-Z]\d+", x))


def assemble(d, dp, co, r, mm, sel, sec, esec, xs, entity):
    """모델 JSON + 엔진 재료 → 양식 3 리포트 JSON"""
    for s0 in d.get("sections") or []:
        if not s0.get("h2", "").startswith(MODEL_SECTIONS):
            raise SystemExit(f"양식 3 본론에 없는 절: {s0.get('h2')} — 쓸 수 있는 절은 {MODEL_SECTIONS}. 내용은 datapack narrative·moat로 옮긴다")
    shares = r["mcap"] / float(dp["profile"]["price"])
    s = scenario_build(d, dp, mm, sel, shares)
    dcf_up = r["scenarios"]["base"]["v0"] - 1
    cfg = config()
    grade = rating(s["upside"], s["rr"], dcf_up, cfg)
    v = d.setdefault("verdict", {})
    alpha = v.get("insight") if v.get("insight") is not None else v.get("alpha")
    v.update({"rating": grade, "upside": round(s["upside"], 4), "downside": round(s["downside"], 4), "rr": round(s["rr"], 3), "upside_basis": f"판단 시나리오 확률 가중 ${s['weighted']:,.0f}"})
    v.pop("confidence", None)
    m_short = {"label_short": sel["label"], "current": sel["now"][0], "peer_p50": sel["peer_p50"], "basis": sel["basis"]}
    d["tiles"] = dashboard(dp, s, m_short, alpha, grade, r["mcap"], r["unit"], entity)
    upline = f"**강세 ${s['bull']:,.0f}({s['bull_up']:+.0%})까지 열려 있다.** {sel['label']} {s['cases'][-1]['multiple']:.1f}배를 강세 {s['metric_name']}에 적용한 값이다. 기본 ${s['base']:,.0f}, 약세 ${s['bear']:,.0f}, 확률 가중 ${s['weighted']:,.0f}({s['upside']:+.0%}). 손익비 {s['rr'] * 100:.0f}%, DCF 기준 업사이드 {dcf_up:+.0%}."
    keep = [x for x in d.get("summary") or [] if not x.get("auto")]
    auto = [{"q": "기업가치를 결정하는 내러티브", "a": ((dp.get("narrative") or {}).get("lead") or {}).get("summary", ""), "auto": True},
            {"q": "밸류에이션 모델로 본 주가 상방은 어디까지인가?", "a": upline, "auto": True}]
    if xs.get("pipeline"):
        import pipeline_view
        auto.append(pipeline_view.summary_item(dp))
    d["summary"] = auto + keep
    price = price_charts(entity)
    view = next((h for h in mm.get("horizons") or [] if h["h"] == 1), None)
    d["gallery"] = gallery(price, actest_chart(dp), rational_chart(view) if view else None, s, esec, mm, xs.get("flow"), sec)
    model = d.get("sections") or []
    find = lambda *keys: [x for x in model if x.get("h2", "").startswith(keys)]
    bear_blocks = [b for x in find("반대 검증") for b in x.get("blocks") or []]
    sell = [i for x in find("킬 조건", "셀온 조건") for b in x.get("blocks") or [] for i in b.get("items") or []]
    if sell:
        bear_blocks.append({"type": "boxes", "items": [{"title": "셀온 조건", "lines": [[f"조건 {i}", t] for i, t in enumerate(sell, 1)]}]})
    scen_text = [b for x in find("판단 시나리오") for b in x.get("blocks") or [] if b.get("type") != "chart"]
    val = valuation_section(s, sel, mm, r, co, sec, co.get("name", d.get("company")), (sec.get("blocks") or [{}])[-1].get("text") if (sec.get("blocks") or [{}])[-1].get("type") == "hl" else None)
    val["blocks"][1:1] = scen_text
    out = [narrative_view.section3(dp, mm), narrative_view.portfolio3(dp)]
    if xs.get("pipeline"):
        d["sources"] = list(dict.fromkeys((d.get("sources") or []) + (xs["pipeline"].pop("_sources", None) or [])))
        out.append({**xs["pipeline"], "h2": "수주·파이프라인"})
    out += [moat_section(dp), {"h2": "약세 논리 및 셀온 조건", "blocks": bear_blocks}, {"h2": "어닝콜 변화", "blocks": earnings_blocks(esec)}, val]
    flows = flow_blocks(xs.get("flow"), price)
    if flows:
        out.append({"h2": "수급", "blocks": flows})
    out += [{**x, "h2": "체크리스트"} for x in find("체크리스트")] + find("재발행 기록", "정정 기록")
    d.update({"format": 3, "sections": out, "terms": dp.get("terms") or {}})
    body = str({k: d.get(k) for k in ("verdict", "summary", "sections", "tiles")})
    left = [w for w in BANNED if w in body]
    if left:
        raise SystemExit(f"양식 3에서 쓰지 않는 표기: {left}")
    bad = unglossed(d, dp)
    if bad:
        raise SystemExit(f"풀이 없는 전문 약자: {bad} — config/report_glossary.yaml terms 또는 datapack terms에 넣는다(금융 용어면 plain_ok)")
    return d
