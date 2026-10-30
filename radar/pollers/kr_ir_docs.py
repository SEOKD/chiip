"""한국 IR 자료 상시 감시 — 실적 발표 뒤 나오는 경영실적 자료·컨퍼런스콜 스크립트를 받아 재분석으로 넘긴다 (2026-10-30 재점검 후 마스터 지시 '이 작업을 여기에서 진행')

왜 필요한가: radar/transcript_watch.py는 Fiscal.ai 전문을 기다리는데 한국 상장사는 전문이 없어 10일 뒤 만료된다. 삼성전자 2026-10-29 3Q처럼 콜 내용이 분석되지 않았다.
DART는 쓰지 않는다 — 키가 마스터 결정으로 비어 있고(2026-10-28), dart.fss.or.kr robots.txt가 뷰어·다운로드를 막는다. KIND는 메타데이터만 허용이다.

원천(수집은 결정론, 판단은 모델):
  ① IRGO 종목 페이지 m.irgo.co.kr/IR-COMP/<종목코드> — 상장사 IR 자료 게시판. 코드 하나로 전 종목을 같은 방식으로 본다(robots.txt 전체 허용, 2026-10-30 확인). 상세 페이지의 'PDF 원문보기'를 받는다.
  ② 회사 공식 자료실 — config/kr_ir.yaml doc_pages가 있는 회사(삼성전자·삼성SDI·LS일렉트릭 등)는 이쪽을 먼저 본다. 같은 기간·같은 종류는 공식 자료를 쓴다.
주기: 실적 구간(실적 일정상 발표 1일 전~10일 뒤, 또는 최근 새 자료)이면 매 회차(10분), 나머지는 180분마다. 한 회차 요청 45회 이하.
분류 kind_of: 스크립트(transcript)·질의응답(qa)·실적 자료(presentation)·요약 재무(supplement). 기간(FY2026Q3)·날짜를 제목과 파일 이름에서 읽는다.
새 자료: 내려받아 텍스트로 radar/inbox/kr_ir/(git 제외)에 두고, 실적 자료는 직전 기간 자료도 받는다(② 뉴팩트 비교용). 글자가 그림으로 든 PDF(글자 < thin_chars)는
  원본 PDF도 남기고 local_pdf로 알린다 — 두산에너빌리티 3Q는 14쪽에서 글자가 1,293자뿐이었다. 펄스 모델이 Read로 쪽 그림을 읽는다.
  실적 자료 → src-kr-ir-docs 'IR 자료'(펄스 ⑥-2), 스크립트·Q&A → src-kr-ir-qa 'IR 질의응답'(펄스 ⑥). 처음 보는 회사는 최근 backlog_days일 자료만 알린다.
robots.txt·1초 간격·로그인 영역 금지는 일본 수집기와 같다. 저장소에는 요약·15단어 이하 인용·링크만.
한국 상장사는 어닝콜·Q&A 스크립트를 공식 IR 사이트에 올리지 않는 게 보통이라(마스터 지시 2026-10-30) ①·②·③·인사이트의 기준 자료는 당기·직전 분기 PT다 — `--pt`가 두 파일을 찾아 준다.
사용: py radar/run_poll.py --only src-kr-ir-docs · 점검: py radar/pollers/kr_ir_docs.py [회사 id…] [--status] · 당기·직전 PT: py radar/pollers/kr_ir_docs.py --pt <회사 id 또는 종목코드>
"""
import hashlib
import html as htmllib
import json
import re
import sys
import time
import unicodedata
import urllib.parse
from datetime import date, datetime, timedelta
from pathlib import Path

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pollers import common, jp_ir_docs as jd, jp_ir_qa as qa  # noqa: E402

SRC = "src-kr-ir-docs"
SRC_QA = "src-kr-ir-qa"
CFG = "config/kr_ir.yaml"
CACHE = common.ROOT / "radar" / "inbox" / "kr_ir"
STATE = "kr_ir_docs"
PARAMS = {"hot_days": 10, "cold_min": 180, "max_fetch": 45, "fresh_days": 21, "backlog_days": 5, "thin_chars": 3000}
IRGO_LIST = "https://m.irgo.co.kr/IR-COMP/{code}"
PT_NAME_RE = re.compile(r"_presentation_(FY\d{4}Q\d)_")
IRGO_ITEM_RE = re.compile(r"""<li[^>]*data-href=["']([^"']+/IR자료/(\d+)/[A-Z]+/([^"']*))["'][^>]*>(.*?)</li>""", re.S)
IRGO_PDF_RE = re.compile(r"""href=["'](https://file\.irgo\.co\.kr/[^"']+?\.pdf)["']""", re.I)
PDF_URL_RE = re.compile(r"""(?:https?:)?//[^"'\s<>()\\]+?\.pdf(?:\?[^"'\s<>()\\]*)?""", re.I)
VIDEO_RE = re.compile(r"동영상|다시\s*보기|webcast|웨비나|audio|youtube\.com|youtu\.be|\.mp[34]\b", re.I)
EXCLUDE_RE = re.compile(r"감사보고서|사업보고서|분기보고서|반기보고서|주주총회|소집|지속가능|ESG|거버넌스|지배구조|정관|배당|CEO|Sustainab|Governance|Annual\s*Report|Audit|NDR|컨퍼런스\s*참[가석]|Conference\s*참[가석]", re.I)
KINDS = [
    ("transcript", re.compile(r"스크립트|녹취|script|transcript|컨퍼런스\s*콜\s*(?:주요\s*)?(?:내용\s*)?요약", re.I)),
    ("qa", re.compile(r"질의\s*응답|Q\s?&\s?A|QnA", re.I)),
    ("presentation", re.compile(r"경영\s*실적|실적\s*발표|컨퍼런스\s*콜|컨콜|conference|presentation|earnings|프리젠테이션|프레젠테이션|IR\s*자료|IR\s*Book|실적\s*자료|결산\s*실적|분기\s*실적|기업\s*설명회|경영\s*현황", re.I)),
    ("supplement", re.compile(r"fact\s*sheet|팩트\s*시트|fact\s*book|재무\s*자료|요약\s*재무|financial\s*(?:data|summary)", re.I)),
]
KIND_KO = {"transcript": "컨퍼런스콜 스크립트", "qa": "컨퍼런스콜 질의응답", "presentation": "실적 발표 자료", "supplement": "요약 재무 자료"}
QA_KINDS = ("transcript", "qa")


def params():
    p = dict(PARAMS)
    p.update((common.load_yaml(CFG) or {}).get("docs_params") or {})
    return p


def fetch(url, timeout=20):
    url = urllib.parse.quote(url, safe=":/?&=%~+,;@!$'()*#")   # IRGO 주소에는 한글이 들어 있다
    if not qa.allowed(url):
        raise PermissionError(f"robots.txt 차단: {url}")
    time.sleep(1.0)
    return common.http_get(url, timeout=timeout, headers={"User-Agent": qa.UA, "Accept-Language": "ko"})


def text_of(raw):
    if isinstance(raw, bytes):
        for enc in ("utf-8", "cp949"):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", "ignore")
    return raw


def _z(s):
    return unicodedata.normalize("NFKC", s or "")


def kind_of(title, url):
    """제목+파일 이름 → kind 또는 None. 영상은 'video'(기록만). 경로의 메뉴 낱말은 보지 않는다(/governance/ 오탐 방지)"""
    name = urllib.parse.unquote(urllib.parse.urlparse(url).path).rsplit("/", 1)[-1]
    hay = _z(f"{title} {name}")
    if EXCLUDE_RE.search(hay):
        return None
    if VIDEO_RE.search(hay):
        return "video"
    for k, rx in KINDS:
        if rx.search(hay):
            return k
    return None


def doc_date(title, url):
    """제목의 '2026.10.29'·'2026년 10월 29일', 주소·파일 이름의 '20261029' → date 또는 None(제목 먼저)"""
    for hay in (_z(title), urllib.parse.unquote(url)):
        for rx in (r"(20\d\d)\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일", r"(20\d\d)[/.\-](\d{1,2})[/.\-](\d{1,2})(?!\d)", r"(?<!\d)(20\d\d)(\d\d)(\d\d)(?!\d)"):
            for m in re.finditer(rx, hay):
                try:
                    return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                except ValueError:
                    continue
    return None


def period_of(title, url):
    """결산 기간 → 'FY2026Q3'(한국은 대부분 12월 결산, 달력 분기와 같다). 못 읽으면 None"""
    for hay in (_z(title), urllib.parse.unquote(url)):
        for rx, y, q in ((r"(20\d\d)\s*년(?:도)?\s*(?:제\s*)?([1-4])\s*(?:분기|Q)", 1, 2),
                         (r"(?<!\d)(20\d\d)[\s._\-]*Q([1-4])(?!\d)", 1, 2),
                         (r"(?<!\d)(20\d\d)[\s._\-]*([1-4])\s*Q(?![A-Za-z0-9])", 1, 2),
                         (r"(?<![A-Za-z0-9])Q([1-4])[\s._\-]*(20\d\d)(?!\d)", 2, 1),
                         (r"(?<![A-Za-z0-9])([1-4])\s*Q[\s._\-']*(20\d\d)(?!\d)", 2, 1),
                         (r"(?<![A-Za-z0-9])([1-4])\s*Q[\s._\-']*(\d\d)(?!\d)", 2, 1),
                         (r"(?<!\d)(\d\d)\s*년\s*([1-4])\s*(?:분기|Q)", 1, 2),
                         (r"(?<!\d)(\d\d)[.\-_]([1-4])\s*Q(?![A-Za-z0-9])", 1, 2)):
            m = re.search(rx, hay, re.I)
            if m:
                yr = m.group(y)
                return f"FY{yr if len(yr) == 4 else '20' + yr}Q{m.group(q)}"
        m = re.search(r"(20\d\d)\s*년(?:도)?\s*(?:연간|결산|경영\s*실적)", hay)
        if m:
            return f"FY{m.group(1)}Q4"
    return None


def bare_period(title, dt):
    """연도 없는 '3Q 실적발표' — 게시 날짜의 연도로. 1~3월에 나온 4Q는 전년 결산"""
    m = re.search(r"(?<![A-Za-z0-9])([1-4])\s*(?:Q|분기)(?![A-Za-z0-9])", _z(title))
    if not m or not dt:
        return None
    return f"FY{dt.year - (1 if m.group(1) == '4' and dt.month <= 3 else 0)}Q{m.group(1)}"


def _doc(url, key, title, name="", dt=None):
    k = kind_of(title, name or url)
    if not k:
        return None
    dt = dt or doc_date(title, name or url)
    return {"url": url, "key": key, "title": title, "kind": k, "date": dt.isoformat() if dt else "", "period": period_of(title, name or url) or bare_period(title, dt)}


def scan_page(html_text, base):
    """공식 자료실 페이지 → 자료 목록. 앵커가 있으면 앵커 글자로, 그 밖의 PDF 주소는 파일 이름으로 분류한다"""
    out, seen = [], set()

    def add(raw, title):
        url = urllib.parse.quote(urllib.parse.urljoin(base, htmllib.unescape(raw.strip())).split("#")[0], safe=":/?&=%~+,;@!$'()*")
        key = jd.norm_url(url)
        if urllib.parse.urlparse(url).scheme not in ("http", "https") or not re.search(r"\.pdf(\?|$)", url, re.I) or key in seen:
            return
        d = _doc(url, key, title)
        if d:
            seen.add(key)
            out.append(d)
    text = html_text or ""
    for href, inner in qa.LINK_RE.findall(text):
        add(href, re.sub(r"\s+", " ", htmllib.unescape(common.strip_tags(inner))).strip())
    for u in PDF_URL_RE.findall(text):
        add(u, "")
    return out


def _age_date(body, today):
    """'13시간전'·'2일전'·'2026.10.27' → date 또는 None"""
    m = re.search(r"(\d+)\s*(분|시간)전", body)
    if m:
        return today
    m = re.search(r"(\d+)\s*일전", body)
    if m:
        return today - timedelta(days=int(m.group(1)))
    m = re.search(r"(20\d\d)[.\-](\d\d)[.\-](\d\d)", body)
    return date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def scan_irgo(html_text, today=None):
    """IRGO 종목 페이지 → 자료 목록. 제목은 h3, 없으면 주소의 글자. 날짜는 주석 속 파일 이름 '[A034020]회사_20261029.pdf', 없으면 'n일전'"""
    today, out, seen = today or common.now_kst().date(), [], set()
    for url, num, slug, body in IRGO_ITEM_RE.findall(html_text or ""):
        if num in seen:
            continue
        seen.add(num)
        m = re.search(r"<h3[^>]*>(.*?)</h3>", body, re.S)
        title = re.sub(r"\s+", " ", htmllib.unescape(common.strip_tags(m.group(1)))).strip() if m else re.sub(r"[-\s]+", " ", urllib.parse.unquote(slug)).strip()
        name = re.search(r"\[A\d{6}\][^&<\s]*\.pdf", body)
        d = _doc(url, f"irgo:{num}", title, name.group(0) if name else "", None if name else _age_date(body, today))
        if d:
            out.append(d)
    return out


def content_of(d):
    """(주소, 본문 글자, 원본 바이트). IRGO는 상세 페이지의 'PDF 원문보기'를, PDF가 없으면 게시글 본문을 쓴다(ISC 콜 요약은 글로 올라온다)"""
    url, page = d["url"], fetch(d["url"], 60)
    if d["key"].startswith("irgo:"):
        m = IRGO_PDF_RE.search(text_of(page))
        if m:
            url, page = m.group(1), fetch(m.group(1), 60)
    return url, qa.to_text(url, page), page


def hot_ids(st, now, hot_days):
    """실적 구간 회사 — 실적 일정(어닝콜 대기 장부·다가오는 일정)의 발표 1일 전~hot_days일 뒤, 최근 새 자료"""
    today, hot = now.date(), set()

    def near(d):
        try:
            return -1 <= (today - date.fromisoformat(str(d)[:10])).days <= hot_days
        except ValueError:
            return False
    for r in (common.load_state("transcripts", {}).get("events") or {}).values():
        if r.get("id") and near(r.get("date")):
            hot.add(r["id"])
    up = common.ROOT / "knowledge" / "models" / "earnings" / "upcoming.json"
    if up.exists():
        hot.update(e["id"] for e in json.loads(up.read_text(encoding="utf-8")).get("events") or [] if e.get("id") and near(e.get("date")))
    cutoff = common.iso(now - timedelta(days=hot_days))
    hot.update(cid for cid, cs in st["companies"].items() if (cs.get("last_new") or "") >= cutoff)
    return hot


def save_text(cid, d, url, text):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{cid}_{d['kind']}_{d['period'] or 'na'}_{hashlib.sha1(d['key'].encode()).hexdigest()[:8]}.txt"
    path.write_text(f"출처: {url}\n자료: {d['title']}\n취득: {common.iso(common.now_kst())}\n\n{text}", encoding="utf-8")
    return str(path.relative_to(common.ROOT))


def save_pdf(cid, d, raw):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{cid}_{d['kind']}_{d['period'] or 'na'}_{hashlib.sha1(d['key'].encode()).hexdigest()[:8]}.pdf"
    path.write_bytes(raw)
    return str(path.relative_to(common.ROOT))


def _saved_pts(cid):
    """받아 둔 PT {기간: {period, text, pdf}} — 같은 기간이 여럿이면 나중에 받은 것"""
    out = {}
    for p in sorted(CACHE.glob(f"{cid}_presentation_*.txt"), key=lambda x: x.stat().st_mtime):
        m = PT_NAME_RE.search(p.name)
        if m:
            pdf = p.with_suffix(".pdf")
            out[m.group(1)] = {"period": m.group(1), "text": str(p.relative_to(common.ROOT)), "pdf": str(pdf.relative_to(common.ROOT)) if pdf.exists() else None}
    return out


def pt_pair(ref):
    """당기·직전 분기 PT(최신 먼저, 최대 2개). 어느 경로로 잡힌 한국 실적이든 ①·②·③을 쓰기 전에 부른다. 둘이 안 되면 자료실에서 받는다"""
    cos = (common.load_yaml(CFG) or {}).get("companies") or {}
    cid = ref if ref in cos else next((k for k, c in cos.items() if c.get("code") == ref), None)
    if not cid:
        raise ValueError(f"{CFG}에 없는 회사: {ref}")
    have = _saved_pts(cid)
    if len(have) < 2:
        docs, _ = company_docs(cos[cid])
        pts = sorted((d for d in docs if d["kind"] == "presentation" and d["period"]), key=lambda d: d["period"], reverse=True)
        for d in pts[:2]:
            if d["period"] not in have:
                url, text, raw = content_of(d)
                save_text(cid, d, url, text)
                if isinstance(raw, bytes) and raw[:5] == b"%PDF-" and len(text) < params()["thin_chars"]:
                    save_pdf(cid, d, raw)
        have = _saved_pts(cid)
    return [have[k] for k in sorted(have, reverse=True)[:2]]


def make_item(cid, c, d, docs):
    url, text, raw = content_of(d)
    name, code = c.get("name", cid), c.get("code", "")
    head = f"{name}({code}) {re.sub(r'^(?:.{0,20}?, |' + re.escape(name) + r' ?)+', '', d['title'])[:80] or KIND_KO[d['kind']]}"
    if d["title"] in ("", "Download PDF") or d["title"].lower().startswith("download"):
        head = f"{name}({code}) {d['period'] or ''} {KIND_KO[d['kind']]}".replace("  ", " ")
    extra = {"entities_matched": [cid], "publisher": name, "kr_code": code, "kind": d["kind"], "period": d["period"], "doc_date": d["date"], "page_url": d["url"],
             "local_text": save_text(cid, d, url, text), "chars": len(text), "lang": "ko"}
    if isinstance(raw, bytes) and raw[:5] == b"%PDF-" and len(text) < params()["thin_chars"]:   # 그림으로 된 PDF — 모델이 쪽 그림을 읽는다
        extra["local_pdf"] = save_pdf(cid, d, raw)
    snippet = f"{KIND_KO[d['kind']]} · {d['period'] or '기간 미확인'} · 글자 {len(text)}"
    uid = hashlib.sha1(d["key"].encode()).hexdigest()[:16]
    now = common.iso(common.now_kst())
    if d["kind"] in QA_KINDS:
        extra.update({"source_class": "IR 질의응답", "tier": KIND_KO[d["kind"]], "grade": "A"})
        return common.make_item(SRC_QA, uid, url, head, now, "IR 질의응답", "ko", snippet, extra=extra)
    prev = jd._prev_same_kind(d, docs)
    if prev and d["kind"] == "presentation":
        try:
            pu, pt, _ = content_of(prev)
            extra.update({"prev_url": pu, "prev_period": prev["period"], "prev_text": save_text(cid, prev, pu, pt)})
        except Exception:
            extra["prev_url"] = prev["url"]
    extra["source_class"] = "IR 자료"
    return common.make_item(SRC, uid, url, head, now, "IR 자료", "ko", snippet, extra=extra)


def company_docs(c):
    """공식 자료실 먼저, 그다음 IRGO. 같은 기간·같은 종류는 앞의 것만. (자료 목록, 요청 수)"""
    docs, n, have = [], 0, set()
    for pg in c.get("doc_pages") or []:
        try:
            for d in scan_page(text_of(fetch(pg)), pg):
                if d["kind"] == "video" or (d["period"], d["kind"]) in have:
                    continue
                have.add((d["period"], d["kind"]))
                docs.append(d)
            n += 1
        except Exception:
            continue
    for d in scan_irgo(text_of(fetch(IRGO_LIST.format(code=c["code"])))):
        if not d["period"] or (d["period"], d["kind"]) not in have:
            docs.append(d)
    return docs, n + 1


def poll(env=None, only=None, force=False):
    p = params()
    cfg = common.load_yaml(CFG) or {}
    st = common.load_state(STATE, {"companies": {}})
    now, today = common.now_kst(), common.now_kst().date()
    hot = hot_ids(st, now, p["hot_days"])
    items, errors, fetches, order = [], [], 0, []
    for cid, c in (cfg.get("companies") or {}).items():
        if only and cid not in only:
            continue
        cs = st["companies"].setdefault(cid, {"seen": []})
        every = 0 if (cid in hot or force or only) else p["cold_min"]
        last = cs.get("checked_at") or ""
        if every and last and datetime.fromisoformat(last) > now - timedelta(minutes=every):
            continue
        order.append((cid in hot, last, cid, c, cs))
    order.sort(key=lambda x: (not x[0], x[1]))   # 실적 구간 먼저, 그다음 오래 안 본 순
    for _, _, cid, c, cs in order:
        if fetches >= p["max_fetch"] and not only:
            break
        try:
            docs, n = company_docs(c)
            fetches += n
            first = "checked_at" not in cs
            periods = sorted({d["period"] for d in docs if d["period"]})
            latest = periods[-1] if periods else None
            for d in docs:
                if d["key"] in cs["seen"]:
                    continue
                recent = d["date"] and (today - date.fromisoformat(d["date"])).days <= p["backlog_days"]
                undated_latest = first and not d["date"] and cid in hot and d["period"] == latest
                if (first and not (recent or undated_latest)) or (not first and not jd.is_fresh(d, latest, today, p["fresh_days"])):
                    cs["seen"].append(d["key"])   # 기준선·과거 자료는 알리지 않는다
                    continue
                try:
                    items.append(make_item(cid, c, d, docs))
                except Exception as exc:   # 받기 실패는 seen에 넣지 않아 다음 회차가 다시 시도한다
                    errors.append(f"{cid} {d['key']}: {type(exc).__name__}")
                    continue
                cs["seen"].append(d["key"])
                cs["last_new"] = common.iso(now)
            cs["seen"] = cs["seen"][-500:]
            cs["checked_at"] = common.iso(now)
        except Exception as exc:   # 회사 하나가 실패해도 나머지는 본다
            errors.append(f"{cid}: {type(exc).__name__}")
    common.save_state(STATE, st)
    if errors:
        print("한국 IR 자료 일부 실패:", ", ".join(errors[:10]))
    return items


def status():
    """실적 구간 회사의 최근 자료 — 자료가 없으면 없다고 보여 준다"""
    cfg = common.load_yaml(CFG) or {}
    st = common.load_state(STATE, {"companies": {}})
    hot = hot_ids(st, common.now_kst(), params()["hot_days"])
    return [{"id": cid, "name": c.get("name"), "hot": cid in hot, "last_new": (st["companies"].get(cid) or {}).get("last_new"), "checked_at": (st["companies"].get(cid) or {}).get("checked_at")}
            for cid, c in (cfg.get("companies") or {}).items()]


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    ids = [a for a in argv if not a.startswith("--")]
    if "--pt" in argv:
        print(json.dumps(pt_pair(ids[0]), ensure_ascii=False, indent=1))
        return 0
    if "--status" in argv:
        for r in status():
            print(r)
        return 0
    its = poll(only=ids or None, force="--force" in argv)
    for it in its:
        print("-", it["source_id"], it.get("kind"), it.get("period"), it.get("doc_date"), it["title"][:80], it.get("chars"), (it.get("prev_url") or "")[-40:])
    print(len(its), "건")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
