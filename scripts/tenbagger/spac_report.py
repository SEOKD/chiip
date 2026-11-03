"""SPAC 종목 리포트 (마스터 지시 2026-11-03 "SPAC 종목은 SPAC 보고서를 중심으로 분석하도록 해라")

합병 전후 스팩은 컨센서스·분기 실적·Fwd 추정이 없어 양식 3 엔진(report_layout)을 쓰지 않는다. 1차 자료는 스팩 서류다:
S-4/F-4·424B3(합병 위임장), 8-K(주총 결과·환매·종결), 슈퍼 8-K, PIPE 계약, 스폰서 계약. 숫자는 여기서 계산하고 모델은 원자료와 판단 글만 쓴다.
datapack "spac" (금액 B$, 주식 백만 주):
  {"as_of": "2026-11-03", "price": 9.29, "trust_per_share": 10.287, "target": "Agility Robotics", "new_ticker": "AGLT", "status": "주총 가결·종결 전",
   "redemption": {"shares": 25.45, "pct": 0.615},
   "cash": {"trust_left": 0.164, "pipe": 0.201, "other": 0.100, "fees": 0.05, "target_cash": 0.0147, "debt": 0.0},   # fees 모르면 생략
   "shares": {"공개 주주(환매 후)": 15.9, "스폰서": 10.4, "PIPE": 20.1, "피인수 기존 주주": 196.0},
   "warrants": [{"name": "공개 워런트", "count": 4.1, "strike": 11.5}],
   "earnout": [{"holder": "피인수 기존 주주", "shares": 15.0, "trigger": 15.0}],
   "lockups": [{"date": "2027-05-03", "who": "스폰서·기존 주주", "shares": 206.0}],
   "fairness": {"low": 1.7, "base": 4.5, "high": 7.3, "by": "평가사 이름"},
   "projections": [{"year": 2027, "rev": 0.05}, …],          # 위임장의 경영진 전망 — 컨센서스가 아니다. 없으면 []
   "peer_ev_rev": 8.0, "burn": 0.17}                           # 동종 EV/매출(선행), 연 현금 소진
모델 글(<id>_spac_model.json): {"title", "subtitle", "biz", "view", "summary": [{"q","a"}], "sections": [{"h2","blocks"}], "sources": [...]}
  모델 절은 엔진 절 뒤에 붙는다(사업·제품·수주의 조건·경쟁·약세 논리·다음 확인 사건).
사용: py scripts/tenbagger/spac_report.py <회사 id> <모델 글 json>  → outputs/tenbagger/reports/<YYYYMMDD>_<티커>.json·.html
목표주가·구매 등급은 내지 않는다(추정 근거가 없다). 경영진 전망은 '경영진 전망'으로만 쓰고 시장 기대로 부르지 않는다.
"""
import json
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
UNKNOWN = "미확인"


def compute(s):
    price = s["price"]
    c = s.get("cash") or {}
    gross = c.get("trust_left", 0) + c.get("pipe", 0) + c.get("other", 0)
    net_cash = gross - c.get("fees", 0) + c.get("target_cash", 0) - c.get("debt", 0)
    basic = sum(s["shares"].values())
    itm = [w for w in s.get("warrants") or [] if price > w["strike"]]
    tsm = sum(w["count"] * (1 - w["strike"] / price) for w in itm)   # 자기주식법 — 행사 대금으로 되사는 몫을 뺀다
    earn = sum(e["shares"] for e in s.get("earnout") or [])
    fully = basic + tsm + earn + sum(w["count"] for w in s.get("warrants") or [] if w not in itm)
    mcap = price * basic / 1000
    ev = mcap - net_cash
    proj = sorted(s.get("projections") or [], key=lambda p: p["year"])
    implied = None
    if s.get("peer_ev_rev") and proj:
        implied = [{"year": p["year"], "rev": p["rev"], "ev": p["rev"] * s["peer_ev_rev"], "price": (p["rev"] * s["peer_ev_rev"] + net_cash) / basic * 1000} for p in proj]
    return {"gross": gross, "net_cash": net_cash, "basic": basic, "fully": fully, "mcap": mcap, "ev": ev, "cash_ps": net_cash / basic * 1000,
            "runway": net_cash / s["burn"] if s.get("burn") else None, "trust_gap": price / s["trust_per_share"] - 1 if s.get("trust_per_share") else None,
            "dilution": fully / basic - 1, "implied": implied, "proj": proj}


def _b(v):
    return UNKNOWN if v is None else f"${v:,.2f}B" if abs(v) >= 1 else f"${v * 1000:,.0f}M"


def sections(s, m):
    own = sorted(s["shares"].items(), key=lambda kv: -kv[1])
    out = []
    head = (f"**합병 후 기본 주식 {m['basic']:,.0f}M주 × ${s['price']:,.2f} = 시가총액 {_b(m['mcap'])}, 순현금 {_b(m['net_cash'])}, EV {_b(m['ev'])}.**"
            f" 주당 순현금 ${m['cash_ps']:,.2f}, 신탁가 대비 주가 {m['trust_gap'] * 100:+.1f}%." if m["trust_gap"] is not None else "")
    B = [{"type": "hl", "text": head}]
    c = s.get("cash") or {}
    steps = [{"label": "신탁 잔액", "value": round(c.get("trust_left", 0) * 1000, 1), "kind": "total"}]
    for k, n in (("pipe", "PIPE"), ("other", "기타 투자")):
        if c.get(k):
            steps.append({"label": n, "value": round(c[k] * 1000, 1), "kind": "cost"})
    if c.get("fees"):
        steps.append({"label": "거래 비용", "value": round(-c["fees"] * 1000, 1), "kind": "cost"})
    if c.get("target_cash"):
        steps.append({"label": "피인수 현금", "value": round(c["target_cash"] * 1000, 1), "kind": "cost"})
    if c.get("debt"):
        steps.append({"label": "차입", "value": round(-c["debt"] * 1000, 1), "kind": "cost"})
    steps.append({"label": "순현금", "value": round(m["net_cash"] * 1000, 1), "kind": "total"})
    B.append({"type": "chart", "chart": {"kind": "waterfall", "title": f"합병 현금 다리($M) — 환매 {s['redemption']['pct'] * 100:.1f}% 뒤", "unit": "$M", "steps": steps}})
    B.append({"type": "chart", "chart": {"kind": "hbars", "w": 480, "label_w": 160, "title": "합병 후 지분 구성(기본 주식)", "unit": "%",
                                         "rows": [{"label": k, "bars": [{"name": "지분", "color": "c", "value": round(v / m["basic"] * 100, 1)}]} for k, v in own]}})
    out.append({"h2": "거래 구조와 현금", "blocks": B})
    rows = [["기본 주식", f"{m['basic']:,.1f}M", "-"]]
    rows += [[f"{w['name']}(행사가 ${w['strike']:,.2f})", f"{w['count']:,.1f}M", "내가격" if s["price"] > w["strike"] else "외가격"] for w in s.get("warrants") or []]
    rows += [[f"언아웃 — {e['holder']}(주가 ${e['trigger']:,.2f} 조건)", f"{e['shares']:,.1f}M", "조건부"] for e in s.get("earnout") or []]
    rows.append(["완전 희석", f"{m['fully']:,.1f}M", f"기본 대비 +{m['dilution'] * 100:.1f}%"])
    D = [{"type": "table", "title": "희석 사다리", "headers": ["항목", "주식", "상태"], "rows": rows}]
    if s.get("lockups"):
        D.append({"type": "table", "title": "보호예수 해제", "headers": ["날짜", "대상", "주식", "기본 주식 대비"],
                  "rows": [[l["date"], l["who"], f"{l['shares']:,.1f}M", f"{l['shares'] / m['basic'] * 100:.0f}%"] for l in s["lockups"]]})
    out.append({"h2": "희석과 오버행", "blocks": D})
    V = []
    f = s.get("fairness") or {}
    cats, vals = ["지금 EV"], [round(m["ev"], 2)]
    for k, n in (("low", "평가사 하단"), ("base", "평가사 기본"), ("high", "평가사 상단")):
        if f.get(k) is not None:
            cats.append(n)
            vals.append(f[k])
    V.append({"type": "chart", "chart": {"kind": "bars", "w": 480, "title": f"지금 EV vs 공정성 의견 범위($B{', ' + f['by'] if f.get('by') else ''})", "unit": "B",
                                         "categories": cats, "series": [{"name": "EV", "color": "c", "values": vals}]}})
    if m["implied"]:
        V.append({"type": "table", "title": f"경영진 전망 × 동종 EV/매출 {s['peer_ev_rev']:.1f}배가 내포하는 주가(경영진 전망은 컨센서스가 아니다)",
                  "headers": ["연도", "경영진 전망 매출", "내포 EV", "내포 주가", "지금 대비"],
                  "rows": [[str(r["year"]), _b(r["rev"]), _b(r["ev"]), f"${r['price']:,.2f}", f"{r['price'] / s['price'] * 100 - 100:+.0f}%"] for r in m["implied"]]})
    if m["runway"]:
        V.append({"type": "p", "text": f"연 현금 소진 {_b(s['burn'])} 기준 순현금으로 약 {m['runway']:.1f}년. 이 기간 안에 매출이 소진을 메우지 못하면 추가 증자가 필요하다."})
    out.append({"h2": "밸류에이션 기준점", "blocks": V})
    return out


def tiles(s, m):
    return [{"k": "주가", "v": f"${s['price']:,.2f}", "sub": f"신탁가 대비 {m['trust_gap'] * 100:+.1f}%" if m["trust_gap"] is not None else ""},
            {"k": "EV", "v": _b(m["ev"]), "sub": f"시가총액 {_b(m['mcap'])}"},
            {"k": "순현금", "v": _b(m["net_cash"]), "sub": f"주당 ${m['cash_ps']:,.2f}"},
            {"k": "환매", "v": f"{s['redemption']['pct'] * 100:.1f}%", "sub": f"{s['redemption']['shares']:,.1f}M주"},
            {"k": "완전 희석", "v": f"+{m['dilution'] * 100:.1f}%", "sub": f"{m['fully']:,.0f}M주"},
            {"k": "현금 버팀", "v": f"{m['runway']:.1f}년" if m["runway"] else UNKNOWN, "sub": f"연 소진 {_b(s.get('burn'))}" if s.get("burn") else ""},
            {"k": "상태", "v": s.get("status", UNKNOWN), "sub": f"새 티커 {s.get('new_ticker', '')}"},
            {"k": "등급", "v": "산정 안 함", "sub": "추정·컨센서스 없음"}]


def build(cid, model_path, today=None):
    dp = json.loads((ROOT / "knowledge" / "models" / "companies" / cid / "datapack.json").read_text(encoding="utf-8"))
    s, mo = dp["spac"], json.loads(Path(model_path).read_text(encoding="utf-8"))
    m = compute(s)
    today = today or date.today()
    d = {"format": 3, "title": mo["title"], "subtitle": mo.get("subtitle"), "date": today.isoformat(), "ticker": dp.get("ticker"), "company": dp.get("name"),
         "biz": mo["biz"], "verdict": {"view": mo["view"]}, "tiles": tiles(s, m), "summary": mo.get("summary") or [],
         "sections": sections(s, m) + (mo.get("sections") or []), "sources": mo.get("sources") or [], "kind": "spac"}
    out = ROOT / "outputs" / "tenbagger" / "reports" / f"{today:%Y%m%d}_{dp.get('ticker')}"
    out.with_suffix(".json").write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    import report_html
    out.with_suffix(".html").write_text(report_html.render(d), encoding="utf-8")
    return out.with_suffix(".html")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    print(build(sys.argv[1], sys.argv[2]))
