"""원출처 판정 — 소식은 오리지널 소스만(마스터 지시 2026-11-24 "Pulse로 중복된 소식을 전달하지 마라. 소식은 오리지널 소스만 가져오도록 하라")

점검(11-23~24 발송): 같은 사건이 재인용 기사로 먼저, 원문으로 다시 나갔고(ABB 블룸버그 17:03 → IR 19:00, NVDA Megaspeed 보도 04:54 → 관보 06:34 '갱신'),
링크에 재인용·사본 사이트가 섞였다(Seeking Alpha 요약, stocktitan 보도자료 사본).
분류:
  primary  — 회사·정부·거래소가 직접 낸 원문(공시·관보·보도자료 배포망·회사 IR·뉴스룸)
  original — 자기 취재로 처음 보도한 언론(단독·관계자 보도). 원문이 없을 때만 쓴다
  relay    — 남의 기사·보도자료를 다시 쓰거나 옮긴 곳(요약·사본·집계 사이트, news.google.com 중계)
결정론 — 모델 없음.
"""
import re
from urllib.parse import urlparse

PRIMARY_HOSTS = ("sec.gov", "federalregister.gov", "regulations.gov", "congress.gov", "whitehouse.gov", "bis.gov", "commerce.gov",
                 "businesswire.com", "prnewswire.com", "globenewswire.com", "accessnewswire.com", "newsfilecorp.com", "einpresswire.com",
                 "dart.fss.or.kr", "kind.krx.co.kr", "kind.or.kr", "release.tdnet.info", "jpx.co.jp", "edinet-fsa.go.jp", "mops.twse.com.tw",
                 "twse.com.tw", "hkexnews.hk", "londonstockexchange.com", "cninfo.com.cn", "sse.com.cn", "szse.cn", "arxiv.org", "ieee.org")
PRIMARY_RE = re.compile(r"^(investors?|ir|newsroom|news|press|media|corporate|stories)\.", re.I)   # 회사 IR·뉴스룸 하위 도메인
PRIMARY_PATH = re.compile(r"/(investors?|investor-relations|ir|newsroom|press-releases?|news-releases?)/", re.I)
GOV_RE = re.compile(r"\.(gov|mil|go\.kr|go\.jp|gov\.tw|europa\.eu)$", re.I)
RELAY_HOSTS = ("news.google.com", "seekingalpha.com", "stocktitan.net", "benzinga.com", "marketbeat.com", "tipranks.com", "investing.com",
               "gurufocus.com", "fool.com", "simplywall.st", "insidermonkey.com", "zacks.com", "msn.com", "finance.yahoo.com", "yahoo.com",
               "ainvest.com", "tradingview.com", "nasdaq.com", "marketscreener.com", "finviz.com", "stockstory.org", "investorplace.com",
               "247wallst.com", "thefly.com", "streetinsider.com", "morningstar.com", "quiverquant.com", "techstock2.com", "barchart.com",
               "fintel.io", "marketwatch.com", "investopedia.com", "aastocks.com", "biztoc.com", "newsbreak.com", "stocktwits.com")
RELAY_PUBLISHERS = re.compile(r"seeking alpha|stocktitan|stock titan|benzinga|marketbeat|tipranks|investing\.com|gurufocus|motley fool|fool\.com|"
                              r"simply wall|insider monkey|zacks|msn|yahoo|ainvest|tradingview|nasdaq|marketscreener|finviz|stockstory|investorplace|"
                              r"24/7 wall|the fly|streetinsider|morningstar|barchart|fintel|marketwatch|investopedia|aastocks|biztoc|newsbreak|stocktwits", re.I)
SCOOP_RE = re.compile(r"exclusive|scoop|is said to|people familiar|sources say|according to (people|sources)|in talks|단독|関係者|独家", re.I)


def host(url):
    try:
        h = (urlparse(url or "").hostname or "").lower()
    except ValueError:
        return ""
    return h[4:] if h.startswith("www.") else h


def _in(h, hosts):
    return any(h == d or h.endswith("." + d) for d in hosts)


def kind(url, title="", publisher=""):
    """'primary' | 'original' | 'relay' | 'press'(일반 언론 — 단독 표시 없음)"""
    h = host(url)
    if h == "news.google.com":   # 중계 주소 — 매체 이름으로만 가른다
        if not publisher or RELAY_PUBLISHERS.search(publisher):
            return "relay"
        return "original" if SCOOP_RE.search(title or "") else "press"
    if h and (_in(h, PRIMARY_HOSTS) or GOV_RE.search(h) or PRIMARY_RE.match(h) or PRIMARY_PATH.search(urlparse(url).path or "")):
        return "primary"
    if (h and _in(h, RELAY_HOSTS)) or (publisher and RELAY_PUBLISHERS.search(publisher)):
        return "relay"
    if SCOOP_RE.search(title or ""):
        return "original"
    return "press"


def is_relay(url, title="", publisher=""):
    return kind(url, title, publisher) == "relay"


def publisher_of(title):
    """'제목 - 매체' 꼴의 끝 매체 이름"""
    t = title or ""
    return t.rsplit(" - ", 1)[1].strip() if " - " in t else ""
