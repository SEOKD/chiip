"""텐배거 판단 체계 — 구루 교차 점검·10배 산술·보유 규율 (마스터 지시 2026-11-21, 방법론 knowledge/methods/tenbagger_playbook.md)

"Ten-bagger 종목을 발굴할 수 있는 사고 논리와 판단 체계, 리서치 방법론 … 스탠리 드러켄밀러, 베일리 기포드, 론 바론, 피터 린치, 워렌 버핏"
숫자는 여기서 계산하고(결정론), 판단은 모델이 메모·카드의 playbook 칸에 관점마다 '통과·미달·미확인 + 이유 + 근거'로 적는다.
  1. 산술   arithmetic(dp)  — 10배·5배·2배에 필요한 연 성장률, 5년 매출 2배 시험(베일리 기포드), ROIC·재투자율·지속 가능 성장(버핏),
                              소유주 이익 근사(버핏 1986), 2년 뒤 EPS 변화(드러켄밀러), 고점 대비 낙폭
  2. 국면   liquidity()     — 10년물·하이일드 스프레드 20일 변화로 완화·중립·긴축(드러켄밀러 — 유동성이 배수를 움직인다)
  3. 검사   check(pb, verdict) — 여섯 관점 답·근거, 통과 수(focus 4·bench 3), 해자 미달이면 focus 불가, 가장 약한 관점 지목(dissent),
                              보유 규율(투자 논리 지표 2개 이상), 판단 기간 3~10년. scripts/discovery/memo_check.py가 부른다
  4. 재심사 drawdowns()      — 추적 후보(tenbagger watch.csv)가 고점 대비 50% 이상 빠졌나. 낙폭은 제외 사유가 아니라 '투자 논리 지표 재확인' 신호다
                              (1985~2024 미국 6,500종목 중앙 낙폭 85%, 최고 종목도 큰 낙폭을 겪는다 — Mauboussin·Callahan 2025)
playbook 칸(메모 머리말 YAML 또는 카드 머리말):
  playbook:
    horizon_years: 7
    target_multiple: 5            # (선택) 이 기간에 기대하는 배수 — 필요한 연 성장률이 arithmetic.rare_cagr 이상이면 '희소' 경고
    views:
      runway:       {verdict: pass|fail|unknown, why: "…", evidence: "URL 또는 저장소 경로"}
      moat_returns: {…}   reinvestment: {…}   people: {…}   change: {…}   mispricing: {…}
    dissent: {view: change, why: "가장 약한 관점과 이유"}
    hold: {kpis: ["수주잔고 YoY", "매출총이익률"], rule: "가격만 −50%면 재심사, 지표가 살아 있으면 유지"}
이름 주의: Analysis 리포트의 datapack "playbook"(투자 포인트·모멘텀 타임라인·가격 틀 — playbook_view.py, 2026-11-16)은 이 파일과 다른 것이다.
리포트 본문의 구루 교차 점검 절은 guru_view.py가 만들고 datapack "guru" 칸을 쓴다(같은 구조, check(…, "report")는 통과 개수를 요구하지 않는다).
지표·연구 보조이며 매매·비중 지시가 아니다. 모르는 값은 None(미확인) — 그럴듯하게 채우지 않는다.
사용: py scripts/tenbagger/playbook.py <회사 id>      # 산술 + 국면
      py scripts/tenbagger/playbook.py --check <메모.md>
      py scripts/tenbagger/playbook.py --drawdowns
"""
import csv
import json
import math
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CO = ROOT / "knowledge" / "models" / "companies"
VERDICTS = ("pass", "fail", "unknown")
KO = {"pass": "통과", "fail": "미달", "unknown": "미확인"}
# '통과'의 근거로 치는 것 — URL, 저장소 파일, 서류 이름(영문 양식·한글 통칭·일본 결산 자료). 서류를 가리키지 않는 문장('경영진이 그렇게 말했다')은 근거가 아니다
EVID = re.compile(r"https?://\S+|[\w./\-]+\.(md|json|yaml|csv|html|htm|pdf)\b|10-[KQ]|8-K|6-K|S-1|DEF 14A|20-F|40-F|Form 4|13[DFG]|Annual Report"
                  r"|사업보고서|분기보고서|반기보고서|연차보고서|위임장|실적 발표|결산|어닝콜|콜 전문|공시|決算短信|有価証券報告書")


def cfg():
    return yaml.safe_load((ROOT / "config" / "tenbagger_playbook.yaml").read_text(encoding="utf-8"))


def _j(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {} if default is None else default


def cagr(multiple, years):
    """k배가 되는 데 필요한 연 성장률"""
    return multiple ** (1 / years) - 1


def required(c=None):
    """{배수: {년: 연 성장률}} — 10배는 5년 58.5%·7년 38.9%·10년 25.9%. 표시할 때 한 번만 반올림하게 여섯 자리로 둔다(네 자리로 줄였다가 39.0%로 찍힌 적이 있다)"""
    a = (c or cfg())["arithmetic"]
    return {m: {y: round(cagr(m, y), 6) for y in a["years"]} for m in a["multiples"]}


def two_engines(target, years, multiple_change):
    """목표 배수를 이익 성장과 배수 변화로 나눈다 — 필요한 EPS 배수와 연 성장률. 배수가 2배가 되면 10배에 EPS 5배(5년 연 38%)면 된다"""
    eps_x = target / multiple_change
    return {"eps_multiple": round(eps_x, 2), "eps_cagr": round(cagr(eps_x, years), 4) if eps_x > 0 else None}


def _years_between(fy_a, fy_b):
    try:
        return int(re.sub(r"\D", "", fy_b)) - int(re.sub(r"\D", "", fy_a))
    except ValueError:
        return None


def drawdown(entity):
    """(지금 ÷ 기간 고점 − 1, 기간 최대 낙폭, 봉 수) — knowledge/models/companies/<id>/ohlcv.csv 종가. 없으면 (None, None, 0)"""
    f = CO / entity / "ohlcv.csv"
    if not f.exists():
        return None, None, 0
    cl = []
    for line in f.read_text(encoding="utf-8").splitlines():
        p = line.split(",")
        if len(p) >= 5 and p[0][:1].isdigit():
            try:
                cl.append(float(p[4]))
            except ValueError:
                continue
    if len(cl) < 20:
        return None, None, len(cl)
    peak, mdd = cl[0], 0.0
    for x in cl:
        peak = max(peak, x)
        mdd = min(mdd, x / peak - 1)
    return round(cl[-1] / max(cl) - 1, 4), round(mdd, 4), len(cl)


def arithmetic(dp, entity=None, c=None):
    """데이터 묶음(datapack) → 관점별 숫자. 칸이 없으면 None"""
    c = c or cfg()
    a = c["arithmetic"]
    fin, cons, fwd, prof = dp.get("financials") or {}, dp.get("consensus") or {}, dp.get("forward") or {}, dp.get("profile") or {}
    out = {"required": required(c), "double_5y": a["double_5y"], "rare_cagr": a["rare_cagr"]}
    # 성장 여지 — 컨센서스 매출 경로의 연 성장률과 2배까지 걸리는 해
    rev = {k: v for k, v in (cons.get("rev") or {}).items() if isinstance(v, (int, float)) and v > 0}
    g = None
    if len(rev) >= 2:
        ks = sorted(rev)
        n = _years_between(ks[0], ks[-1])
        if n:
            g = (rev[ks[-1]] / rev[ks[0]]) ** (1 / n) - 1
            out["rev_path"] = {"from": ks[0], "to": ks[-1], "cagr": round(g, 4)}
    if g is None and isinstance(fin.get("rev_growth_ttm"), (int, float)):
        g = fin["rev_growth_ttm"]
        out["rev_path"] = {"from": "TTM", "to": "TTM", "cagr": round(g, 4), "basis": "최근 12개월 성장(추정 경로 없음)"}
    out["years_to_double"] = round(math.log(2) / math.log(1 + g), 1) if g and g > 0 else None
    out["doubles_in_5y"] = None if g is None else g >= a["double_5y"]
    # 해자와 자본수익률·재투자 — ROIC, 재투자율(설비투자 − 감가상각, 운전자본 변화는 없음 = 근사), 지속 가능 성장
    tax = dp.get("tax") if isinstance(dp.get("tax"), (int, float)) else 0.21
    ebit, ic = fin.get("ebit_ttm"), fin.get("invested_capital")
    nopat = ebit * (1 - tax) if isinstance(ebit, (int, float)) else None
    out["roic"] = round(nopat / ic, 4) if nopat is not None and isinstance(ic, (int, float)) and ic > 0 else None
    capex, da, sbc = fin.get("capex_ttm"), fin.get("da_ttm"), fin.get("sbc_ttm") or 0
    if nopat and nopat > 0 and isinstance(capex, (int, float)) and isinstance(da, (int, float)):
        rr = max(0.0, capex - da) / nopat
        out["reinvest_rate"] = round(rr, 4)
        out["sustainable_growth"] = round(out["roic"] * rr, 4) if out["roic"] is not None else None
    else:
        out["reinvest_rate"] = out["sustainable_growth"] = None
    # 넓은 재투자(2026-11-27 — '재투자 복리' 미확인 18건의 원인: 설비투자만 봐서 자산이 가벼운 회사는 0%로 나왔다)
    # = (순설비투자 + 인수 지출 + 연구개발) ÷ (NOPAT + 연구개발). 연구개발을 투자로 보는 Damodaran식 근사 — 칸이 없으면 None
    acq, rnd = fin.get("acq_ttm"), fin.get("rnd_ttm")
    if nopat is not None and isinstance(capex, (int, float)) and isinstance(da, (int, float)) and (isinstance(acq, (int, float)) or isinstance(rnd, (int, float))):
        base = nopat + (rnd or 0)
        out["reinvest_broad"] = round((max(0.0, capex - da) + (acq or 0) + (rnd or 0)) / base, 4) if base > 0 else None
        out["rnd_share"] = round(rnd / fin["rev_ttm"], 4) if isinstance(rnd, (int, float)) and isinstance(fin.get("rev_ttm"), (int, float)) and fin["rev_ttm"] > 0 else None
    else:
        out["reinvest_broad"] = out["rnd_share"] = None
    # 소유주 이익 근사(버핏 1986: 이익 + 비현금 비용 − 유지 설비투자) — 유지 설비투자 = 감가상각으로 가정, 주식 보상은 비용으로 뺀다
    price, sh = prof.get("price"), prof.get("shares_basic")
    mcap = price * sh if isinstance(price, (int, float)) and isinstance(sh, (int, float)) else None
    oe = nopat - sbc if nopat is not None else None
    out["owner_earnings_yield"] = round(oe / mcap, 4) if oe is not None and mcap else None
    # 변화의 방향 — 2년 뒤 EPS ÷ 다음 12개월 EPS
    e1, e2 = (fwd.get("ntm") or {}).get("eps"), ((fwd.get("horizons") or {}).get("2") or {}).get("eps")
    out["eps_change_24m"] = round(e2 / e1 - 1, 4) if isinstance(e1, (int, float)) and isinstance(e2, (int, float)) and e1 > 0 else None
    out["pe_fwd"] = (dp.get("multiples_now") or {}).get("pe_fwd")
    if entity:
        now, mdd, n = drawdown(entity)
        out["from_peak"], out["max_drawdown"], out["bars"] = now, mdd, n
    return out


def liquidity(c=None, macro=None):
    """(국면, 근거 문장) — 완화·중립·긴축·미확인"""
    c = c or cfg()
    if macro is None:
        macro = _j(ROOT / "knowledge" / "models" / "portfolio" / "market_latest.json").get("macro") or {}
    y, hy = (macro.get("us10y") or {}).get("d20"), (macro.get("hy") or {}).get("d20")
    if y is None and hy is None:
        return "미확인", "금리·신용 스프레드 자료 없음"
    yb, hb = (y or 0) * 100, (hy or 0) * 100
    t, e = c["liquidity"]["tighten"], c["liquidity"]["ease"]
    why = f"10년물 20일 {yb:+.0f}bp · 하이일드 스프레드 20일 {hb:+.0f}bp"
    if yb >= t["us10y_d20_bp"] or hb >= t["hy_d20_bp"]:
        return "긴축", why
    if yb <= e["us10y_d20_bp"] and hb <= 0 or hb <= e["hy_d20_bp"]:
        return "완화", why
    return "중립", why


def check(pb, verdict="focus", c=None):
    """(실패 목록, 경고 목록, 요약) — 메모·카드의 playbook 칸 검사"""
    c = c or cfg()
    g, views = c["gate"], c["views"]
    fails, warns = [], []
    if not isinstance(pb, dict):
        return ["playbook 칸 없음 — 구루 교차 점검(config/tenbagger_playbook.yaml) 여섯 관점을 적는다"], [], {}
    hz = pb.get("horizon_years")
    if not isinstance(hz, (int, float)) or not g["horizon"][0] <= hz <= g["horizon"][1]:
        fails.append(f"판단 기간(horizon_years) {hz} — {g['horizon'][0]}~{g['horizon'][1]}년")
    req, tm = None, pb.get("target_multiple")
    if isinstance(tm, (int, float)) and tm > 1 and isinstance(hz, (int, float)) and hz > 0:
        req = round(cagr(tm, hz), 6)          # 목표 배수 ÷ 판단 기간 = 필요한 연 성장률
        if req >= c["arithmetic"]["rare_cagr"]:
            warns.append(f"{hz:g}년에 {tm:g}배는 연 {req * 100:.1f}% — 희소한 경로다(문턱 {c['arithmetic']['rare_cagr'] * 100:.0f}%). 기간을 늘리거나 근거를 더 댄다")
    got = pb.get("views") or {}
    counts = {"pass": 0, "fail": 0, "unknown": 0}
    for k, v in views.items():
        a = got.get(k)
        if not isinstance(a, dict) or a.get("verdict") not in VERDICTS or not str(a.get("why") or "").strip():
            fails.append(f"{v['name']}({k}): verdict(pass·fail·unknown)와 이유가 필요하다")
            continue
        counts[a["verdict"]] += 1
        if a["verdict"] == "pass" and not EVID.search(str(a.get("evidence") or "")):
            fails.append(f"{v['name']}({k}): '통과'에는 근거(1차 출처 URL·서류 이름·저장소 파일)가 필요하다")
    need = g["pass_min"].get(verdict)
    if need and counts["pass"] < need:
        fails.append(f"통과 {counts['pass']}개 < {need}개({verdict}) — 미확인은 통과가 아니다")
    if verdict == "focus":
        for k in g.get("must_not_fail") or []:
            if (got.get(k) or {}).get("verdict") == "fail":
                fails.append(f"{views[k]['name']} 미달 — focus 불가(복리가 끊긴다)")
    ds = pb.get("dissent") or {}
    if ds.get("view") not in views or not str(ds.get("why") or "").strip():
        fails.append("dissent(가장 약한 관점과 이유)가 없다 — 반대 검증")
    elif (got.get(ds["view"]) or {}).get("verdict") == "pass" and counts["fail"] + counts["unknown"] > 0:
        warns.append("가장 약한 관점으로 '통과'를 골랐는데 미달·미확인 관점이 따로 있다")
    hold = pb.get("hold") or {}
    if len([x for x in hold.get("kpis") or [] if str(x).strip()]) < g["kpis_min"]:
        fails.append(f"보유 규율: 투자 논리 지표(hold.kpis) {g['kpis_min']}개 이상 — 가격이 아니라 이 지표로 유지·종료를 가른다")
    if counts["unknown"] >= 3:
        warns.append(f"미확인 {counts['unknown']}개 — 조사가 덜 됐다")
    return fails, warns, {"pass": counts["pass"], "fail": counts["fail"], "unknown": counts["unknown"], "dissent": ds.get("view"), "required_cagr": req}


def drawdowns(c=None, rows=None, dd=drawdown, ids=None):
    """추적 후보 중 고점 대비 drawdown_review 이상 빠진 종목 — '재심사' 목록(제외가 아니다)"""
    c = c or cfg()
    lim = c["arithmetic"]["drawdown_review"]
    if rows is None:
        p = ROOT / "knowledge" / "models" / "tenbagger" / "watch.csv"
        rows = list(csv.DictReader(p.open(encoding="utf-8", newline=""))) if p.exists() else []
    if ids is None:
        ids = {}
        f = ROOT / "config" / "tradingview_symbols.csv"
        if f.exists():
            with f.open(encoding="utf-8", newline="") as fh:
                ids = {r["ticker"].upper(): r["entity_id"] for r in csv.DictReader(fh) if r.get("entity_id") and r.get("ticker")}
    out, seen = [], set()
    for r in rows:
        t = str(r.get("ticker") or "").upper()
        if r.get("status") == "종료" or not t or t in seen:
            continue
        seen.add(t)
        eid = ids.get(t) or f"us-{t.lower()}"
        now, mdd, n = dd(eid)
        if now is not None and now <= -lim:
            out.append({"ticker": t, "id": eid, "from_peak": now, "max_drawdown": mdd, "kills": r.get("kill_conditions") or "",
                        "note": "낙폭은 제외 사유가 아니다 — 킬 조건·투자 논리 지표를 다시 확인한다(재심사)"})
    return sorted(out, key=lambda x: x["from_peak"])


def lines(a, liq):
    """산술 요약 문장(사람이 읽는 출력)"""
    p = lambda v, s=False: "미확인" if v is None else (f"{v * 100:+.1f}%" if s else f"{v * 100:.1f}%")  # noqa: E731
    rare = a.get("rare_cagr") or 9.9
    L = ["10배에 필요한 연 성장률: " + " · ".join(f"{y}년 {a['required'][10][y] * 100:.1f}%" + ("(희소)" if a["required"][10][y] >= rare else "")
                                          for y in sorted(a["required"][10]))]
    rp = a.get("rev_path")
    L.append(f"성장 여지: 매출 경로 {rp['from']}→{rp['to']} 연 {p(rp['cagr'])}, 2배까지 {a['years_to_double']}년 — 5년 2배(연 14.9%) "
             + ("충족" if a["doubles_in_5y"] else "미달") if rp else "성장 여지: 매출 경로 미확인")
    L.append(f"해자·재투자: ROIC {p(a['roic'])} · 재투자율 {p(a['reinvest_rate'])} · 지속 가능 성장 {p(a['sustainable_growth'])}(근사) · 소유주 이익 수익률 {p(a['owner_earnings_yield'])}(근사)")
    L.append(f"변화의 방향: 2년 뒤 EPS가 다음 12개월보다 {p(a['eps_change_24m'], True)} · 유동성 국면 {liq[0]}({liq[1]})")
    if a.get("from_peak") is not None:
        L.append(f"낙폭: 기간 고점 대비 {p(a['from_peak'], True)}, 기간 최대 낙폭 {p(a['max_drawdown'], True)}")
    return L


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if "--check" in argv:
        sys.path.insert(0, str(ROOT / "scripts" / "discovery"))
        import memo_check
        d = memo_check.front(Path(argv[argv.index("--check") + 1]).read_text(encoding="utf-8")) or {}
        fails, warns, s = check(d.get("playbook"), d.get("verdict") or "focus")
        for x in fails:
            print("오류 " + x)
        for x in warns:
            print("경고 " + x)
        print(("통과" if not fails else f"오류 {len(fails)}건") + (f" — 통과 {s.get('pass')}·미달 {s.get('fail')}·미확인 {s.get('unknown')}" if s else ""))
        return 1 if fails else 0
    if "--drawdowns" in argv:
        rows = drawdowns()
        print(f"재심사 대상 {len(rows)}종목(고점 대비 −{cfg()['arithmetic']['drawdown_review'] * 100:.0f}% 이상) — 낙폭은 제외 사유가 아니다. "
              "킬 조건과 투자 논리 지표를 다시 확인하고, 지표가 살아 있으면 유지한다")
        for r in rows:
            print(f"  {r['ticker']} 고점 대비 {r['from_peak'] * 100:+.0f}% · 킬 조건: {(r['kills'] or '없음(먼저 적는다)')[:70]}")
        return 0
    if not argv:
        print(__doc__)
        return 0
    eid = argv[0]
    dp = _j(CO / eid / "datapack.json")
    if not dp:
        print(f"데이터 묶음 없음: {eid}")
        return 1
    print("\n".join(lines(arithmetic(dp, eid), liquidity())))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
