"""규칙 상향 (2026-10-29 마스터 지시 — Broadcom–Anthropic 630억 달러 금융 보도가 P2로 묻힌 뒤)

판정 모델(radar-triage)이 P2·P3로 둔 항목도 config/alert_rules.yaml promote_p1 규칙에 걸리면 P1로 올린다.
판정 기준이 T0(삼성·SK하이닉스) 중심이라 미국 AI 밸류체인 사건을 '일반 업계 뉴스'로 낮추는 문제를 결정론으로 보완한다.
  mega_deal        100억 달러 이상 + AI·칩·데이터센터·전력 문맥 + 거래 문구
  frontier_ipo     프런티어 AI 랩·AI 인프라 비상장사의 상장 서류
  exclusive        주요 매체 단독(감시 기업이 잡힌 것만)
  portfolio_related 마스터 보유 종목의 경쟁사·고객(config/portfolio.yaml related) + 사건 문구
같은 신호(서명)는 window_h 안에 1번만 올린다(같은 사건 기사 수십 건 폭주 방지). 상태: radar/state/promote.json
"""
import re
from datetime import datetime, timedelta

from pollers import common

STATE = "promote"
AMOUNT_RE = re.compile(r"(?:US)?\$\s?(\d{1,4}(?:[.,]\d+)?)\s?(trillion|tn|billion|bn|B)\b", re.I)
_CACHE = {}


def _rules():
    if "rules" not in _CACHE:
        _CACHE["rules"] = (common.load_yaml("config/alert_rules.yaml") or {}).get("promote_p1") or {}
    return _CACHE["rules"]


def _fin():
    if "fin" not in _CACHE:
        c = common.load_yaml("config/financing_watch.yaml") or {}
        _CACHE["fin"] = {"terms": re.compile(c.get("terms") or r"$^", re.I),
                         "orgs": re.compile("|".join(r"\b" + re.escape(n) + r"\b" for n in c.get("org_names") or []) or r"$^", re.I)}
    return _CACHE["fin"]


def _related():
    """[(보유 티커, 관련 이름, 정규식)]"""
    if "related" not in _CACHE:
        out = []
        for h in (common.load_yaml("config/portfolio.yaml") or {}).get("holdings") or []:
            if h.get("status", "보유") != "보유":
                continue
            for n in h.get("related") or []:
                out.append((h["ticker"], n, re.compile(rf"\b{re.escape(n)}\b", re.I)))
        _CACHE["related"] = out
    return _CACHE["related"]


def amount_billion(text):
    best = None
    for num, unit in AMOUNT_RE.findall(text or ""):
        v = float(num.replace(",", ""))
        v = v * 1000 if unit.lower() in ("trillion", "tn") else v
        best = v if best is None else max(best, v)
    return best


def _title(item):
    return (item.get("title") or "").rsplit(" - ", 1)[0]


def _publisher(item):
    if item.get("publisher"):
        return item["publisher"].strip()
    t = item.get("title") or ""
    return t.rsplit(" - ", 1)[1].strip() if " - " in t else ""


def match(item):
    """(이유, 서명) 또는 None — 상태를 보지 않는 순수 판정"""
    r = _rules()
    title = _title(item)
    text = f"{title} {item.get('snippet') or ''}"
    ents = sorted(item.get("entities_matched") or [])
    m = r.get("frontier_ipo") or {}
    if m:
        terms = re.compile(m["terms"], re.I)
        for lab in m.get("labs") or []:
            if re.search(rf"\b{re.escape(lab)}\b", title, re.I) and terms.search(title):
                return f"규칙 상향: 프런티어 AI 상장({lab})", f"ipo:{lab.lower()}"
    m = r.get("mega_deal") or {}
    if m:
        amt = amount_billion(text)
        if amt is not None and amt >= float(m.get("min_billion", 10)) and re.search(m["context"], text, re.I) and re.search(m["deal"], text, re.I):
            key = ",".join(ents) or re.sub(r"\W+", "", title.lower())[:24]
            return f"규칙 상향: AI 밸류체인 대형 거래(${amt:g}B)", f"mega:{key}:{round(amt)}"
    m = r.get("ai_financing") or {}
    if m:
        fin = _fin()
        amt = amount_billion(text)
        org = fin["orgs"].search(title)
        if amt is not None and amt >= float(m.get("min_billion", 1)) and fin["terms"].search(title) and (ents or org):
            key = ",".join(ents) or org.group(0).lower()
            return f"규칙 상향: AI 자금 조달(${amt:g}B)", f"fin:{key}:{round(amt)}"
    m = r.get("ma_talks") or {}
    pubs = {p.lower() for p in (r.get("exclusive") or {}).get("publishers") or []} | {"seeking alpha", "cnbc", "business insider"}
    if m and ents and _publisher(item).lower() in pubs and re.search(m["pattern"], title, re.I):
        return "규칙 상향: 감시 기업 M&A 보도", "ma:" + ",".join(ents)
    m = r.get("exclusive") or {}
    if m and ents and _publisher(item).lower() in {p.lower() for p in m.get("publishers") or []} and re.search(m["pattern"], title, re.I):
        return f"규칙 상향: {_publisher(item)} 단독", "excl:" + re.sub(r"\W+", " ", title.lower()).strip()[:80]
    m = r.get("portfolio_related") or {}
    if m:
        for tk, name, pat in _related():
            if pat.search(title) and re.search(m["event"], title, re.I):
                return f"규칙 상향: 보유 {tk} 관련({name})", f"rel:{tk}:{name.lower()}"
    return None


def check(item, now=None):
    """P1로 올릴 이유 또는 None. 올리면 서명을 기록한다(window_h 안 같은 서명은 None)"""
    hit = match(item)
    if not hit:
        return None
    why, sig = hit
    now = now or common.now_kst()
    st = common.load_state(STATE, {})
    sigs = st.setdefault("sigs", {})
    win = timedelta(hours=float(_rules().get("window_h", 24)))
    last = sigs.get(sig)
    if last and datetime.fromisoformat(last) > now - win:
        return None
    sigs[sig] = common.iso(now)
    for k in [k for k, v in sigs.items() if datetime.fromisoformat(v) < now - timedelta(days=7)]:
        del sigs[k]
    common.save_state(STATE, st)
    return why
