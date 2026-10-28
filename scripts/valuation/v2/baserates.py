"""M2-2 기저율(외부 관점) — 실제 기업들이 달성한 매출 CAGR 분포에서 가정의 백분위를 잰다

1단계 표본: SEC XBRL로 받은 미국 상장·ADR 종목(knowledge/models/fundamentals/us/) — 생존 종목·AI 수혜 대형주
위주라 고성장 쪽으로 치우친다(편향 표시 필수). EODHD 연결 후 전 상장사 10년+ 이력으로 교체(3단계).
문헌 사전값: 장기 성장의 지속성은 우연 수준(Chan·Karceski·Lakonishok 2003), 10년 연 20%+ 성장은 드묾(Mauboussin 2016).
"""
import bisect
from pathlib import Path

import reorg

BUCKETS = [(0, 1e9, "<10억$"), (1e9, 1e10, "10~100억$"), (1e10, 5e10, "100~500억$"), (5e10, float("inf"), ">500억$")]
BIAS_NOTE = "표본: SEC XBRL 미국 상장 AI 밸류체인 생존 종목 — 고성장 쪽 편향"


def windows(years=5):
    """[(출발 매출(달러), CAGR)] 겹치는 years년 구간 전부"""
    out = []
    for f in sorted(reorg.FUND.glob("*.csv")):
        rev = {y: v["revenue"] for y, v in reorg.annual(f.stem).items() if v.get("revenue")}
        for y in rev:
            if y + years in rev and rev[y] > 0 and rev[y + years] > 0:
                out.append((rev[y], (rev[y + years] / rev[y]) ** (1 / years) - 1))
    return out


def bucket_of(start_rev):
    for lo, hi, name in BUCKETS:
        if lo <= start_rev < hi:
            return lo, hi, name
    return BUCKETS[-1]


def percentile(cagr, start_rev, years=5, min_n=30, sample=None):
    """(백분위 0~100, 표본 수, 구간 이름, 비고). 같은 규모 구간 표본이 min_n 미만이면 전체 표본으로"""
    sample = sample if sample is not None else windows(years)
    lo, hi, name = bucket_of(start_rev)
    xs = sorted(c for r, c in sample if lo <= r < hi)
    note = BIAS_NOTE
    if len(xs) < min_n:
        xs = sorted(c for _, c in sample)
        name, note = "전체", BIAS_NOTE + f" · 규모 구간 표본 부족으로 전체 사용"
    if len(xs) < min_n:
        return None, len(xs), name, "표본 부족"
    pct = 100.0 * bisect.bisect_left(xs, cagr) / len(xs)
    return pct, len(xs), name, note
