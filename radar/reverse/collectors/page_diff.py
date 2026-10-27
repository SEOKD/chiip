"""L7 웹 변경·침묵 탐지 — config/page_watch.yaml의 공개 페이지를 텍스트로 정규화해 기준선과 비교.
변경분(추가·삭제 줄)만 후보로 저장 → page-diff-review가 판정.
"""
import difflib
import hashlib

from common_rev import common, save_candidates

SOURCE_ID = "src-page-diff"
BASE = common.ROOT / "radar" / "reverse" / "baselines"


def normalize(raw):
    text = common.strip_tags(raw.decode("utf-8", errors="ignore"))
    return [l.strip() for l in text.splitlines() if l.strip()]


def run():
    pages = (common.load_yaml("config/page_watch.yaml") or {}).get("pages") or []
    BASE.mkdir(parents=True, exist_ok=True)
    cands = []
    for p in pages:
        lines = normalize(common.http_get(p["url"], timeout=30))
        f = BASE / f"{p['id']}.txt"
        old = f.read_text(encoding="utf-8").splitlines() if f.exists() else None
        f.write_text("\n".join(lines), encoding="utf-8")
        if old is None:
            continue  # 첫 실행 = 기준선
        diff = [d for d in difflib.unified_diff(old, lines, lineterm="", n=0) if d[:1] in "+-" and d[:3] not in ("+++", "---")]
        if not diff:
            continue
        for eid in p.get("watch_for", []) or [None]:
            cands.append({"uid": hashlib.sha1(("\n".join(diff)).encode()).hexdigest()[:16], "mentioned_entity": eid,
                          "match_text": "", "counterparty": p["id"], "form": "웹변경",
                          "published_at": common.iso(common.now_kst()), "language": "", "url": p["url"],
                          "diff": diff[:80], "signal_type_hint": "웹변경"})
    n = save_candidates("L7", SOURCE_ID, cands)
    common.record_health(SOURCE_ID, True)
    return len(cands), n


if __name__ == "__main__":
    print("웹 변경: 후보 %d, 신규 %d" % run())