"""수집 관문 (BUILD_PROMPT §21.13) — common.save_new_items가 저장 직전에 부른다.

1) 관심도 집계: 관문에 걸러지기 전 모든 항목의 종목 언급을 날짜별로 센다(포커스 점수의 attention 재료).
   걸러진 종목도 세야 다시 포커스에 들어올 수 있다.
2) 뉴스 제한: doc_type '기사'는 마스터가 정한 7개 매체(alert_rules telegram_filter.allowed_publishers)만 저장.
3) 포커스 관문: 종목이 잡힌 항목은 포커스 종목(점수 ≥ 기준)이 하나라도 있어야 저장.
   종목이 안 잡힌 항목은 정책·학회·협회·X·리서치·7곳 기사만 저장(업계 전반 자료). 보도자료·공시는 종목이 있어야 한다.
"""
import json
from datetime import datetime, timedelta

from . import common

FOCUS_FILE = common.ROOT / "knowledge" / "models" / "focus" / "latest.json"
SECTOR_TYPES = {"규제·정책", "학회·협회", "SNS", "리서치", "기사"}
_CACHE = {}


def _cfg():
    return common.load_yaml("config/focus.yaml") or {}


def focus_state():
    """(포커스 id 집합 또는 None=관문 열림, 사유)"""
    cfg = _cfg()
    if not FOCUS_FILE.exists():
        return (None, "점수 파일 없음") if cfg.get("fail_open", True) else (set(cfg.get("always_include") or []), "")
    data = json.loads(FOCUS_FILE.read_text(encoding="utf-8"))
    try:
        age = common.now_kst().date() - datetime.fromisoformat(data["as_of"]).date()
    except (KeyError, ValueError):
        age = timedelta(days=999)
    if age > timedelta(days=int(cfg.get("stale_days", 3))) and cfg.get("fail_open", True):
        return None, f"점수 {age.days}일 지남"
    return set(data.get("focus", [])) | set(cfg.get("always_include") or []), ""


def news_allowed(item):
    if item.get("doc_type") != "기사":
        return True
    if "allowed" not in _CACHE:
        rule = (common.load_yaml("config/alert_rules.yaml") or {}).get("telegram_filter") or {}
        _CACHE["allowed"] = {p.lower() for p in rule.get("allowed_publishers", [])}
    pub = item.get("publisher") or (item.get("title", "").rsplit(" - ", 1)[1] if " - " in item.get("title", "") else "")
    return pub.strip().lower() in _CACHE["allowed"]


def keep(item, focus):
    if not news_allowed(item):
        return False
    ents = item.get("entities_matched") or []
    if item.get("doc_type") in ("규제·정책", "학회·협회"):
        return True
    if focus is None:
        return True
    if ents:
        return any(e in focus for e in ents)
    return item.get("doc_type") in SECTOR_TYPES


def count_mentions(items):
    """종목별 일 언급 수(같은 항목은 하루 한 번). radar/state/mentions.json"""
    st = common.load_state("mentions", {"days": {}, "seen": {}})
    day = common.now_kst().strftime("%Y%m%d")
    counts = st["days"].setdefault(day, {})
    seen = set(st["seen"].get(day, []))
    for it in items:
        if it["item_id"] in seen:
            continue
        seen.add(it["item_id"])
        for e in it.get("entities_matched") or []:
            counts[e] = counts.get(e, 0) + 1
    st["seen"][day] = sorted(seen)
    keep_days = sorted(st["days"])[-14:]
    st["days"] = {d: st["days"][d] for d in keep_days}
    st["seen"] = {d: v for d, v in st["seen"].items() if d in keep_days[-2:]}
    common.save_state("mentions", st)


def mentions(days=7, end=None):
    st = common.load_state("mentions", {"days": {}})
    end = end or common.now_kst().date()
    want = {(end - timedelta(days=i)).strftime("%Y%m%d") for i in range(days)}
    out = {}
    for d, c in st.get("days", {}).items():
        if d in want:
            for e, n in c.items():
                out[e] = out.get(e, 0) + n
    return out


def apply(items):
    if not items:
        return items
    count_mentions(items)
    focus, _ = focus_state()
    return [it for it in items if keep(it, focus)]
