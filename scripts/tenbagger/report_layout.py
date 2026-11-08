"""텐배거 리포트 양식 3 (마스터 지시 2026-10-31 — 구매 등급·대시보드·한눈에 보기·본론 순서 개편)

순서: 제목 → Chiip View → 대시보드 → 한 장 요약 → 한눈에 보기(그림 번호 없음) → 내러티브 → 포트폴리오 → 고객 → 수주·파이프라인 → 마진 구조 → 공급망 병목 → 생산능력 → 해자 →
      약세 논리 및 셀온 조건 → 어닝콜 변화 → 거시 지표 싱크로율 → P·Q 사이클 → 밸류에이션 → 매수 위치(일봉) → 애널리스트 토론 → 수급 → 체크리스트.
모델은 JSON에 title·subtitle·date·ticker·company·biz·verdict(view·alpha)·summary·sections(판단 시나리오·반대 검증·킬 조건(또는 셀온 조건)·체크리스트)만 쓴다.
숫자·순서·그래프는 이 파일이 만든다. 모르는 절이 있으면 멈춘다 — 본론 순서가 고정이기 때문이다.

datapack 새 재료(없으면 --merge가 멈춘다, 옛 리포트 정정은 --legacy):
  "moat": {"summary": "한 줄", "items": [{"kind": "이 회사의 해자 이름", "verdict": "강함|보통|약함", "claim": "무엇이 해자인가",
            "evidence": "1차 자료 숫자", "quant": "숫자(선택)", "falsifier": "깨지는 조건"}…]}   # 회사별로 독립적으로 찾는다, 2개 이상
  "leaders": scripts/tenbagger/leader_view.py 맨 위 — 창업자·회장·CEO 프로필과 네트워크 정량화
  "margin": scripts/tenbagger/margin_view.py 맨 위 — GPM·OPM 비용 요인과 핵심 제품·서비스 BOM 분해
  "supply": scripts/tenbagger/supply_view.py 맨 위 — 부품 공급망 업체와 공급 병목 10점
  "customers": scripts/tenbagger/customer_view.py 맨 위 — 고객사와 고객별 매출 믹스 추정
  "sync": scripts/tenbagger/sync_view.py 맨 위 — 무역·PPI·수출 지표와 매출·영업이익 싱크로율, 가이던스·컨센서스 비교
  "ma": scripts/tenbagger/ma_view.py 맨 위 — 인수 시너지 램프·가치 vs 웃돈·EPS 효과, 없으면 {"none": "이유"}
  "pq": scripts/tenbagger/pq_view.py 맨 위 — 매출의 가격·물량 분해, P·Q 사이클 국면·강도·전환 분기
  "quarters_hist": scripts/tenbagger/quarters.py — 분기 손익 20개(싱크로율·매출→GP 비용 다리)
  "debate": scripts/tenbagger/debate_view.py 맨 위 — 등급별 가상 애널리스트 5인 토론, 규칙 등급에서 debate.max_shift 단계까지 조율
  "capacity": scripts/tenbagger/capacity_view.py 맨 위 — 현재 생산능력, 확충 계획, CAPEX와 매출 대비. 시설 위성 판독은 scripts/tenbagger/site_view.py 맨 위
  "multiple_view": {"adj": -0.2, "why": "사이클·실행 할인 등 IB식 판단 한 줄"}   # 조정폭은 config/tenbagger.yaml multiple_select.judge_cap 안에서
  "target_view": {"adj": 0.1, "why": "요인에 안 잡히는 판단 한 줄"}   # 선택. 목표주가 위치 조정, target_price.judge_cap 안에서
  "guidance": {"next": {"period": "4Q26", "rev": 285, "rev_cons": 285, "eps": 0.95, "eps_cons": 1.0, "unit": "$M"}}   # 같은 기간 회사 가이던스 vs 컨센서스, 없는 지표는 뺀다
  "consensus": {"ratings": {"strong_buy": 6, "buy": 0, "hold": 5, "sell": 0, "strong_sell": 0, "as_of": "2026-10-20"}}   # Fiscal.ai company_analyst_ratings
  "next_event": {"date": "2027-02-03", "tag": "4Q26 실적(예상)"}   # 어닝·오퍼링·인베스터데이 중 가장 가까운 것
  "terms": {"Triton": "CPO 광 시험 장비"}   # 이 리포트의 제품명·정책명 풀이
  "currency_symbol": "NOK ", "unit": "BNOK", "unit_usd": 1.0e+8   # 달러가 아닌 종목만. 금액은 현지 통화로 쓴다
JSON '판단 시나리오' 절의 scenario 차트: cases마다 {"name", "prob", "eps" 또는 "ebitda", "why", "color"} — 멀티플·주가는 엔진이 정한다.
"""
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import capacity_view  # noqa: E402
import site_view  # noqa: E402
import customer_view  # noqa: E402
import debate_view  # noqa: E402
import cost_bridge_view  # noqa: E402
import sync_view  # noqa: E402
import pq_view  # noqa: E402
import entry_view  # noqa: E402
import ma_view  # noqa: E402
import flow  # noqa: E402
import input_view  # noqa: E402
import leader_view  # noqa: E402
import levels  # noqa: E402
import margin_view  # noqa: E402
import narrative_view  # noqa: E402
import supply_view  # noqa: E402
import target_price  # noqa: E402

RATINGS = ("Strong Buy", "Buy", "Neutral", "Sell", "Strong Sell")
ANALYST = (("strong_buy", "Strong Buy"), ("buy", "Buy"), ("hold", "Neutral"), ("sell", "Sell"), ("strong_sell", "Strong Sell"))
MODEL_SECTIONS = ("판단 시나리오", "반대 검증", "킬 조건", "셀온 조건", "체크리스트", "재발행 기록", "정정 기록")
BANNED = ("DCF ÷ 시가총액", "주주가치 ÷ 시가총액", "배수 사다리", "컨빅션")
# 한눈에 보기 순서 — 모든 리포트가 이 순서 하나만 쓴다(마스터 지시 2026-10-31, 2026-11-02 "이 구조를 엔진 아키텍처에 영구적으로 설계하라", tests/test_report_layout.py가 고정)
GALLERY = ("일봉", "주봉", "월봉", "실적", "주가 변화 분석", "EPS 리비전", "시나리오", "주가별 업사이드", "포트폴리오", "고객 믹스", "공급 병목", "생산능력", "CAPEX", "위성 판독", "어닝콜 변화",
           "멀티플 프리미엄", "합리적 멀티플", "일별 거래량", "기관 자금", "몬테카를로")
# 맨 아래로 내리는 그림 — 본문에서 올라온 그림(마진·P·Q·싱크로율 등)보다도 뒤(마스터 지시 2026-11-08 "일별 거래량 분해와 기관 자금 흐름은, 몬테카를로는 맨 아래 순서로 내려라")
GALLERY_LAST = ("일별 거래량 분해", "기관 자금 흐름", "몬테카를로")
SHORT_TITLES = {"콜 변화": "어닝콜 변화별 주주가치 영향", "최근 4개 분기 주가": "최근 4개 분기 주가 변화 분석", "일별 거래량": "일별 거래량 분해", "기관 자금": "기관 자금 흐름"}


def sym(dp):
    """표시 통화 — 달러가 아닌 종목은 datapack currency_symbol(예 'NOK ')"""
    return (dp or {}).get("currency_symbol") or "$"


def config():
    return yaml.safe_load((ROOT / "config" / "tenbagger.yaml").read_text(encoding="utf-8"))


def rating(up, rr, dcf_up, cfg):
    """구매 등급(마스터 지시 2026-10-31) — 목표주가 업사이드(2026-11-01)·손익비·DCF 교차 확인으로 규칙이 고른다. 모델이 고르지 않는다. 개인 포지션을 읽지 않는다"""
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
    c.update({"current": price, "unit": sym(dp).strip(), "title": "밸류에이션 주가 시나리오"})
    cases = {k["name"]: k for k in c["cases"]}
    for need in ("약세", "기본", "강세"):
        if need not in cases:
            raise SystemExit(f"판단 시나리오에 {need}가 없다")
    weighted = sum(float(k["prob"]) * k["value"] for k in c["cases"])
    return {"chart": c, "price": price, "bull": cases["강세"]["value"], "base": cases["기본"]["value"], "bear": cases["약세"]["value"], "weighted": weighted,
            "upside": weighted / price - 1, "downside": cases["약세"]["value"] / price - 1, "bull_up": cases["강세"]["value"] / price - 1,
            "rr": reward_risk(price, cases["강세"]["value"], cases["약세"]["value"]) or 0.0, "cases": c["cases"], "metric_name": "EBITDA" if ev_metric else "EPS", "sym": sym(dp)}


FRAME = {"일봉": "일봉", "주봉": "주봉", "월봉": "월봉"}


def plain_level(src):
    """'주봉 피보 61.8%' → '주봉 피보나치 61.8% 되돌림 지지선', '일봉 200일선' → '200일 이동평균선 지지선'(마스터 지시 2026-11-01 "차트 기법상 무엇을 나타내는지 풀어 설명")"""
    s = str(src)
    m = re.search(r"피보\s*([\d.]+%)", s)
    frame = next((f for f in FRAME if s.startswith(f)), "")
    if m:
        return f"{frame} 피보나치 {m.group(1)} 되돌림 지지선".strip()
    m = re.search(r"(\d+)(일|주|개월|월)선", s)
    if m:
        unit = {"일": "일", "주": "주", "개월": "개월", "월": "개월"}[m.group(2)]
        return f"{m.group(1)}{unit} 이동평균선 지지선"
    if "스윙 저점" in s:
        return f"{frame} 직전 저점 지지선".strip()
    return s


def upside_chart(s, zones):
    """주가별 업사이드 — 현재가와 차트 기법 지지선마다 목표주가까지의 업사이드를 막대로(마스터 지시 2026-11-01)"""
    cur, w = s.get("sym", "$"), s.get("target") or s["weighted"]
    rows = [{"label": f"현재 {cur}{s['price']:,.2f}", "bars": [{"name": "현재가", "color": "e", "value": round((w / s["price"] - 1) * 100, 1)}]}]
    for z in zones:
        up = (w / z["mid"] - 1) * 100
        tag = plain_level(z["srcs"][0]) + (f" 외 {len(z['srcs']) - 1}" if len(z["srcs"]) > 1 else "")
        rows.append({"label": f"{cur}{z['mid']:,.2f} {tag}", "bars": [{"name": "지지선", "color": "d" if up >= 0 else "b", "value": round(up, 1)}]})
    return {"kind": "hbars", "w": 640, "label_w": 330, "title": "주가별 업사이드", "unit": "%", "rows": rows}


def _at(rows, idx):
    return rows[idx] if -len(rows) <= idx < len(rows) else None


def actest_chart(dp):
    """분기 매출·EPS 실적 vs 컨센서스 — 지난 4개 분기는 실적과 발표 직전 추정, 앞으로 3개 분기는 컨센서스만"""
    cons = dp.get("consensus") or {}
    rows = cons.get("surprise") or []
    panels = []
    tag = sym(dp).strip()
    for metric, name, scale in (("매출", f"매출({tag}M)" if tag == "$" else f"매출({tag} M)", 1.0), ("EPS", f"EPS({tag})", 1.0)):
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
    # EPS 칸을 매출과 같은 분기로 맞춘다(마스터 지시 2026-11-01 "매출은 당기 전후 3개 분기의 실적·컨센서스가 있는데 EPS도 동일하게")
    base, other = panels[0]["categories"], panels[1]
    both = sorted(set(base) | set(other["categories"]))[:7] if len(base) < 7 else base
    panels = [{**p, "actual": [dict(zip(p["categories"], p["actual"])).get(c) for c in both], "est": [dict(zip(p["categories"], p["est"])).get(c) for c in both], "categories": both} for p in panels]
    return {"kind": "actest", "title": "분기 매출·EPS 실적과 컨센서스", "panels": panels}


def price_charts(entity):
    """일봉·주봉·월봉 — 차트 기법으로 찾은 지지선 + 이동평균선 2개(2026-11-08 마스터 지시로 다시 표기). 지지선 계산은 levels.supports"""
    daily = flow.load_ohlcv(entity)
    if len(daily) < 60:
        return [], []
    if flow.approx_daily(entity):   # 근사 봉은 캔들 모양이 틀린다 — TradingView 실측 일봉을 먼저 넣는다(마스터 지시 2026-11-08)
        raise SystemExit(f"{entity} 일봉이 Fiscal.ai 근사(고가·저가 없음)다 — mcp-tv-get-ohlcv(1D, count 760, format columns — 100주선용 약 3년) 응답을 파일로 저장 → py scripts/fiscal/adapter.py --ohlcv-tv {entity} <파일> <심볼>")
    sp = levels.supports(daily, flow.load_monthly(entity))
    price = sp["price"]
    fmt = (lambda v: f"{v:,.2f}") if price < 1000 else (lambda v: f"{v:,.0f}")
    out = []
    for title, tail in (("일봉", 120), ("주봉", 78), ("월봉", 60)):
        view = sp["bars"][title][-tail:]
        near = [x for x in sp["frames"][title] if x["price"] >= min(b["l"] for b in view) * 0.85][:4]
        marks = [{"y": x["price"], "label": f"{plain_level(x['src']).replace(title + ' ', '').replace(' 지지선', '')} {fmt(x['price'])}", "color": "d"} for x in near]
        # 이동평균선(마스터 지시 2026-11-08 "일봉·주봉·월봉에 이평선 지지선도 표기") — 지지선 엔진 기간(levels.MA_WINDOWS: 일 50·200, 주 20·50, 월 12·24) + 100
        allb = sp["bars"][title]
        ns, unit = levels.MA_WINDOWS[title]
        lines, legend = [], []
        for n, col in zip(sorted(set(ns) | {100}), ("e", "d", "c")):   # 100일·주·개월선 추가(마스터 지시 2026-11-08) — 봉이 모자라면 그 선은 빠진다
            pts = [[allb[i]["date"], sum(b["c"] for b in allb[i - n + 1:i + 1]) / n] for i in range(n - 1, len(allb))]
            pts = [x for x in pts if x[0] >= view[0]["date"]]
            if len(pts) > 1:
                cur = pts[-1][1]
                lines.append({"color": col, "points": pts})
                legend.append({"name": f"{n}{unit}선 {fmt(cur)}" + (" 지지" if cur < price else " 저항"), "color": col})
        # 피보나치 되돌림 전체(23.6~78.6%, 마스터 지시 2026-11-09 "이동평균선뿐 아니라 피보나치도 함께") — 그 봉의 기준 스윙(levels.zones), 보이는 가격대 ±10% 안만.
        # 현재가 아래는 지지(초록), 위는 저항(빨강). 스윙 저점 등 다른 지지선은 피보나치와 겹치지 않는 것만 남긴다
        sw = (sp.get("swings") or {}).get(title) or {}
        lo_v, hi_v = min(b["l"] for b in view), max(b["h"] for b in view)
        fib = [{"y": v, "label": f"피보 {k} {fmt(v)}", "color": "d" if v < price else "b"} for k, v in (sw.get("ret") or {}).items() if lo_v * 0.9 <= v <= hi_v * 1.1]
        marks = fib + [m for m in marks if "피보" not in m["label"] and all(abs(m["y"] - f["y"]) / price > 0.005 for f in fib)]
        if fib:
            legend.append({"name": f"피보나치 되돌림({'상승' if sw.get('up') else '하락'} 스윙 {fmt(sw['low'])}↔{fmt(sw['high'])})", "color": "d"})
        out.append({"kind": "candle", "w": 480, "title": title, "unit": "$", "bars": [[x["date"], x["o"], x["h"], x["l"], x["c"]] for x in view], "hlines": marks,
                    "lines": lines, "legend": legend, "levels": [[plain_level(x["src"]), x["price"]] for x in near]})
    return out, sp["zones"]


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
    cur = sym(dp)
    money = lambda x: f"{cur}{x:,.2f}B"
    tiles = [{"k": "주가", "v": f"{cur}{s['price']:,.2f}", "sub": f"고점 대비 {from_high:+.0%} · 1년 {yr:+.0%}" if from_high is not None else "미확인", "tone": "red" if (from_high or 0) < -0.3 else ""},
             {"k": "시가총액", "v": money(mcap), "sub": f"EV {money(ev)}"},
             {"k": "업사이드", "v": f"{s['upside']:+.0%}", "sub": f"목표주가 {cur}{s['target']:,.0f} · 다운사이드 {s['downside']:+.0%} · 손익비 {s['rr']:.1f}", "tone": "red" if s["upside"] > 0 else "blue"}]
    ra = cons.get("ratings") or {}
    counts = " · ".join(f"{name} {ra.get(k, 0)}" for k, name in ANALYST)
    tiles.append({"k": "구매등급", "v": grade, "sub": f"애널리스트 {sum(ra.get(k, 0) for k, _ in ANALYST)}명: {counts}" if ra else "애널리스트 등급 미확인",
                  "tone": "red" if "Buy" in grade else ("blue" if "Sell" in grade else ""), "second": ra.get("source") in ("easyconomics", "yfinance")})
    tiles.append({"k": "멀티플", "v": f"{mm['label_short']} {mm['current']:.1f}배", "sub": f"동종 중앙값 {mm['peer_p50']:.1f}배"})
    g = (dp.get("guidance") or {}).get("next") or {}
    if g:
        head = " · ".join(x for x in (f"{cur}{g['rev']:,.0f}M" if g.get("rev") is not None else "", f"{cur}{g['eps']:.2f}" if g.get("eps") is not None else "") if x)
        vs = " · ".join(x for x in (f"{cur}{g['rev_cons']:,.0f}M" if g.get("rev_cons") is not None else "", f"{cur}{g['eps_cons']:.2f}" if g.get("eps_cons") is not None else "") if x)
        tiles.append({"k": f"가이던스 {g.get('period', '')}".strip(), "v": head, "sub": f"컨센서스 {vs}" if vs else "컨센서스 미확인"})
    else:
        tiles.append({"k": "가이던스", "v": "없음", "sub": "회사가 숫자를 내지 않았다"})
    tiles.append({"k": "알파", "v": f"{alpha}/10", "sub": "텐배거 가능성 점수"})
    ne = dp.get("next_event") or {}
    tiles.append({"k": "이벤트", "v": str(ne.get("tag") or "미확인"), "sub": str(ne.get("date") or "")})
    return tiles


def moat_section(dp):
    """해자는 회사별로 따로 찾는다 — 정해진 항목이 없다(마스터 지시 2026-11-01 "내가 제시한 명제를 기본 틀로 삼지 말고 기업별로 각각 독립적으로")"""
    m = dp.get("moat") or {}
    items = [x for x in m.get("items") or [] if x.get("kind") and x.get("claim") and x.get("evidence")]
    if len(items) < 2:
        raise SystemExit("datapack moat.items에 이 회사의 해자 2개 이상이 필요하다(kind·claim·evidence·verdict) — report_layout.py 맨 위")
    B = [{"type": "hl", "text": m["summary"]}] if m.get("summary") else []
    B.append({"type": "boxes", "items": [{"title": x["kind"], "tag": x.get("verdict"), "lines": [["해자", x.get("claim")], ["근거", x.get("evidence")], ["숫자", x.get("quant")], ["깨지는 조건", x.get("falsifier")]]}
                                         for x in items]})
    return {"h2": "해자", "blocks": B}


def _pick(blocks, *prefix, typ=None):
    return next((b for b in blocks if (typ is None or b.get("type") == typ) and any(str(b.get("title") or (b.get("chart") or {}).get("title") or "").startswith(p) for p in prefix)), None)


def earnings_blocks(esec):
    """어닝콜 변화 — 표와 해석만, 그래프는 한눈에 보기로"""
    B = (esec or {}).get("blocks") or []
    out = [b for b in (_pick(B, "직전 콜 대비", typ="table"), _pick(B, "사건별 EPS 리비전", typ="table")) if b]   # 실적 vs 컨센서스는 한눈에 보기 그림으로만(마스터 지시 2026-11-01)
    for b in out:
        b["title"] = str(b["title"]).split(" — ")[0].split(" (")[0]
    read = next((b for b in B if b.get("type") == "p" and str(b.get("text")).startswith("**해석:**")), None)
    return out + ([read] if read else [])


def gallery(price, actest, ev_chart, s, esec, mm, flow_sec, sec, zones=None, portfolio=None, supply=None, capacity=(None, None), customers=None, site=None):
    """한눈에 보기 — 그림을 모은 뒤 GALLERY 순서로 낸다. 순서를 바꾸려면 GALLERY만 고친다"""
    E = [b for b in (esec or {}).get("blocks") or [] if b.get("type") == "chart"]
    get = lambda blocks, key: next((dict(b["chart"]) for b in blocks if key in str((b.get("chart") or {}).get("title"))), None)
    parts = {c["title"]: c for c in price}
    parts.update({"실적": actest, "시나리오": s["chart"], "주가별 업사이드": upside_chart(s, zones or []), "포트폴리오": portfolio, "고객 믹스": customers, "공급 병목": supply, "위성 판독": site, "생산능력": capacity[0], "CAPEX": capacity[1], "합리적 멀티플": ev_chart})
    rev = next((dict(b["chart"]) for b in E if b["chart"].get("kind") == "revision"), None)
    if rev:
        rev["title"] = "EPS 리비전"
        parts["EPS 리비전"] = rev
    call = get(E, "콜 변화")
    if call:
        call["title"] = SHORT_TITLES["콜 변화"]
        parts["어닝콜 변화"] = call
    dec = get(E, "최근 4개 분기 주가")
    if dec:
        dec["title"] = SHORT_TITLES["최근 4개 분기 주가"]
        parts["주가 변화 분석"] = dec
    want = "EV/EBITDA" if mm["basis"] != "pe_fwd" else "P/E"
    trend = next((dict(b["chart"]) for b in E if "멀티플 프리미엄 추이" in str(b["chart"].get("title")) and want in str(b["chart"].get("metric"))), None)
    prem = None if trend else get(E, "멀티플 프리미엄")   # 최근 4개 분기 추이가 있으면 그것을(마스터 지시 2026-11-06)
    if trend:
        trend["title"] = f"멀티플 프리미엄({trend['metric']}, 최근 4개 분기말)"
        parts["멀티플 프리미엄"] = trend
    if prem:
        want = "EV/EBITDA" if mm["basis"] != "pe_fwd" else "P/E"
        idx = [i for i, c in enumerate(prem["categories"]) if want in c]
        series = [{**x, "values": [x["values"][i] for i in idx]} for x in prem["series"]]
        # 분기 추이 재료(자기 월말 배수·동종사 분기말 배수)가 없으면 현재값만 — 이유를 제목에 밝힌다(2026-11-07 삼성전자: Fiscal.ai 미수록 종목)
        prem.update({"title": "멀티플 프리미엄(현재값 — 최근 4개 분기 추이 재료 없음)", "categories": [prem["categories"][i] for i in idx], "series": [x for x in series if any(v is not None for v in x["values"])]})
        parts["멀티플 프리미엄"] = prem
    F = [b for b in (flow_sec or {}).get("blocks") or [] if b.get("type") == "chart"]
    for key, name in (("일별 거래량", SHORT_TITLES["일별 거래량"]), ("기관 자금", SHORT_TITLES["기관 자금"])):
        c = get(F, key)
        if c:
            c["title"] = name
            parts[key] = c
    mc = get(sec.get("blocks") or [], "몬테카를로")
    if mc:
        mc["title"] = "몬테카를로"
        mc["categories"] = [f"{(float(x) - 1) * 100:+.0f}%" for x in mc["categories"]]
        mc["conclusion"] = [x for x in mc.get("conclusion") or [] if x.startswith("해석")]
        parts["몬테카를로"] = mc
    return [parts[k] for k in GALLERY if parts.get(k)]


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


def valuation_section(s, sel, mm, r, co, sec, name, decision_line, pt, dp=None):
    """밸류에이션 — 계산은 엔진이 체계적으로, 글은 짧게(마스터 지시 2026-10-31)"""
    mcap = r["mcap"]
    base, bull, bear = r["scenarios"]["base"], r["scenarios"]["bull"], r["scenarios"]["bear"]
    cur = s["sym"]
    B = [{"type": "hl", "text": f"**목표주가 {cur}{pt['target']:,.0f}, 업사이드 {s['upside']:+.0%}.** 자리는 {pt['place']}이고 도달 확률은 약 {pt['reach']:.0%}다. 기본 {cur}{s['base']:,.0f}, 강세 {cur}{s['bull']:,.0f}({s['bull_up']:+.0%}), 약세 {cur}{s['bear']:,.0f}({s['downside']:+.0%}). "
                                f"DCF 기준 업사이드는 기본 {base['v0'] - 1:+.0%}, 강세 {bull['v0'] - 1:+.0%}, 약세 {bear['v0'] - 1:+.0%}다(WACC {r['coc']['wacc']:.1%})."}]
    B.append({"type": "chart", "chart": target_price.chart(pt, s)})
    B.append({"type": "boxes", "items": [{"title": f"{k['name']} {cur}{k['value']:,.0f} ({k['value'] / s['price'] - 1:+.0%})", "tag": f"확률 {k['prob']:.0%}",
                                          "lines": [["가정", f"{k['multiple']:.1f}배 × {s['metric_name']} " + (f"{cur}{k['eps']:.2f}" if k.get("eps") is not None else f"{cur}{k['ebitda']:,.2f}B")], ["근거", k.get("why", "")]]} for k in s["cases"]]})
    B.append({"type": "table", "title": f"멀티플 선정 — {sel['label']}", "headers": ["단계", "조정", "근거"], "rows": sel["rows"]})
    peers = [[x["ticker"]] + [("-" if x.get(k) is None else f"{x[k]:.1f}") for k in sel["keys"]] + [f"{x['growth']:.0%}", f"{x['ebit_margin']:.0%}", "-" if x.get("roic") is None else f"{x['roic']:.0%}"] for x in mm["peers"]]
    B.append({"type": "table", "title": "동종 레인지", "headers": ["회사"] + sel["labels"] + ["성장", "영업이익률", "ROIC"], "rows": peers + [[f"**{name}**"] + [f"{v:.1f}" for v in sel["now"]] + ["", "", ""]]})
    import peg_view   # 성장주는 PEG도(마스터 지시 2026-11-08)
    B.extend(peg_view.blocks(dp, name))
    u = r["upside"]
    tail = f"몬테카를로 중앙값 업사이드 {u['v0_p50'] - 1:+.0%}"
    if u.get("implied_cagr") is not None:
        tail = f"지금 주가가 요구하는 5년 매출 CAGR {u['implied_cagr']:.0%}, 기본 시나리오 {u['base_cagr']:.0%}. " + tail
    B.append({"type": "p", "text": tail + "."})
    if decision_line:
        B.append({"type": "hl", "text": decision_line})
    return {"h2": "밸류에이션", "blocks": B}


def flow_blocks(flow_sec, price_list, cur="$"):
    B = [b for b in (flow_sec or {}).get("blocks") or [] if b.get("type") != "chart" and not str(b.get("text", "")).startswith("**읽는 법")]
    rows = [[c["title"], " · ".join(f"{t} {cur}{v:,.2f}" for t, v in c.get("levels") or []) or "-"] for c in price_list]
    if rows:
        B.append({"type": "table", "title": "지지선", "headers": ["봉", "지지선"], "rows": rows})
    return B


def unglossed(d, dp):
    """풀이 없는 전문 약자 — 금융 용어(plain_ok)·티커가 아니면 report_glossary.yaml 또는 datapack terms에 넣게 한다. 대문자 약자만 잡는다(제품명은 모델이 terms에 쓴다)"""
    g = yaml.safe_load((ROOT / "config" / "report_glossary.yaml").read_text(encoding="utf-8"))
    known = set(g["terms"]) | set(g.get("no_gloss") or {}) | set(g.get("names") or {}) | set(g.get("plain_ok") or []) | set(dp.get("terms") or {}) | set(dp.get("names") or [])
    names = " ".join(known)
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
    found = set(re.findall(r"(?<![A-Za-z0-9/&.\-])[A-Z][A-Z0-9]{1,6}(?![A-Za-z0-9\-])|(?<![A-Za-z0-9])[A-Z][a-z]?[A-Z][A-Za-z0-9]{0,6}(?![A-Za-z0-9\-])", " ".join(text)))
    miss = {x for x in found if x not in known and x not in tick and not re.fullmatch(r"\d?Q\d+|FY\d+|CY\d+|[A-Z]\d+", x)}
    # 제품·사업명은 대문자 약자가 아니어도 풀이가 있어야 한다(마스터 지시 2026-11-01)
    for p in ((dp.get("narrative") or {}).get("lead") or {}).get("products") or []:
        for w in re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", str(p.get("name"))):
            if w not in names:
                miss.add(w)
    return sorted(miss)


def assemble(d, dp, co, r, mm, sel, sec, esec, xs, entity):
    """모델 JSON + 엔진 재료 → 양식 3 리포트 JSON"""
    for s0 in d.get("sections") or []:
        if not s0.get("h2", "").startswith(MODEL_SECTIONS):
            raise SystemExit(f"양식 3 본론에 없는 절: {s0.get('h2')} — 쓸 수 있는 절은 {MODEL_SECTIONS}. 내용은 datapack narrative·moat로 옮긴다")
    input_view.check(dp)
    margin_sec, supply_sec, capacity_sec, customer_sec = margin_view.section(dp), supply_view.section(dp), capacity_view.section(dp), customer_view.section(dp)   # 재료가 없으면 여기서 멈춘다
    shares = r["mcap"] / float(dp["profile"]["price"])
    s = scenario_build(d, dp, mm, sel, shares)
    dcf_up = r["scenarios"]["base"]["v0"] - 1
    cfg = config()
    prof = dp["profile"]
    pt = target_price.build(s, r["scenarios"]["base"]["v0"], r["coc"]["ke"], (dp.get("narrative") or {}).get("stage"), dp.get("target_view"), flow.load_ohlcv(entity),
                            (prof.get("debt") or 0) - (prof.get("cash") or 0), shares, cfg["target_price"], ((dp.get("consensus") or {}).get("ratings") or {}).get("target_mean"))
    s.update({"weighted_up": s["upside"], "target": pt["target"], "upside": pt["upside"]})
    s["chart"].update({"target": pt["target"]})
    grade, deb = debate_view.decide(dp, rating(s["upside"], s["rr"], dcf_up, cfg))   # 규칙 등급 → 가상 애널리스트 5인 토론으로 조율(2026-11-03 마스터 지시)
    v = d.setdefault("verdict", {})
    alpha = v.get("insight") if v.get("insight") is not None else v.get("alpha")
    cur = sym(dp)
    v.update({"rating": grade, "rule_rating": deb["rule"], "upside": round(s["upside"], 4), "downside": round(s["downside"], 4), "rr": round(s["rr"], 3), "price": s["price"], "bear": s["bear"], "bull": s["bull"], "dcf_up": round(dcf_up, 4), "target": pt["target"], "target_text": f"{cur}{pt['target']:,.0f}", "target_place": pt["place"], "target_reach": round(pt["reach"], 3),
              "weighted_upside": round(s["weighted_up"], 4), "upside_basis": f"목표주가 {cur}{pt['target']:,.0f}"})
    v.pop("confidence", None)
    m_short = {"label_short": sel["label"], "current": sel["now"][0], "peer_p50": sel["peer_p50"], "basis": sel["basis"]}
    d["tiles"] = dashboard(dp, s, m_short, alpha, grade, r["mcap"], r["unit"], entity)
    upline = f"**목표주가 {cur}{pt['target']:,.0f}({s['upside']:+.0%}), {pt['place']}다.** 강세 {cur}{s['bull']:,.0f}({s['bull_up']:+.0%})는 {sel['label']} {s['cases'][-1]['multiple']:.1f}배를 강세 {s['metric_name']}에 적용한 값이다. 기본 {cur}{s['base']:,.0f}, 약세 {cur}{s['bear']:,.0f}. 손익비 {s['rr']:.1f}, DCF 기준 업사이드 {dcf_up:+.0%}."
    keep = [x for x in d.get("summary") or [] if not x.get("auto")]
    auto = [{"q": "기업가치를 결정하는 내러티브", "a": ((dp.get("narrative") or {}).get("lead") or {}).get("summary", ""), "auto": True},
            {"q": "밸류에이션 모델로 본 주가 상방은 어디까지인가?", "a": upline, "auto": True}]
    if xs.get("pipeline"):
        import pipeline_view
        auto.append(pipeline_view.summary_item(dp))
    if customer_sec:
        auto.append(customer_view.summary_item(dp))
    auto.append(supply_view.summary_item(dp))
    if capacity_sec:
        auto.append(capacity_view.summary_item(dp))
    d["summary"] = auto + keep
    price, zones = price_charts(entity)
    view = next((h for h in mm.get("horizons") or [] if h["h"] == 1), None)
    pchart = narrative_view.portfolio_chart(dp)
    d["gallery"] = gallery(price, actest_chart(dp), rational_chart(view) if view else None, s, esec, mm, xs.get("flow"), sec, zones, pchart, supply_view.chart(dp), capacity_view.charts(dp), customer_view.chart(dp), site_view.chart(dp))
    model = d.get("sections") or []
    find = lambda *keys: [x for x in model if x.get("h2", "").startswith(keys)]
    bear_blocks = [b for x in find("반대 검증") for b in x.get("blocks") or []]
    sell = [i for x in find("킬 조건", "셀온 조건") for b in x.get("blocks") or [] for i in b.get("items") or []]
    if sell:
        bear_blocks.append({"type": "boxes", "items": [{"title": "셀온 조건", "lines": [[f"조건 {i}", t] for i, t in enumerate(sell, 1)]}]})
    scen_text = [b for x in find("판단 시나리오") for b in x.get("blocks") or [] if b.get("type") != "chart"]
    val = valuation_section(s, sel, mm, r, co, sec, co.get("name", d.get("company")), (sec.get("blocks") or [{}])[-1].get("text") if (sec.get("blocks") or [{}])[-1].get("type") == "hl" else None, pt, dp)
    val["blocks"][1:1] = scen_text
    pressure_line = input_view.valuation_line(dp)
    if pressure_line:
        val["blocks"].append(pressure_line)
    out = [narrative_view.section3(dp, mm), narrative_view.portfolio3(dp)]
    try:   # 제품·서비스 이미지 = 내러티브 절, 분해도 + BOM = 공급망 병목 첫머리(마스터 지시 2026-11-08, image_view)
        import image_view
        imgs = image_view.company_blocks(entity)
    except Exception as exc:   # 이미지 단계가 실패해도 리포트는 멈추지 않는다
        imgs = {"narrative": [{"type": "p", "text": f"이미지 없음({type(exc).__name__})"}], "supply": []}
    # 제품·분해도 사진은 한눈에 보기의 제품·서비스 포트폴리오 바로 다음에(마스터 지시 2026-11-08). 본문에는 BOM 표·'이미지 없음' 줄만 남긴다
    photos = [b for b in imgs["narrative"] + imgs["supply"] if b.get("type") == "image"]
    imgs = {k: [b for b in v if b.get("type") != "image"] for k, v in imgs.items()}
    if photos:
        at = next((i for i, c in enumerate(d["gallery"]) if c is pchart), None)
        at = len([c for c in d["gallery"] if c.get("title") in GALLERY[:GALLERY.index("포트폴리오")]]) if at is None else at + 1
        d["gallery"][at:at] = [{"kind": "image_block", "title": f"사진 {b.get('photo')}. {b.get('title')}", "block": b} for b in photos]
        d["gallery_images"] = photos   # 마크다운·노션 판도 같은 사진을 쓴다
    out[0]["blocks"] = list(out[0].get("blocks") or []) + imgs["narrative"]
    if customer_sec:
        d["sources"] = list(dict.fromkeys((d.get("sources") or []) + customer_sec.pop("_sources")))
        out.append(customer_sec)
    if xs.get("pipeline"):
        import pipeline_view
        d["sources"] = list(dict.fromkeys((d.get("sources") or []) + (xs["pipeline"].pop("_sources", None) or [])))
        out.append(pipeline_view.section3(dp))
    margin_sec["blocks"][1:1] = cost_bridge_view.blocks(dp)   # 매출 → 매출총이익 비용 다리·강도(2026-11-03 마스터 지시)
    margin_sec["blocks"] += input_view.margin_blocks(dp)
    if supply_sec:
        supply_sec["blocks"] += input_view.supply_blocks(dp)
        supply_sec["blocks"][0:0] = imgs["supply"]
    elif imgs["supply"]:
        out.append({"h2": "공급망 병목", "blocks": imgs["supply"]})
    for part in (margin_sec, supply_sec, capacity_sec):
        if part:
            d["sources"] = list(dict.fromkeys((d.get("sources") or []) + part.pop("_sources")))
            out.append(part)
    money = lambda x: f"{cur}{x:,.2f}B"
    out += [x for x in [ma_view.section(dp)] if x]   # M&A 시너지(2026-11-03 마스터 지시)
    out += [moat_section(dp), leader_view.report_section(dp, r, money), {"h2": "약세 논리 및 셀온 조건", "blocks": bear_blocks}, {"h2": "어닝콜 변화", "blocks": earnings_blocks(esec)}] + [x for x in [sync_view.section(dp), pq_view.section(dp)] if x] + [val] + [x for x in [entry_view.section(flow.load_ohlcv(entity), pt["target"])] if x] + [debate_view.section(dp, deb)]   # 매수 위치(일봉, 2026-11-03)   # 거시 지표 싱크로율(2026-11-03 마스터 지시)
    d["support"] = next((f"{cur}{v:,.2f} {t}" for c in price if c["title"] == "일봉" for t, v in (c.get("levels") or [])[:1]), "")   # 수급은 한눈에 보기 그림만(마스터 지시 2026-11-01)
    import social_view   # 커뮤니티 내러티브(Quantral, 2026-11-07 마스터 지시) — 그래프는 아래에서 한눈에 보기로 옮긴다
    out += [x for x in [social_view.section(dp, entity)] if x]
    import sotp_view   # 사업부 가치 합산(ADR-016, 2026-11-07 마스터 지시) — 폭포 그림은 한눈에 보기로
    out += [x for x in [sotp_view.section(entity)] if x]
    market = narrative_view.market_section(dp)   # 셀사이드·바이사이드·언론은 체크리스트 바로 앞(마스터 지시 2026-11-01)
    if market:
        out.append(market)
    out += [{**x, "h2": "체크리스트"} for x in find("체크리스트")] + find("재발행 기록", "정정 기록")
    # 본문의 그래프·사진을 모두 한눈에 보기로 올린다(마스터 지시 2026-11-07 "모든 시각물은 한 눈에 보기에 몰아놔 — 거시 지표 싱크로율, 마진 구조, 제품 사진 등")
    have = {c.get("title") for c in d["gallery"]}
    d["gallery_photos"] = []
    for part in out:
        keep = []
        for b in part.get("blocks") or []:
            if b.get("type") == "chart" and b.get("chart"):
                if b["chart"].get("title") not in have:
                    d["gallery"].append(b["chart"])
                    have.add(b["chart"].get("title"))
            elif b.get("type") == "photos":
                d["gallery_photos"].append(b)
            else:
                keep.append(b)
        part["blocks"] = keep
    last = [c for k in GALLERY_LAST for c in d["gallery"] if c.get("title") == k]
    d["gallery"] = [c for c in d["gallery"] if c.get("title") not in GALLERY_LAST] + last
    # 다음 분기 매출 — 지표 추세 vs 가이던스·컨센서스(싱크로율)는 '분기 매출·EPS 실적과 컨센서스' 바로 아래(마스터 지시 2026-11-08)
    nq = [c for c in d["gallery"] if "지표 추세 vs 가이던스" in str(c.get("title"))]
    at = next((i for i, c in enumerate(d["gallery"]) if c.get("kind") == "actest"), None)
    if nq and at is not None:
        d["gallery"] = [c for c in d["gallery"] if c not in nq]
        d["gallery"][at + 1:at + 1] = nq
    out[:] = [x for x in out if x.get("blocks")]
    d.update({"format": 3, "sections": out, "terms": dp.get("terms") or {}, "names": dp.get("names") or []})

    def zero(o):
        if isinstance(o, dict):
            return {k: zero(x) if k not in ("gallery", "bars") else x for k, x in o.items()}
        if isinstance(o, list):
            return [zero(x) for x in o]
        return re.sub(r"(?<![\d.])-0%", "0%", o) if isinstance(o, str) else o
    d.update({k: zero(d[k]) for k in ("tiles", "summary", "sections")})
    body = str({k: d.get(k) for k in ("verdict", "summary", "sections", "tiles")})
    left = [w for w in BANNED if w in body]
    if left:
        raise SystemExit(f"양식 3에서 쓰지 않는 표기: {left}")
    bad = unglossed(d, dp)
    if bad:
        raise SystemExit(f"풀이 없는 전문 약자: {bad} — 기술·제품·프로젝트·유형자산이면 config/report_glossary.yaml terms 또는 datapack terms, 회사명·티커면 datapack names(풀이하지 않는다), 금융 용어면 plain_ok")
    return d
