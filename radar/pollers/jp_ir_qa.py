"""일본 IR 질의응답(Q&A) 수집기 (마스터 지시 2026-10-29 "easyconomics에는 일본 어닝콜이 없다. 일본 AI 밸류체인 종목은 공식 IR
페이지에서 Q&A 전문이 있으면 가져와 분석하는 프로세스를 설계하라. 영문판이 아니라 일본판으로 들어가야 나온다").

흐름(수집은 결정론, 판단은 모델):
  1) 탐색 — config/jp_ir.yaml의 일본어 IR 페이지(ir_pages, 없으면 site + seeds를 2단계까지 따라가며 'IR 자료·説明会' 페이지를 찾는다).
     찾은 페이지는 상태(radar/state/jp_ir_qa.json)에 7일 보관하고 다시 탐색한다.
  2) 감지 — 그 페이지들의 링크 중 질의응답 문서(質疑応答·主な質疑·Q&A·質疑要旨 + 決算·説明会 문맥, 일반 'よくあるご質問' 제외)를 찾는다.
  3) 새 문서만 내려받아 텍스트로 — PDF는 pdftotext(Git 설치본, 새 패키지 없음), HTML은 태그 제거. 원문 텍스트는
     radar/inbox/jp_qa/(git 제외)에만 둔다 — 저장소에는 요약·15단어 이하 인용·링크만(저작권).
  4) 항목(src-jp-ir-qa, doc_type 'IR 질의응답')으로 레이더에 넣는다 → 펄스 ⑥ IR 질의응답이 판단(docs/tasks/chiip-pulse.md).
매 요청 전 robots.txt 확인, 사이트당 요청 간격 1초, 로그인·유료 영역 접근 안 함. 첫 회차는 기준선(이미 있던 문서는 알림 없이 기록,
회사별 최신 1건은 텍스트를 받아 두어 데이터 묶음 call 재료로 쓴다).
사용: py radar/run_poll.py --only src-jp-ir-qa  ·  탐색 점검: py radar/pollers/jp_ir_qa.py --discover [회사 id]
"""
import hashlib
import html as htmllib
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.robotparser
from datetime import datetime, timedelta
from pathlib import Path

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pollers import common  # noqa: E402

SRC = "src-jp-ir-qa"
UA = "chiip-radar/0.1 (personal research)"
CACHE = common.ROOT / "radar" / "inbox" / "jp_qa"
LINK_RE = re.compile(r'<a\s[^>]*href=["\']([^"\'#]+)["\'][^>]*>(.*?)</a>', re.I | re.S)
QA_RE = re.compile(r"質疑応答|質疑要旨|主な質疑|主なご質問|質問と回答|Ｑ＆Ａ|Q\s?&\s?A|QA(?:\.pdf|_|-)|qa\d|_qa", re.I)
QA_CONTEXT_RE = re.compile(r"決算|説明会|カンファレンス|スモールミーティング|事業説明|IR\s?Day|Investor|Business Briefing|kessan|setsumeikai|presentation|briefing|earnings|financial", re.I)
QA_EXCLUDE_RE = re.compile(r"よくあるご質問|よくある質問|株主様からの|株式に関する|FAQ(?!.*決算)|お問い合わせ|個人投資家向け.*Q&A", re.I)
IR_PAGE_RE = re.compile(r"IR(資料|ライブラリ|ライブラリー|イベント|情報)|決算説明|説明会|決算短信|プレゼンテーション|投資家情報|株主・投資家|/ir/|investors", re.I)
ENGLISH_PATH_RE = re.compile(r"/(en|english|global)(/|$)|_e\.pdf$|-en\.pdf$|/eng/", re.I)
MAX_FETCH_DISCOVER = 10
# 마스터 지시문 A(2026-10-30) — 자료 우선순위와 출처 등급(A 회사 원문·스크립트 / B 회사 편집 요지 / C 제3자 전사 / D 자체 전사 / E 보도 재구성)
TRANSCRIPT_RE = re.compile(r"書き起こし|全文|スクリプト|transcript|presentation with script", re.I)
SUMMARY_RE = re.compile(r"要旨|概要|summary", re.I)
VIDEO_RE = re.compile(r"動画|音声|配信|オンデマンド|webcast|audio|youtube\.com|youtu\.be|\.mp4", re.I)
MATERIAL_RE = re.compile(r"説明会資料|プレゼンテーション資料|決算短信|決算補足|補足資料|presentation material|supplementary", re.I)
EXTERNAL_RE = re.compile(r"finance\.logmi\.jp|logmi\.jp|scriptsasia|youtube\.com|youtu\.be", re.I)
TIERS = {1: ("Q&A", "B"), 2: ("전문·스크립트", "A"), 3: ("요지", "B"), 4: ("영상·음성", "D")}
RECHECK_BDAYS = (3, 7)   # 게재 시차 — 설명회 자료가 나온 뒤 +3·+7영업일에 Q&A 재확인, 둘 다 없으면 지시문 B(대체 경로)로


def tier_of(hay):
    """링크 앵커+주소 → (등급 번호, 이름, 출처 등급) 또는 None. 1 Q&A > 2 전문 > 3 요지 > 4 영상"""
    if QA_EXCLUDE_RE.search(hay):
        return None
    if QA_RE.search(hay):
        t = TIERS[1]
        return 1, t[0], ("A" if TRANSCRIPT_RE.search(hay) else t[1])   # Q&A 전문이면 A, 회사가 고른 '主な質疑'면 B
    if TRANSCRIPT_RE.search(hay):
        return (2,) + TIERS[2]
    if SUMMARY_RE.search(hay) and QA_CONTEXT_RE.search(hay):
        return (3,) + TIERS[3]
    if VIDEO_RE.search(hay) and QA_CONTEXT_RE.search(hay):
        return (4,) + TIERS[4]
    return None


def add_bdays(d, n, holidays=None):
    """일본 영업일 n일 뒤 — 주말과 config/jp_ir.yaml holidays(도쿄증권거래소 휴장일) 제외"""
    hol = set(holidays if holidays is not None else (common.load_yaml("config/jp_ir.yaml") or {}).get("holidays") or [])
    while n > 0:
        d += timedelta(days=1)
        if d.weekday() < 5 and d.isoformat() not in hol:
            n -= 1
    return d


def scan_page(html_text, base):
    """한 IR 페이지(일본어·영문 모두) → {"docs": {url: (tier, 이름, 등급, 앵커, 언어)}, "materials": {url: 앵커}, "external": {url: 앵커}}"""
    page_ctx = bool(QA_CONTEXT_RE.search(common.strip_tags(html_text or "")[:20000]))
    out = {"docs": {}, "materials": {}, "external": {}}
    for href, inner in LINK_RE.findall(html_text or ""):
        url = urllib.parse.urljoin(base, htmllib.unescape(href.strip())).split("#")[0]
        if urllib.parse.urlparse(url).scheme not in ("http", "https"):
            continue
        title = re.sub(r"\s+", " ", htmllib.unescape(common.strip_tags(inner))).strip()
        hay = f"{title} {urllib.parse.unquote(url)}"
        if EXTERNAL_RE.search(url):
            out["external"][url] = title
            continue
        t = tier_of(hay)
        if t and (QA_CONTEXT_RE.search(hay) or page_ctx):
            out["docs"][url] = t + (title, "en" if ENGLISH_PATH_RE.search(url) else "ja")
        elif MATERIAL_RE.search(hay):
            out["materials"][url] = title
    return out


def profile_of(cid, scan, prev=None):
    """회사 IR 프로필(지시문 A 7) — IR 페이지·Q&A 형식(전문/요지/없음)·언어·외부 전사 채널·영상 유무. 게재 시차는 관측되면 누적"""
    docs = scan["docs"].values()
    best = min((d[0] for d in docs), default=None)
    fmt = {1: "전문" if any(d[0] == 1 and d[2] == "A" for d in docs) else "요지", 2: "전문(발표부)", 3: "요지", 4: "없음(영상만)"}.get(best, "없음")
    ext = sorted({"로그미" if "logmi" in u else "SCRIPTS Asia" if "scriptsasia" in u else "YouTube" for u in scan["external"]})
    p = dict(prev or {})
    p.update({"qa_format": fmt, "languages": sorted({d[4] for d in docs}) or ["ja"], "external": ext or ["없음"],
              "video": any(d[0] == 4 for d in docs) or "YouTube" in ext, "checked_at": common.iso(common.now_kst())})
    return p
REDISCOVER_DAYS = 7


def _robots(base, _cache={}):
    host = urllib.parse.urlparse(base).netloc
    if host not in _cache:
        rp = urllib.robotparser.RobotFileParser()
        try:
            raw = common.http_get(f"https://{host}/robots.txt", timeout=10)
            raw = raw.decode("utf-8", "ignore") if isinstance(raw, bytes) else raw
            rp.parse([] if "<html" in raw[:300].lower() else raw.splitlines())
        except Exception:
            rp.parse([])   # robots.txt가 없으면 제한 없음(표준 해석)
        _cache[host] = rp
    return _cache[host]


def allowed(url):
    rp = _robots(url)
    return rp.can_fetch(UA, url) and rp.can_fetch("ClaudeBot", url)


def fetch(url, timeout=20):
    if not allowed(url):
        raise PermissionError(f"robots.txt 차단: {url}")
    time.sleep(1.0)
    raw = common.http_get(url, timeout=timeout, headers={"User-Agent": UA, "Accept-Language": "ja"})
    return raw


def _text(raw):
    if isinstance(raw, bytes):
        for enc in ("utf-8", "shift_jis", "euc_jp", "cp932"):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", "ignore")
    return raw


def links(html_text, base):
    """같은 회사 도메인(하위 도메인 포함)의 링크 → [(url, 앵커 글자)]. 영문판 경로는 뺀다"""
    root = ".".join(urllib.parse.urlparse(base).netloc.split(".")[-2:])
    out = []
    for href, inner in LINK_RE.findall(html_text or ""):
        url = urllib.parse.urljoin(base, htmllib.unescape(href.strip()))
        u = urllib.parse.urlparse(url)
        if u.scheme not in ("http", "https") or not u.netloc.endswith(root) or ENGLISH_PATH_RE.search(u.path):
            continue
        title = re.sub(r"\s+", " ", htmllib.unescape(common.strip_tags(inner))).strip()
        out.append((url.split("#")[0], title))
    return out


def qa_links(html_text, base):
    """질의응답 문서 후보 — 앵커나 주소에 Q&A 표현 + (앵커·주소·페이지에) 결산·설명회 문맥, 일반 FAQ 제외"""
    page_ctx = bool(QA_CONTEXT_RE.search(common.strip_tags(html_text or "")[:20000]))
    found = {}
    for url, title in links(html_text, base):
        hay = f"{title} {urllib.parse.unquote(url)}"
        if not QA_RE.search(hay) or QA_EXCLUDE_RE.search(hay):
            continue
        if not (QA_CONTEXT_RE.search(hay) or page_ctx):
            continue
        found.setdefault(url, title or Path(urllib.parse.urlparse(url).path).name)
    return found


def discover(site, seeds, ir_pages=None):
    """일본어 IR 페이지 찾기 → (IR 페이지 목록, 그 안에서 찾은 Q&A 링크). 사이트당 요청 MAX_FETCH_DISCOVER회 이하"""
    queue = list(ir_pages or []) or [urllib.parse.urljoin(site, s) for s in seeds]
    seen, pages, qa, n = set(), [], {}, 0
    depth = {u: 0 for u in queue}
    while queue and n < MAX_FETCH_DISCOVER:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        try:
            raw = fetch(url)
            n += 1
        except Exception:
            continue
        html_text = _text(raw)
        found = qa_links(html_text, url)
        if found or IR_PAGE_RE.search(url) or IR_PAGE_RE.search(common.strip_tags(html_text)[:3000]):
            pages.append(url)
        qa.update(found)
        if depth[url] < 2:
            for u, t in links(html_text, url):
                if u not in depth and not re.search(r"\.(pdf|xlsx?|zip|mp4)$", u, re.I) and IR_PAGE_RE.search(f"{t} {u}"):
                    depth[u] = depth[url] + 1
                    queue.append(u)
    return pages[:8], qa


def to_text(url, raw):
    """PDF → pdftotext(UTF-8), HTML → 본문 글자. 실패하면 ''"""
    if url.lower().endswith(".pdf") or (isinstance(raw, bytes) and raw[:5] == b"%PDF-"):
        exe = shutil.which("pdftotext") or r"C:\Program Files\Git\ucrt64\bin\pdftotext.exe"
        if not Path(exe).exists():
            return ""
        CACHE.mkdir(parents=True, exist_ok=True)
        tmp = CACHE / "_tmp.pdf"
        tmp.write_bytes(raw)
        try:
            r = subprocess.run([exe, "-enc", "UTF-8", "-layout", str(tmp), "-"], capture_output=True, timeout=60,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))   # 창 없이(2026-10-30 CMD 창 문제)
            return r.stdout.decode("utf-8", "ignore")
        except Exception:
            return ""
        finally:
            tmp.unlink(missing_ok=True)
    return re.sub(r"\n\s*\n+", "\n", common.strip_tags(re.sub(r"(?is)<(script|style|nav|header|footer).*?</\1>", " ", _text(raw))))


def save_text(cid, url, text):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{cid}_{hashlib.sha1(url.encode()).hexdigest()[:10]}.txt"
    path.write_text(f"出典: {url}\n取得: {common.iso(common.now_kst())}\n\n{text}", encoding="utf-8")
    return path


def poll(env=None, only=None):
    cfg = common.load_yaml("config/jp_ir.yaml") or {}
    names = {c["id"]: c for c in (common.load_yaml("config/jp_watch.yaml") or {}).get("companies") or []}
    st = common.load_state("jp_ir_qa", {"companies": {}})
    now = common.now_kst()
    items, errors = [], []
    for cid, c in (cfg.get("companies") or {}).items():
        if only and cid not in only:
            continue
        cs = st["companies"].setdefault(cid, {"seen": [], "pages": [], "discovered_at": None})
        try:
            stale = not cs["pages"] or not cs["discovered_at"] or datetime.fromisoformat(cs["discovered_at"]) < now - timedelta(days=REDISCOVER_DAYS)
            if stale:
                pages, qa = discover(c["site"], cfg.get("seeds") or [], c.get("ir_pages"))
                cs["pages"], cs["discovered_at"] = pages, common.iso(now)
            else:
                qa = {}
                for pg in cs["pages"]:
                    try:
                        qa.update(qa_links(_text(fetch(pg)), pg))
                    except Exception:
                        continue
            # 지시문 A(2026-10-30): 우선순위별 자료·외부 전사·IR 프로필·게재 시차
            scan = {"docs": {}, "materials": {}, "external": {}}
            for pg in cs["pages"]:
                try:
                    sp = scan_page(_text(fetch(pg)), pg)
                except Exception:
                    continue
                for k in scan:
                    scan[k].update(sp[k])
            for u, ttl in list(scan["external"].items()):   # 로그미 書き起こし(robots 허용) — 질의응답이 있으면 C등급 Q&A
                if "logmi" in u and u not in cs["seen"] and allowed(u):
                    try:
                        if re.search(r"質疑応答|質問者", _text(fetch(u))):
                            scan["docs"][u] = (1, "Q&A(로그미)", "C", ttl, "ja")
                    except Exception:
                        pass
            for u, d in scan["docs"].items():
                if d[0] <= 3:
                    qa.setdefault(u, d[3])
            prof = st.setdefault("profiles", {})
            prof[cid] = profile_of(cid, scan, prof.get(cid))
            prof[cid]["ir_pages"] = cs["pages"][:4]
            meta = scan["docs"]
            first = not cs["seen"] and not cs.get("baselined")
            from pollers.jp_ir_docs import norm_url   # 갱신 쿼리(cvid 등)를 뺀 주소로 비교 — jp_ir_docs가 먼저 보낸 Q&A와 겹치지 않게
            seen_n = {norm_url(u) for u in cs["seen"]}
            new = [(u, t) for u, t in qa.items() if u not in cs["seen"] and norm_url(u) not in seen_n]
            mats_seen = cs.setdefault("materials_seen", [])
            new_mats = [u for u in scan["materials"] if u not in mats_seen]
            # Q&A 대기(+3·+7영업일)·지시문 B 항목은 jp_ir_docs.py가 맡는다(2026-10-30 — 여기 materials_seen은 자료실 목록 페이지라 기간을 알 수 없었다)
            cs.pop("pending", None)
            cs["materials_seen"] = (mats_seen + new_mats)[-200:]
            if first:   # 기준선: 알림 없이 기록하고, 최신으로 보이는 1건만 텍스트를 받아 둔다(데이터 묶음 call 재료)
                cs["seen"], cs["baselined"] = sorted(qa), True
                latest = sorted(qa.items(), key=lambda x: x[0])[-1:] if qa else []
                for u, t in latest:
                    try:
                        cs["latest_text"] = str(save_text(cid, u, to_text(u, fetch(u, 40))).relative_to(common.ROOT))
                        cs["latest_url"] = u
                    except Exception:
                        pass
                continue
            for u, t in new:
                text = to_text(u, fetch(u, 40))
                path = save_text(cid, u, text)
                nm = names.get(cid, {})
                label = (nm.get("ja") or [nm.get("en", cid)])[0]
                items.append(common.make_item(
                    SRC, hashlib.sha1(norm_url(u).encode()).hexdigest()[:16], u, f"{label}（{nm.get('code', '')}）IR 質疑応答: {t[:80]}",
                    common.iso(now), "IR 질의응답", "ja", f"글자 {len(text)} · 로컬 {path.name}",
                    extra={"entities_matched": [cid], "local_text": str(path.relative_to(common.ROOT)), "chars": len(text),
                           "publisher": nm.get("en", cid), "source_class": "IR 질의응답",
                           "tier": (meta.get(u) or (1, "Q&A", "B"))[1], "grade": (meta.get(u) or (1, "Q&A", "B"))[2],
                           "lang": (meta.get(u) or (0, 0, 0, 0, "ja"))[4]}))
                cs["seen"].append(u)
                cs["latest_text"], cs["latest_url"] = str(path.relative_to(common.ROOT)), u
            cs["seen"] = cs["seen"][-300:]
        except Exception as exc:   # 회사 하나가 실패해도 나머지는 본다
            errors.append(f"{cid}: {type(exc).__name__}")
    common.save_state("jp_ir_qa", st)
    common.save_state("jp_ir_profile", st.get("profiles") or {})   # 일본 IR 프로필 — 모델이 노션 '일본 IR 프로필'과 맞춘다(지시문 A 0·7)
    if errors:
        print("일본 IR Q&A 일부 실패:", ", ".join(errors[:10]))
    return items


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    cfg = common.load_yaml("config/jp_ir.yaml") or {}
    if argv and argv[0] == "--discover":
        ids = argv[1:] or list((cfg.get("companies") or {}))
        for cid in ids:
            c = cfg["companies"][cid]
            pages, qa = discover(c["site"], cfg.get("seeds") or [], c.get("ir_pages"))
            print(f"{cid}: IR 페이지 {len(pages)} · Q&A {len(qa)}" + (f" · 예 {list(qa.items())[0]}" if qa else "") + (f" · 페이지 {pages[:2]}" if pages else ""))
        return 0
    print(len(poll(only=argv or None)), "건")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
