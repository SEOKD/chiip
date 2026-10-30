"""일본 IR 자료실 상시 감시 (마스터 지시 2026-10-30 "일본 시장 팔로업이 너무 느리다. 이비덴은 실적 PT 자료를 냈고 무라타도 실적 발표와 함께
PT 자료를 냈다. 일본 기업들은 실적 보도자료를 내도 PT 자료나 Q&A 스크립트를 뒤늦게 낸다 — 일본 상장기업 공식 IR 사이트는 지속적으로 들어가라").

jp_ir_qa.py가 놓친 것: ① IR 첫 화면만 보고 PDF가 실제로 걸리는 자료실 하위 페이지(決算説明会資料·決算短信·質疑応答 목록)는 보지 않았고
② 6시간마다였으며 ③ 説明会資料(PT)는 알림 대상이 아니었다. 이 수집기가 그 셋을 맡는다.

흐름(수집은 결정론, 판단은 모델):
  1) 자료실 페이지(doc_pages) — config/jp_ir.yaml의 doc_pages, 없으면 IR 페이지(jp_ir_qa 상태)에서 '決算説明会·決算短信·質疑応答·IRライブラリ'
     링크를 2단계까지 따라가 실제 자료 링크가 걸린 페이지를 찾는다(7일 보관, 한 회차에 DISCOVER_PER_RUN곳).
  2) 주기 — 실적 구간(적시공시 미러에 決算·説明会 제목, 이 수집기가 새 자료를 찾음, Q&A 대기 중 — 최근 HOT_DAYS일)인 회사는 매 회차(10분),
     나머지는 COLD_MIN분마다. 한 회차 페이지 요청은 MAX_FETCH회 이하(오래 안 본 회사부터).
  3) 자료 분류 kind_of — 動画(기록만) · 書き起こし(A) · 質疑応答(A/B) · 決算説明会資料(PT) · 決算短信 · 補足資料. 결산 기간(FY2026Q2)·날짜를
     앵커와 주소에서 읽는다. 과거 아카이브는 알리지 않는다(날짜가 FRESH_DAYS일 넘음, 또는 날짜 없이 최신 기간이 아님).
     페이지를 처음 볼 때는 기준선(최근 BACKLOG_DAYS일 자료만 알림 — 밀린 자료를 놓치지 않게).
  4) 새 자료는 내려받아 텍스트로(PDF·.ashx → pdftotext) radar/inbox/jp_ir/(git 제외)에만 두고, PT·短信은 직전 기간 같은 종류 자료도 받아 둔다(비교용).
     PT·短信·補足 → src-jp-ir-docs 'IR 자료'(펄스 ⑥-2), 質疑応答·書き起こし → src-jp-ir-qa 'IR 질의응답'(펄스 ⑥, jp_ir_qa와 같은 항목 id라 중복 없음).
  5) Q&A 대기 — Q&A·전문을 내 온 회사가 PT를 냈는데 같은 기간 Q&A가 없으면 +3·+7영업일까지 실적 구간으로 두고 매 회차 본다.
     올라오면 게재 시차를 IR 프로필에 기록, +7영업일에도 없으면 'Q&A 미게재 — 지시문 B 대상' 항목(knowledge/methods/jp_ir_qa_procedure.md).
robots.txt·1초 간격·로그인 영역 금지는 jp_ir_qa와 같다(fetch 공유). 저장소에는 요약·15단어 이하 인용·링크만.
사용: py radar/run_poll.py --only src-jp-ir-docs  ·  점검: py radar/pollers/jp_ir_docs.py [회사 id…] [--discover]
"""
import hashlib
import html as htmllib
import json
import re
import sys
import unicodedata
import urllib.parse
from datetime import date, datetime, timedelta
from pathlib import Path

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pollers import common, jp_ir_qa  # noqa: E402

SRC = "src-jp-ir-docs"
CACHE = common.ROOT / "radar" / "inbox" / "jp_ir"
STATE = "jp_ir_docs"
PARAMS = {"hot_days": 10, "cold_min": 180, "max_fetch": 45, "discover_per_run": 4, "fresh_days": 21, "backlog_days": 3}
VIDEO_RE = re.compile(r"動画|音声|配信|オンデマンド|webcast|audio|youtube\.com|youtu\.be|\.mp4|/video/", re.I)
KINDS = [  # 앞에서부터 — 'Q&A 書き起こし'는 전문, '動画配信(Q&A)'은 영상
    ("transcript", re.compile(r"書き起こし|書起こし|全文|スクリプト|transcript", re.I)),
    ("qa", jp_ir_qa.QA_RE),
    ("presentation", re.compile(r"決算説明会資料|説明会資料|決算説明資料|決算概要資料|プレゼンテーション資料|presentation|speach|speech|kessann?setsumei|setsumeikai", re.I)),
    ("tanshin", re.compile(r"決算短信|tanshin|-fls\b|_fls\b", re.I)),
    ("supplement", re.compile(r"補足資料|決算補足|参考資料|データブック|ファクトブック|fact ?book|data ?book|supplementary", re.I)),
]
KIND_KO = {"transcript": "결산설명회 전문", "qa": "결산설명회 질의응답", "presentation": "결산설명회 자료(PT)", "tanshin": "결산 단신", "supplement": "결산 보충 자료"}
QA_KINDS, MAT_KINDS = ("transcript", "qa"), ("presentation", "tanshin", "supplement")
DOC_RE = re.compile(r"\.(pdf|ashx|pptx?)(\?|$)|PDF", re.I)
CTX_RE = re.compile(r"決算|説明会|四半期|中間|通期|年度|月期|FY|Q[1-4]|results|earnings|briefing|presentation", re.I)
EXCLUDE_RE = re.compile(r"よくある|株主総会|招集|統合報告|有価証券報告|コーポレート・ガバナンス|個人投資家|ESG|サステナ|English|英語版", re.I)
DOC_PAGE_RE = re.compile(r"決算説明会|説明会資料|決算短信|決算資料|IRライブラリ|IR資料|プレゼンテーション|質疑応答|決算情報|業績|library|presentation|results|meetings|briefing|financial", re.I)
VOLATILE_Q = re.compile(r"^(cvid|intcid\d*|utm_\w+|_)$", re.I)


def params():
    p = dict(PARAMS)
    p.update((common.load_yaml("config/jp_ir.yaml") or {}).get("docs_params") or {})
    return p


def norm_url(url):
    """자료 정체성 — 갱신 때마다 바뀌는 쿼리(무라타 cvid·intcid5 등)를 뺀다"""
    u = urllib.parse.urlparse(url)
    q = [(k, v) for k, v in urllib.parse.parse_qsl(u.query, keep_blank_values=True) if not VOLATILE_Q.match(k)]
    return urllib.parse.urlunparse(u._replace(query=urllib.parse.urlencode(q), fragment=""))


def _z(s):
    return unicodedata.normalize("NFKC", s or "")


def kind_of(title, url):
    """앵커+주소 → kind 또는 None. 영상은 'video'(기록만)"""
    hay = _z(f"{title} {urllib.parse.unquote(url)}")
    if EXCLUDE_RE.search(title or "") or jp_ir_qa.QA_EXCLUDE_RE.search(hay):
        return None
    if VIDEO_RE.search(hay):
        return "video" if CTX_RE.search(hay) else None
    for k, rx in KINDS:
        if rx.search(hay):
            return k
    return None


def doc_date(title, url):
    """앵커의 '2026年10月30日'·주소의 '/2026/1030/'·'cvid=20261030…' → date 또는 None(앵커 먼저)"""
    for hay in (_z(title), urllib.parse.unquote(url)):
        for rx in (r"(20\d\d)年\s*(\d{1,2})月\s*(\d{1,2})日", r"(20\d\d)[/.\-](\d{1,2})[/.\-](\d{1,2})(?!\d)",
                   r"/(20\d\d)/(\d\d)(\d\d)(?!\d)", r"(?<!\d)(20\d\d)(\d\d)(\d\d)(?!\d)"):
            for m in re.finditer(rx, hay):
                try:
                    return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                except ValueError:
                    continue
    return None


def period_of(title, url):
    """결산 기간 → 'FY2026Q2'(일본 '年度' 기준 — 2027年3月期 = 2026年度). 못 읽으면 None"""
    for hay in (_z(title), urllib.parse.unquote(url)):
        m = re.search(r"(20\d\d)年\s*(\d{1,2})月期\s*(?:第\s*([1-4])\s*四半期|(中間|上期|上半期)|(決算|通期|期末))", hay)
        if m:
            y = int(m.group(1)) - (1 if int(m.group(2)) <= 6 else 0)
            return f"FY{y}Q{m.group(3) or ('2' if m.group(4) else '4')}"
        m = re.search(r"(20\d\d)年度\s*(?:第\s*([1-4])\s*四半期|(中間|上期|上半期)|(決算|通期|期末))?", hay)
        if m:
            return f"FY{m.group(1)}Q{m.group(2) or ('2' if m.group(3) else '4')}"
        m = re.search(r"FY\s?(20\d\d|\d\d)\s?Q([1-4])|(?<![0-9])(20\d\d)\s?Q([1-4])|(?<![0-9])(\d\d)q([1-4])(?![0-9])", hay, re.I)
        if m:
            y, q = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4)) if m.group(3) else (m.group(5), m.group(6))
            return f"FY{y if len(y) == 4 else '20' + y}Q{q}"
        m = re.search(r"FY\s?(20\d\d|\d\d)(?!\d)", hay, re.I)
        if m:
            y = m.group(1)
            return f"FY{y if len(y) == 4 else '20' + y}Q4"
    return None


def scan_docs(html_text, base):
    """자료실 페이지 → [{url, key, title, kind, date, period}] (페이지 순서 그대로, 같은 key는 처음 것만)"""
    out, seen = [], set()
    for href, inner in jp_ir_qa.LINK_RE.findall(html_text or ""):
        url = urllib.parse.urljoin(base, htmllib.unescape(href.strip())).split("#")[0]
        url = urllib.parse.quote(url, safe=":/?&=%~+,;@!$'()*")   # 무라타 '1030ｂ'처럼 전각 글자가 든 주소 — 그대로면 요청이 깨진다
        if urllib.parse.urlparse(url).scheme not in ("http", "https") or jp_ir_qa.ENGLISH_PATH_RE.search(urllib.parse.urlparse(url).path):
            continue
        title = re.sub(r"\s+", " ", htmllib.unescape(common.strip_tags(inner))).strip()
        k = kind_of(title, url)
        if not k:
            continue
        if k != "video" and not DOC_RE.search(f"{url} {title}") and not (k in QA_KINDS and not re.search(r"/(index\.html?)?$", url)):
            continue   # 자료 자체(PDF·.ashx)만 — 목록 페이지로 가는 메뉴 링크는 자료가 아니다(이비덴 '最新の決算概要について知りたい' 오탐)
        key = norm_url(url)
        if key in seen or not CTX_RE.search(_z(f"{title} {urllib.parse.unquote(url)}")):
            continue
        seen.add(key)
        dt = doc_date(title, url)
        out.append({"url": url, "key": key, "title": title, "kind": k, "date": dt.isoformat() if dt else "", "period": period_of(title, url)})
    return out


def is_fresh(doc, latest_period, today, fresh_days):
    """알릴 만한 새 자료인가 — 날짜가 있으면 fresh_days일 안, 없으면 그 페이지의 최신 기간"""
    if doc["date"]:
        return (today - date.fromisoformat(doc["date"])).days <= fresh_days
    return bool(doc["period"]) and doc["period"] == latest_period


def discover_doc_pages(c, ir_pages, budget=8):
    """IR 페이지 → 자료 링크(PT·短信·Q&A·전문)가 실제로 걸린 자료실 페이지 상위 3곳"""
    queue = list(c.get("ir_pages") or []) + [p for p in ir_pages if p not in (c.get("ir_pages") or [])]
    queue = queue or [urllib.parse.urljoin(c["site"], s) for s in (common.load_yaml("config/jp_ir.yaml") or {}).get("seeds") or []]
    depth, seen, scored, n = {u: 0 for u in queue}, set(), {}, 0
    today = common.now_kst().date()
    while queue and n < budget:
        url = queue.pop(0)
        if norm_url(url) in seen:
            continue
        seen.add(norm_url(url))
        try:
            h = jp_ir_qa._text(jp_ir_qa.fetch(url))
            n += 1
        except Exception:
            continue
        # 최근 자료(400일 안, 날짜 없으면 작년 이후 기간)가 많은 목록 페이지 — 과거 보관함·분기 전용 행사 페이지는 깎는다
        recent = [d for d in scan_docs(h, url) if d["kind"] != "video" and (
            (today - date.fromisoformat(d["date"])).days <= 400 if d["date"] else (d["period"] or "FY0")[2:6] >= str(today.year - 1))]
        if recent:
            sc = sum(1 + 3 * (d["kind"] in ("presentation", "transcript", "qa")) for d in recent)
            sc *= 0.3 if re.search(r"archive|backnumber|/past|kako", url, re.I) else 0.5 if re.search(r"/20\d\d/", url) else 1
            scored[url] = sc
        if depth[url] < 2:
            for u, t in jp_ir_qa.links(h, url):
                if u not in depth and not DOC_RE.search(u) and DOC_PAGE_RE.search(f"{t} {u}") and not EXCLUDE_RE.search(t):
                    depth[u] = depth[url] + 1
                    queue.insert(0, u) if re.search(r"決算説明会|説明会資料|質疑応答|presentation|meetings", f"{t} {u}", re.I) else queue.append(u)
    keys = {}
    for u in sorted(scored, key=lambda x: -scored[x]):
        keys.setdefault(norm_url(u).rstrip("/").replace("/index.html", ""), u)
    return list(keys.values())[:3]


def hot_ids(st, now, hot_days):
    """실적 구간 회사 — 적시공시 미러의 決算·説明会·業績 제목, 최근 새 자료, Q&A 대기"""
    hot = set()
    for i in range(hot_days):
        folder = common.ROOT / "radar" / "inbox" / (now - timedelta(days=i)).strftime("%Y%m%d")
        for f in folder.glob("src-jp-disclosure_*.json") if folder.exists() else []:
            try:
                it = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if re.search(r"決算|説明会|業績予想", it.get("title", "")):
                hot.update(it.get("entities_matched") or [])
    cutoff = common.iso(now - timedelta(days=hot_days))
    for cid, cs in st["companies"].items():
        if (cs.get("last_new") or "") >= cutoff or cs.get("expect"):
            hot.add(cid)
    return hot


def save_text(cid, d, text):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{cid}_{d['kind']}_{d['period'] or 'na'}_{hashlib.sha1(d['key'].encode()).hexdigest()[:8]}.txt"
    path.write_text(f"出典: {d['url']}\n資料: {d['title']}\n取得: {common.iso(common.now_kst())}\n\n{text}", encoding="utf-8")
    return str(path.relative_to(common.ROOT))


def _prev_same_kind(d, docs):
    """같은 종류의 직전 기간 자료(비교용) — 기간이 있으면 기간 순, 없으면 페이지에서 그다음 것"""
    same = [x for x in docs if x["kind"] == d["kind"] and x["key"] != d["key"]]
    if d["period"]:
        older = sorted((x for x in same if x["period"] and x["period"] < d["period"]), key=lambda x: x["period"], reverse=True)
        if older:
            return older[0]
    after = docs[docs.index(d) + 1:] if d in docs else []
    return next((x for x in after if x["kind"] == d["kind"]), None)


def _label(cid, names):
    nm = names.get(cid, {})
    return (nm.get("ja") or [nm.get("en", cid)])[0], nm.get("code", ""), nm.get("en", cid)


def poll(env=None, only=None, force=False):
    p = params()
    cfg = common.load_yaml("config/jp_ir.yaml") or {}
    names = {c["id"]: c for c in (common.load_yaml("config/jp_watch.yaml") or {}).get("companies") or []}
    qa_st = common.load_state("jp_ir_qa", {"companies": {}})
    st = common.load_state(STATE, {"companies": {}})
    now, today = common.now_kst(), common.now_kst().date()
    hot = hot_ids(st, now, p["hot_days"])
    holidays = cfg.get("holidays") or []
    items, errors, fetches, discovered = [], [], 0, 0
    order = []
    for cid, c in (cfg.get("companies") or {}).items():
        if only and cid not in only:
            continue
        cs = st["companies"].setdefault(cid, {"pages": {}, "seen": []})
        every = 0 if (cid in hot or force or only) else p["cold_min"]
        last = cs.get("checked_at") or ""
        if last and datetime.fromisoformat(last) > now - timedelta(minutes=every) and every:
            continue
        order.append((cid in hot, last, cid, c, cs))
    order.sort(key=lambda x: (not x[0], x[1]))   # 실적 구간 먼저, 그다음 오래 안 본 순
    for is_hot, _, cid, c, cs in order:
        if fetches >= p["max_fetch"] and not only:
            break
        try:
            pages = c.get("doc_pages") or cs.get("doc_pages")
            stale = not cs.get("doc_pages_at") or datetime.fromisoformat(cs["doc_pages_at"]) < now - timedelta(days=jp_ir_qa.REDISCOVER_DAYS)
            if not c.get("doc_pages") and (not pages or stale):
                if discovered >= p["discover_per_run"] and not only:
                    continue
                pages = discover_doc_pages(c, (qa_st["companies"].get(cid) or {}).get("pages") or [])
                cs["doc_pages"], cs["doc_pages_at"] = pages, common.iso(now)
                discovered += 1
                fetches += 8
            label, code, en = _label(cid, names)
            qa_seen = {norm_url(u) for u in (qa_st["companies"].get(cid) or {}).get("seen") or []}
            all_docs = []
            for pg in pages or []:
                try:
                    docs = scan_docs(jp_ir_qa._text(jp_ir_qa.fetch(pg)), pg)
                    fetches += 1
                except Exception:
                    continue
                all_docs += [d for d in docs if d["key"] not in {x["key"] for x in all_docs}]
                first_page = pg not in cs["pages"]
                cs["pages"][pg] = common.iso(now)
                periods = sorted({d["period"] for d in docs if d["period"]})
                latest = periods[-1] if periods else None
                for d in docs:
                    if d["key"] in cs["seen"]:
                        continue
                    cs["seen"].append(d["key"])
                    if d["kind"] == "video":
                        cs["video"] = d["url"]
                        continue
                    recent = d["date"] and (today - date.fromisoformat(d["date"])).days <= p["backlog_days"]
                    if (first_page and not recent) or (not first_page and not is_fresh(d, latest, today, p["fresh_days"])):
                        continue   # 기준선·과거 아카이브 — 알리지 않는다(2026-10-30 h28~h31 옛 Q&A 재수집 문제)
                    if d["kind"] in QA_KINDS and d["key"] in qa_seen:
                        continue   # jp_ir_qa가 이미 보낸 Q&A
                    items.append(_item(cid, d, docs, label, code, en))
                    cs["last_new"] = common.iso(now)
                    _expect(cs, d, docs, today, holidays, st, cid)
            _fallback(cs, cid, today, items, label, code, en, all_docs)
            cs["seen"] = cs["seen"][-500:]
            cs["checked_at"] = common.iso(now)
        except Exception as exc:   # 회사 하나가 실패해도 나머지는 본다
            errors.append(f"{cid}: {type(exc).__name__}")
    for it in items:   # Q&A는 jp_ir_qa 상태에도 기록 — 두 수집기가 같은 Q&A를 두 번 보내지 않게
        if it["source_id"] == jp_ir_qa.SRC:
            cs = qa_st["companies"].setdefault(it["entities_matched"][0], {"seen": [], "pages": [], "discovered_at": None})
            cs.setdefault("seen", []).append(it["url"])
            cs["latest_text"], cs["latest_url"] = it.get("local_text"), it["url"]
    common.save_state("jp_ir_qa", qa_st)
    common.save_state(STATE, st)
    if errors:
        print("일본 IR 자료실 일부 실패:", ", ".join(errors[:10]))
    return items


def _item(cid, d, docs, label, code, en):
    raw = jp_ir_qa.fetch(d["url"], 60)
    text = jp_ir_qa.to_text(d["url"], raw)
    extra = {"entities_matched": [cid], "publisher": en, "jp_code": code, "kind": d["kind"], "period": d["period"], "doc_date": d["date"],
             "local_text": save_text(cid, d, text), "chars": len(text)}
    if d["kind"] in QA_KINDS:   # 펄스 ⑥ IR 질의응답 — jp_ir_qa와 같은 항목 id(정규화 주소 해시)
        t = jp_ir_qa.tier_of(f"{d['title']} {d['url']}") or (1, "Q&A", "B")
        extra.update({"source_class": "IR 질의응답", "tier": t[1], "grade": "A" if d["kind"] == "transcript" else t[2], "lang": "ja"})
        return common.make_item(jp_ir_qa.SRC, hashlib.sha1(d["key"].encode()).hexdigest()[:16], d["url"],
                                f"{label}（{code}）IR 質疑応答: {d['title'][:80]}", common.iso(common.now_kst()), "IR 질의응답", "ja",
                                f"{KIND_KO[d['kind']]} · {d['period'] or '기간 미확인'} · 글자 {len(text)}", extra=extra)
    prev = _prev_same_kind(d, docs)
    if prev and d["kind"] in ("presentation", "tanshin"):   # 직전 기간 같은 자료 — ② 뉴팩트·B8 자료 비교 재료
        try:
            extra.update({"prev_url": prev["url"], "prev_period": prev["period"],
                          "prev_text": save_text(cid, prev, jp_ir_qa.to_text(prev["url"], jp_ir_qa.fetch(prev["url"], 60)))})
        except Exception:
            extra["prev_url"] = prev["url"]
    extra["source_class"] = "IR 자료"
    return common.make_item(SRC, hashlib.sha1(d["key"].encode()).hexdigest()[:16], d["url"],
                            f"{label}（{code}）{d['title'][:90]}", common.iso(common.now_kst()), "IR 자료", "ja",
                            f"{KIND_KO[d['kind']]} · {d['period'] or '기간 미확인'} · 글자 {len(text)}", extra=extra)


def _expect(cs, d, docs, today, holidays, st, cid):
    """PT가 나왔고 그 회사가 Q&A·전문을 내 왔으면 같은 기간 Q&A를 기다린다 / Q&A가 오면 게재 시차 기록"""
    ex = cs.get("expect")
    if d["kind"] in QA_KINDS:
        if ex and (not d["period"] or not ex.get("period") or d["period"] >= ex["period"]):
            prof = common.load_state("jp_ir_profile", {})
            prof.setdefault(cid, {})["lag_days"] = (today - date.fromisoformat(ex["found"])).days
            prof[cid]["lag_observed_at"] = today.isoformat()
            common.save_state("jp_ir_profile", prof)
            cs.pop("expect", None)
        return
    if d["kind"] != "presentation" or ex:
        return
    publishes_qa = any(x["kind"] in QA_KINDS for x in docs)
    has_now = any(x["kind"] in QA_KINDS and d["period"] and x["period"] == d["period"] for x in docs)
    if publishes_qa and not has_now:
        cs["expect"] = {"period": d["period"], "material": d["url"], "found": today.isoformat(),
                        "due": [jp_ir_qa.add_bdays(today, n, holidays).isoformat() for n in jp_ir_qa.RECHECK_BDAYS]}


def _fallback(cs, cid, today, items, label, code, en, docs):
    ex = cs.get("expect")
    if not ex:
        return
    if any(x["kind"] in QA_KINDS and ex.get("period") and x["period"] == ex["period"] for x in docs):
        cs.pop("expect", None)   # 다른 경로(jp_ir_qa)로 이미 올라옴
        return
    if today < date.fromisoformat(ex["due"][-1]):
        return
    cs.pop("expect", None)
    items.append(common.make_item(
        jp_ir_qa.SRC, hashlib.sha1(("fallback|" + ex["material"]).encode()).hexdigest()[:16], ex["material"],
        f"{label}（{code}）決算説明会 Q&A 미게재(+{jp_ir_qa.RECHECK_BDAYS[-1]}영업일) — 지시문 B 대상", common.iso(common.now_kst()), "IR 질의응답", "ja",
        "공식 IR에 Q&A 없음 — 로그미·제3자 전사·영상·보도·다른 IR 행사·주주와의 대화·자료 비교 순으로(knowledge/methods/jp_ir_qa_procedure.md B)",
        extra={"entities_matched": [cid], "publisher": en, "source_class": "IR 질의응답", "fallback": True, "material": ex["material"], "period": ex.get("period")}))


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    cfg = common.load_yaml("config/jp_ir.yaml") or {}
    ids = [a for a in argv if not a.startswith("--")]
    if "--discover" in argv:
        qa_st = common.load_state("jp_ir_qa", {"companies": {}})
        st = common.load_state(STATE, {"companies": {}})
        for cid in ids or list(cfg.get("companies") or {}):
            c = cfg["companies"][cid]
            pages = c.get("doc_pages") or discover_doc_pages(c, (qa_st["companies"].get(cid) or {}).get("pages") or [])
            cs = st["companies"].setdefault(cid, {"pages": {}, "seen": []})
            cs["doc_pages"], cs["doc_pages_at"] = pages, common.iso(common.now_kst())
            common.save_state(STATE, st)
            print(f"{cid}: 자료실 {len(pages)} {pages}")
        return 0
    its = poll(only=ids or None, force="--force" in argv)
    for it in its:
        print("-", it["source_id"], it.get("kind"), it.get("period"), it["title"][:90], it.get("prev_url", "")[:60])
    print(len(its), "건")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
