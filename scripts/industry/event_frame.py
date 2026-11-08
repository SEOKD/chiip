"""Industry Report '사건 때 심층' 엔진 (마스터 지시 2026-11-08)

마스터의 논리 구조를 고정된 여덟 단계로 계산한다(config/industry_event.yaml):
  ① 사건과 명목 해석 — 시장이 받아들인 해석을 사업군별 상대 수익으로 잰다
  ② 돈의 흐름 — 로비(LD)·PAC·슈퍼 PAC 숫자. 양당 모두에 간 돈을 반드시 확인한다(한쪽만 보면 가설을 확인만 하게 된다)
  ③ 지연 유인 vs 실행 압력 — 시간을 끌수록 자금줄이 이어지는 유인(지대 추출, McChesney 1987)과 결과물을 보여야 하는 압력
  ④ 실행 경로와 시계 — 주·연방 의회·연방 기관·행정부, 정책 단계(금지표: 발의 → 시행 아님), 선거 직후 창
  ⑤ 산업 영향 — 경로마다 실행 확률 p × 사업군 가치 영향(가정, %)
  ⑥ 시장 반영 vs Chiip — 기대 영향 Σp·영향 − 시장 상대 수익 = 갭 → 산업 판단 등급(규칙 계산, 토론은 한 단계까지)
  ⑦ 반대 검증 ⑧ 반증 조건·체크포인트(날짜·확률, predictions.csv에 등록)
datapack: knowledge/models/industries/events/<id>/datapack.json (구조는 build() 참고). 관문을 못 넘으면 SystemExit — 빈칸을 채우지 않는다.
사용: py scripts/industry/event_frame.py <id> [--predictions]   → outputs/industry/<날짜>_<id>.json, 렌더는 industry_html.py
"""
import argparse
import csv
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CFG = ROOT / "config" / "industry_event.yaml"
EVENTS = ROOT / "knowledge" / "models" / "industries" / "events"
OUT = ROOT / "outputs" / "industry"
PRED = ROOT / "knowledge" / "predictions.csv"
STEPS = ["① 사건과 명목 해석", "② 돈의 흐름", "③ 지연 유인 vs 실행 압력", "④ 실행 경로와 시계", "⑤ 산업 영향", "⑥ 시장 반영 vs Chiip", "⑦ 반대 검증", "⑧ 반증 조건·체크포인트"]


def config():
    return yaml.safe_load(CFG.read_text(encoding="utf-8"))


def load(eid):
    return json.loads((EVENTS / eid / "datapack.json").read_text(encoding="utf-8"))


def gate(dp, cfg):
    """관문 — 빠진 것 목록(비면 통과)"""
    g, bad = cfg["gate"], []
    src = lambda x: bool(x.get("source") or x.get("url"))
    if len([r for r in (dp.get("reaction") or {}).get("items") or [] if r.get("rel") is not None]) < g["reaction_min"]:
        bad.append("① 시장 반응 측정값 없음")
    money = [m for m in dp.get("money") or [] if m.get("amount") is not None and src(m)]
    if len(money) < g["money_min"]:
        bad.append(f"② 출처 있는 돈의 흐름 숫자 {len(money)}개(최소 {g['money_min']})")
    if g.get("money_both_parties"):
        parties = {m.get("party") for m in money}
        if not ({"민주", "양당"} & parties and {"공화", "양당"} & parties):
            bad.append("② 양당 모두에 간 돈을 확인하지 않았다")
    inc = dp.get("incentives") or {}
    for k, need, name in (("delay", g["delay_min"], "지연 유인"), ("act", g["act_min"], "실행 압력")):
        if len([x for x in inc.get(k) or [] if src(x)]) < need:
            bad.append(f"③ {name} 근거 부족")
    stages, levels = set(cfg["stages"]), set(cfg["levels"])
    for c in dp.get("channels") or []:
        if c.get("stage") not in stages or c.get("level") not in levels:
            bad.append(f"④ 경로 {c.get('id')} 단계·수준 값 오류({c.get('level')}/{c.get('stage')})")
        if not 0 <= float(c.get("p", -1)) <= 1 or not src(c) or not c.get("window"):
            bad.append(f"④ 경로 {c.get('id')} 확률·시계·출처 누락")
    if not dp.get("channels"):
        bad.append("④ 실행 경로 없음")
    if len([x for x in dp.get("counter") or [] if src(x)]) < g["counter_min"]:
        bad.append("⑦ 반대 근거 부족")
    if len([x for x in dp.get("checkpoints") or [] if x.get("date") and x.get("p") is not None]) < g["checkpoint_min"]:
        bad.append("⑧ 날짜·확률 붙은 체크포인트 부족")
    import logic as LG   # 2026-11-09 이후 사건 심층도 IB 논리 층(결론·논쟁·기대·시나리오·인과 사슬) — ADR-020
    return bad + [f"논리: {b}" for b in LG.gate(dp, "event")]


def market(dp):
    """사업군별 시장 반영 = 소속 종목 상대 수익(벤치마크 대비 %p) 평균"""
    out = {}
    for r in (dp.get("reaction") or {}).get("items") or []:
        if r.get("rel") is not None:
            out.setdefault(r["group"], []).append(float(r["rel"]))
    return {g: sum(v) / len(v) for g, v in out.items()}


def expected(dp, case=None):
    """사업군별 Chiip 기대 영향 = Σ 경로 확률 × 영향(%). case='worst'면 불리한 경로만 모두 실행, 'best'면 유리한 경로만 모두 실행"""
    out = {g["id"]: 0.0 for g in dp["groups"]}
    for c in dp["channels"]:
        for g, v in (c.get("impact") or {}).items():
            v = float(v)
            w = float(c["p"]) if case is None else (1.0 if (v < 0) == (case == "worst") else 0.0)
            out[g] = out.get(g, 0.0) + w * v
    return out


def confidence(dp, cfg):
    """확신도 — 그 사업군에 영향을 주는 경로의 서로 다른 출처 수(4개면 1.0), 교란이 있으면 깎는다"""
    conf = {}
    confound = bool((dp.get("reaction") or {}).get("confound"))
    for g in dp["groups"]:
        srcs = {c.get("source") or c.get("url") for c in dp["channels"] if (c.get("impact") or {}).get(g["id"])}
        v = min(1.0, len(srcs) / 4)
        conf[g["id"]] = max(0.0, v - (cfg["rating"]["confound_penalty"] if confound else 0))
    return conf


def rate(gap, conf, cfg, adjust=0):
    r = cfg["rating"]
    labels = r["labels"]
    i = 1
    if conf >= r["min_confidence"]:
        i = 0 if gap >= r["gap_band"] else (2 if gap <= -r["gap_band"] else 1)
    step = max(-r["debate_max_steps"], min(r["debate_max_steps"], int(adjust or 0)))
    return labels[i], labels[max(0, min(2, i - step))]   # adjust +1 = 한 단계 우호 쪽


def compute(dp, cfg=None):
    cfg = cfg or config()
    m, e, conf = market(dp), expected(dp), confidence(dp, cfg)
    lo, hi = expected(dp, "worst"), expected(dp, "best")
    rows = []
    for g in dp["groups"]:
        gid = g["id"]
        mk = m.get(gid)
        gap = None if mk is None else e[gid] - mk
        rule, final = rate(gap if gap is not None else 0.0, conf[gid] if gap is not None else 0.0, cfg, ((dp.get("debate") or {}).get(gid) or {}).get("adjust", 0))
        rows.append({"id": gid, "name": g["name"], "market": mk, "expected": e[gid], "gap": gap, "conf": conf[gid], "rule": rule, "rating": final,
                     "worst": lo[gid], "best": hi[gid], "why": ((dp.get("debate") or {}).get(gid) or {}).get("reason")})
    return rows


def pct(x, d=1, unit="%"):
    return "미확인" if x is None else f"{x:+.{d}f}{unit}"


def build(dp, cfg=None):
    """datapack → 리포트 JSON(industry_html이 그린다). 글은 datapack narrative, 숫자·표·그림은 여기서"""
    cfg = cfg or config()
    bad = gate(dp, cfg)
    if bad:
        raise SystemExit("사건 심층 관문 미통과 — " + " · ".join(bad))
    rows = compute(dp, cfg)
    nar = dp.get("narrative") or {}
    grp = {g["id"]: g["name"] for g in dp["groups"]}
    rx = dp["reaction"]
    sec = []
    # ① 명목 해석
    B = [{"type": "hl", "text": nar.get("nominal", "")},
         {"type": "table", "title": f"사업군별 시장 반응 — {rx['window']}, {rx['benchmark']} 대비", "headers": ["사업군", "종목", "수익률", "상대(%p)"],
          "rows": [[grp.get(r["group"], r["group"]), r["name"], pct(r.get("ret")), pct(r.get("rel"), unit="%p")] for r in rx["items"]]}]
    if rx.get("etf"):
        B.append({"type": "table", "title": "업종 ETF 선거 뒤 비정상 누적 수익(CAR, 시장 모형)", "headers": ["ETF", "CAR", "t"],
                  "rows": [[x["name"], pct(x["car"]), f"{x['t']:+.2f}"] for x in rx["etf"]]})
    if rx.get("confound"):
        B.append({"type": "p", "text": "교란: " + rx["confound"]})
    sec.append({"h2": STEPS[0], "blocks": B})
    # ② 돈의 흐름
    money = dp["money"]
    B = [{"type": "hl", "text": nar.get("money", "")},
         {"type": "table", "title": "규제산업의 정치 자금 — 로비(LD)·PAC·슈퍼 PAC", "headers": ["종류", "누가", "금액", "어느 쪽", "기간", "출처"],
          "rows": [[m["kind"], m["who"], m.get("amount_text") or f"${m['amount']:,.0f}", m["party"], m.get("period", ""), m.get("source", "")] for m in money]}]
    sec.append({"h2": STEPS[1], "blocks": B})
    # ③ 지연 vs 실행
    inc = dp["incentives"]
    n = max(len(inc["delay"]), len(inc["act"]))
    cell = lambda xs, i: f"{xs[i]['text']} ({xs[i].get('source', '')})" if i < len(xs) else ""
    sec.append({"h2": STEPS[2], "blocks": [{"type": "hl", "text": nar.get("incentives", "")},
                                         {"type": "table", "title": "시간을 끌 유인 vs 결과물을 보여야 할 압력", "headers": ["지연 유인", "실행 압력"],
                                          "rows": [[cell(inc["delay"], i), cell(inc["act"], i)] for i in range(n)]}]})
    # ④ 경로와 시계
    B = [{"type": "hl", "text": nar.get("channels", "")},
         {"type": "table", "title": "실행 경로 — 누가, 어느 단계에서, 언제", "headers": ["경로", "수준", "현재 단계", "주체", "창", "12개월 실행 확률", "근거"],
          "rows": [[c["name"], c["level"], c["stage"], c.get("actor", ""), c["window"], f"{float(c['p']):.0%}", c.get("source", "")] for c in dp["channels"]]},
         {"type": "table", "title": "실행 시계 — 선거 직후 창", "headers": ["날짜", "무엇", "의미"], "rows": [[x["date"], x["what"], x.get("why", "")] for x in dp.get("clock") or []]}]
    if dp.get("analog"):
        B.append({"type": "table", "title": "선례 — 집권 직후 실행 속도", "headers": ["선례", "숫자", "출처"], "rows": [[a["what"], a["number"], a.get("source", "")] for a in dp["analog"]]})
    sec.append({"h2": STEPS[3], "blocks": B})
    # ⑤ 영향 행렬
    gids = [g["id"] for g in dp["groups"]]
    sec.append({"h2": STEPS[4], "blocks": [{"type": "hl", "text": nar.get("impact", "")},
                                         {"type": "table", "title": "경로별 사업군 가치 영향(실행 시, %, 가정) × 확률", "headers": ["경로", "확률"] + [grp[g] for g in gids],
                                          "rows": [[c["name"], f"{float(c['p']):.0%}"] + [pct((c.get("impact") or {}).get(g)) if (c.get("impact") or {}).get(g) is not None else "-" for g in gids]
                                                   for c in dp["channels"]]}]})
    # ⑥ 시장 vs Chiip
    B = [{"type": "hl", "text": nar.get("gap", "")},
         {"type": "table", "title": "산업 판단 등급 — 규칙 계산(갭 ±" + f"{cfg['rating']['gap_band']:.0f}%p, 확신도 {cfg['rating']['min_confidence']:.1f} 이상)",
          "headers": ["사업군", "시장 반영(SPY 대비)", "Chiip 기대 영향", "갭", "확신도", "규칙 등급", "최종", "최악(불리한 경로 전부)", "최선(유리한 경로 전부)"],
          "rows": [[r["name"], pct(r["market"], unit="%p"), pct(r["expected"]), pct(r["gap"], unit="%p"), f"{r['conf']:.2f}", r["rule"], r["rating"], pct(r["worst"]), pct(r["best"])] for r in rows]}]
    adj = [f"{r['name']}: {r['rule']} → {r['rating']} — {r['why']}" for r in rows if r["rule"] != r["rating"] and r.get("why")]
    if adj:
        B.append({"type": "ul", "items": adj})
    sec.append({"h2": STEPS[5], "blocks": B})
    sec.append({"h2": STEPS[6], "blocks": [{"type": "hl", "text": nar.get("counter", "")}, {"type": "ul", "items": [f"{x['text']} ({x.get('source', '')})" for x in dp["counter"]]}]})
    sec.append({"h2": STEPS[7], "blocks": [{"type": "table", "title": "확인할 사건 — 날짜·Chiip 확률(predictions.csv 등록)", "headers": ["기한", "무엇", "잴 것", "확률", "맞으면"],
                                          "rows": [[x["date"], x["what"], x.get("metric", ""), f"{float(x['p']):.0%}", x.get("confirms", "")] for x in dp["checkpoints"]]},
                                         {"type": "p", "text": nar.get("kill", "")}]})
    sec.append({"h2": "종료 상태", "blocks": [{"type": "p", "text": nar.get("status", "")}]})
    import logic as LG
    LS = LG.sections(dp, "event")
    if LS:
        out = [{"h2": "결론", "blocks": LS["bottom"]}]
        for x in sec:
            if x["h2"] == STEPS[5]:
                x["blocks"] = LS.get("expectations", []) + x["blocks"] + LS.get("scenarios", [])
            if x["h2"] == STEPS[6] and LS.get("debates"):
                out.append({"h2": "핵심 논쟁", "blocks": LS["debates"]})
            out.append(x)
            if x["h2"] == STEPS[4]:
                out += [{"h2": h, "blocks": LS[k]} for k, h in (("drivers", "동인 분해"), ("cycle", "사이클 지표판"), ("profit_pool", "이익 풀 이동")) if LS.get(k)]
        sec = out
    image_plan = place_images(dp, sec, cfg)
    gallery = charts(dp, rows)
    return {"kind": "industry_event", "id": dp["id"], "title": dp["title"], "subtitle": dp.get("subtitle", ""), "date": dp["date"], "industry": dp["industry"],
            "event": dp["event"]["name"], "value_add": dp.get("value_add", []), "verdict": {"view": nar.get("view", "")},
            "ratings": [{"name": r["name"], "rating": r["rating"]} for r in rows],
            "tiles": dp.get("tiles") or [], "summary": [{"q": q, "a": a} for q, a in nar.get("summary", [])], "gallery": gallery, "sections": sec,
            "sources": dp.get("sources") or [], "terms": dp.get("terms") or {}, "names": dp.get("names") or [], "image_plan": image_plan}


IMG_CONDITIONS = ("구조", "병목 위치", "세대 비교", "생소한 제품", "공급사 지도")   # 산업 이미지 지시서 1절 — 하나라도 해당해야 넣는다


def place_images(dp, sec, cfg=None):
    """datapack images[{section, product, condition, view?}] → 그 절 첫머리에 제품·분해도·BOM 블록(마스터 지시 2026-11-08 산업판 1·5절).
    리포트당 최대 3장(분해도 2). 조건이 표에 없거나 절이 없으면 넣지 않는다. 판정 기록(절·조건·종류·재사용·예상 비용)을 돌려준다"""
    plan = []
    want = dp.get("images") or []
    if not want:
        return plan
    sys.path.insert(0, str(ROOT / "scripts" / "tenbagger"))
    import image_view
    import product_images as PI
    k = 0
    c = PI.cfg()
    lim = c["per_industry_report_max"]
    for w in want[:lim["total"]]:
        target = next((s for s in sec if s["h2"].startswith(w["section"])), None)
        if not target or w.get("condition") not in IMG_CONDITIONS:
            plan.append({"section": w.get("section"), "condition": w.get("condition"), "kind": None, "reuse": None, "usd": 0, "why": "절 없음" if not target else "조건 표 밖"})
            continue
        try:
            blocks, k = image_view.product_blocks(w["product"], k, w.get("view"), c)
        except (OSError, ValueError, KeyError) as exc:
            plan.append({"section": w["section"], "condition": w["condition"], "kind": None, "reuse": None, "usd": 0, "why": f"BOM 없음({type(exc).__name__})"})
            continue
        target["blocks"][0:0] = blocks
        for t in PI.targets_product(w["product"], w.get("view"), c):
            hit = PI.cached(t, c)
            plan.append({"section": w["section"], "condition": w["condition"], "kind": t["kind"], "product": w["product"], "reuse": bool(hit), "usd": 0 if hit else PI.est_cost(t, True, c)})
    return plan


def charts(dp, rows):
    out = [{"kind": "hbars", "w": 560, "label_w": 170, "title": "시장 반영 vs Chiip 기대 영향(사업군, %p)", "unit": "%p",
            "rows": [{"label": r["name"], "bars": [{"name": "시장 반영", "color": "b", "value": round(r["market"], 1)},
                                                    {"name": "Chiip 기대", "color": "c", "value": round(r["expected"], 1)}]} for r in rows if r["market"] is not None]}]
    money = [m for m in dp["money"] if m["kind"] == "로비(LD)" and m.get("amount")]
    if money:
        out.append({"kind": "bars", "title": "분기 로비 지출(하원 LD, $M)", "unit": "", "categories": [m["who"] for m in money],
                    "series": [{"name": m.get("period", ""), "color": "c", "values": [round(x["amount"] / 1e6, 2) for x in money]} for m in money[:1]]})
    pac = [m for m in dp["money"] if m["kind"] == "PAC 기부" and m.get("split")]
    if pac:
        out.append({"kind": "bars", "stack": True, "title": "기업 PAC 기부 — 정당별($K, FEC 상위 기부 기준)", "unit": "", "categories": [m["who"] for m in pac],
                    "series": [{"name": "민주", "color": "c", "values": [round(m["split"]["민주"] / 1e3) for m in pac]},
                               {"name": "공화", "color": "b", "values": [round(m["split"]["공화"] / 1e3) for m in pac]}]})
    if dp.get("pipeline"):
        out.append({"kind": "hbars", "w": 560, "label_w": 170, "title": dp["pipeline"]["title"], "unit": "",
                    "rows": [{"label": x["label"], "bars": [{"name": "GW", "color": "d" if x.get("dem") else "e", "value": x["gw"]}]} for x in dp["pipeline"]["rows"]]})
    if (dp.get("reaction") or {}).get("paths"):
        out.append({"kind": "line", "title": "업종 ETF 일별 비정상 수익 누적(선거일 = 0)", "unit": "%", "series": dp["reaction"]["paths"]})
    return out


def register(dp, made_on, tag="IND", origin="industry_event", basis="Industry Report 사건 심층"):
    """⑧ 체크포인트를 예측 장부에 올린다(이미 있으면 건너뛴다). 사후 수정 금지 — 정정은 새 행"""
    with PRED.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows, fields = list(reader), reader.fieldnames
    have = {r["pred_id"] for r in rows}
    add = []
    for i, x in enumerate(dp["checkpoints"], 1):
        pid = f"P-{made_on.replace('-', '')}-{tag}{i}"
        if pid in have:
            continue
        add.append({**{k: "" for k in fields}, "pred_id": pid, "made_on": made_on, "thesis_id": dp["id"], "statement": x["what"], "metric": x.get("metric", ""),
                    "target": x.get("target", ""), "deadline": x["date"], "probability": x["p"], "basis": x.get("basis", basis), "owner": "Chiip", "origin": origin})
    if add:
        with PRED.open("a", encoding="utf-8", newline="") as f:
            csv.DictWriter(f, fieldnames=fields).writerows(add)
    return len(add)


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("id")
    ap.add_argument("--predictions", action="store_true")
    a = ap.parse_args(argv)
    dp = load(a.id)
    d = build(dp)
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"{dp['date'].replace('-', '')}_{dp['id']}.json"
    p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[사건 심층] {p}")
    for r in d["ratings"]:
        print(f"  {r['name']}: {r['rating']}")
    if a.predictions:
        print(f"  예측 장부 {register(dp, dp['date'])}행 추가")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
