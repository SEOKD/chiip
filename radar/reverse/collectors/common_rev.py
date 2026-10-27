"""역방향 레이더 수집기 공통 (BUILD_PROMPT §11.11) — 모델 호출 없음

수집 결과는 '후보(candidate)'다. scout 에이전트가 판정해 신호 레코드(SIG-)로 만든다.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # radar/
from pollers import common  # noqa: E402

REV_INBOX = common.ROOT / "radar" / "reverse" / "inbox"


def lexicon():
    """entity_id -> {'names': [...], 'negative': [...]} (lexicon 없으면 watchlist·엔티티 별칭)"""
    out = {}
    aliases = common.entity_aliases()
    for row in common.load_watchlist():
        if row["tier"] != "T0":
            continue
        eid = row["entity_id"]
        lex = common.load_yaml(f"config/lexicon/{eid}.yaml") or {}
        names = set(aliases.get(eid, []))
        for vals in (lex.get("names") or {}).values():
            names.update(vals or [])
        names.update(lex.get("legal_entities") or [])
        out[eid] = {"names": sorted(n for n in names if len(n) >= 3),
                    "negative": lex.get("negative_context") or [],
                    "euphemisms": lex.get("euphemisms") or {}}
    return out


def english_names(eid, lex=None):
    lex = lex or lexicon()
    seen, out = set(), []
    for n in lex[eid]["names"]:  # 대소문자만 다른 표기는 하나로(전문 검색은 대소문자 무시)
        if re.fullmatch(r"[A-Za-z0-9 .,&'-]+", n) and len(n) >= 5 and n.lower() not in seen:
            seen.add(n.lower())
            out.append(n)
    return out


def save_candidates(layer, source_id, cands):
    """후보 저장(중복 제거). 반환: 새 후보 수"""
    seen = common.load_state("rev_seen")
    day = REV_INBOX / common.now_kst().strftime("%Y%m%d")
    new = 0
    for c in cands:
        key = f"{source_id}:{c['uid']}:{c.get('mentioned_entity', '')}"
        if key in seen:
            continue
        seen[key] = common.iso(common.now_kst())
        day.mkdir(parents=True, exist_ok=True)
        c.update({"layer": layer, "source_id": source_id, "detected_at": common.iso(common.now_kst()),
                  "status": "후보"})
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", key)[:150]
        (day / f"{safe}.json").write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")
        new += 1
    if len(seen) > 30000:
        seen = dict(list(seen.items())[-30000:])
    common.save_state("rev_seen", seen)
    return new
