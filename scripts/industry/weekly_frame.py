"""Chiip Industry Weekly 조립 (마스터 지시 2026-11-08 — 매주 일요일 08:00 KST 산업 하나, IB 산업 노트 양식)

datapack(knowledge/models/industries/weekly/<YYYY-Www>-<산업>/datapack.json) → 리포트 JSON(outputs/industry/<날짜>_weekly-<산업>.json, industry_html이 그린다).
절(2026-11-08 고도화: 결론·핵심 논쟁·동인 분해·사이클 지표판·이익 풀·가격 내포 기대·시나리오를 logic.py가 끼운다): ① 왜 지금(선정 점수 — weekly_pick) ② 수요 ③ 공급·캐파 ④ 병목·가격 ⑤ 가치사슬 지도 ⑥ 시장 반영 vs Chiip(사업군 등급)
    ⑦ 반대 검증 ⑧ 반증 조건·체크포인트(predictions.csv 등록) ⑨ 종료 상태.
등급은 사건 심층과 같은 규칙(event_frame.rate — 갭 ±5%p·확신도 0.5, 토론 조정은 한 단계). 매매·비중·금액 지시가 아니다.
datapack 필수: industry, week, title, narrative{view, summary, demand, supply, bottleneck, counter, kill, status},
  segments[{id, name, market, expected, confidence}](2개 이상), value_chain[{layer, who, bottleneck}], checkpoints[{date, what, metric, p, confirms}](2개 이상),
  counter[{text, source}], sources(3개 이상). 선택: kpis, tiles, images(산업 이미지 지시서), debate{seg_id: {adjust, why}}.
사용: py scripts/industry/weekly_frame.py <폴더 이름> [--predictions]
"""
import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import event_frame as E  # noqa: E402
import logic as LG  # noqa: E402
import weekly_pick as W  # noqa: E402

BASE = ROOT / "knowledge" / "models" / "industries" / "weekly"
NEED_NAR = ("view", "summary", "demand", "supply", "bottleneck", "counter", "kill", "status")


def gate(dp):
    bad = []
    for k in ("industry", "week", "title", "segments", "value_chain", "checkpoints", "counter", "sources"):
        if not dp.get(k):
            bad.append(f"{k} 없음")
    nar = dp.get("narrative") or {}
    bad += [f"narrative.{k} 없음" for k in NEED_NAR if not nar.get(k)]
    if len(dp.get("segments") or []) < 2:
        bad.append("사업군 2개 미만")
    for s in dp.get("segments") or []:
        if not isinstance(s.get("market"), (int, float)) or not isinstance(s.get("expected"), (int, float)):
            bad.append(f"사업군 {s.get('name')}: market·expected 숫자 필요(%p)")
    if len(dp.get("checkpoints") or []) < 2:
        bad.append("체크포인트 2개 미만")
    if len(dp.get("sources") or []) < 3:
        bad.append("출처 3개 미만")
    return bad + [f"논리: {b}" for b in LG.gate(dp, "weekly")]


def rows_of(dp, cfg):
    out = []
    for s in dp["segments"]:
        gap = s["expected"] - s["market"]
        adj = ((dp.get("debate") or {}).get(s["id"]) or {})
        rule, final = E.rate(gap, float(s.get("confidence") or 0), cfg, adj.get("adjust", 0))
        out.append({**s, "gap": gap, "rule": rule, "rating": final, "why": adj.get("why", "")})
    return out


def why_now(dp):
    """선정 점수표 상위 3 — 이 산업을 이번 주에 쓰는 이유(시의성)"""
    r = W.rank()
    top = r[:3]
    rows = [[x["name"], f"{x['score']:.2f}"] + [f"{v[0]}" for v in x["parts"].values()] for x in top]
    me = next((x for x in r if x["industry"] == dp["industry"]), None)
    hl = dp.get("why_now") or (f"이번 주 선정 점수 {me['score']:.2f}" + (f"({', '.join(me['notes'])})" if me and me["notes"] else "") if me else "")
    return [{"type": "hl", "text": hl},
            {"type": "table", "title": "이번 주 산업 선정 — 상위 3(촉매·가격·뉴스 가속·1차 사건·알파·논쟁, 0~10)", "headers": ["산업", "점수", "촉매", "가격", "뉴스 가속", "1차 사건", "알파", "논쟁"], "rows": rows}]


def build(dp, cfg=None):
    cfg = cfg or E.config()
    bad = gate(dp)
    if bad:
        raise SystemExit("주간 산업 관문 미통과 — " + " · ".join(bad))
    nar = dp["narrative"]
    rows = rows_of(dp, cfg)
    pct = E.pct
    sec = [{"h2": "① 왜 지금", "blocks": why_now(dp)},
           {"h2": "② 수요", "blocks": [{"type": "p", "text": nar["demand"]}] + ([{"type": "table", "title": "핵심 지표", "headers": ["지표", "값", "기준", "출처"],
                                                                               "rows": [[k["name"], k["value"], k.get("as_of", ""), k.get("source", "")] for k in dp["kpis"]]}] if dp.get("kpis") else [])},
           {"h2": "③ 공급·캐파", "blocks": [{"type": "p", "text": nar["supply"]}]},
           {"h2": "④ 병목·가격", "blocks": [{"type": "p", "text": nar["bottleneck"]}] + ([{"type": "p", "text": nar["pricing"]}] if nar.get("pricing") else [])},
           {"h2": "⑤ 가치사슬 지도", "blocks": [{"type": "table", "title": "층별 공급사·병목", "headers": ["층", "누가", "병목", "메모"],
                                              "rows": [[v["layer"], v["who"], v.get("bottleneck", ""), v.get("note", "")] for v in dp["value_chain"]]}]},
           {"h2": "⑥ 시장 반영 vs Chiip", "blocks": [{"type": "hl", "text": nar.get("gap") or nar["view"]},
                                                  {"type": "table", "title": f"사업군 판단 등급 — 규칙 계산(갭 ±{cfg['rating']['gap_band']:.0f}%p, 확신도 {cfg['rating']['min_confidence']:.1f} 이상)",
                                                   "headers": ["사업군", "시장 반영", "Chiip 기대", "갭", "확신도", "규칙", "최종"],
                                                   "rows": [[r["name"], pct(r["market"], unit="%p"), pct(r["expected"], unit="%p"), pct(r["gap"], unit="%p"), f"{float(r.get('confidence') or 0):.2f}", r["rule"], r["rating"]] for r in rows]}]
            + [{"type": "p", "text": f"{r['name']}: {r['rule']} → {r['rating']} — {r['why']}"} for r in rows if r["rule"] != r["rating"] and r.get("why")]},
           {"h2": "⑦ 반대 검증", "blocks": [{"type": "hl", "text": nar["counter"]}, {"type": "ul", "items": [f"{x['text']} ({x.get('source', '')})" for x in dp["counter"]]}]},
           {"h2": "⑧ 반증 조건·체크포인트", "blocks": [{"type": "table", "title": "확인할 사건 — 날짜·Chiip 확률(predictions.csv 등록)", "headers": ["기한", "무엇", "잴 것", "확률", "맞으면"],
                                                   "rows": [[x["date"], x["what"], x.get("metric", ""), f"{float(x['p']):.0%}", x.get("confirms", "")] for x in dp["checkpoints"]]},
                                                  {"type": "p", "text": nar["kill"]}]},
           {"h2": "종료 상태", "blocks": [{"type": "p", "text": nar["status"]}]}]
    LS = LG.sections(dp, "weekly")
    if LS:   # IB 산업 노트의 사고 순서 — 결론 먼저, 논쟁, 동인, 기대, 시나리오(ADR-020)
        ins = {"① 왜 지금": ("debates", "핵심 논쟁"), "② 수요": ("market_size", "시장 규모(TAM)"), "③ 공급·캐파": ("drivers", "동인 분해 — 물량 × 가격"),
               "④ 병목·가격": ("cycle", "사이클 지표판")}
        ins2 = {"③ 공급·캐파": ("roadmap", "기술 로드맵"), "⑤ 가치사슬 지도": ("comps", "경쟁 구도·밸류에이션 비교")}
        out = [{"h2": "결론", "blocks": LS["bottom"]}]
        for x in sec:
            if x["h2"].startswith("⑤") and LS.get("profit_pool"):
                x["blocks"] += LS["profit_pool"]
            if x["h2"].startswith("⑥"):
                x["blocks"] = LS.get("expectations", []) + x["blocks"] + LS.get("scenarios", [])
            out.append(x)
            for m in (ins, ins2):
                k = m.get(x["h2"])
                if k and LS.get(k[0]):
                    out.append({"h2": k[1], "blocks": LS[k[0]]})
        sec = out
    image_plan = E.place_images(dp, sec)
    return {"kind": "industry_weekly", "cycle": "weekly", "id": f"weekly-{dp['industry']}-{dp['week']}", "title": dp["title"], "subtitle": dp.get("subtitle", ""),
            "date": dp["date"], "industry": dp.get("industry_name") or W.cfg()["industries"][dp["industry"]]["name"], "event": f"{dp['week']} 주간 산업",
            "value_add": dp.get("value_add", []), "verdict": {"view": nar["view"]}, "ratings": [{"name": r["name"], "rating": r["rating"]} for r in rows],
            "tiles": dp.get("tiles") or [], "summary": [{"q": q, "a": a} for q, a in nar["summary"]], "gallery": [], "sections": sec,
            "sources": dp["sources"], "terms": dp.get("terms") or {}, "names": dp.get("names") or [], "image_plan": image_plan}


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--predictions", action="store_true")
    a = ap.parse_args(argv)
    dp = json.loads((BASE / a.folder / "datapack.json").read_text(encoding="utf-8"))
    d = build(dp)
    out = ROOT / "outputs" / "industry" / f"{dp['date'].replace('-', '')}_weekly-{dp['industry']}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    if a.predictions:
        E.register({**dp, "id": dp.get("id") or f"weekly-{dp['industry']}-{dp['week']}"}, dp["date"], "INW", "industry_weekly", "Industry Weekly")
    print(f"[Industry Weekly] {out.relative_to(ROOT)}")
    for r in d["ratings"]:
        print(f"  {r['name']}: {r['rating']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
