"""텐배거 리포트 '마진 구조' 절 (마스터 지시 2026-11-02 "GPM과 OPM 등 마진을 결정하는 비용 요인을 분석하는 항목을 넣어라.
특히 핵심 제품 및 서비스 BOM을 구성하는 요인을 분해하고 각각의 마진 영향력을 분석하라")

숫자는 여기서 계산한다. 모델은 datapack "margin"에 원자료만 쓴다. 모르는 값은 "미확인"으로 두고 지어내지 않는다.
datapack "margin":
  {"as_of": "2026-09-30", "basis": "GAAP", "summary": "한 줄",
   "periods": [{"period": "TTM 3Q25", "rev": 2.1, "cogs": 1.75, "rd": 0.1, "sga": 0.17, "other": 0.0},   # 오래된 기간부터, 마지막이 지금. 금액은 리포트 단위
               {"period": "TTM 3Q26", "rev": 2.44, "cogs": 1.98, "rd": 0.11, "sga": 0.2}],
   "costs": [{"name": "원재료", "stage": "매출원가",   # STAGES 중 하나. 지금 기간 비용 전체를 나눈다(모르는 몫은 '기타' 한 줄)
              "pct_rev": 0.55, "prior_pct": 0.57,      # 매출 대비. 직전 값을 모르면 "미확인"
              "fixed": 0.1,                            # 고정비 몫 0~1, 모르면 "미확인"
              "driver": "무엇이 이 비용을 움직이나", "basis": "공시", "source": "10-K p.31"}],
   "products": [{"name": "제품·서비스", "rev_share": 0.6, "gpm": 0.25, "gpm_basis": "세그먼트 공시",   # 제품 GPM을 모르면 회사 GPM을 쓰고 gpm_basis에 그렇게 쓴다
                 "bom": [{"item": "항목", "share": 0.35,    # 제품 매출원가에서 이 항목의 몫. 범위는 [0.3, 0.4], 모르면 "미확인"
                          "basis": "공시",                  # BASIS 중 하나. '추정'이면 리포트에 그대로 나온다
                          "source": "출처",
                          "pass_through": 0.5,              # 항목 가격 상승을 판매가로 넘기는 몫 0~1, 모르면 "미확인"(0으로 재고 표에 밝힌다)
                          "why": "이 항목 가격을 움직이는 것"}]}]}
  서비스·소프트웨어는 bom에 서비스 원가 항목(인건비·외주·GPU 감가상각·전력·호스팅)을 쓴다.

엔진 계산: GPM·OPM 변화, 비용 요인별 OPM 영향, 영업 레버리지, BOM 항목별 제품 GPM·회사 OPM·영업이익 민감도(가격 +shock, config/supply_bottleneck.yaml margin).
"""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
UNKNOWN = "미확인"
STAGES = ("매출원가", "연구개발", "판관비", "기타")
BASIS = ("공시", "티어다운", "업계", "추정")
TIE = 0.015   # 비용 합과 손익 원자료가 어긋나도 되는 폭(매출 대비)
MIN_REV_SHARE = 0.5   # 핵심 제품이 덮어야 하는 매출 몫
MIN_ITEMS = 3         # 제품마다 몫을 쓴 BOM 항목 수


def config():
    return yaml.safe_load((ROOT / "config" / "supply_bottleneck.yaml").read_text(encoding="utf-8"))


def _num(x):
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def share_of(x):
    """(중앙, 하단, 상단) — 숫자, [하단, 상단], 미확인"""
    if isinstance(x, (list, tuple)) and len(x) == 2 and all(_num(v) is not None for v in x):
        return (x[0] + x[1]) / 2, float(x[0]), float(x[1])
    v = _num(x)
    return (v, v, v) if v is not None else (None, None, None)


def margins(p):
    rev = float(p["rev"])
    opex = sum(float(p.get(k) or 0) for k in ("rd", "sga", "other"))
    gross = rev - float(p["cogs"])
    return {"period": p.get("period"), "rev": rev, "gpm": gross / rev, "rd": float(p.get("rd") or 0) / rev, "sga": float(p.get("sga") or 0) / rev,
            "other": float(p.get("other") or 0) / rev, "opm": (gross - opex) / rev}


def gpm_after(g, share, shock, passed):
    """제품 GPM 변화 — 항목 원가가 shock만큼 오르고 passed만큼 판매가로 넘긴다"""
    d = (1 - g) * share * shock
    return (g - (1 - passed) * d) / (1 + passed * d) - g


def opm_after(opm, weight, g, share, shock, passed):
    """회사 OPM 변화 — weight는 이 제품의 매출 몫"""
    d = weight * (1 - g) * share * shock
    return (opm - (1 - passed) * d) / (1 + passed * d) - opm


def leverage(opm, costs, step):
    """매출이 step 늘 때 OPM 변화 — 고정비 몫을 모르는 비용이 있으면 재지 않는다"""
    if any(_num(c.get("fixed")) is None for c in costs):
        return None
    variable = sum(float(c["pct_rev"]) * (1 - float(c["fixed"])) for c in costs)
    return {"variable": variable, "incremental": 1 - variable, "move": (opm + step * (1 - variable)) / (1 + step) - opm}


def check(mg):
    """예약 회차가 빈칸을 그럴듯하게 채우지 않도록 원자료를 검사한다"""
    periods, costs, products = mg.get("periods") or [], mg.get("costs") or [], mg.get("products") or []
    if len(periods) < 2 or not costs or not products or len(str(mg.get("as_of") or "")) < 7:
        raise ValueError("datapack margin에 as_of, periods 2개 이상, costs, products가 필요하다 — scripts/tenbagger/margin_view.py 맨 위")
    now = margins(periods[-1])
    for c in costs:
        name = c.get("name") or "이름 없음"
        if c.get("stage") not in STAGES or _num(c.get("pct_rev")) is None or not c.get("driver") or c.get("basis") not in BASIS or not c.get("source"):
            raise ValueError(f"margin.costs {name}: stage·pct_rev·driver·basis·source가 필요하다")
        if _num(c.get("fixed")) is None and c.get("fixed") != UNKNOWN or _num(c.get("prior_pct")) is None and c.get("prior_pct") != UNKNOWN:
            raise ValueError(f"margin.costs {name}: fixed·prior_pct가 필요하다(모르면 '미확인')")
    cogs = sum(c["pct_rev"] for c in costs if c["stage"] == "매출원가")
    if abs(cogs - (1 - now["gpm"])) > TIE:
        raise ValueError(f"margin.costs 매출원가 합 {cogs:.1%}이 손익의 {1 - now['gpm']:.1%}와 맞지 않는다 — 모르는 몫은 '기타' 줄로")
    total = sum(c["pct_rev"] for c in costs)
    if abs(total - (1 - now["opm"])) > TIE:
        raise ValueError(f"margin.costs 비용 합 {total:.1%}이 손익의 {1 - now['opm']:.1%}와 맞지 않는다 — 모르는 몫은 '기타' 줄로")
    share = sum(_num(p.get("rev_share")) or 0 for p in products)
    if not MIN_REV_SHARE <= share <= 1 + TIE:
        raise ValueError(f"margin.products 매출 몫 합 {share:.0%} — 핵심 제품으로 매출의 {MIN_REV_SHARE:.0%} 이상을 덮는다")
    for p in products:
        name = p.get("name") or "이름 없음"
        if _num(p.get("gpm")) is None or not p.get("gpm_basis"):
            raise ValueError(f"margin.products {name}: gpm·gpm_basis가 필요하다")
        known = 0
        mids = 0.0
        for b in p.get("bom") or []:
            mid = share_of(b.get("share"))[0]
            if mid is None and b.get("share") != UNKNOWN:
                raise ValueError(f"margin BOM {b.get('item')}: share는 숫자, [하단, 상단], '미확인' 중 하나")
            if not b.get("item") or b.get("basis") not in BASIS or not b.get("source") or not b.get("why"):
                raise ValueError(f"margin BOM {b.get('item')}: item·basis·source·why가 필요하다")
            if _num(b.get("pass_through")) is None and b.get("pass_through") != UNKNOWN:
                raise ValueError(f"margin BOM {b.get('item')}: pass_through가 필요하다(모르면 '미확인')")
            known += mid is not None
            mids += mid or 0
        if known < MIN_ITEMS:
            raise ValueError(f"margin.products {name}: 몫을 쓴 BOM 항목이 {MIN_ITEMS}개 이상 필요하다")
        if mids > 1 + TIE:
            raise ValueError(f"margin.products {name}: BOM 몫 합 {mids:.0%}이 100%를 넘는다")


def compute(dp):
    mg, shock = dp["margin"], config()["margin"]["shock"]
    now = margins(mg["periods"][-1])
    rows = []
    for p in mg["products"]:
        g, w = float(p["gpm"]), float(p["rev_share"])
        for b in p["bom"]:
            mid, lo, hi = share_of(b.get("share"))
            passed = _num(b.get("pass_through"))
            r = {**b, "product": p["name"], "mid": mid, "lo": lo, "hi": hi, "passed": passed, "cost_weight": None, "gpm_move": None, "opm_move": None}
            if mid is not None:
                keep = passed or 0.0
                r.update({"cost_weight": w * (1 - g) * mid, "gpm_move": gpm_after(g, mid, shock, keep), "opm_move": opm_after(now["opm"], w, g, mid, shock, keep)})
            rows.append(r)
    return {"now": now, "periods": [margins(p) for p in mg["periods"]], "items": rows, "shock": shock}


def _pt(x, digits=1):
    return UNKNOWN if x is None else f"{x * 100:+.{digits}f}%p"


def _pct(x, digits=1):
    return UNKNOWN if x is None else f"{x * 100:.{digits}f}%"


def _share_text(r):
    if r["mid"] is None:
        return UNKNOWN
    return _pct(r["mid"], 0) if r["lo"] == r["hi"] else f"{r['lo'] * 100:.0f}~{r['hi'] * 100:.0f}%"


def by_item(items):
    """같은 항목이 여러 제품에 들어가면 회사 OPM 영향을 더한다 — 영향 큰 순서"""
    total = {}
    for r in items:
        if r["opm_move"] is not None:
            total[r["item"]] = total.get(r["item"], 0.0) + r["opm_move"]
    return sorted(total.items(), key=lambda kv: kv[1])


def section(dp):
    mg = (dp or {}).get("margin")
    if not mg:
        raise SystemExit("datapack에 margin이 없다(scripts/tenbagger/margin_view.py 맨 위) — 옛 리포트 정정은 --legacy")
    check(mg)
    c, cfg = compute(dp), config()["margin"]
    now, first, step, tag = c["now"], c["periods"][-2], cfg["rev_step"], f"+{c['shock'] * 100:.0f}%"
    lev = leverage(now["opm"], mg["costs"], step)
    head = f"**GPM {_pct(now['gpm'])}, OPM {_pct(now['opm'])}.** {first['period']} 대비 GPM {_pt(now['gpm'] - first['gpm'])}, OPM {_pt(now['opm'] - first['opm'])}."
    if lev:
        head += f" 변동비는 매출의 {_pct(lev['variable'], 0)}이고, 매출이 {step * 100:.0f}% 늘면 OPM은 {_pt(lev['move'])} 움직인다."
    if mg.get("summary"):
        head += " " + str(mg["summary"])
    B = [{"type": "hl", "text": head}]
    B.append({"type": "table", "title": f"GPM에서 OPM까지({mg.get('basis', 'GAAP')})", "headers": ["기간", "GPM", "연구개발", "판관비", "기타", "OPM"],
              "rows": [[p["period"], _pct(p["gpm"]), _pct(p["rd"]), _pct(p["sga"]), _pct(p["other"]), _pct(p["opm"])] for p in c["periods"]]})
    costs = sorted(mg["costs"], key=lambda k: -k["pct_rev"])
    rows = []
    for x in costs:
        prior = _num(x.get("prior_pct"))
        rows.append([x["name"], _pct(x["pct_rev"]), UNKNOWN if prior is None else _pt(x["pct_rev"] - prior), UNKNOWN if _num(x.get("fixed")) is None else _pct(x["fixed"], 0), _pt(-x["pct_rev"] * c["shock"], 2)])
    B.append({"type": "table", "title": f"마진을 결정하는 비용 요인 — 비용 {tag} 시 OPM", "headers": ["비용", "매출 대비", "변화", "고정비", "OPM"], "rows": rows})
    B.append({"type": "table", "title": "비용을 움직이는 요인", "headers": ["비용", "요인"], "rows": [[f"{x['name']}({x['stage']})", f"{x['driver']} · 근거 {x['basis']}"] for x in costs]})
    B.append({"type": "chart", "chart": {"kind": "hbars", "w": 480, "label_w": 150, "title": f"BOM 항목 가격 {tag} 시 OPM 변화", "unit": "%p",
                                         "rows": [{"label": name, "bars": [{"name": "OPM 변화", "color": "b", "value": round(v * 100, 2)}]} for name, v in by_item(c["items"])[:8]]}})
    for p in mg["products"]:
        items = sorted((r for r in c["items"] if r["product"] == p["name"]), key=lambda r: -(r["mid"] or 0))
        known = sum(r["mid"] or 0 for r in items)
        rest = [["미분해", _pct(max(1 - known, 0), 0), "-", "-", "-"]] if known < 1 - TIE else []
        B.append({"type": "table", "title": f"{p['name']} BOM — 매출의 {_pct(p['rev_share'], 0)}, GPM {_pct(p['gpm'], 0)}({p['gpm_basis']}), 항목 가격 {tag} 시",
                  "headers": ["항목", "원가 몫", "전가", "제품 GPM", "OPM"],
                  "rows": [[r["item"], _share_text(r), UNKNOWN if r["passed"] is None else _pct(r["passed"], 0), _pt(r["gpm_move"]), _pt(r["opm_move"], 2)] for r in items] + rest})
    notes = []
    ranked = by_item(c["items"])
    if ranked and now["opm"] > 0:
        notes.append(f"{ranked[0][0]} 가격이 {tag} 오르면 영업이익은 {ranked[0][1] / now['opm'] * 100:+.1f}% 움직인다.")
    if any(r["passed"] is None and r["mid"] is not None for r in c["items"]):
        notes.append("판매가 전가를 모르는 항목은 전가 0%로 계산했다.")
    if notes:
        B.append({"type": "p", "text": " ".join(notes)})
    seen = list(dict.fromkeys((r["item"], r["why"], r["basis"]) for r in c["items"]))
    B.append({"type": "table", "title": "BOM 항목 가격을 움직이는 것", "headers": ["항목", "요인"], "rows": [[item, f"{why} · 근거 {basis}"] for item, why, basis in seen]})
    return {"h2": "마진 구조", "blocks": B, "_sources": sorted({str(x["source"]) for x in mg["costs"]} | {str(r["source"]) for r in c["items"]})}


def top_item(dp):
    """OPM을 가장 크게 흔드는 BOM 항목 (이름, OPM 변화)"""
    ranked = by_item(compute(dp)["items"])
    return ranked[0] if ranked else None
