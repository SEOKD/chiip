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
TW_EVENT_RE = re.compile(r"財務報告|自結|營收|財務預測|資本支出|擴廠|擴產|現金增資|可轉換公司債|收購|併購|合併(?!財務)|重大合約|股利|庫藏股|取得.{0,6}(設備|廠房)")
TW_NOISE_RE = re.compile(r"代子公司|代重要子公司|聯合授信|授信|背書保證|資金貸與|更正|補充說明|更新取得|增資.{0,10}(子公司|轉投資)")   # 자회사 대리·금융 약정·정정 — 원문이지만 사건 아님
# 방위 섹터(2026-10-29 마스터 지시, config/defense.yaml) — 수주·계약·대외군사판매·양산 결정·실적. 다국어 원문 제목
DEF_EVENT_RE = re.compile(r"\b(contracts?|awards?|awarded|orders?|selected|framework|multi-?year|full-rate production|LRIP|Foreign Military Sales?|backlog|results|guidance)\b|"
                          r"Rahmenvertrag|Auftrag|Bestellung|commande|contrat|contratto|contrato|adjudica|契約|受注|業績予想", re.I)
DEF_NOISE_RE = re.compile(r"webinar|conference call invitation|invitation|celebrat|showcase|demonstrat|exercise|anniversary|visits?\b|award(s|ed)? (for|to) (employee|excellence)|"
                          r"scholarship|career|sponsor|\bhonou?r", re.I)


def defense_ids():
    if "def" not in _DEF:
        _DEF["def"] = {c["id"] for c in common.defense_companies()}
    return _DEF["def"]


_DEF = {}
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
        names = (c.get("firms") or []) + (c.get("firm_short") or [])   # 정식 이름 + 기사 제목의 짧은 이름(2026-10-29)
        _CACHE["shorts"] = {"firms": re.compile("|".join(r"\b" + re.escape(n) + r"\b" for n in names) or r"$^", re.I),
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
    site = item.get("source_id") == "src-short-sites"   # 운용사 원문 사이트의 새 글 = 그 자체가 숏 리포트(2026-10-29)
    if site and not firm:
        firm = re.search(re.escape(_publisher(item) or "운용사"), _publisher(item) or "운용사")
    # 숏 리포트(2026-10-29 — Culper의 Cerebras 리포트 누락 뒤). 실제 제목은 'short'를 안 쓰는 경우가 많다
    # ('Culper Research Takes Aim at Cerebras', 'Cerebras shares fall after Culper report') → 운용사 이름 + 대상 종목이면 충분
    if firm or short:
        target = next((tk for tk, pat in _holdings() if pat.search(title)), None)
        if target and (firm or sh["terms"].search(title)):
            return f"규칙 상향: 보유 종목 {target} 숏 리포트", f"short:{target}"
        org = _fin()["orgs"].search(title)
        tk = re.search(r"\((?:NASDAQ|NYSE|NYSEAMERICAN|TSX|ASX)?:?\s*([A-Z]{1,5})\)", title)
        if (firm or sh["terms"].search(title)) and (ents or org or (site and tk)):
            return "규칙 상향: AI 밸류체인 숏 리포트", "short:" + (",".join(ents) or (org.group(0).lower() if org else tk.group(1) if tk else re.sub(r"\W+", " ", title.lower())[:50]))
    if item.get("source_id") == "src-tw-disclosure" and ents and TW_EVENT_RE.search(title) and not TW_NOISE_RE.search(title):   # 대만 원문 공시(2026-10-29 Chiip Ten-bagger Discovery)
        return "규칙 상향: 대만 공시", f"tw:{','.join(ents)}:{TW_EVENT_RE.search(title).group(0)}"
    sid = item.get("source_id") or ""
    dsca = re.match(r"DSCA [\d-]+", title) if sid == "src-defense-gov-gn" else None
    if dsca:   # 미 대외군사판매 의회 통보(DSCA 보도자료 번호)
        return "규칙 상향: 미 대외군사판매 통보", f"dsca:{dsca.group(0)}"
    dents = [e for e in ents if e in defense_ids()]
    dev = DEF_EVENT_RE.search(title)
    if dents and dev and not DEF_NOISE_RE.search(title):
        amt = amount_billion(text)
        if sid.startswith("src-defense-") or (amt is not None and amt >= 1):   # 방위 원천은 수주·계약이면, 그 밖(보도자료 배포처·SEC)은 10억 달러 이상만
            return "규칙 상향: 방위 수주·계약", f"def:{','.join(dents)}:{dev.group(0).lower()}"
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
    """영문은 단어, 한·중·일은 글자 2개씩 — 일본어 제목이 빈 집합이 되어 중복 검사를 빠져나가던 문제(2026-10-29 이비덴)"""
    t = re.sub(r"\[\d{3,4}[A-Z]?\]|\d{4}年\d{1,2}月\d{1,2}日|\(適時開示\)|：日経会社情報DIGITAL|日本経済新聞", " ", t)
    out = {w for w in re.sub(r"[^a-z0-9$ ]", " ", t.lower()).split() if w not in _STOP and len(w) > 1}
    cjk = re.sub(r"[^぀-ヿ一-鿿가-힯]", "", t)
    out |= {cjk[i:i + 2] for i in range(len(cjk) - 1)}
    return out


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


# ---- 사건 단위 발송(마스터 지시 2026-10-29 "P1은 항상 원문 중심으로만 중복 없이 한 번만") ----
EVENT_TYPES = [   # (종류, 회사가 스스로 발표하는 사건인가, 정규식 — 영·일·한)
    ("guide", True, re.compile(r"guidance|outlook|forecast|raises?.{0,20}(view|target|outlook)|業績予想|上方修正|下方修正|通期.{0,6}(予想|見通し)|가이던스|전망치|실적 전망", re.I)),
    ("earn", True, re.compile(r"earnings|results|quarter|revenue|profit|決算|最高益|増益|減益|실적|영업이익|매출", re.I)),
    ("capex", True, re.compile(r"capex|capital (spending|expenditure)|new (plant|fab|factory)|expan(d|sion)|設備投資|新工場|増産|固定資産の取得|증설|설비투자", re.I)),
    ("return", True, re.compile(r"buyback|repurchase|dividend|自社株買い|自己株式|増配|配当|자사주|배당", re.I)),
    ("equity", True, re.compile(r"offering|convertible|private placement|公募|新株|第三者割当|転換社債|유상증자|전환사채", re.I)),
    ("contract", True, re.compile(r"contract|order|agreement|supply deal|受注|契約|수주|공급계약", re.I)),
    ("deal", False, re.compile(r"acqui|merger|takeover|in talks|nears? (a )?deal|買収|TOB|ＴＯＢ|인수|합병", re.I)),
    ("short", False, re.compile(r"short seller|short report|we are short|空売り|공매도", re.I)),
    ("rating", False, re.compile(r"upgrade|downgrade|price target|initiat|目標株価|レーティング|목표주가|투자의견", re.I)),
    ("legal", False, re.compile(r"lawsuit|probe|investigation|antitrust|DOJ|FTC|SAMR|ban\b|tariff|export control|訴訟|調査|소송|조사", re.I)),
]
PRIMARY_SOURCES = ("src-sec", "src-newsroom", "src-prn", "src-bw", "src-globenewswire", "src-dart", "src-edgar")
SCOOP_RE = re.compile(r"exclusive|scoop|is said to|people familiar|sources say|in talks|단독|関係者", re.I)


def event_type(item):
    title = _title(item)
    for name, company_originated, rx in EVENT_TYPES:
        if rx.search(title):
            return name, company_originated
    return "other", False


def is_primary(item):
    """회사·정부가 직접 낸 1차 자료인가 — 공시·보도자료·적시공시 원문(미러), 기업 뉴스룸"""
    sid = item.get("source_id") or ""
    if item.get("doc_type") in ("공시", "보도자료", "실적", "규제·정책") or sid.startswith(PRIMARY_SOURCES):
        return True
    return "適時開示" in (item.get("title") or "")


def event_key(item):
    """같은 사건 = 같은 주 종목 + 같은 사건 종류(하루 단위는 상태의 24시간 창으로). 종목이 없으면 제목 앞부분"""
    ents = sorted(item.get("entities_matched") or [])
    etype, _ = event_type(item)
    if etype in ("guide", "earn"):   # 실적과 가이던스는 같은 발표에서 함께 나온다 — 한 사건으로
        etype = "results"
    who = ents[0] if ents else re.sub(r"\W+", "", _title(item).lower())[:20]
    return f"{who}:{etype}"


def event_gate(item, level, now=None, window_h=24):
    """P0·P1을 보내기 전 사건 단위 판정 → (보낼지, 앞머리, 사유).
    ① 회사 발표형 사건(실적·가이던스·설비투자·주주환원·증자·계약)은 원문(공시·보도자료)만 보낸다 — 파생 기사는 P2(단독·관계자 보도는 예외)
    ② 같은 사건은 24시간에 한 번 — 단, 기사로 먼저 나간 사건의 원문이 나중에 오면 '[원문 확인]'으로 한 번 더"""
    now = now or common.now_kst()
    etype, company_originated = event_type(item)
    primary = is_primary(item)
    if level in ("P0", "P1") and company_originated and not primary and not SCOOP_RE.search(_title(item)):
        return False, "", f"원문 중심 — 회사 발표형 사건({etype})의 파생 기사"
    key = event_key(item)
    st = common.load_state("events_sent", {})
    prev = st.get(key)
    fresh = prev and datetime.fromisoformat(prev["at"]) > now - timedelta(hours=window_h)
    if fresh:
        if primary and not prev.get("primary"):
            st[key] = {"at": prev["at"], "primary": True}
            common.save_state("events_sent", st)
            return True, "[원문 확인] ", "기사로 먼저 나간 사건의 원문"
        return False, "", f"같은 사건 이미 발송({prev['at'][11:16]})"
    st[key] = {"at": common.iso(now), "primary": primary}
    for k in [k for k, v in st.items() if datetime.fromisoformat(v["at"]) < now - timedelta(days=3)]:
        del st[k]
    common.save_state("events_sent", st)
    return True, "", ""


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
