"""EDINET(일본 금융청 전자공시) API v2 — 감시 일본 회사의 법정 공시 목록 (데이터 채널 승인 대기 처리, 2026-11-12 마스터 지시 "승인 대기 3건을 처리해봐").

적시공시 미러(jp_disclosure.py, Google News 색인)가 못 잡는 법정 서류 — 유가증권보고서·반기보고서·임시보고서·대량보유보고서 —
를 1차 원천에서 본다. 일본 IR 자료실 미발견·기간 판독 실패 종목의 보완 경로(knowledge/models/channels/scout.csv 2026-11-02).
결정론 수집만(모델 없음). 목록 API(documents.json type=2)만 쓰고 본문은 내려받지 않는다 — 제목·제출자·서류 종류·docID만.
  감시 회사 = config/jp_watch.yaml code(4자리) — EDINET secCode는 5자리(끝 0)
출력: 새 서류 → inbox src-edinet → Pulse '공시'. 상태 radar/state(edinet).
키: EDINET_API_KEY(EDINET API 이용 등록 후 발급되는 Subscription-Key) — 없으면 '키 대기'로 건너뛴다. 키가 든 주소는 출력·오류 메시지에 쓰지 않는다.
사용: py radar/edinet.py [YYYY-MM-DD]
"""
import json
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

API = "https://api.edinet-fsa.go.jp/api/v2/documents.json"
VIEW = "https://disclosure2.edinet-fsa.go.jp/"
TYPES = {"120": "유가증권보고서", "130": "유가증권보고서 정정", "140": "분기보고서", "160": "반기보고서",
         "170": "반기보고서 정정", "180": "임시보고서", "220": "자기주식 매입 현황", "350": "대량보유보고서", "360": "대량보유보고서 정정"}


def key():
    return common.load_env().get("EDINET_API_KEY")


def watch():
    cfg = common.load_yaml("config/jp_watch.yaml") or {}
    return {str(c["code"]) + "0": c for c in cfg.get("companies") or [] if c.get("code")}


def documents(day, k):
    try:
        raw = common.http_get(API, {"date": day, "type": 2, "Subscription-Key": k}, timeout=30)
    except Exception as exc:   # 예외 문자열에 키가 든 주소가 섞일 수 있다 — 종류만
        raise RuntimeError(f"EDINET 목록 실패({type(exc).__name__})") from None
    d = json.loads(raw)
    if str(d.get("metadata", {}).get("status", "200")) != "200":
        raise RuntimeError(f"EDINET 응답 {d['metadata'].get('status')}")
    return d.get("results") or []


def pick(rows, w):
    out = []
    for r in rows:
        c = w.get(r.get("secCode") or "")
        if c and r.get("docTypeCode") in TYPES and r.get("withdrawalStatus", "0") == "0":
            out.append((c, r))
    return out


def run(day=None):
    k = key()
    if not k:
        common.record_health("edinet", True, "키 대기(EDINET_API_KEY)")
        return "키 대기(EDINET_API_KEY) — docs/TODO_MASTER.md"
    now = common.now_kst()
    days = [day] if day else [(now.date() - timedelta(days=1)).isoformat(), now.date().isoformat()]
    st = common.load_state("edinet", {"seen": []})
    seen, items, w = set(st["seen"]), [], watch()
    for dd in days:
        for c, r in pick(documents(dd, k), w):
            if r["docID"] in seen:
                continue
            seen.add(r["docID"])
            t = f"[EDINET] {c['ja'][0]}({c['code']}) {TYPES[r['docTypeCode']]} — {r.get('docDescription') or ''}"
            items.append(common.make_item("src-edinet", r["docID"], VIEW, t[:200], (r.get("submitDateTime") or dd).replace(" ", "T") + ":00+09:00"
                                          if len(r.get("submitDateTime") or "") == 16 else now.isoformat(), "공시", "ja",
                                          f"제출자 {r.get('filerName', '')} · docID {r['docID']} · EDINET에서 docID로 검색",
                                          extra={"entities_matched": [c["id"]], "source_class": "법정 공시(1차)"}))
    st["seen"] = sorted(seen)[-5000:]
    common.save_state("edinet", st)
    saved = common.save_new_items(items)
    common.record_health("edinet", True, f"새 서류 {len(saved)}")
    return f"EDINET 감시 {len(w)}곳 · 새 서류 {len(saved)}"


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(run(sys.argv[1] if len(sys.argv) > 1 else None))
