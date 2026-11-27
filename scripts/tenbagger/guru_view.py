"""구루 교차 점검 — 여섯 관점 (Analysis 리포트 절 · 한 장 요약 한 줄. 마스터 지시 2026-11-21 → 2026-11-22 "넣어라", ADR-050)

배치: 한 장 요약 한 줄(린치 분류를 앞에 붙인다), 본문 한 절 — 피터 린치 분류는 이 절 안 첫 소절이다(마스터 지시 2026-11-27 "피터린치 항목을 구루들 평가 항목에 넣어라").
미확인을 줄이는 재료(2026-11-27): 사람 = datapack people_pack(py scripts/tenbagger/people_pack.py <id> --write — Form 4·위임장),
재투자 = financials.acq_ttm(인수 지출)·rnd_ttm(연구개발) → 넓은 재투자율. 판정이 갈릴 때는 무게가 실린 쪽으로 통과·미달을 쓰고 이유에 반대 근거를 적는다 —
미확인은 판정할 재료 자체가 없을 때만 쓴다.
숫자는 scripts/tenbagger/playbook.py가 계산하고(결정론) 판정은 모델이 datapack "guru"에 쓴다.
datapack "playbook"(투자 포인트·모멘텀 타임라인·가격 틀 — playbook_view.py)과 다른 칸이다. 이름이 비슷해 헷갈리지 않게 여기는 "guru"다.

datapack "guru"(위원회 메모·카드 머리말의 playbook 칸과 같은 구조 — 방법론 knowledge/methods/tenbagger_playbook.md):
  {"horizon_years": 7,                       # 판단 기간 3~10년
   "target_multiple": 5,                     # (선택) 그 기간에 기대하는 배수 — 필요한 연 성장률이 45% 이상이면 '희소' 표시
   "views": {"runway":       {"verdict": "pass|fail|unknown", "why": "한 문장", "evidence": "1차 출처 URL 또는 서류 이름(사업보고서·위임장·실적 발표 자료)"},
             "moat_returns": {…}, "reinvestment": {…}, "people": {…}, "change": {…}, "mispricing": {…}},
   "dissent": {"view": "change", "why": "가장 약한 관점과 이유"},
   "hold": {"kpis": ["수주잔고 YoY", "매출총이익률"], "rule": "가격만 빠지고 지표가 살아 있으면 유지"}}
쓰는 순서: ① py scripts/tenbagger/playbook.py <회사 id> 로 숫자를 먼저 본다 ② 관점마다 1차 자료로 판정한다 — 모르면 unknown(미확인은 통과가 아니다)
③ 통과로 쓴 관점이 스크립트 숫자와 어긋나면(5년 2배 미달·ROIC < 자본비용·2년 뒤 EPS 감소) 조립 때 경고가 뜨고 절에도 그대로 실린다 — 이유를 why에 적는다.
리포트는 통과 개수를 요구하지 않는다(나쁜 회사도 리포트는 쓴다). 구조만 본다: 여섯 관점 판정·이유, 통과의 근거, 가장 약한 관점, 투자 논리 지표 2개 이상, 판단 기간.
GATE_FROM 이후 날짜의 리포트는 guru가 없으면 조립이 멈춘다. 그 전 리포트는 숫자만 싣고 판정은 '미확인'으로 둔다.
지표·점검 틀이며 매매·비중 지시가 아니다.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lynch  # noqa: E402
import people_pack  # noqa: E402
import playbook  # noqa: E402

GATE_FROM = "2026-11-23"   # 이 날짜 리포트부터 datapack guru 필수(2026-11-22 마스터 "넣어라" — 진행 중인 당일 회차는 멈추지 않게 하루 뒤부터)
H2 = "구루 교차 점검"
Q = "구루들은 어떻게 보는가 — 피터 린치 분류와 여섯 관점"
ORDER = ("runway", "moat_returns", "reinvestment", "people", "change", "mispricing")
KO = {"pass": "통과", "fail": "미달", "unknown": "미확인"}
UNKNOWN = "미확인"
URL = re.compile(r"https?://\S+")


def _pct(v, sign=False):
    return UNKNOWN if v is None else (f"{v * 100:+.1f}%" if sign else f"{v * 100:.1f}%")


def check(dp, c=None):
    """빠진 재료 목록 — 있으면 조립이 멈춘다(리포트는 통과 개수를 요구하지 않는다)"""
    g = (dp or {}).get("guru")
    if not isinstance(g, dict):
        return ["datapack guru 없음 — 여섯 관점 판정·가장 약한 관점·투자 논리 지표를 쓴다(scripts/tenbagger/guru_view.py 맨 위)"]
    fails, _, _ = playbook.check(g, "report", c or playbook.cfg())
    return fails


def numbers(a, liq, wacc=None, hz=None, pp=None):
    """관점별 스크립트 숫자 한 줄 — 칸이 없으면 '미확인'"""
    rp = a.get("rev_path")
    run = (f"매출 경로 {rp['from']}→{rp['to']} 연 {_pct(rp['cagr'])}, 2배까지 {a['years_to_double']}년" if rp and a.get("years_to_double") is not None
           else (f"매출 경로 연 {_pct(rp['cagr'])}" if rp else "매출 경로 미확인"))
    moat = f"ROIC {_pct(a.get('roic'))}" + (f" · 자본비용 {_pct(wacc)}" if wacc is not None else "")
    if a.get("reinvest_rate") == 0:   # 설비투자 ≤ 감가상각 — 자산이 가벼운 회사는 연구개발·인수로 재투자한다. 0%를 '재투자 없음'으로 읽히게 두지 않는다
        rein = "설비 재투자율 0%(설비투자가 감가상각 이하 — 연구개발·인수로 하는 재투자는 이 숫자에 없다)"
    else:
        rein = f"설비 재투자율 {_pct(a.get('reinvest_rate'))} · 지속 가능 성장 {_pct(a.get('sustainable_growth'))}(근사)"
    if a.get("reinvest_broad") is not None:
        rein += f" · 넓은 재투자율 {_pct(a['reinvest_broad'])}(설비 + 인수 + 연구개발)" + (f" · 연구개발 매출의 {_pct(a['rnd_share'])}" if a.get("rnd_share") is not None else "")
    rein += f" · 소유주 이익 수익률 {_pct(a.get('owner_earnings_yield'))}(근사)"
    chg = f"2년 뒤 EPS {_pct(a.get('eps_change_24m'), True)}(다음 12개월 대비) · 유동성 국면 {liq[0]}"
    y = hz if isinstance(hz, (int, float)) and hz > 0 else 7
    mis = f"{y:g}년에 5배 = 연 {_pct(playbook.cagr(5, y))} · 10배 = 연 {_pct(playbook.cagr(10, y))}" + (f" · Fwd P/E {a['pe_fwd']:.1f}배" if isinstance(a.get("pe_fwd"), (int, float)) else "")
    return {"runway": run, "moat_returns": moat, "reinvestment": rein, "people": people_pack.line(pp), "change": chg, "mispricing": mis}


def conflicts(g, a, wacc=None):
    """'통과'로 쓴 관점이 스크립트 숫자와 어긋나는 곳 — 조립 때 경고로 찍고 절에도 싣는다(마스터 가설도 같은 강도로 반대 검증)"""
    v = lambda k: ((g or {}).get("views") or {}).get(k, {}).get("verdict")  # noqa: E731
    out = []
    if v("runway") == "pass" and a.get("doubles_in_5y") is False:
        out.append(f"성장 여지를 통과로 봤지만 매출 경로는 연 {_pct((a.get('rev_path') or {}).get('cagr'))}로 5년 2배(연 14.9%)에 못 미친다")
    if v("moat_returns") == "pass" and a.get("roic") is not None and wacc is not None and a["roic"] < wacc:
        out.append(f"해자와 자본수익률을 통과로 봤지만 ROIC {_pct(a['roic'])}가 자본비용 {_pct(wacc)}보다 낮다")
    if v("change") == "pass" and a.get("eps_change_24m") is not None and a["eps_change_24m"] < 0:
        out.append(f"변화의 방향을 통과로 봤지만 2년 뒤 EPS 추정이 다음 12개월보다 {_pct(a['eps_change_24m'], True)}다")
    return out


def _counts(g):
    n = {"pass": 0, "fail": 0, "unknown": 0}
    for k in ORDER:
        vd = ((g.get("views") or {}).get(k) or {}).get("verdict")
        n[vd if vd in n else "unknown"] += 1
    return n


def _evidence(text):
    """근거 칸 표기 — URL은 출처 목록으로 보내고 표에는 '출처 목록' 한 마디만, 서류 약자는 한글로"""
    t = str(text or "").strip()
    if not t:
        return "", []
    urls = URL.findall(t)
    rest = URL.sub("", t).strip(" ,;·")
    rest = re.sub(r"DEF\s*14A", "위임장", rest)
    return (rest + (" · " if rest else "") + "출처 목록") if urls else rest, urls


def _materials(dp, entity, c, liq):
    c = c or playbook.cfg()
    return c, playbook.arithmetic(dp or {}, entity, c), liq or playbook.liquidity(c)


def summary_item(dp, entity=None, wacc=None, c=None, liq=None):
    c, a, liq = _materials(dp, entity, c, liq)
    g = (dp or {}).get("guru")
    num = numbers(a, liq, wacc, (g or {}).get("horizon_years"), (dp or {}).get("people_pack"))
    ly = lynch.summary_item(dp or {})["a"]
    ly = "**피터 린치 분류:** " + ly + " "
    if not isinstance(g, dict):
        return {"q": Q, "a": ly + f"여섯 관점 판정 미확인 — 계산한 숫자만 싣는다. {num['runway']} · {num['moat_returns']} · {num['change']}.", "auto": True}
    n = _counts(g)
    ds = g.get("dissent") or {}
    weak = (c["views"].get(ds.get("view")) or {}).get("name")
    hz = g.get("horizon_years")
    txt = ly + f"**통과 {n['pass']} · 미달 {n['fail']} · 미확인 {n['unknown']}**(여섯 관점). "
    if weak:
        txt += f"가장 약한 관점은 {weak} — {str(ds.get('why') or '').rstrip('.')}. "
    if isinstance(hz, (int, float)) and hz > 0:
        txt += f"판단 기간 {hz:g}년, 그 안에 10배면 연 {_pct(playbook.cagr(10, hz))}가 필요하다. "
    kp = [str(x) for x in (g.get("hold") or {}).get("kpis") or [] if str(x).strip()]
    if kp:
        txt += "투자 논리 지표: " + " · ".join(kp[:3]) + "."
    return {"q": Q, "a": txt.strip(), "auto": True}


def section(dp, entity=None, wacc=None, c=None, liq=None):
    c, a, liq = _materials(dp, entity, c, liq)
    g = (dp or {}).get("guru")
    has = isinstance(g, dict)
    g = g if has else {}
    hz = g.get("horizon_years")
    num = numbers(a, liq, wacc, hz, (dp or {}).get("people_pack"))
    views, src = g.get("views") or {}, []
    boxes = []   # 관점마다 설명 박스 하나 — 글이 긴 칸을 표에 넣으면 오른쪽 정렬로 읽기 어렵다(2026-11-22 화면 확인)
    for k in ORDER:
        v, x = c["views"][k], views.get(k) or {}
        ev, urls = _evidence(x.get("evidence"))
        src += urls
        boxes.append({"title": v["name"], "tag": KO.get(x.get("verdict"), UNKNOWN),
                      "lines": [["질문", v["ask"]], ["이유", str(x.get("why") or ("판정 재료 없음" if not has else ""))], ["계산한 숫자", num[k]], ["근거", ev]]})
    B = []
    if has:
        n = _counts(g)
        ds = g.get("dissent") or {}
        weak = (c["views"].get(ds.get("view")) or {}).get("name")
        B.append({"type": "hl", "text": f"**여섯 관점 중 통과 {n['pass']} · 미달 {n['fail']} · 미확인 {n['unknown']}.** "
                                        + (f"가장 약한 관점은 {weak} — {str(ds.get('why') or '').rstrip('.')}." if weak else "")})
    else:
        B.append({"type": "p", "text": "여섯 관점 판정은 미확인이다(판정 재료 없음). 아래 숫자는 계산값이다."})
    if has:
        B.append({"type": "p", "text": "판정은 자체추론이고 숫자는 계산값이다."})
    B.append({"type": "boxes", "items": boxes})
    # 피터 린치 분류 — 구루 절 안 소절(마스터 지시 2026-11-27). 분류는 통과·미달 개수에 넣지 않는다(판정이 아니라 기대치 틀)
    ls = lynch.section(dp or {})
    B += [{"type": "h3", "text": "피터 린치 분류 — 크기·이야기 유형·기대 수익"}] + ls["blocks"]
    bad = conflicts(g, a, wacc)
    if bad:
        B.append({"type": "ul", "items": [f"숫자와 판정이 어긋난다: {x}" for x in bad]})
    req = a["required"]
    rare = a.get("rare_cagr") or 9.9
    ys = sorted(next(iter(req.values())))
    B.append({"type": "table", "title": "배수별로 필요한 연 성장률 — 이익 성장과 배수 변화를 합친 속도", "headers": ["목표"] + [f"{y}년" for y in ys],
              "rows": [[f"{m}배"] + [_pct(req[m][y]) + ("(희소)" if req[m][y] >= rare else "") for y in ys] for m in sorted(req)]})
    tm = g.get("target_multiple")
    if isinstance(tm, (int, float)) and tm > 1 and isinstance(hz, (int, float)) and hz > 0:
        need = playbook.cagr(tm, hz)
        B.append({"type": "p", "text": f"이 리포트의 판단 기간은 {hz:g}년, 기대 배수는 {tm:g}배다 — 연 {_pct(need)}가 필요하다" + ("(희소한 경로 — 근거를 더 본다)." if need >= rare else ".")})
    hold = g.get("hold") or {}
    kp = [str(x) for x in hold.get("kpis") or [] if str(x).strip()]
    items = []
    if kp:
        items.append("투자 논리 지표: " + " · ".join(kp))
    if hold.get("rule"):
        items.append(f"규칙: {hold['rule']}")
    if a.get("from_peak") is not None:
        lim = c["arithmetic"]["drawdown_review"]
        items.append(f"지금 주가는 일봉 {a.get('bars') or 0:,}개 기간의 고점 대비 {_pct(a['from_peak'], True)}, 그 기간 최대 낙폭은 {_pct(a['max_drawdown'], True)}다"
                     + (f" — 고점 대비 −{lim * 100:.0f}%를 넘어 재심사 구간이다. 가격이 아니라 위 지표로 유지·종료를 가른다." if a["from_peak"] <= -lim else "."))
    if items:
        B += [{"type": "h3", "text": "보유 규율 — 가격이 아니라 지표로 유지·종료를 가른다"}, {"type": "ul", "items": items}]
    B.append({"type": "p", "text": "여섯 관점은 베일리 기포드(성장 여지·5배 경로), 워렌 버핏(해자·재투자), 론 바론(사람), 피터 린치(분류·내부자), 스탠리 드러켄밀러(변화의 방향·유동성)의 질문을 옮긴 점검 틀이다. "
                                   f"유동성 국면은 {liq[0]}({liq[1]}). 설비 재투자율은 설비투자에서 감가상각을 뺀 몫만 본 근사이고(연구개발·인수·운전자본은 빠진다), 소유주 이익 수익률은 유지 설비투자를 감가상각과 같다고 본 근사다. 점검 틀이며 매매·비중 지시가 아니다."})
    return {"h2": H2, "blocks": B, "_sources": list(dict.fromkeys(src)), "_warnings": bad}


def main(argv):
    import json
    sys.stdout.reconfigure(encoding="utf-8")
    if not argv:
        print(__doc__)
        return 0
    eid = argv[0]
    dp = playbook._j(playbook.CO / eid / "datapack.json")
    if not dp:
        print(f"데이터 묶음 없음: {eid}")
        return 1
    err = check(dp) if dp.get("guru") else ["datapack guru 없음 — 숫자만 싣는다"]
    for e in err:
        print("점검:", e)
    print(json.dumps({"summary": summary_item(dp, eid), "section": section(dp, eid)}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
