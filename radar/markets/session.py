"""실적 지표 정리의 주가 줄 — 보고 시점이 장중·장전·장후 중 어디인가 (마스터 지시 2026-10-30 "장중이면 보고 시점에 주가 변화를 %로, 장중이 아니라면 장전·장후 주가 반응으로")

정규장 시각만 본다. 거래소 휴장일은 모른다(평일 휴장이면 그날 장이 없으니 주가 줄을 쓰기 전에 확인). 주말은 장후.
tzdata가 없어 zoneinfo를 쓰지 않고 시차·서머타임 규칙을 직접 계산한다.
사용: py radar/markets/session.py <회사 키 또는 거래소>   예) NASDAQ_UCTT · XKRX_009150 · XJPX
"""
import sys
from datetime import date, datetime, timedelta, timezone

UTC_H = {"US": -5, "KR": 9, "JP": 9, "TW": 8, "HK": 8, "EU": 1, "UK": 0}   # 표준시
HOURS = {"US": ("09:30", "16:00"), "KR": ("09:00", "15:30"), "JP": ("09:00", "15:30"), "TW": ("09:00", "13:30"),
         "HK": ("09:30", "16:00"), "EU": ("09:00", "17:30"), "UK": ("08:00", "16:30")}
MARKET = {"NASDAQ": "US", "NYSE": "US", "AMEX": "US", "XKRX": "KR", "XKOS": "KR", "XJPX": "JP", "TSE": "JP", "XTAI": "TW", "XHKG": "HK",
          "XETR": "EU", "XPAR": "EU", "XMIL": "EU", "XAMS": "EU", "XMAD": "EU", "XSTO": "EU", "XOSL": "EU", "XCSE": "EU", "XHEL": "EU", "XLON": "UK", "LSE": "UK"}


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
    head = str(ref).split("_")[0].upper()
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


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(*label(sys.argv[1]))
