"""레이더 공통 모듈 — 정규화·중복제거·상태·헬스 (BUILD_PROMPT §5.12, §10.4)

수집 스크립트는 모델을 호출하지 않는다. 새 항목 판단은 run_triage.py가 한다.
"""
import hashlib
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _hide_child_windows():
    """창 없는 수집기(pyw)가 띄우는 하위 프로그램(pdftotext·git·claude 등)이 CMD 창을 띄우지 않게 — 모든 subprocess의 기본값에
    CREATE_NO_WINDOW를 더한다(마스터 지시 2026-10-30 "계속 CMD 창이 뜬다"). 호출부가 직접 준 flags는 그대로 두고 비트만 더한다"""
    if os.name != "nt":
        return
    import subprocess
    if getattr(subprocess.Popen, "_chiip_hidden", False):
        return
    orig = subprocess.Popen.__init__

    def init(self, *a, **kw):
        kw["creationflags"] = kw.get("creationflags", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        orig(self, *a, **kw)
    subprocess.Popen.__init__ = init
    subprocess.Popen._chiip_hidden = True


_hide_child_windows()
KST = timezone(timedelta(hours=9))
LOCAL_ONLY = Path(os.environ.get("CHIIP_LOCAL_ONLY", r"D:\local-only"))
STATE = ROOT / "radar" / "state"
INBOX = ROOT / "radar" / "inbox"
UA = "chiip-radar/0.1 (personal research)"


def stay_awake():
    """수집 중 절전 진입 막기(이 프로세스가 끝나면 자동 해제) — 작업 스케줄러 '절전 중 깨우기'로 깨어난 뒤
    수집을 마치기 전에 다시 잠들지 않게(마스터 승인 2026-10-29). 윈도우 전원 설정은 바꾸지 않는다"""
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)   # ES_CONTINUOUS | ES_SYSTEM_REQUIRED


# ---------- 시간 ----------
def now_kst():
    return datetime.now(KST)


def iso(dt):
    return dt.isoformat(timespec="seconds")


# ---------- 설정 ----------
def load_yaml(path):
    p = ROOT / path if not Path(path).is_absolute() else Path(path)
    if not p.exists():
        return None
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def load_env():
    """D:\\local-only\\secrets\\.env 를 읽는다. 값은 로그·출력에 쓰지 않는다."""
    env = {}
    f = LOCAL_ONLY / "secrets" / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    for k, v in os.environ.items():
        if k.isupper():
            env.setdefault(k, v)
    return env


def load_watchlist():
    import csv
    with (ROOT / "config" / "watchlist.csv").open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def tier_of(entity_id, watchlist=None):
    for row in watchlist or load_watchlist():
        if row["entity_id"] == entity_id:
            return row["tier"]
    return None


def entity_aliases():
    """entity_id -> 검색용 이름 목록 (watchlist 이름 + 엔티티 파일 aliases + lexicon names)"""
    out = {}
    for row in load_watchlist():
        names = {row["name"]}
        base = re.sub(r"\s*\(.*?\)", "", row["name"]).strip()
        names.add(base)
        efile = ROOT / "knowledge" / "entities" / "companies" / f"{row['entity_id']}.md"
        if efile.exists():
            text = efile.read_text(encoding="utf-8")
            m = re.search(r"^aliases:\s*\[(.*?)\]", text, re.M)
            if m:
                names.update(a.strip() for a in m.group(1).split(",") if a.strip())
        lex = load_yaml(f"config/lexicon/{row['entity_id']}.yaml")
        if lex and isinstance(lex.get("names"), dict):
            for vals in lex["names"].values():
                names.update(vals or [])
        out[row["entity_id"]] = sorted(n for n in names if len(n) >= 2)
    # 밸류에이션 유니버스(config/valuation.yaml)에만 있는 종목 — aliases가 있으면 그것만(일반 단어 오탐 방지)
    for u in (load_yaml("config/valuation.yaml") or {}).get("universe", []):
        if u["id"] not in out:
            out[u["id"]] = sorted(n for n in (u.get("aliases") or [u["name"]]) if len(n) >= 2)
        elif u.get("en") and u["en"] not in out[u["id"]]:
            out[u["id"]] = sorted(out[u["id"]] + [u["en"]])
    # 어닝 감시 확장 종목(config/earnings_watch.yaml extra) — 레이더·공시·핵심 루프가 같은 종목을 보게(2026-10-28 GEV 누락 수정)
    for u in (load_yaml("config/earnings_watch.yaml") or {}).get("extra") or []:
        if u["id"] not in out:
            names = set(u.get("aliases") or [u["name"]])
            if u.get("kind_name"):
                names.add(u["kind_name"])
            out[u["id"]] = sorted(n for n in names if len(n) >= 2)
    # Ten-bagger 발굴 후보·커버리지·구간 시드(2026-10-29) — 같은 코드가 이미 감시 목록에 있으면 그 id에 이름만 더한다
    by_code = {}
    for f in ("config/valuation.yaml", "config/earnings_watch.yaml"):
        for u in (load_yaml(f) or {}).get("universe" if "valuation" in f else "extra") or []:
            if u.get("code"):
                by_code.setdefault(str(u["code"]).upper(), u["id"])
    for cid, names, code in discovery_entities():
        key = by_code.get(code.upper(), cid) if code else cid
        if names or key in out:
            out[key] = sorted(set(out.get(key, [])) | {n for n in names if len(n) >= 2})
    # 방위 섹터 지도(config/defense.yaml, 마스터 지시 2026-10-29) — 이미 있는 종목은 현지 표기만 더한다
    for u in defense_companies():
        names = set(u.get("aliases") or [u["name"]]) | ({u["local"]} if u.get("local") else set())
        out[u["id"]] = sorted(set(out.get(u["id"], [])) | {n for n in names if len(n) >= 2})
    return out


GENERIC_NAMES = {"Elastic", "Diodes", "Tenable", "Applied", "Box", "Nova", "Asana", "Braze"}   # 일반어와 겹치는 회사명 — aliases가 있어야 인식


def _distinct(name):
    """레이더 인식에 써도 되는 이름인가 — 짧거나 일반어면 aliases로만(2026-10-29: 'Nova'·'Box'·'Diodes' 오탐 방지)"""
    return bool(name) and len(name) >= 5 and name not in GENERIC_NAMES


def discovery_entities():
    """Ten-bagger 발굴 후보·커버리지·구간 시드 → [(id, 이름 목록, 코드)] — 마스터 지시 2026-10-29 "FormFactor·Nova 같은 엣지 있는
    중소형 종목도 반드시 관측": 발굴 대상이 레이더 종목 인식·SEC 공시 수집에서 빠지지 않게"""
    out = []
    for t in (load_yaml("config/discovery.yaml") or {}).get("themes") or []:
        for c in t.get("candidates") or []:
            names = list(c.get("aliases") or ([c["name"]] if _distinct(c.get("name")) else []))
            names += [c["local"]] if c.get("local") else []
            names += list(c.get("ko") or [])
            code = f"{c.get('code')}.US" if c.get("market") == "us" and c.get("code") else str(c.get("code") or "")
            out.append((c["id"], names, code))
    for c in (load_yaml("config/coverage.yaml") or {}).get("companies") or []:
        out.append((c["id"], [c["name"]] if _distinct(c.get("name")) else [], str(c.get("code") or "")))
    for seeds in ((load_yaml("config/tenbagger_universe.yaml") or {}).get("seeds") or {}).values():
        for s in seeds or []:
            names = list(s.get("aliases") or ([s["name"]] if _distinct(s.get("name")) else []))
            out.append((f"us-{s['ticker'].lower()}", names, f"{s['ticker']}.US"))
    return out


def edge_watch_entries():
    """SEC 공시 수집에 더할 미국 상장 발굴 종목 — 조용한 매집형 상승 watch(knowledge/models/discovery/quiet_latest.json) + 마스터 지정 always_watch"""
    q = ROOT / "knowledge" / "models" / "discovery" / "quiet_latest.json"
    ids = set(json.loads(q.read_text(encoding="utf-8")).get("watch") or []) if q.exists() else set()
    ids |= set(((load_yaml("config/discovery.yaml") or {}).get("quiet") or {}).get("always_watch") or [])
    out = {}
    for cid, names, code in discovery_entities():   # 발굴 후보와 구간 시드에 같은 종목이 있으면 이름을 합친다
        if cid in ids and code.endswith(".US"):
            e = out.setdefault(cid, {"id": cid, "name": (names or [cid])[0], "aliases": [], "code": code})
            e["aliases"] = list(dict.fromkeys(e["aliases"] + list(names)))
    return list(out.values())


def defense_companies():
    """방위 섹터 지도의 기업 목록(상장·비상장 모두)"""
    return (load_yaml("config/defense.yaml") or {}).get("companies") or []


_ALIAS_CACHE = None


def match_entities(text):
    global _ALIAS_CACHE
    if _ALIAS_CACHE is None:
        _ALIAS_CACHE = entity_aliases()
    hits = []
    low = text.lower()
    for eid, names in _ALIAS_CACHE.items():
        for n in names:
            # 짧은 영문 약칭은 단어 경계로
            if re.fullmatch(r"[A-Za-z]{2,4}", n):
                if re.search(rf"\b{re.escape(n)}\b", text):
                    hits.append(eid)
                    break
            elif re.search(r"[A-Za-z]", n):   # 영문 이름은 단어 경계로(2026-10-29: 'Applebee's'가 Apple로 잡혀 P1 오발송)
                if re.search(rf"(?<![A-Za-z0-9]){re.escape(n)}(?![A-Za-z0-9])", text, re.I):
                    hits.append(eid)
                    break
            elif n.lower() in low:   # 한·중·일 이름은 부분 일치
                hits.append(eid)
                break
    return hits


_KW_CACHE = None


def match_keywords(text):
    global _KW_CACHE
    if _KW_CACHE is None:
        data = load_yaml("config/keywords.yaml") or {}
        kws = set()
        for key, vals in data.items():
            if key == "events":
                for v in (vals or {}).values():
                    kws.update(v)
            else:
                for v in vals or []:
                    kws.update(p.strip() for p in str(v).split("/"))
        _KW_CACHE = sorted(k for k in kws if len(k) >= 2)
    low = text.lower()
    return [k for k in _KW_CACHE if k.lower() in low]


# ---------- HTTP ----------
def http_get(url, params=None, headers=None, timeout=20):
    if params:
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def strip_tags(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


# ---------- 상태 ----------
def _read_json(path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return default
    return default


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def load_state(name, default=None):
    return _read_json(STATE / f"{name}.json", {} if default is None else default)


def save_state(name, data):
    _write_json(STATE / f"{name}.json", data)


def record_health(source_id, ok, error=None):
    h = load_state("health")
    e = h.setdefault(source_id, {"last_ok": None, "last_error": None, "error_count": 0})
    if ok:
        e["last_ok"] = iso(now_kst())
        e["error_count"] = 0
    else:
        e["last_error"] = f"{iso(now_kst())} {str(error)[:200]}"
        e["error_count"] += 1
    save_state("health", h)


def is_due(source_id, interval_min):
    last = load_state("last_run").get(source_id)
    if not last:
        return True
    return now_kst() - datetime.fromisoformat(last) >= timedelta(minutes=interval_min)


def mark_run(source_id):
    s = load_state("last_run")
    s[source_id] = iso(now_kst())
    save_state("last_run", s)


def interval_for(tier, when=None):
    """alert_rules.yaml schedule 에서 현재 시각의 폴링 간격(분)"""
    when = when or now_kst()
    rules = (load_yaml("config/alert_rules.yaml") or {}).get("schedule", {})
    key = "weekend" if when.weekday() >= 5 else "weekday"
    hhmm = when.strftime("%H:%M")
    col = "T0" if tier == "T0" else "T2"
    for slot in rules.get(key, []):
        a, b = slot["from"], slot["to"]
        inside = (a <= hhmm < b) if a < b else (hhmm >= a or hhmm < b)
        if inside:
            return slot.get(col, 60)
    return 60


# ---------- 항목 ----------
def make_item(source_id, uid, url, title, published_at, doc_type, language, snippet="", extra=None):
    text = f"{title} {snippet}"
    item = {
        "item_id": f"{source_id}:{uid}",
        "source_id": source_id,
        "url": url,
        "title": title.strip(),
        "published_at": published_at,
        "detected_at": iso(now_kst()),
        "entities_matched": match_entities(text),
        "keywords_matched": match_keywords(text),
        "doc_type": doc_type,
        "language": language,
        "snippet": (snippet or "")[:200],
        "content_hash": hashlib.sha1(f"{title}|{url}".encode("utf-8")).hexdigest(),
        "event_cluster": None,
    }
    if extra:
        item.update(extra)
    return item


def save_new_items(items):
    """처음 보는 항목만 inbox에 저장하고 반환. 저장 전 수집 관문(뉴스 7곳·포커스 종목, pollers/gate.py)을 거친다"""
    from . import gate
    items = gate.apply(items)
    seen = load_state("seen")
    new = []
    for it in items:
        if it["item_id"] in seen or it["content_hash"] in seen.values():
            continue
        seen[it["item_id"]] = it["content_hash"]
        day = INBOX / now_kst().strftime("%Y%m%d")
        day.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", it["item_id"])[:120]
        (day / f"{safe}.json").write_text(json.dumps(it, ensure_ascii=False, indent=1), encoding="utf-8")
        new.append(it)
    # 오래된 seen 정리(최근 2만 건 유지)
    if len(seen) > 20000:
        seen = dict(list(seen.items())[-20000:])
    save_state("seen", seen)
    return new
