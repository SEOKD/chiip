"""중국 본토·홍콩 원문 공시 — 아시아 스크리너 후보·와치리스트 중국/홍콩 종목 (마스터 지시 2026-11-09 "Pulse·Ten-bagger·Analysis 종목 탐지망에 대만·중국 발굴 파이프라인 보완").

점검: 중국·홍콩 공시 원천이 하나도 없었다(대만은 src-tw-disclosure·월매출). 회사가 직접 낸 공시가 원문이다.
- 중국 본토(상하이·선전·베이징): 巨潮资讯网 cninfo 공시 조회(hisAnnouncement/query, 증권감독위원회 지정 공시 매체 — 공개 조회, robots.txt 없음)
- 홍콩: HKEXnews 제목 검색(titleSearchServlet, 공개 조회, robots.txt 없음)
대상: knowledge/models/discovery/asia_candidates.json의 china·hongkong 상위 + config/tradingview_symbols.csv의 SSE·SZSE·HKEX 종목.
전체 피드는 하루 수천 건이라 앞쪽만 보면 놓친다 → 종목별로 조회한다(내부 id는 radar/state/cn_hk_disclosure.json에 캐시).
중요 공시만(실적·업적 예고·수주·증설·자사주·지분 변동·설명회) — 정기 거래 보고(翌日披露报表 등)는 건너뛴다.
사용: py radar/pollers/cn_hk_disclosure.py              # 한 회차(run_poll이 poll()을 부른다)
      py radar/pollers/cn_hk_disclosure.py --about 688110  # 한 종목 최근 60일(Analysis 원천 수집 gather.py)
"""
import csv
import html
import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pollers import common  # noqa: E402

SRC = "src-cn-hk-disclosure"
CNINFO = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
CN_SEARCH = "http://www.cninfo.com.cn/new/information/topSearch/query"
HKEX = "https://www1.hkexnews.hk/search/titleSearchServlet.do"
HK_PREFIX = "https://www1.hkexnews.hk/search/prefix.do"
CST = timezone(timedelta(hours=8))
KST = timezone(timedelta(hours=9))
CN_KEEP = re.compile(r"业绩|预告|快报|年度报告|季度报告|半年度报告|合同|订单|中标|投资|扩产|产能|项目|募集|定增|回购|增持|减持|股权激励|收购|重组|调研|投资者关系|说明会")
CN_SKIP = re.compile(r"翌日披露|月报表|法律意见书|核查意见|保荐|独立董事|章程|议事规则|提示性公告$")
HK_KEEP = re.compile(r"results|quarterly report|interim report|annual report|profit warning|positive profit alert|inside information|contract|acquisition|disposal|"
                     r"placing|subscription|repurchase|capacity|investment|connected transaction|voluntary announcement|business update|operational update", re.I)
HK_SKIP = re.compile(r"published by the issuer in the Chinese section|poll results|next day disclosure|monthly return|exchange traded fund|form of proxy|"
                     r"notification letter|circular|exemption under rule", re.I)
LOOK_D = 3
PAUSE_S = 1.0   # 종목별 조회 사이 간격(공개 조회 예의)


def targets():
    """{'cn': {6자리 코드: 이름}, 'hk': {5자리 코드: 이름}}"""
    out = {"cn": {}, "hk": {}}
    try:
        a = json.loads((common.ROOT / "knowledge" / "models" / "discovery" / "asia_candidates.json").read_text(encoding="utf-8"))
        for m, k in (("china", "cn"), ("hongkong", "hk")):
            for r in (a.get("markets") or {}).get(m) or []:
                out[k][str(r["code"]).zfill(5 if k == "hk" else 6)] = r.get("name") or r["code"]
    except (OSError, ValueError):
        pass
    with (common.ROOT / "config" / "tradingview_symbols.csv").open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r["exchange"] in ("SSE", "SZSE"):
                out["cn"].setdefault(r["ticker"].zfill(6), r["name"])
            elif r["exchange"] == "HKEX":
                out["hk"].setdefault(r["ticker"].zfill(5), r["name"])
    return out


def _post(url, body, timeout=30):
    req = urllib.request.Request(url, data=body, headers={"User-Agent": common.UA, "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def cn_org(code, cache):
    if code not in cache:
        hit = json.loads(_post(CN_SEARCH, f"keyWord={code}&maxNum=3".encode()).decode("utf-8"))
        cache[code] = next((h["orgId"] for h in hit if h.get("code") == code), None)
    return cache[code]


def hk_sid(code, cache):
    if code not in cache:
        raw = common.http_get(HK_PREFIX, params={"callback": "cb", "lang": "EN", "type": "A", "name": code, "market": "SEHK"}, timeout=30).decode("utf-8")
        info = json.loads(raw[raw.index("(") + 1:raw.rindex(")")]).get("stockInfo") or []
        cache[code] = next((i["stockId"] for i in info if i.get("code") == code), None)
    return cache[code]


def cn_filings(code, org, days, now):
    """[(시각 CST, 제목, URL, 회사명, 공시 id)] — 중요 공시만"""
    col = "sse" if code[:1] in "68" else "szse"
    body = (f"pageNum=1&pageSize=50&column={col}&tabName=fulltext&searchkey=&stock={code},{org}&category=&"
            f"seDate={(now - timedelta(days=days)).date()}~{now.date()}&isHLtitle=true").encode()
    out = []
    for r in json.loads(_post(CNINFO, body).decode("utf-8")).get("announcements") or []:
        t = re.sub(r"<[^>]+>", "", r.get("announcementTitle") or "")
        if CN_KEEP.search(t) and not CN_SKIP.search(t):
            out.append((datetime.fromtimestamp((r.get("announcementTime") or 0) / 1000, CST), t, "http://static.cninfo.com.cn/" + (r.get("adjunctUrl") or ""),
                        r.get("secName") or code, r.get("announcementId")))
    return out


def hk_filings(sid, days, now):
    q = {"sortDir": "0", "sortByOptions": "DateTime", "category": "0", "market": "SEHK", "stockId": str(sid), "documentType": "-1",
         "fromDate": (now - timedelta(days=days)).strftime("%Y%m%d"), "toDate": now.strftime("%Y%m%d"), "title": "", "searchType": "0",
         "t1code": "-2", "t2Gcode": "-2", "t2code": "-2", "rowRange": "100", "lang": "E"}
    out = []
    for r in json.loads(json.loads(common.http_get(HKEX, params=q, timeout=40).decode("utf-8")).get("result") or "[]"):
        t = html.unescape(" ".join((r.get("TITLE") or "").split()))
        if HK_KEEP.search(f"{t} {r.get('LONG_TEXT', '')}") and not HK_SKIP.search(t):
            out.append((datetime.strptime(r["DATE_TIME"], "%d/%m/%Y %H:%M").replace(tzinfo=CST), t, "https://www1.hkexnews.hk" + (r.get("FILE_LINK") or ""),
                        r.get("STOCK_NAME") or "", r.get("NEWS_ID")))
    return out


def poll(env=None, now=None):
    now = now or datetime.now(CST)
    tg = targets()
    st = common.load_state("cn_hk_disclosure", {"cn_org": {}, "hk_sid": {}})
    items, errors, n = [], [], 0
    for code, name in tg["cn"].items():
        try:
            org = cn_org(code, st["cn_org"])
            if org:
                for t, title, url, sec, aid in cn_filings(code, org, LOOK_D, now):
                    items.append(common.make_item(SRC, f"cn-{aid}", url, f"[China filing] {sec}({code}) {title}", common.iso(t.astimezone(KST)), "공시", "zh",
                                                  f"cninfo · {name}", extra={"source_class": "공시", "cn_code": code, "exchange": "SSE" if code[:1] in "68" else "SZSE"}))
            n += 1
        except Exception as exc:
            errors.append(f"cn {code} {type(exc).__name__}")
        time.sleep(PAUSE_S)
    for code, name in tg["hk"].items():
        try:
            sid = hk_sid(code, st["hk_sid"])
            if sid:
                for t, title, url, sec, nid in hk_filings(sid, LOOK_D, now):
                    items.append(common.make_item(SRC, f"hk-{nid}", url, f"[HKEX filing] {sec or name}({code}) {title}", common.iso(t.astimezone(KST)), "공시", "en",
                                                  f"HKEXnews · {name}", extra={"source_class": "공시", "hk_code": code, "exchange": "HKEX"}))
            n += 1
        except Exception as exc:
            errors.append(f"hk {code} {type(exc).__name__}")
        time.sleep(PAUSE_S)
    common.save_state("cn_hk_disclosure", st)
    if errors and not n:
        raise RuntimeError("중국·홍콩 공시 전부 실패: " + ", ".join(errors[:5]))
    if errors:
        print("중국·홍콩 공시 일부 건너뜀:", ", ".join(errors[:5]))
    return items


def about(ticker, days=60):
    """한 종목의 최근 중요 공시 목록 — 6자리면 중국 본토, 그 밖은 홍콩"""
    now = datetime.now(CST)
    code = str(ticker).split(":")[-1].split(".")[0]
    st = common.load_state("cn_hk_disclosure", {"cn_org": {}, "hk_sid": {}})
    if len(code) == 6 and code.isdigit():
        org = cn_org(code, st["cn_org"])
        rows = cn_filings(code, org, days, now) if org else None
    else:
        code = code.zfill(5)
        sid = hk_sid(code, st["hk_sid"])
        rows = hk_filings(sid, days, now) if sid else None
    common.save_state("cn_hk_disclosure", st)
    if rows is None:
        return [f"종목 없음: {code}"]
    return [f"{t.date()} {title} {url}" for t, title, url, _, _ in rows] or ["최근 중요 공시 없음"]


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if "--about" in sys.argv:
        print("\n".join(about(sys.argv[sys.argv.index("--about") + 1])))
    else:
        print(f"{len(poll())}건")
