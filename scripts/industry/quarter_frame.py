"""Chiip Industry Quarterly 조립 — 산업 하나의 분기 결산 리포트 (ADR-018, 마스터 결정 2026-11-08: 산업마다 따로)

입력: 종목 장부 knowledge/models/industries/quarterly/<YYYYQn>/members.csv(radar/industry_quarter.py) + 글 datapack
      knowledge/models/industries/quarterly/<YYYYQn>/<산업>/datapack.json
datapack 필수: narrative{view, summary[[q,a]], changed, why, winners, cycle, counter, kill, status}, segments[{id,name,market,expected,confidence}](2+),
  checkpoints[{date, what, metric, p, confirms}](2+), counter[{text, source}], sources(3+). 선택: value_chain_shift, debate, images, trial(시험판 문구).
숫자는 장부에서 계산한다(모델이 쓰지 않는다): 매출 성장(전년·전분기)·GPM 변화·재고 변화·CAPEX 변화·다음 분기 컨센서스 내포 성장·시즌 전 기대 대비 서프라이즈.
가중은 대략 달러 환산 매출(config/industry_quarterly.yaml fx_usd — 가중용, 보고 숫자는 각 통화 그대로).
절(2026-11-08 고도화, ADR-020): 결론(한 문장 + 인과 사슬) → ① 핵심 논쟁 → ② 시즌 스코어카드(세그먼트 풀 산업은 사업부 매출 기준, 회사 전체 지표는 따로)
    → ③ 동인 분해(물량 × 가격, 실제와의 잔차) → ④ 무엇이 바뀌었나 → ⑤ 사이클 지표판 → ⑥ 이익 풀 → ⑦ 가격 내포 기대 vs Chiip(등급) → ⑧ 시나리오
    → ⑨ 지난 판단 채점 → ⑩ 반대 검증 → ⑪ 체크포인트·반증(INQ 등록) → 종료 상태. 논리 관문 scripts/industry/logic.py.
사용: py scripts/industry/quarter_frame.py <YYYYQn> <산업> [--predictions]
"""
import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "radar"))
import event_frame as E  # noqa: E402
import industry_segments as S  # noqa: E402
import logic as LG  # noqa: E402
import industry_quarter as IQ  # noqa: E402
import weekly_frame as WF  # noqa: E402
import weekly_pick as W  # noqa: E402

NEED = ("view", "summary", "changed", "why", "winners", "cycle", "counter", "kill", "status")


def f(x):
    return IQ._f(x)


def ratio(a, b):
    a, b = f(a), f(b)
    return a / b - 1 if a is not None and b else None


def member_rows(quarter, industry, c=None):
    """종목별 계산 — 장부 값에서만"""
    c = c or IQ.cfg()
    out = []
    for (ind, cid), r in IQ.load(quarter).items():
        if ind != industry:
            continue
        rev, gp, gpy = f(r.get("rev")), f(r.get("gp")), f(r.get("gp_prev_y"))
        revy = f(r.get("rev_prev_y"))
        gpm = gp / rev if gp is not None and rev else None
        gpm_y = gpy / revy if gpy is not None and revy else None
        inv, invq = f(r.get("inventory")), f(r.get("inventory_prev_q"))
        cap, capy = f(r.get("capex")), f(r.get("capex_prev_y"))
        fx = c["fx_usd"].get((r.get("currency") or "USD").upper())
        out.append({"id": cid, "name": r.get("name") or cid, "currency": r.get("currency"), "reported": r.get("period") == quarter and rev is not None,
                    "rev": rev, "rev_yoy": ratio(rev, revy), "rev_qoq": ratio(rev, r.get("rev_prev_q")), "gpm": gpm,
                    "gpm_chg": (gpm - gpm_y) if gpm is not None and gpm_y is not None else None,
                    "inv_qoq": ratio(inv, invq), "capex_yoy": ratio(abs(cap) if cap is not None else None, abs(capy) if capy is not None else None),
                    "next_q_growth": ratio(r.get("next_q_cons"), rev), "surprise": ratio(rev, r.get("cons_pre_q")),
                    "w": (rev or 0) * fx if fx else None, "guide_note": r.get("guide_note") or "", "inventory_note": r.get("inventory_note") or "",
                    "broker_src": r.get("broker_src") or "", "source": r.get("source") or "", "layer": r.get("layer") or ""})
    return sorted(out, key=lambda x: -(x["w"] or 0))


def weighted(rows, k):
    xs = [(x[k], x["w"]) for x in rows if x.get(k) is not None and x.get("w")]
    tw = sum(w for _, w in xs)
    return sum(v * w for v, w in xs) / tw if tw else None


def pct(x, unit="%"):
    return "미확인" if x is None else (f"{x * 100:+.1f}%p" if unit == "%p" else f"{x * 100:+.1f}%")


def scored_predictions(quarter, industry):
    """기한이 이번 분기 말 이후 지금까지인 Chiip 산업 예측(사건·주간·분기) — 판정이 있으면 결과, 없으면 '판정 대기'"""
    _, end = IQ.season_quarter()
    out = []
    with E.PRED.open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            if r.get("origin") not in ("industry_event", "industry_weekly", "industry_quarterly"):
                continue
            if not (end.isoformat() <= (r.get("deadline") or "") <= date.today().isoformat()) and not (r.get("thesis_id") or "").find(industry) >= 0:
                continue
            out.append([r["pred_id"], r["statement"][:60], r["deadline"], r["probability"], r.get("outcome") or "판정 대기"])
    return out


def brier(rows):
    xs = [(float(p), 1.0 if o in ("맞음", "hit", "1", "true", "True") else 0.0) for _, _, _, p, o in rows if o not in ("판정 대기", "")]
    return sum((p - o) ** 2 for p, o in xs) / len(xs) if xs else None


def gate(dp, rows, c):
    bad = [f"narrative.{k} 없음" for k in NEED if not (dp.get("narrative") or {}).get(k)]
    for k in ("segments", "checkpoints", "counter", "sources"):
        if not dp.get(k):
            bad.append(f"{k} 없음")
    if len(dp.get("segments") or []) < 2:
        bad.append("사업군 2개 미만")
    if len(dp.get("checkpoints") or []) < 2:
        bad.append("체크포인트 2개 미만")
    if len(dp.get("sources") or []) < 3:
        bad.append("출처 3개 미만")
    rep = [x for x in rows if x["reported"]]
    if not rows or len(rep) / len(rows) < c["min_share_rate"]:
        bad.append(f"발표 종목 {len(rep)}/{len(rows)} — {c['min_share_rate']:.0%} 미만이면 등급을 매기지 않는다")
    return bad


def seg_block(quarter, industry, c):
    """세그먼트 풀 산업 — 회사 전체가 아니라 그 산업 사업부 매출로 잰다(마스터 지시 2026-11-08, ADR-020)"""
    sc = S.cfg()
    rs = S.rows(quarter, industry, c["fx_usd"], sc)
    summ = S.pool_summary(rs, sc)
    pname = {p: m["name"] for p, m in S.pools_of(industry, sc)}

    def money(v, cur):
        if v is None:
            return "미공시"
        return f"{v / 1e12:,.1f}조 원" if cur == "KRW" else f"{v / 1e8:,.0f}억 엔" if cur == "JPY" else f"${v / 1e9:,.2f}B"
    table = [[pname[r["pool"]], r["name"], r["exposure"] + (f"({r['share']:.0%})" if r["share"] is not None else ""), money(r["seg_rev"], r["currency"]),
              pct(r["seg_yoy"]), pct(r["seg_qoq"]), pct(r["vol_chg"]) if r["vol_chg"] is not None else "—", pct(r["price_chg"]) if r["price_chg"] is not None else "—",
              r["grade"] + ("(추정)" if r["grade"] == "E" else "" if r["aggregate"] else "(합산 제외)"), (r["method"] + (" · " + r["source"] if r["source"] else ""))[:140]] for r in rs]
    hl = " ".join(f"{pname[p]} 산업 매출 ${v['usd'] / 1e9:,.1f}B({v['n']}사 사업부 합산) — 전분기 {pct(v['qoq'])}({v['qoq_n']}사), 전년 {pct(v['yoy'])}({v['yoy_n']}사 — 전년 값이 있는 회사만), 공시·IR(A·B) 근거 {v['ab_share']:.0%}." for p, v in summ.items())
    excl = [r["name"] for r in rs if not r["aggregate"]]
    blocks = [{"type": "hl", "text": hl or "세그먼트 장부가 비어 있다."},
              {"type": "table", "title": "세그먼트 기준 스코어카드 — 회사 전체가 아니라 그 산업 사업부 매출(근거 A 공시·B IR·C 제3자 집계·E Chiip 추정·U 미공시)",
               "headers": ["풀", "회사", "노출도(사업부/전사)", "세그먼트 매출", "전년", "전분기", "물량", "가격", "근거", "방법·출처"], "rows": table}]
    if excl:
        blocks.append({"type": "p", "text": "합산에서 뺀 회사: " + ", ".join(excl) + " — 사업부 매출이 공시되지 않아 산업 값에 넣지 않았다(빈칸을 추정으로 채우지 않음)."})
    hold = {p for p in pname if p not in summ or summ[p]["ab_share"] < sc["min_graded_share"]}   # 공시·IR 근거가 모자란 풀은 등급 보류
    return rs, summ, pname, blocks, hold


def build(quarter, industry, dp, c=None):
    c = c or IQ.cfg()
    ecfg = E.config()
    rows = member_rows(quarter, industry, c)
    pooled = S.has_pools(industry)
    summ, pname = {}, {}
    if pooled:
        srs, summ, pname, seg_blocks, hold = seg_block(quarter, industry, c)
        bad = gate(dp, [{"reported": r["aggregate"]} for r in srs], c)
    else:
        hold = set()
        bad = gate(dp, rows, c)
    bad += [f"논리: {b}" for b in LG.gate(dp, "quarterly")]
    if bad:
        raise SystemExit("분기 결산 관문 미통과 — " + " · ".join(bad))
    nar = dp["narrative"]
    share, n_rep, n_all, basis = IQ.progress(industry, quarter, c)
    name = IQ.industry_name(industry)
    agg = {k: weighted(rows, k) for k in ("rev_yoy", "rev_qoq", "gpm_chg", "inv_qoq", "capex_yoy", "next_q_growth", "surprise")}
    surprise_known = [x for x in rows if x["surprise"] is not None]
    beat = sum(1 for x in surprise_known if x["surprise"] > 0) / len(surprise_known) if surprise_known else None
    segs = WF.rows_of(dp, ecfg)
    for r in segs:   # 사업군에 pool이 있으면 그 풀만, 없으면 하나라도 보류면 보류
        if (r.get("pool") in hold) or (hold and not r.get("pool")):
            r["rating"] = "보류(근거 등급 부족)"
    preds = scored_predictions(quarter, industry)
    br = brier(preds)
    actual = ({**{p: v["qoq"] for p, v in summ.items()}, **{f"{r['pool']}:{r['id']}": r["seg_qoq"] for r in srs if r["seg_qoq"] is not None}} if pooled else None)
    LS = LG.sections(dp, "quarterly", actual=actual)
    card = [[x["name"], "발표" if x["reported"] else "미발표", pct(x["rev_yoy"]), pct(x["rev_qoq"]), pct(x["gpm_chg"], "%p"), pct(x["inv_qoq"]), pct(x["capex_yoy"]),
             pct(x["next_q_growth"]), pct(x["surprise"]) if x["surprise"] is not None else "기대 동결 없음", x["source"]] for x in rows]
    if not pooled:
        card.append(["산업(매출 가중)", f"{share:.0%} 발표", pct(agg["rev_yoy"]), pct(agg["rev_qoq"]), pct(agg["gpm_chg"], "%p"), pct(agg["inv_qoq"]), pct(agg["capex_yoy"]),
                     pct(agg["next_q_growth"]), pct(agg["surprise"]) if agg["surprise"] is not None else "—", basis])
    co_title = ("회사 전체 지표 — 세그먼트가 아니다(겸업 회사는 다른 사업이 섞여 있어 산업 값에 넣지 않는다)" if pooled else "종목별 분기 결산 — 장부 계산(통화별 원값, 가중은 대략 달러 환산)")
    co_table = {"type": "table", "title": co_title, "headers": ["종목", "상태", "매출(전년)", "매출(전분기)", "GPM 변화", "재고(전분기)", "CAPEX(전년)", "다음 분기 컨센서스", "서프라이즈", "원천"], "rows": card}
    if pooled:
        score = seg_blocks + [co_table, {"type": "chart", "chart": {"kind": "hbars", "w": 480, "label_w": 150, "title": "세그먼트 매출 성장(전분기 대비)", "unit": "%",
                                                                    "rows": [{"label": f"{r['name']}·{pname[r['pool']]}", "bars": [{"name": "전분기", "color": "b", "value": round(r["seg_qoq"] * 100, 1)}]}
                                                                             for r in srs if r["aggregate"] and r["seg_qoq"] is not None]}}]
    else:
        score = [{"type": "hl", "text": f"{quarter} {name} — 구성 {n_all}종목 중 {n_rep}종목 발표(매출 가중 {share:.0%}). 산업 매출 {pct(agg['rev_yoy'])}(전년), GPM {pct(agg['gpm_chg'], '%p')}, 다음 분기 컨센서스 내포 {pct(agg['next_q_growth'])}(전분기 대비)."
                                      + (f" 시즌 전 기대 대비 상회 {beat:.0%}." if beat is not None else " 시즌 전 기대 동결이 없어 서프라이즈는 재지 않았다(4분기부터).")}, co_table,
                 {"type": "chart", "chart": {"kind": "hbars", "w": 480, "label_w": 120, "title": "매출 성장(전년 대비)", "unit": "%",
                                             "rows": [{"label": x["name"], "bars": [{"name": "전년 대비", "color": "b", "value": round(x["rev_yoy"] * 100, 1)}]} for x in rows if x["rev_yoy"] is not None]}}]
    notes = [[x["name"], x["guide_note"] or "—", x["inventory_note"] or "—", x["broker_src"] or "—"] for x in rows if x["guide_note"] or x["inventory_note"]]
    cyc_chart = {"type": "chart", "chart": {"kind": "hbars", "w": 480, "label_w": 120, "title": "재고(전분기)·CAPEX(전년) 변화 — 회사 전체", "unit": "%",
                                            "rows": [{"label": x["name"], "bars": [b for b in ([{"name": "재고", "color": "e", "value": round(x["inv_qoq"] * 100, 1)}] if x["inv_qoq"] is not None else [])
                                                                               + ([{"name": "CAPEX", "color": "c", "value": round(x["capex_yoy"] * 100, 1)}] if x["capex_yoy"] is not None else [])]}
                                                     for x in rows if x["inv_qoq"] is not None or x["capex_yoy"] is not None]}}
    rating_tbl = {"type": "table", "title": f"사업군 판단 등급 — 규칙 계산(갭 ±{ecfg['rating']['gap_band']:.0f}%p, 확신도 {ecfg['rating']['min_confidence']:.1f} 이상)" + (f" · 공시·IR 근거 {S.cfg()['min_graded_share']:.0%} 미만 풀({', '.join(pname[p] for p in hold)})은 보류" if hold else ""),
                  "headers": ["사업군", "시장 반영", "Chiip 기대", "갭", "확신도", "규칙", "최종"],
                  "rows": [[r["name"], E.pct(r["market"], unit="%p"), E.pct(r["expected"], unit="%p"), E.pct(r["gap"], unit="%p"), f"{float(r.get('confidence') or 0):.2f}", r["rule"], r["rating"]] for r in segs]}
    sec = [{"h2": "결론", "blocks": LS.get("bottom") or [{"type": "hl", "text": nar["view"]}]},
           {"h2": "① 핵심 논쟁", "blocks": LS.get("debates", [])},
           {"h2": "② 시즌 스코어카드", "blocks": score},
           {"h2": "③ 동인 분해 — 물량 × 가격", "blocks": LS.get("drivers", [])},
           {"h2": "④ 무엇이 바뀌었나", "blocks": [{"type": "p", "text": nar["changed"]}, {"type": "p", "text": nar["why"]}]
            + ([{"type": "table", "title": "가이던스·재고 — 회사 공시가 비면 국내 증권사 공개 요약(언론 보도, 2차 인용 C등급)", "headers": ["종목", "가이던스", "재고", "출처"], "rows": notes}] if notes else [])},
           {"h2": "⑤ 사이클 지표판", "blocks": LS.get("cycle", []) + [{"type": "p", "text": nar["cycle"]}, cyc_chart]},
           {"h2": "⑥ 이익 풀 — 누가 유리해졌나", "blocks": [{"type": "p", "text": nar["winners"]}] + LS.get("profit_pool", []) + ([{"type": "p", "text": nar["value_chain_shift"]}] if nar.get("value_chain_shift") else [])},
           {"h2": "⑦ 가격 내포 기대 vs Chiip", "blocks": LS.get("expectations", []) + [{"type": "hl", "text": nar.get("gap") or nar["view"]}, rating_tbl]},
           {"h2": "⑧ 시나리오", "blocks": LS.get("scenarios", [])},
           {"h2": "⑨ 지난 판단 채점", "blocks": ([{"type": "table", "title": "기한이 이번 시즌에 든 Chiip 산업 예측", "headers": ["예측", "내용", "기한", "확률", "결과"], "rows": preds}] if preds
                                            else [{"type": "p", "text": "이번 시즌에 기한이 든 산업 예측이 없다 — 첫 분기 결산이라 채점할 이력이 없다."}])
            + ([{"type": "p", "text": f"브라이어 점수 {br:.3f}(0이 완벽, 0.25가 동전 던지기)."}] if br is not None else [])},
           {"h2": "⑩ 반대 검증", "blocks": [{"type": "hl", "text": nar["counter"]}, {"type": "ul", "items": [f"{x['text']} ({x.get('source', '')})" for x in dp["counter"]]}]},
           {"h2": "⑪ 체크포인트·반증 조건", "blocks": [{"type": "table", "title": "확인할 사건 — 날짜·Chiip 확률(predictions.csv 등록)", "headers": ["기한", "무엇", "잴 것", "확률", "맞으면"],
                                                   "rows": [[x["date"], x["what"], x.get("metric", ""), f"{float(x['p']):.0%}", x.get("confirms", "")] for x in dp["checkpoints"]]},
                                                  {"type": "p", "text": nar["kill"]}]},
           {"h2": "종료 상태", "blocks": [{"type": "p", "text": nar["status"]}]}]
    sec = [x for x in sec if x["blocks"]]
    if dp.get("trial"):
        sec[0]["blocks"].insert(0, {"type": "p", "text": dp["trial"]})
    image_plan = E.place_images(dp, sec)
    if pooled:
        tiles = [{"k": f"{pname[p]} 매출(전분기)", "v": pct(v["qoq"]), "sub": f"${v['usd'] / 1e9:,.1f}B · {v['n']}사 사업부"} for p, v in summ.items()] \
            + [{"k": f"{pname[p]} 매출(전년)", "v": pct(v["yoy"]), "sub": f"{v['yoy_n']}사 기준 · 공시·IR 근거 {v['ab_share']:.0%}"} for p, v in summ.items()]
    else:
        tiles = [{"k": "산업 매출(전년)", "v": pct(agg["rev_yoy"]), "sub": f"{n_rep}/{n_all}종목 발표"}, {"k": "GPM 변화", "v": pct(agg["gpm_chg"], "%p"), "sub": "매출 가중"},
                 {"k": "다음 분기 컨센서스", "v": pct(agg["next_q_growth"]), "sub": "전분기 대비"}, {"k": "재고(전분기)", "v": pct(agg["inv_qoq"]), "sub": "매출 가중"}]
    return {"kind": "industry_quarterly", "cycle": "quarterly", "id": f"quarterly-{industry}-{quarter}", "title": dp["title"], "subtitle": dp.get("subtitle", ""),
            "date": dp["date"], "industry": name, "event": f"{quarter} 분기 결산", "value_add": dp.get("value_add", []), "verdict": {"view": nar["view"]},
            "ratings": [{"name": r["name"], "rating": r["rating"]} for r in segs], "tiles": tiles[:4], "summary": [{"q": q, "a": a} for q, a in nar["summary"]],
            "gallery": [], "sections": sec, "sources": dp["sources"], "terms": dp.get("terms") or {}, "names": dp.get("names") or [], "image_plan": image_plan}


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("quarter")
    ap.add_argument("industry")
    ap.add_argument("--predictions", action="store_true")
    a = ap.parse_args(argv)
    dp = json.loads((IQ.BASE / a.quarter / a.industry / "datapack.json").read_text(encoding="utf-8"))
    import weekly_frame   # 노션 IB 자료 요지·인용(마스터 지시 2026-11-08) — 분기 키는 옛 분야 키(nand-storage 등)라 datapack industry_key가 있으면 그것으로
    dp = weekly_frame.notion_ref({**dp, "industry": dp.get("industry_key") or a.industry})
    d = build(a.quarter, a.industry, dp)
    out = ROOT / "outputs" / "industry" / f"{dp['date'].replace('-', '')}_quarterly-{a.industry}-{a.quarter}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    if a.predictions:
        E.register({**dp, "id": d["id"]}, dp["date"], "INQ", "industry_quarterly", "Industry Quarterly")
    print(f"[Industry Quarterly] {out.relative_to(ROOT)}")
    for r in d["ratings"]:
        print(f"  {r['name']}: {r['rating']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
