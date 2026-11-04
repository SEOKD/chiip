"""EDGAR 최신 공시 목록 감시 (마스터 지시 2026-11-04 "시의성 있는 정보를 실시간급 속도로") — 2분마다

sec_filings는 종목마다 submissions JSON을 15분마다 본다(종목 수만큼 요청). 여기서는 EDGAR '최신 제출' Atom 한 장만 2분마다 보고,
감시 종목(sec_filings 상태의 ciks) 서류가 새로 뜨면 True를 돌려준다 → run_poll이 그 회차에 sec_filings를 바로 돌린다.
항목은 만들지 않는다(형식·중복 판정은 sec_filings가 그대로 한다). SEC 접속 규칙: 프로젝트 User-Agent(sec_filings._ua), 초당 10회 이하.
"""
import re

from . import common
from .sec_filings import _ua

URL = "https://www.sec.gov/cgi-bin/browse-edgar"
FORMS = ("8-K", "6-K", "10-Q", "10-K", "20-F", "S-1", "424B5", "SC 13D")
STATE = "edgar_current"
CIK_RE = re.compile(r"\((\d{6,10})\)")


def watched():
    return {str(c).lstrip("0") for c in (common.load_state("sec_filings", {}).get("ciks") or {}).values() if c}


def hits(atoms, ciks, seen):
    """새로 뜬 감시 종목 서류의 accession(링크) 목록"""
    out = []
    for xml in atoms:
        for entry in re.findall(r"<entry>(.*?)</entry>", xml, re.S):
            title = re.search(r"<title>(.*?)</title>", entry, re.S)
            link = re.search(r'<link[^>]*href="([^"]+)"', entry)
            m = CIK_RE.search(title[1] if title else "")
            if not (m and link) or m[1].lstrip("0") not in ciks or link[1] in seen:
                continue
            out.append(link[1])
    return out


def run():
    ciks = watched()
    if not ciks:
        return False
    st = common.load_state(STATE, {})
    seen = set(st.get("seen", []))
    atoms = []
    for form in ("8-K", "6-K"):   # 실적·계약·IR은 8-K·6-K로 먼저 나온다. 나머지는 sec_filings 15분 주기로 충분
        atoms.append(common.http_get(URL, {"action": "getcurrent", "type": form, "count": 100, "output": "atom"},
                                     {"User-Agent": _ua()}, timeout=20).decode("utf-8", "replace"))
    new = hits(atoms, ciks, seen)
    if new:
        st["seen"] = (list(seen) + new)[-500:]
        common.save_state(STATE, st)
    common.record_health("src-edgar-current", True)
    return bool(new)
