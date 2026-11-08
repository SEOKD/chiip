"""Fiscal.ai IR 문서 감시 → Pulse 'IR 자료' (마스터 지시 2026-11-08 "AT&S도 최근 실적 발표 프레젠테이션 자료를 공유했는데 이걸 가져오고 있는지 파이프라인을 점검하라")

점검 결과: 유럽 상장사는 실적 PT를 받는 길이 없었다. 회사 IR 수집기는 일본·한국·대만·홍콩뿐이고, AT&S는 config/fiscal_keys.yaml에 키도 없었으며
회사 사이트(www.ats.net)는 수집기 요청에 응답하지 않는다(우회하지 않는다). 같은 자료가 Fiscal.ai IR 이벤트(slide_deck·press_release·interim_report)에 있다.
구조(설정 config/fiscal_ir_docs.yaml):
  ① 관문 — Pulse(radar/pulse.py)가 status()를 부른다. interval_h마다 회차를 연다.
  ② 수집(모델 — Fiscal.ai MCP는 스크립트가 직접 못 부른다) — `--plan`이 대상 종목을 묶음으로 나눈 execute_code 본문을 준다(scripts/fiscal/templates/ir_docs_batch.js).
     출력 파일을 `--put`으로 넣는다. 문서 목록(역할·날짜·filingId)만 받는다.
  ③ 처음 보는 문서 중 이벤트 날짜가 fresh_days 안이면 inbox에 src-fiscal-ir-docs 'IR 자료'로 저장 → 다음 Pulse 회차의 ⑥-2 IR 자료 절차가 분석한다
     (본문은 모델이 Fiscal `filing_page_image`로 쪽을 읽는다 — 라이선스 자료라 저장소에는 요지·15단어 이하 인용만).
대상: config/fiscal_keys.yaml 키 중 미국·일본·한국·대만·홍콩(다른 경로가 있는 시장)을 뺀 것 + 설정 extra.
상태 radar/state/fiscal_ir_docs.json. 사용: py radar/fiscal_ir_docs.py [--status] · --plan · --put <파일>
"""
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

ROOT = common.ROOT
CFG = ROOT / "config" / "fiscal_ir_docs.yaml"
KEYS = ROOT / "config" / "fiscal_keys.yaml"
TEMPLATE = ROOT / "scripts" / "fiscal" / "templates" / "ir_docs_batch.js"
STATE = "fiscal_ir_docs"
SRC = "src-fiscal-ir-docs"
ROLE_KO = {"slide_deck": "실적 발표 자료(PT)", "press_release": "실적 보도자료", "interim_report": "분기·반기 보고서", "annual_report": "연차 보고서"}


def cfg():
    return yaml.safe_load(CFG.read_text(encoding="utf-8"))


def universe(c=None):
    """{id: Fiscal 키}"""
    c = c or cfg()
    keys = (yaml.safe_load(KEYS.read_text(encoding="utf-8")) or {}).get("keys") or {}
    out = {i: (v or {}).get("key") for i, v in keys.items() if (v or {}).get("key") and not str((v or {}).get("key")).startswith(tuple(c["exclude_prefix"]))}
    for cid, v in (c.get("extra") or {}).items():
        out[cid] = v["key"] if isinstance(v, dict) else v
    return out


def status(now=None, c=None):
    c = c or cfg()
    now = now or common.now_kst()
    st = common.load_state(STATE, {})
    last = st.get("checked")
    if last and datetime.fromisoformat(last) > now - timedelta(hours=c["interval_h"]):
        return {"due": False, "next": (datetime.fromisoformat(last) + timedelta(hours=c["interval_h"])).isoformat(timespec="minutes")}
    return {"due": True, "phase": "collect", "n": len(universe(c))}


def plan(c=None):
    c = c or cfg()
    keys = sorted(set(universe(c).values()))
    body = TEMPLATE.read_text(encoding="utf-8").replace("__ROLES__", json.dumps(c["roles"]))
    n = c["batch"]
    return [body.replace("__KEYS__", json.dumps(keys[i:i + n])) for i in range(0, len(keys), n)]


def _name(cid, c=None):
    ex = ((c or cfg()).get("extra") or {}).get(cid)
    return (ex.get("name") if isinstance(ex, dict) else None) or next(
        (r.get("name") for r in common.load_watchlist() if r["entity_id"] == cid), None) or cid


def put(path, now=None, c=None):
    """ir_docs_batch.js 출력 → 새 문서만 inbox 항목으로. (저장 수, 기록만 한 수)"""
    c = c or cfg()
    now = now or common.now_kst()
    text = Path(path).read_text(encoding="utf-8")
    rows = json.loads(text[text.index("["):text.rindex("]") + 1])
    by_key = {}
    for cid, k in universe(c).items():
        by_key.setdefault(k, cid)
    st = common.load_state(STATE, {})
    seen = set(st.get("seen") or [])
    items, logged = [], 0
    for r in rows:
        cid = by_key.get(r.get("key"))
        if not cid or r.get("error"):
            continue
        for d in r.get("docs") or []:
            if not d.get("id") or d["id"] in seen:
                continue
            seen.add(d["id"])
            try:
                age = (now.date() - date.fromisoformat(str(d.get("date"))[:10])).days
            except ValueError:
                age = None
            if age is None or age > c["fresh_days"]:
                logged += 1
                continue
            period = f"FY{d['fy']}Q{d['fq']}" if d.get("fy") and d.get("fq") else "기간 미확인"
            name = _name(cid, c)
            extra = {"entities_matched": [cid], "publisher": name, "kind": {"slide_deck": "presentation", "press_release": "release"}.get(d["role"], "report"),
                     "period": period, "doc_date": d.get("date"), "fiscal_key": r["key"], "filing_id": d["id"], "grade": "A", "tier": ROLE_KO.get(d["role"], d["role"]),
                     "fetch": f"Fiscal.ai filing_page_image(filingId='{d['id']}', companyKey='{r['key']}', pageNumber=1…)"}
            items.append(common.make_item(SRC, d["id"], "", f"{name} IR: {ROLE_KO.get(d['role'], d['role'])} {period}", common.iso(now), "IR 자료", "en",
                                          f"{d['role']} · {period} · 발표 {d.get('date')}", extra=extra))
    st["seen"] = sorted(seen)[-3000:]
    st["checked"] = common.iso(now)
    common.save_state(STATE, st)
    new = common.save_new_items(items) if items else []
    return len(new), logged


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if "--plan" in argv:
        bodies = plan()
        print(json.dumps(status(), ensure_ascii=False))
        for i, b in enumerate(bodies, 1):
            print(f"----- 묶음 {i}/{len(bodies)} (execute_code 본문) -----")
            print(b)
        return 0
    if "--put" in argv:
        n, logged = put(argv[argv.index("--put") + 1])
        print(f"[Fiscal IR 문서] 새 문서 {n}건 inbox 저장 · 오래된 문서 {logged}건 기록만")
        return 0
    u = universe()
    print(json.dumps({**status(), "targets": len(u), "sample": dict(list(u.items())[:8])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
