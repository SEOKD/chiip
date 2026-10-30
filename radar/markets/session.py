"""실적 지표 정리의 주가 줄 — 보고 시점이 장중·장전·장후 중 어디인가 (마스터 지시 2026-10-30 "장중이면 보고 시점에 주가 변화를 %로, 장중이 아니라면 장전·장후 주가 반응으로")

정규장 시각만 본다. 거래소 휴장일은 모른다(평일 휴장이면 그날 장이 없으니 주가 줄을 쓰기 전에 확인). 주말은 장후.
tzdata가 없어 zoneinfo를 쓰지 않고 시차·서머타임 규칙을 직접 계산한다.
주가 줄 값(마스터 지시 2026-10-31 "실적 지표 정리할 때 주가 반응도 넣어" — 그때까지 ① 12건 모두 줄이 빠졌다. 규칙만 있고 값을 가져올 길이 없었다):
  TradingView mcp-tv-get-symbol-data(열 COLUMNS)의 값을 reaction()에 넘긴다. 장중 = 일간 등락, 장전 = 장전 등락, 장후 = 시간외 등락. 시간외 값이 없는 시장은
  발표가 그날 정규장 전·중이면 `종가 ±x%`, 장 마감 뒤 발표면 아직 반응이 없으므로 빈 값(줄을 뺀다). 지연 시세는 `(20분 지연)`을 붙인다.
사용: py radar/markets/session.py <회사 키·TradingView 종목·거래소>   예) NASDAQ_UCTT · XKRX_009150 · KRX:000660 · XJPX → 장·현지 시각·TradingView 종목
      py radar/markets/session.py <종목> --line <get-symbol-data의 data JSON 파일> [--after-close]  → 주가 줄
"""
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone

UTC_H = {"US": -5, "KR": 9, "JP": 9, "TW": 8, "HK": 8, "EU": 1, "UK": 0}   # 표준시
HOURS = {"US": ("09:30", "16:00"), "KR": ("09:00", "15:30"), "JP": ("09:00", "15:30"), "TW": ("09:00", "13:30"),
         "HK": ("09:30", "16:00"), "EU": ("09:00", "17:30"), "UK": ("08:00", "16:30")}
MARKET = {"NASDAQ": "US", "NYSE": "US", "AMEX": "US", "XKRX": "KR", "KRX": "KR", "XKOS": "KR", "XJPX": "JP", "TSE": "JP", "XTAI": "TW", "TWSE": "TW", "TPEX": "TW", "XHKG": "HK", "HKEX": "HK",
          "XETR": "EU", "XPAR": "EU", "XMIL": "EU", "XAMS": "EU", "XMAD": "EU", "XSTO": "EU", "XOSL": "EU", "XCSE": "EU", "XHEL": "EU", "EURONEXT": "EU", "MIL": "EU", "BME": "EU",
          "OSL": "EU", "OMXSTO": "EU", "OMXHEX": "EU", "VIE": "EU", "SIX": "EU", "XLON": "UK", "LSE": "UK"}
COLUMNS = ["close", "change", "premarket_change", "postmarket_change", "update_mode"]
FISCAL_TV = {"XKRX": "KRX", "XKOS": "KRX", "XJPX": "TSE", "XHKG": "HKEX", "XTAI": "TWSE", "XETR": "XETR", "XLON": "LSE", "XPAR": "EURONEXT", "XAMS": "EURONEXT", "XMIL": "MIL", "XMAD": "BME", "XSTO": "OMXSTO", "XOSL": "OSL", "XHEL": "OMXHEX"}


def _sunday(y, m, nth):
    """그달 n번째 일요일(nth = -1이면 마지막)"""
    if nth > 0:
        d = date(y, m, 1)
        return d + timedelta(days=(6 - d.weekday()) % 7 + 7 * (nth - 1))
    d = date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)
    return d - timedelta(days=(d.weekday() + 1) % 7)


def _dst(mkt, utc):
    """서머타임이면 1시간 — 미국 3월 둘째~11월 첫째 일요일, 유럽·영국 3월 마지막~10월 마지막 일요일(날짜 단위 근사)"""
    d = utc.date()
    if mkt == "US":
        return _sunday(d.year, 3, 2) <= d < _sunday(d.year, 11, 1)
    return mkt in ("EU", "UK") and _sunday(d.year, 3, -1) <= d < _sunday(d.year, 10, -1)


def market_of(ref):
    head = re.split(r"[_:]", str(ref))[0].upper()
    if head in UTC_H:
        return head
    if head not in MARKET:
        raise ValueError(f"거래소를 모른다: {ref}")
    return MARKET[head]


def label(ref, now=None):
    """(장중|장전|장후, 현지 시각). 실적 지표 정리 ①의 주가 줄 이름"""
    mkt = market_of(ref)
    utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    local = utc + timedelta(hours=UTC_H[mkt] + _dst(mkt, utc))
    hm = local.strftime("%H:%M")
    open_, close = HOURS[mkt]
    if local.weekday() >= 5 or hm >= close:
        name = "장후"
    else:
        name = "장전" if hm < open_ else "장중"
    return name, local.strftime("%Y-%m-%d %H:%M")


def tv_symbol(ref):
    """Fiscal.ai 회사 키 → TradingView 종목(NASDAQ_UCTT → NASDAQ:UCTT, XKRX_009150 → KRX:009150). 대만은 상장처가 둘이라 틀리면 search-symbols로 찾는다"""
    s = str(ref)
    if ":" in s or "_" not in s:
        return s
    ex, tk = s.split("_", 1)
    return f"{FISCAL_TV.get(ex.upper(), ex.upper())}:{tk}"


def delay_note(mode):
    m = re.search(r"delayed\w*?_(\d+)$", str(mode or ""))
    return f" ({int(m.group(1)) // 60}분 지연)" if m else ""


def reaction(ref, data, after_close=False, now=None):
    """주가 줄 — 값이 없으면 빈 문자열(줄을 뺀다). after_close = 발표가 그날 정규장 마감 뒤"""
    name, _ = label(ref, now)
    data = data or {}
    key = {"장중": "change", "장전": "premarket_change", "장후": "postmarket_change"}[name]
    v = data.get(key)
    if not v and name == "장후":     # 시간외 거래가 없는 시장은 0이나 빈 값으로 온다(LSE)
        v = None
        if not after_close:
            name, v = "종가", data.get("change")
    if v is None:
        return ""
    return f"{name} {v:+.1f}%" + (delay_note(data.get("update_mode")) if name in ("장중", "장전") else "")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    argv = sys.argv[1:]
    if "--line" in argv:
        i = argv.index("--line")
        print(reaction(argv[0], json.loads(open(argv[i + 1], encoding="utf-8").read()), "--after-close" in argv))
    else:
        print(*label(argv[0]), "·", tv_symbol(argv[0]), "· 열", ",".join(COLUMNS))
