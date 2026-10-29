"""수집 관문 (BUILD_PROMPT §21.13) — common.save_new_items가 저장 직전에 부른다.

0) 신선도: 공개 시각이 오래된 항목은 버린다(config/alert_rules.yaml freshness — 마스터 지시 "무조건 시의성").
1) 관심도 집계: 관문에 걸러지기 전 모든 항목의 종목 언급을 날짜별로 센다(포커스 점수의 attention 재료).
   걸러진 종목도 세야 다시 포커스에 들어올 수 있다.
2) 뉴스 제한: doc_type '기사'는 마스터가 정한 9개 매체(alert_rules telegram_filter.allowed_publishers)만 저장.
3) 포커스 관문: 종목이 잡힌 항목은 포커스 종목(점수 ≥ 기준)이 하나라도 있어야 저장.
   종목이 안 잡힌 항목은 정책·학회·협회·X·리서치·지정 매체 기사만 저장(업계 전반 자료). 보도자료·공시는 종목이 있어야 한다.
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
    if cfg.get("retired"):   # 포커스 점수 기능 정리(2026-10-29) — 점수 대신 감시 목록 전체를 추적한다
        return None, "포커스 점수 폐지 — 감시 목록 전체"
    if not FOCUS_FILE.exists():
        return (None, "점수 파일 없음") if cfg.get("fail_open", True) else (set(cfg.get("always_include") or []), "")
    data = json.loads(FOCUS_FILE.read_text(encoding="utf-8"))
    try:
        age = common.now_kst().date() - datetime.fromisoformat(data["as_of"]).date()
    except (KeyError, ValueError):
        age = timedelta(days=999)
    if age > timedelta(days=int(cfg.get("stale_days", 3))) and cfg.get("fail_open", True):
        return None, f"점수 {age.days}일 지남"
    return set(data.get("focus", [])) | set(cfg.get("always_include") or []) | extra_focus(), ""


def extra_focus():
    """알파 잠재력 기준 이상 + 마스터 노션 Stocks + 레이더 테마(config/earnings_watch.yaml radar_themes) — 포커스 점수와 무관하게 추적"""
    if "extra_focus" not in _CACHE:
        ew = common.load_yaml("config/earnings_watch.yaml") or {}
        s = set(ew.get("master_stocks") or [])
        for ids in (ew.get("radar_themes") or {}).values():   # 레이더 테마(데이터센터 전력 등, 마스터 지시)
            s |= set(ids or [])
        s |= portfolio_ids()   # 마스터 포트폴리오(config/portfolio.yaml, 2026-10-29)
        s |= {c["id"] for c in common.defense_companies()}   # 방위 섹터 지도(config/defense.yaml, 2026-10-29 마스터 지시)
        p = common.ROOT / "knowledge" / "models" / "alpha" / "latest.json"
        if p.exists():
            try:
                s |= set(json.loads(p.read_text(encoding="utf-8")).get("pass", []))
            except ValueError:
                pass
        _CACHE["extra_focus"] = s
    return _CACHE["extra_focus"]


def portfolio_ids():
    """마스터 포트폴리오 보유 종목 id — 레이더·어닝 캘린더가 점수와 무관하게 항상 포함"""
    hs = (common.load_yaml("config/portfolio.yaml") or {}).get("holdings") or []
    return {h["id"] for h in hs if h.get("status", "보유") == "보유" and h.get("id")}


def watch_ids():
    """어닝 감시 전체(valuation universe + earnings_watch extra) — 이 종목들의 공시·실적은 포커스와 무관하게 저장"""
    if "watch" not in _CACHE:
        ids = {u["id"] for u in (common.load_yaml("config/valuation.yaml") or {}).get("universe", [])}
        ids |= {u["id"] for u in (common.load_yaml("config/earnings_watch.yaml") or {}).get("extra") or []}
        _CACHE["watch"] = ids
    return _CACHE["watch"]


def news_allowed(item):
    if item.get("doc_type") != "기사":
        return True
    if item.get("source_id") == "src-jp-disclosure":   # 일본 매체는 수집기가 config/jp_watch.yaml publishers로 이미 거름(2026-10-29)
        return True
    if "allowed" not in _CACHE:
        rule = (common.load_yaml("config/alert_rules.yaml") or {}).get("telegram_filter") or {}
        _CACHE["allowed"] = {p.lower() for p in rule.get("allowed_publishers", [])}
    pub = item.get("publisher") or (item.get("title", "").rsplit(" - ", 1)[1] if " - " in item.get("title", "") else "")
    return pub.strip().lower() in _CACHE["allowed"]


def keep(item, focus):
    if item.get("source_id") in ("src-short-sites", "src-jp-ir-qa", "src-tw-disclosure"):   # 숏 운용사 원문·일본 IR 질의응답은 포커스와 무관하게 저장(2026-10-29)
        return True
    if not news_allowed(item):
        return False
    ents = item.get("entities_matched") or []
    if item.get("doc_type") in ("규제·정책", "학회·협회"):
        return True
    if focus is None:
        return True
    if ents and item.get("doc_type") in ("공시", "실적") and any(e in watch_ids() for e in ents):
        return True   # 감시 종목의 공시·실적은 핵심 루프(알파 감지)의 원천이라 항상 저장
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


def _published(item):
    s = str(item.get("published_at") or "").strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        try:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(s)
        except (TypeError, ValueError):
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=common.KST)


def is_fresh(item, stage="collect"):
    """공개 시각 기준 신선도(config/alert_rules.yaml freshness). stage: collect | alert"""
    if "fresh" not in _CACHE:
        _CACHE["fresh"] = (common.load_yaml("config/alert_rules.yaml") or {}).get("freshness") or {}
    rule = _CACHE["fresh"]
    limits = rule.get(stage) or {}
    if not limits:
        return True
    dt = _published(item)
    dtype = item.get("doc_type")
    if dt is None:
        return dtype not in rule.get("drop_undated", [])
    hours = limits.get(dtype, limits.get("default", 48))
    return common.now_kst() - dt <= timedelta(hours=hours)  # 미래 시각(지방 회의 예정일 등)은 통과


def apply(items):
    if not items:
        return items
    count_mentions(items)
    focus, _ = focus_state()
    return [it for it in items if is_fresh(it, "collect") and keep(it, focus)]
