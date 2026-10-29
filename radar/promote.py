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


def _holdings():
    """[(보유 티커, 정규식)] — 회사명·별칭·티커"""
    if "held" not in _CACHE:
        out = []
        for h in (common.load_yaml("config/portfolio.yaml") or {}).get("holdings") or []:
            if h.get("status", "보유") != "보유":
                continue
            alts = [r"\b" + re.escape(n) + r"\b" for n in (h.get("names") or [h["name"]])] + [r"\b" + re.escape(h["ticker"]) + r"\b"]
            out.append((h["ticker"], re.compile("|".join(alts), re.I)))
        _CACHE["held"] = out
    return _CACHE["held"]


MAJOR_RE = re.compile(r"acqui|merger|takeover|\bbuy(s|ing)?\b|deal|talks|is said to|earnings|results|guidance|forecast|offering|convertible|"
                      r"downgrade|upgrade|lawsuit|probe|ban\b|CEO|CFO|resign", re.I)


EVENT_CLASS = [("ma", re.compile(r"acqui|merger|takeover|\bbuy(s|ing)?\b|deal|talks|is said to|bid\b", re.I)),
               ("earn", re.compile(r"earnings|results|guidance|forecast|outlook", re.I)),
               ("fin", re.compile(r"offering|convertible|notes|debt|raise", re.I)),
               ("rating", re.compile(r"downgrade|upgrade|price target|initiat", re.I)),
               ("mgmt", re.compile(r"\bCEO\b|\bCFO\b|resign|appoint", re.I)),
               ("legal", re.compile(r"lawsuit|probe|investigation|ban\b|tariff|export control", re.I))]


JP_EVENT = [("guide", re.compile(r"業績予想の修正|上方修正|下方修正|最高益|通期.{0,6}(引き上げ|引き下げ)")),
            ("capex", re.compile(r"設備投資|新工場|増産|固定資産の取得")),
            ("return", re.compile(r"自社株買い|自己株式の取得|増配")),
            ("deal", re.compile(r"買収|株式取得|提携|資本業務提携|公開買付|ＴＯＢ|TOB")),
            ("equity", re.compile(r"公募|新株|第三者割当|転換社債")),
            ("earn", re.compile(r"決算短信|決算速報"))]   # '決算' 단독은 시황·기업 정보 페이지까지 잡아 제외(2026-10-29)
JP_LABEL = {"guide": "실적 전망 수정", "capex": "설비투자", "return": "주주환원", "deal": "인수·제휴", "equity": "자금 조달", "earn": "실적 발표"}


def level_for(item, why):
    """보유 종목의 큰 사건(M&A·실적·가이던스·증자·투자의견·경영진)은 P0, 나머지 상향은 P1"""
    if why and "숏 리포트" in why and "보유 종목" in why:
        return "P0"
    if why and why.startswith("규칙 상향: 보유 종목") and MAJOR_RE.search(_title(item)):
        return "P0"
    return "P1"


def _shorts():
    if "shorts" not in _CACHE:
        c = common.load_yaml("config/short_watch.yaml") or {}
        _CACHE["shorts"] = {"firms": re.compile("|".join(r"\b" + re.escape(n) + r"\b" for n in c.get("firms") or []) or r"$^", re.I),
                            "terms": re.compile(c.get("terms") or r"$^", re.I)}
    return _CACHE["shorts"]


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
    sh = _shorts()
    firm, short = sh["firms"].search(title), sh["terms"].search(title) or re.search(r"\bshort", title, re.I)
    if (firm and short) or short:   # 숏 리포트(2026-10-29 — Culper의 Cerebras 리포트 누락 뒤). 운용사 이름만 걸린 다른 글은 제외
        target = next((tk for tk, pat in _holdings() if pat.search(title)), None)
        if target and (firm or sh["terms"].search(title)):
            return f"규칙 상향: 보유 종목 {target} 숏 리포트", f"short:{target}"
        org = _fin()["orgs"].search(title)
        if (firm or sh["terms"].search(title)) and (ents or org):
            return "규칙 상향: AI 밸류체인 숏 리포트", "short:" + (",".join(ents) or (org.group(0).lower() if org else re.sub(r"\W+", " ", title.lower())[:50]))
    if item.get("source_id") == "src-jp-disclosure" and ents and not noise(item):   # 일본 정보망(2026-10-29 — 이비덴·어드밴테스트 실적 상향 누락 뒤)
        cls = next((k for k, rx in JP_EVENT if rx.search(title)), None)
        if cls:
            return f"규칙 상향: 일본 {JP_LABEL[cls]}", f"jp:{','.join(ents)}:{cls}"
    ev = (r.get("portfolio_related") or {}).get("event") or r"$^"
    for tk, pat in _holdings():   # 마스터 보유 종목 자체(2026-10-29 — MRVL·Lumentum 인수 협상 보도가 P2로 묻힌 뒤)
        if pat.search(title):
            cls = next((k for k, rx in EVENT_CLASS if rx.search(title)), "event" if re.search(ev, title, re.I) else None)
            if cls:   # 사건 문구가 없는 시황('shares edge higher')은 올리지 않는다. 같은 사건 기사 여러 건은 종목×사건 종류로 묶는다
                return f"규칙 상향: 보유 종목 {tk}", f"held:{tk}:{cls}"
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
    ctx = (r.get("mega_deal") or {}).get("context") or r"$^"
    if m:
        for tk, name, pat in _related():   # AI·데이터센터·전력 문맥이 있어야(2026-10-29: 지멘스에너지 해상풍력 협력이 INIO 관련으로 오발송)
            if pat.search(title) and re.search(m["event"], title, re.I) and re.search(ctx, title, re.I):
                return f"규칙 상향: 보유 {tk} 관련({name})", f"rel:{tk}:{name.lower()}"
    return None


NOISE_RE = re.compile(r"株価・株式情報|企業情報|：企業概要|寄り前|引け後|後場コメント|前場コメント|株価指数先物|個別銘柄戦略|決算発表予定|注目銘柄|transcript|earnings call (presentation|slides)|\bslides\b|\bpresentation\b|\bvideo\b|podcast|daily briefing|"
                      r"newsletter|stock price|in real time|live updates?|what to know|stocks to watch|top stocks|premarket|"
                      r"pre-market movers|movers|closing bell|market wrap|evening briefing|morning briefing|\bopinion\b", re.I)
_STOP = {"the", "a", "an", "of", "to", "in", "on", "for", "and", "as", "at", "by", "with", "its", "is", "are", "after", "from", "says", "said"}


def noise(item):
    """제목만 봐도 새 사실이 아닌 것(콜 녹취 전재·발표 자료·영상·브리핑·시세 페이지) — P1에서 P2로 내린다"""
    return bool(NOISE_RE.search(_title(item)))


def _words(t):
    return {w for w in re.sub(r"[^a-z0-9$ ]", " ", t.lower()).split() if w not in _STOP and len(w) > 1}


def duplicate_of(item, hours=12, now=None):
    """지난 hours 안에 보낸 P0·P1(radar/state/alerts.json)과 같은 사건이면 그 제목 — 같은 종목 + 제목 단어 겹침 50% 이상,
    또는 종목 무관 70% 이상(같은 사건 기사가 여러 매체·배치로 들어와 P1이 겹치던 문제, 2026-10-29)"""
    now = now or common.now_kst()
    w = _words(_title(item))
    if len(w) < 3:
        return None
    ents = set(item.get("entities_matched") or [])
    for a in common.load_state("alerts", {}).values():
        try:
            if datetime.fromisoformat(a.get("sent_at")) < now - timedelta(hours=hours):
                continue
        except (TypeError, ValueError):
            continue
        if a.get("item_id") == item.get("item_id"):
            continue
        aw = _words((a.get("title") or "").rsplit(" - ", 1)[0])
        if not aw:
            continue
        j = len(w & aw) / len(w | aw)
        if j >= 0.7 or (ents & set(a.get("entities") or []) and j >= 0.5):
            return a.get("title")
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
