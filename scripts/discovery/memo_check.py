"""위원회 메모 검사기 — IB 리서치 하우스식 '종목 선정 위원회' 관문을 기계로 확인한다 (마스터 지시 2026-11-15 "월스트리트 IB 리서치 하우스의 접근 방법과
프로세스를 접목", 설계 knowledge/methods/discovery_engine.md '위원회 메모' 절, 근거 scratch 조사 A — Mauboussin·Rappaport 2021 기대 투자,
Klein 2007 사전 부검, Kahneman·Lovallo 1993 바깥 관점, Harvey 외 2020 Man Group 킬 규칙, Akepanidtaworn 외 2023 JF 매도 판단)

메모(knowledge/models/discovery/memos/<YYYYMMDD>_<id>.md) 맨 위 YAML 머리말(--- … ---)을 읽는다. 본문 서술은 그대로 두고, 판단의 뼈대만 칸으로 적는다:
  id · date · verdict(focus|bench|hold) · thesis · channels(발굴 경로) · edge_type(behavioral|analytical|informational|technical) · other_side(누가 반대편에 있나)
  evidence: [1차 출처 URL ≥ 2]              — 회사 공시·결산 자료·IR Q&A·고객/공급사 공시(2차 보도 단독 불가)
  consensus_gap: [{driver, ours, consensus, unit, sigma?, source}] — 핵심 동인 중 하나 이상이 합의와 max(1σ, 10%) 이상 달라야 한다(변이 관점)
  price · scenarios: {bull: {value, p}, base: {value, p}, bear: {value, p}} — 12개월, 확률 합 1, 상방 기대 ÷ 하방 기대 ≥ skew_min(사전값 2.0)
  catalysts: [{date, what}] — 365일 안에 하나 이상(촉매 점수: 90일 안 1.0 → 365일 0)
  premortem: [실패 경로 ≥ 3] · kills: [{metric, threshold, deadline, source} ≥ 2]
  implied: {growth, pctile, source} — 가격이 내포한 성장과 동종 기저율 분위(역DCF). 90분위를 넘으면 새 1차 출처 2개 이상이 없을 때 확률을 절반으로(경고)
  red_team: {verdict, answered} · expiry — 365일 안(지나면 다시 심사)
focus·bench 결론은 모든 관문 통과가 필요하다. hold(보류)는 검사 결과만 남긴다. 숫자는 판단 보조이고 매수 권유·목표주가가 아니다.
사용: py scripts/discovery/memo_check.py <메모.md> [--json]
"""
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import yaml

EDGE_TYPES = ("behavioral", "analytical", "informational", "technical")
SKEW_MIN = 2.0          # 등록부 prm-memo-skew-min(사전값 — Morgan Stanley 위험·보상 스크린은 문턱을 공개하지 않는다)
GAP_MIN_REL = 0.10      # prm-memo-gap-rel — 분산 정보가 없을 때 합의 대비 10%
CAT_FULL_D, CAT_ZERO_D = 90, 365   # prm-memo-catalyst — 촉매 점수 1.0 → 0
PCTILE_WARN = 90        # prm-memo-baserate-pctile — 바깥 관점(Kahneman·Lovallo 1993)
URL = re.compile(r"https?://\S+")


def front(text):
    m = re.match(r"\s*---\s*\n(.*?)\n---\s*(\n|$)", text, re.S)
    if not m:
        return None
    try:
        return yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"머리말 YAML 오류: {exc}") from None


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _date(v):
    try:
        return v if isinstance(v, date) else date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def skew(price, sc):
    """(상방 기대, 하방 기대, 비율, 확률 합)"""
    up = dn = ps = 0.0
    for k in ("bull", "base", "bear"):
        s = sc.get(k) or {}
        v, p = _num(s.get("value")), _num(s.get("p"))
        if v is None or p is None:
            return None, None, None, None
        ps += p
        up += p * max(v - price, 0)
        dn += p * max(price - v, 0)
    return up, dn, (up / dn) if dn > 0 else float("inf"), ps


def catalyst_score(cats, d0):
    best = 0.0
    for c in cats or []:
        d = _date((c or {}).get("date"))
        if not d:
            continue
        days = (d - d0).days
        if days < 0:
            continue
        s = 1.0 if days <= CAT_FULL_D else max(0.0, 1 - (days - CAT_FULL_D) / (CAT_ZERO_D - CAT_FULL_D))
        best = max(best, s)
    return round(best, 2)


def check(d):
    """(통과 여부, 실패 이유 목록, 경고 목록, 수치)"""
    fails, warns, nums = [], [], {}
    for k in ("id", "date", "verdict", "thesis", "edge_type", "other_side", "evidence", "consensus_gap", "price", "scenarios", "catalysts", "premortem", "kills", "red_team", "expiry"):
        if d.get(k) in (None, "", [], {}):
            fails.append(f"칸 없음: {k}")
    d0 = _date(d.get("date")) or date.today()
    if d.get("verdict") not in ("focus", "bench", "hold"):
        fails.append("verdict는 focus·bench·hold 중 하나")
    if d.get("edge_type") and d["edge_type"] not in EDGE_TYPES:
        fails.append(f"edge_type은 {', '.join(EDGE_TYPES)} 중 하나")
    ev = [u for u in d.get("evidence") or [] if URL.match(str(u))]
    if len(ev) < 2:
        fails.append(f"1차 출처 URL {len(ev)}개 — 2개 이상")
    gaps = []
    for g in d.get("consensus_gap") or []:
        o, c, s = _num(g.get("ours")), _num(g.get("consensus")), _num(g.get("sigma"))
        if o is None or c is None or not g.get("source"):
            continue
        need = max(s or 0, GAP_MIN_REL * abs(c))
        gaps.append({"driver": g.get("driver"), "gap": round(o - c, 4), "need": round(need, 4), "ok": abs(o - c) >= need and need > 0})
    nums["consensus_gap"] = gaps
    if not any(x["ok"] for x in gaps):
        fails.append("변이 관점 없음 — 합의와 max(1σ, 10%) 이상 다른 동인이 없다(출처 포함)")
    price = _num(d.get("price"))
    if price and d.get("scenarios"):
        up, dn, ratio, ps = skew(price, d["scenarios"])
        if ratio is None:
            fails.append("시나리오 값·확률 누락")
        else:
            nums.update({"up": round(up, 4), "down": round(dn, 4), "skew": None if ratio == float("inf") else round(ratio, 2), "p_sum": round(ps, 3)})
            if abs(ps - 1) > 0.02:
                fails.append(f"시나리오 확률 합 {ps:.2f} — 1이어야 한다")
            if ratio < SKEW_MIN:
                fails.append(f"상방÷하방 {ratio:.2f} < {SKEW_MIN}")
            bear = _num((d["scenarios"].get("bear") or {}).get("value"))
            if bear is not None and bear >= price:
                warns.append("약세 값이 현재가 이상 — 하방이 정의되지 않는다(약세 시나리오를 다시 본다)")
    cs = catalyst_score(d.get("catalysts"), d0)
    nums["catalyst_score"] = cs
    if cs <= 0:
        fails.append("365일 안 날짜 붙은 촉매 없음")
    if len(d.get("premortem") or []) < 3:
        fails.append(f"사전 부검 {len(d.get('premortem') or [])}개 — 3개 이상")
    ks = [k for k in d.get("kills") or [] if isinstance(k, dict) and all(k.get(x) for x in ("metric", "threshold", "deadline", "source"))]
    if len(ks) < 2:
        fails.append(f"킬 조건(지표·문턱·기한·출처) {len(ks)}개 — 2개 이상")
    imp = d.get("implied") or {}
    pc = _num(imp.get("pctile"))
    nums["implied_pctile"] = pc
    if pc is None:
        warns.append("가격 내포 성장·기저율 분위 없음(역DCF) — 바깥 관점 미확인")
    elif pc > PCTILE_WARN and len(ev) < 4:
        warns.append(f"내포 성장 {pc:.0f}분위 > {PCTILE_WARN} — 새 1차 출처 2개 이상이 없으면 성공 확률을 절반으로 본다")
    rt = d.get("red_team") or {}
    if not rt.get("verdict") or rt.get("answered") is not True:
        fails.append("red-team 판정과 답 없음")
    ex = _date(d.get("expiry"))
    if not ex or ex > d0 + timedelta(days=366) or ex <= d0:
        fails.append("expiry는 메모 날짜 뒤 365일 안")
    if d.get("verdict") == "hold":
        return True, fails, warns, nums   # 보류는 검사 결과만 남긴다
    return not fails, fails, warns, nums


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if not argv:
        print(__doc__)
        return 1
    text = Path(argv[0]).read_text(encoding="utf-8")
    d = front(text)
    if d is None:
        print("머리말(--- YAML ---) 없음 — 메모 맨 위에 판단 칸을 적는다(사용법은 이 파일 맨 위)")
        return 1
    ok, fails, warns, nums = check(d)
    if "--json" in argv:
        print(json.dumps({"ok": ok, "fails": fails, "warns": warns, "nums": nums}, ensure_ascii=False, indent=1, default=str))
    else:
        print(("통과" if ok and not fails else ("보류 — 검사 결과만 기록" if d.get("verdict") == "hold" else "불통과")) +
              (f" · 상방÷하방 {nums.get('skew')}" if nums.get("skew") is not None else "") + f" · 촉매 점수 {nums.get('catalyst_score')}")
        for f in fails:
            print(" - 실패:", f)
        for w in warns:
            print(" - 경고:", w)
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
