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
            r = subprocess.run([exe, "-enc", "UTF-8", "-layout", str(tmp), "-"], capture_output=True, timeout=60)
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
            first = not cs["seen"] and not cs.get("baselined")
            new = [(u, t) for u, t in qa.items() if u not in cs["seen"]]
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
                    SRC, hashlib.sha1(u.encode()).hexdigest()[:16], u, f"{label}（{nm.get('code', '')}）IR 質疑応答: {t[:80]}",
                    common.iso(now), "IR 질의응답", "ja", f"글자 {len(text)} · 로컬 {path.name}",
                    extra={"entities_matched": [cid], "local_text": str(path.relative_to(common.ROOT)), "chars": len(text),
                           "publisher": nm.get("en", cid), "source_class": "IR 질의응답"}))
                cs["seen"].append(u)
                cs["latest_text"], cs["latest_url"] = str(path.relative_to(common.ROOT)), u
            cs["seen"] = cs["seen"][-300:]
        except Exception as exc:   # 회사 하나가 실패해도 나머지는 본다
            errors.append(f"{cid}: {type(exc).__name__}")
    common.save_state("jp_ir_qa", st)
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
