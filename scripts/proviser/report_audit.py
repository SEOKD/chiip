"""Chiip proviser — 당일 텐배거 리포트 3건 정량 점검 (마스터 지시 2026-10-29 "Proviser는 그날 하루 적은 3건의 텐배거 리포트 내용에 틀린 게
없는지 다시 점검하고, 분석이 올바른 과정으로 진행됐고 결론이 합리적으로 산출됐는지 모두 정량적으로 평가해 수정·보완하라. 당일 이외 리포트는
건들지 마라. 하루에 3건의 리포트만 다루어라")

결정론 점검 13개(사실·과정·결론) — 프로바이저 모델 점검(1차 출처 재확인·추론 검토)의 바닥이다.
 사실  ① 데이터 검증(datapack_check) 10/10 ② 시나리오 차트의 현재값 = 원자료 가격 또는 시가총액(±2%) ③ 원자료 조회일 = 리포트 날짜(±1일)
       ④ 금액 단위 $B·$M·$T(‘억$’ 남음 금지)
 과정  ⑤ 의무 절(config/proviser.yaml reports.required) ⑥ 차트 ≥ 3·HTML svg 수 = 차트 수 ⑦ 출처 ≥ 3·1차 출처 링크
       ⑧ 프로바이저 보강 표시('보강 적용')
 결론  ⑨ 판단 시나리오 확률 합 = 1(±0.01) ⑩ 확률 가중값 재계산 = 본문 수치(±0.05배) ⑪ 판단이 v2 결과와 크게 다르면 차이 설명
       ⑫ 킬 조건 2~4개 + 날짜 붙은 다음 확인 ⑬ 처방 표현(매수·매도·비중 지시) 없음 + 면책 문구
통과 1 · 경고 0.5 · 실패 0 → 자동 점수 = 합 ÷ 13 × 10.
최종 리포트 점수 = (1 − w) × 프로바이저 루브릭(사실·과정·결론·정량·반증 각 0.0~2.0, 0.1 단위) + w × 자동 점수, w = reports.auto_weight(0.4) — 소수 첫째 자리.
대상: outputs/tenbagger/reports/log.csv에서 date = 그날인 행 중 가장 최근 3건. 다른 날짜 파일은 열지도 고치지도 않는다.
사용: py scripts/proviser/report_audit.py [--date YYYY-MM-DD] [--write]
      py scripts/proviser/report_audit.py --final <id> <사실> <과정> <결론> <정량> <반증> [fixes=n] [--date …] --write
"""
import csv
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
LOG = ROOT / "outputs" / "tenbagger" / "reports" / "log.csv"
OUT = ROOT / "docs" / "proviser" / "reports"
SCORES = OUT / "report_scores.csv"
DEFAULT = {"max_per_day": 3, "auto_weight": 0.4, "price_tol": 0.02, "ratio_tol": 0.05,
           "required": {"밸류에이션(맥킨지·IB)": "밸류에이션 — 맥킨지", "멀티플(동종·할인 분해)": "합리적 멀티플|동종사|할인 분해",
                        "어닝콜 변화·컨센서스": "어닝콜 변화", "내러티브": "내러티브", "수급": "수급", "가격 구간(피보나치)": "피보나치|가격 구간",
                        "판단 시나리오": "판단 시나리오|시나리오", "반대 검증": "반대 검증", "킬 조건·체크리스트": "킬 조건"}}
PRESCRIPTIVE = re.compile(r"매수하라|매도하라|팔아라|사라[.!]|보유하라|비중을?\s*(늘|줄|확대|축소)하|목표\s*주가는")


def cfg():
    c = (yaml.safe_load((ROOT / "config" / "proviser.yaml").read_text(encoding="utf-8")) or {}).get("reports") or {}
    return {**DEFAULT, **c, "required": c.get("required") or DEFAULT["required"]}


def day_reports(day, c=None):
    """그날 리포트 행(최근 3건) — [{date,id,ticker,html,view,json}]"""
    c = c or cfg()
    if not LOG.exists():
        return []
    with LOG.open(encoding="utf-8", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r.get("date") == day]
    out = []
    for r in rows[-int(c["max_per_day"]):]:
        r["json"] = str(Path(r["html"]).with_suffix(".json"))
        out.append(r)
    return out


def _text(d):
    return json.dumps(d, ensure_ascii=False)


def _blocks(d):
    for s in d.get("sections") or []:
        for b in s.get("blocks") or []:
            yield s, b


def audit(r, c=None):
    c = c or cfg()
    checks = []

    def add(axis, name, st, detail):
        checks.append({"axis": axis, "name": name, "status": st, "detail": detail})

    jp, hp = ROOT / r["json"], ROOT / r["html"]
    if not jp.exists():
        return {"id": r["id"], "ticker": r["ticker"], "auto": 0.0, "checks": [{"axis": "과정", "name": "리포트 JSON", "status": "실패", "detail": f"{r['json']} 없음"}]}
    d = json.loads(jp.read_text(encoding="utf-8"))
    html = hp.read_text(encoding="utf-8") if hp.exists() else ""
    full = _text(d)
    dp_path = ROOT / "knowledge" / "models" / "companies" / r["id"] / "datapack.json"
    dp = json.loads(dp_path.read_text(encoding="utf-8")) if dp_path.exists() else {}

    # ---- 사실 ----
    sys.path.insert(0, str(ROOT / "scripts" / "valuation" / "v2"))
    try:
        import datapack_check
        sc = datapack_check.check(dp)["score"] if dp else None
    except Exception as exc:   # 검사기 오류는 실패로
        sc = None
        add("사실", "데이터 검증", "실패", f"검사 오류 {type(exc).__name__}")
    if sc is not None:
        add("사실", "데이터 검증 10/10", "통과" if sc >= 10 else ("경고" if sc >= 8 else "실패"), f"datapack_check {sc}/10")
    elif not dp:
        add("사실", "데이터 검증 10/10", "실패", "datapack 없음")
    scen = next((b["chart"] for _, b in _blocks(d) if b.get("type") == "chart" and b["chart"].get("kind") == "scenario"), None)
    pf = dp.get("profile") or {}
    price, shares = pf.get("price"), pf.get("shares_basic")
    mcap = price * shares if price and shares else None
    cur = (scen or {}).get("current")
    if cur is None:
        add("사실", "현재값 = 원자료", "경고", "판단 시나리오 차트 없음 또는 현재값 없음")
    elif "배" in str((scen or {}).get("unit") or "") or abs(cur - 1.0) < 1e-9:
        add("사실", "현재값 = 원자료", "통과", "배수 기준 시나리오(현재 = 1.0)")
    else:
        ok = any(x and abs(cur - x) <= c["price_tol"] * x for x in (price, mcap))
        add("사실", "현재값 = 원자료", "통과" if ok else "실패", f"차트 현재값 {cur} vs 가격 {price} · 시총 {round(mcap, 2) if mcap else None}")
    ret = str((dp.get("raw") or {}).get("retrieved_at") or "")[:10]
    try:
        gap = abs((date.fromisoformat(ret) - date.fromisoformat(str(d.get("date"))[:10])).days)
        add("사실", "원자료 조회일 = 리포트 날짜", "통과" if gap <= 1 else "실패", f"조회 {ret} · 리포트 {d.get('date')}")
    except ValueError:
        add("사실", "원자료 조회일 = 리포트 날짜", "실패", f"조회일 없음({ret or '-'})")
    left = re.findall(r"\d[\d,.]*\s*(?:억|조)\s*(?:\$|달러)", html or full)
    add("사실", "금액 단위 $B·$M", "통과" if not left else "실패", "남은 표기 없음" if not left else f"남음 {len(left)}건 예: {left[0]}")

    # ---- 과정 ----
    heads = " ".join(s.get("h2", "") for s in d.get("sections") or [])
    miss = [k for k, pat in c["required"].items() if not re.search(pat, heads if k != "멀티플(동종·할인 분해)" else full)]
    add("과정", "의무 절", "통과" if not miss else ("경고" if len(miss) <= 1 else "실패"), "모두 있음" if not miss else "빠짐: " + ", ".join(miss))
    n_chart = sum(1 for _, b in _blocks(d) if b.get("type") == "chart")
    n_svg = html.count("<svg")
    add("과정", "차트 ≥ 3·렌더 일치", "통과" if n_chart >= 3 and (not html or n_svg == n_chart) else "실패", f"차트 {n_chart} · svg {n_svg}")
    src = d.get("sources") or []
    prim = [s for s in src if re.search(r"sec\.gov|investors?\.|/ir\b|ir\.|8-K|10-Q|EX-99", str(s), re.I)]
    add("과정", "출처 ≥ 3·1차 출처", "통과" if len(src) >= 3 and prim else ("경고" if len(src) >= 3 else "실패"), f"출처 {len(src)} · 1차 {len(prim)}")
    add("과정", "프로바이저 보강 표시", "통과" if "보강 적용" in full else "경고", "있음" if "보강 적용" in full else "출처 끝 '보강 적용: D-…' 없음")

    # ---- 결론 ----
    if scen and scen.get("cases"):
        probs = [float(x.get("prob") or 0) for x in scen["cases"]]
        add("결론", "시나리오 확률 합 = 1", "통과" if abs(sum(probs) - 1) <= 0.01 else "실패", f"합 {sum(probs):.3f}")
        if cur:
            ew = sum(float(x.get("prob") or 0) * float(x.get("value") or 0) for x in scen["cases"]) / cur
            stated = [float(m) for m in re.findall(r"확률\s*가중[^0-9]{0,15}([0-9]+(?:\.[0-9]+)?)\s*배", full)]
            if stated:   # 본문의 '확률 가중'은 DCF 몫일 수도 있다 — 하나도 안 맞으면 경고(모델이 어느 수치인지 가린다)
                okr = any(abs(s - ew) <= c["ratio_tol"] for s in stated)
                add("결론", "확률 가중값 재계산", "통과" if okr else "경고", f"판단 시나리오 재계산 {ew:.2f}배 vs 본문 {', '.join(f'{s:.2f}' for s in stated[:3])}배"
                    + ("" if okr else " — 판단 시나리오의 가중값이 본문에 없거나 다름"))
            else:
                add("결론", "확률 가중값 재계산", "경고", f"재계산 {ew:.2f}배 · 본문에 '확률 가중 x배' 수치 없음")
        else:
            add("결론", "확률 가중값 재계산", "경고", "현재값 없음")
    else:
        add("결론", "시나리오 확률 합 = 1", "실패", "판단 시나리오 없음")
        add("결론", "확률 가중값 재계산", "실패", "판단 시나리오 없음")
    view = str((d.get("verdict") or {}).get("view") or "")
    v2m = re.search(r"(?:v2|DCF)[^0-9]{0,20}([0-9]+(?:\.[0-9]+)?)\s*배", full)
    if scen and cur and v2m:
        ew = sum(float(x.get("prob") or 0) * float(x.get("value") or 0) for x in scen["cases"]) / cur
        v2v = float(v2m.group(1))
        far = v2v > 0 and abs(ew / v2v - 1) > 0.3
        expl = bool(re.search(r"차이|원인|괴리|다른 이유|배수 기준", full))
        add("결론", "v2와 차이 설명", "통과" if (not far or expl) else "실패", f"판단 {ew:.2f}배 vs v2 {v2v:.2f}배" + (" — 설명 있음" if far and expl else ""))
    else:
        add("결론", "v2와 차이 설명", "경고" if view else "실패", "v2 배수 또는 판단 시나리오를 찾지 못함")
    kill = next((s for s in d.get("sections") or [] if "킬" in s.get("h2", "")), None)
    n_kill, dated = 0, False
    if kill:   # 킬 조건은 목록(ul) 또는 첫 표의 행으로 적는다
        first = next((b for b in kill.get("blocks") or [] if b.get("type") in ("ul", "table")), None)
        if first:
            n_kill = len(first.get("items") or first.get("rows") or [])
    for s in d.get("sections") or []:
        if re.search(r"킬|체크리스트", s.get("h2", "")) and re.search(r"\d{1,2}/\d{1,2}|\d{4}-\d{2}|\d+월|분기|Q[1-4]", _text(s)):
            dated = True
    add("결론", "킬 조건 2~4 + 날짜", "통과" if 2 <= n_kill <= 6 and dated else ("경고" if n_kill else "실패"), f"킬 조건 {n_kill}개 · 날짜 {'있음' if dated else '없음'}")
    bad = PRESCRIPTIVE.findall(full)
    disc = ("투자 권유" in html) if html else True
    add("결론", "처방 표현 없음·면책", "통과" if not bad and disc else "실패", ("처방 표현 " + str(len(bad)) + "건") if bad else ("면책 문구 없음" if not disc else "이상 없음"))

    pts = {"통과": 1.0, "경고": 0.5, "실패": 0.0}
    auto = round(sum(pts[x["status"]] for x in checks) / len(checks) * 10, 1) if checks else 0.0
    return {"id": r["id"], "ticker": r["ticker"], "json": r["json"], "auto": auto, "checks": checks}


def final_score(auto, rubric, c=None):
    c = c or cfg()
    rub = sum(min(2.0, max(0.0, round(x * 10) / 10)) for x in rubric)
    w = float(c["auto_weight"])
    return round((1 - w) * rub + w * auto, 1), round(rub, 1)


def write_audit(day, results):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{day.replace('-', '')}.json").write_text(json.dumps({"date": day, "reports": results}, ensure_ascii=False, indent=1), encoding="utf-8")
    L = [f"# 당일 텐배거 리포트 점검 {day} (Chiip Proviser)", "", f"대상 {len(results)}건(그날 최근 3건) — 다른 날짜 리포트는 다루지 않는다.", ""]
    for res in results:
        L += [f"## {res['ticker']} ({res['id']}) — 자동 점수 {res['auto']}/10", "", "| 축 | 점검 | 결과 | 내용 |", "|---|---|---|---|"]
        L += [f"| {x['axis']} | {x['name']} | {x['status']} | {x['detail']} |" for x in res["checks"]]
        L += ["", "### 프로바이저 판단(모델이 채움)", "- 사실: ", "- 과정: ", "- 결론: ", "- 정량: ", "- 반증: ", "- 정정: ", ""]
    p = OUT / f"{day.replace('-', '')}.md"
    p.write_text("\n".join(L), encoding="utf-8")
    return p


def record_final(day, rid, ticker, auto, rubric, final, rub, fixes):
    OUT.mkdir(parents=True, exist_ok=True)
    new = not SCORES.exists()
    with SCORES.open("a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["date", "id", "ticker", "auto", "facts", "process", "conclusion", "quant", "falsify", "rubric", "final", "fixes"])
        w.writerow([day, rid, ticker, auto] + [round(x, 1) for x in rubric] + [rub, f"{final:.1f}", fixes])


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    day = argv[argv.index("--date") + 1] if "--date" in argv else date.today().isoformat()
    reps = day_reports(day)
    if not reps:
        print(f"[리포트 점검] {day} 리포트 없음")
        return 0
    if argv and argv[0] == "--final":
        rid = argv[1]
        r = next((x for x in reps if x["id"] == rid), None)
        if not r:
            print(f"[리포트 점검] {day}의 3건에 {rid} 없음 — 당일 3건만 다룬다")
            return 1
        nums = [a for a in argv[2:] if a != "--write" and not a.startswith("fixes=") and a != "--date" and a != day]
        rubric = [float(x) for x in nums[:5]]
        fixes = next((a[6:] for a in argv if a.startswith("fixes=")), "0")
        res = audit(r)
        final, rub = final_score(res["auto"], rubric)
        print(f"[{r['ticker']}] 최종 {final:.1f} = 0.6 × 루브릭 {rub} + 0.4 × 자동 {res['auto']} · 정정 {fixes}건")
        if "--write" in argv:
            record_final(day, rid, r["ticker"], res["auto"], rubric, final, rub, fixes)
        return 0
    results = [audit(r) for r in reps]
    for res in results:
        fails = [x["name"] for x in res["checks"] if x["status"] == "실패"]
        print(f"[{res['ticker']}] 자동 {res['auto']}/10 · 실패 {len(fails)}" + (f": {', '.join(fails)}" if fails else ""))
    if "--write" in argv:
        print(f"→ {write_audit(day, results).relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
