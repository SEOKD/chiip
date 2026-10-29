"""수급 볼륨 지표 'Chiip Flow' — 누가(리테일·기관) 왜(사건) 거래했나 (마스터 지시 2026-10-29 "단순 볼륨 계산을 넘어서 볼륨 변화가 왜
생겼는지, 수급이 리테일과 기관 중에 어디서 발생하고 있는지 정량적으로 보여주는 볼륨 인디케이터를 하나 만들어라")

원자료
  ① 일봉 OHLCV — knowledge/models/companies/<id>/ohlcv.csv(date,o,h,l,c,v). 지금은 모델이 easyconomics company_price_history로 채운다
     (EODHD 키가 들어오면 결정론 수집으로 바꾼다 — TODO_MASTER).
  ② FINRA Reg SHO 일별(api.finra.org regShoDaily, 공개·인증 불필요) — 장외(TRF) 체결 거래량·그중 공매도 거래량. 결정론 조회, finra.json에 캐시.
  ③ FINRA OTC 주간(api.finra.org weeklySummary, 공개, 약 2주 지연) — ATS(다크풀)와 비ATS 장외 거래량을 체결 회사별로.

분해
  주간(확정치에 가깝다): 리테일 = 비ATS 장외 중 리테일 도매 체결사(아래 WHOLESALERS) · 기관 다크 = ATS 합계 · 기타 장외 = 비ATS 나머지
    (단일 딜러 플랫폼·블록) · 거래소(lit) = 전체 − 장외.
    근거: 미국 리테일 시장가 주문의 대부분은 도매 체결사가 장외에서 내부화한다 — Boehmer, Jones, Zhang & Zhang (2021, Journal of Finance)
    "Tracking Retail Investor Activity"의 리테일 식별도 이 장외 체결을 쓴다. 도매 체결사 비ATS 물량에도 일부 기관 주문이 섞이고, 리테일 지정가
    주문 일부는 거래소로 간다 → '리테일 근사치'로 표기한다.
  일별 추정: 리테일_t = 장외_t × (그 주 리테일 ÷ 장외; 그 주가 아직 없으면 최근 4주 평균) · 기관_t = 전체_t − 리테일_t.

방향
  리테일 매수 압력(정황) = 장외 공매도 비율의 60일 z 점수(5일 평균). 도매 체결사·마켓메이커는 리테일 매수 주문에 공매도로 물량을 대므로
    장외 공매도 비율이 평소보다 높으면 리테일 순매수 쪽으로 읽는 실무 관행(다크풀 지표 DIX 계열). 학술 검증이 제한적이라 단정하지 않는다.
  기관 매집·분산 = 기관 거래량으로 계산한 Chaikin Money Flow(20일) = Σ(CLV × 기관 거래량) ÷ Σ 기관 거래량,
    CLV = ((종가 − 저가) − (고가 − 종가)) ÷ (고가 − 저가). +면 종가가 고가 쪽(매집), −면 저가 쪽(분산). Chaikin의 널리 쓰는 지표를 기관 몫에만 적용.

왜(이상 거래일 원인)
  상대 거래량 RVOL = 거래량 ÷ 직전 50일 중앙값. RVOL ≥ 1.8 또는 z ≥ 2인 날에 사건 태그를 붙이고, 그날 늘어난 거래량(전체 − 50일 중앙값)을
  리테일·기관 몫으로 나눈다. 태그: 실적 발표일·다음 날, 셋째 금요일 월 만기(3·6·9·12월은 지수 정기 변경·쿼드러플 위칭), 월말,
  datapack events(8-K·의견 변경 등), 레이더 기사 수(radar/inbox 날짜 폴더에서 이 종목이 잡힌 항목).

사용: v2_to_report가 '수급 — 누가 왜 샀나' 절로 넣는다. 단독: py scripts/tenbagger/flow.py <entity_id> [--refresh]
지표일 뿐 매매 권유가 아니다.
"""
import csv
import json
import statistics
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FINRA = "https://api.finra.org/data/group/otcMarket/name/{name}"
UA = "chiip-radar/0.1 (personal research)"
# 리테일 도매 체결사(비ATS 장외, FINRA 주간 자료의 marketParticipantName — 2026-10 PWR 자료에서 확인)
WHOLESALERS = ("CITADEL SECURITIES", "VIRTU AMERICAS", "G1 EXECUTION", "JANE STREET CAPITAL", "HRT FINANCIAL", "TWO SIGMA SECURITIES")


def _cfg():
    """config/report_tools.yaml flow 절(등록부 prm-flow-*) — 없으면 사전값"""
    try:
        import yaml
        return (yaml.safe_load((ROOT / "config" / "report_tools.yaml").read_text(encoding="utf-8")) or {}).get("flow") or {}
    except (OSError, ImportError):
        return {}


CFG = _cfg()
RVOL_MIN, Z_MIN = float(CFG.get("rvol_min", 1.8)), float(CFG.get("z_min", 2.0))
CMF_N, PRESSURE_N, PRESSURE_SMOOTH = int(CFG.get("cmf_n", 20)), int(CFG.get("pressure_n", 60)), int(CFG.get("pressure_smooth", 5))


def company_dir(entity):
    return ROOT / "knowledge" / "models" / "companies" / entity


def load_ohlcv(entity):
    p = company_dir(entity) / "ohlcv.csv"
    if not p.exists():
        return []
    lines = [l for l in p.read_text(encoding="utf-8").splitlines() if l and not l.startswith("#")]
    out = []
    for r in csv.DictReader(lines):
        out.append({"date": r["date"], "o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]), "c": float(r["c"]), "v": float(r["v"])})
    return sorted(out, key=lambda b: b["date"])


# ---------- FINRA ----------
def _post(name, body, timeout=40):
    req = urllib.request.Request(FINRA.format(name=name), data=json.dumps(body).encode(), method="POST",
                                 headers={"User-Agent": UA, "Accept": "application/json", "Content-Type": "application/json"})
    for i in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                txt = r.read().decode("utf-8")
                return json.loads(txt) if txt.strip() else []
        except Exception:
            if i == 2:
                raise
            time.sleep(2 * (i + 1))


def fetch_daily(symbol, start, end):
    """{날짜: {"trf": 장외 거래량, "short": 그중 공매도}} — 시설(NCTRF·NQTRF·NYTRF)별 행을 날짜로 합친다"""
    out, offset = {}, 0
    while True:
        rows = _post("regShoDaily", {"limit": 5000, "offset": offset,
                                      "compareFilters": [{"compareType": "equal", "fieldName": "securitiesInformationProcessorSymbolIdentifier", "fieldValue": symbol}],
                                      "dateRangeFilters": [{"fieldName": "tradeReportDate", "startDate": start, "endDate": end}]})
        for r in rows:
            d = out.setdefault(r["tradeReportDate"], {"trf": 0.0, "short": 0.0})
            d["trf"] += float(r.get("totalParQuantity") or 0)
            d["short"] += float(r.get("shortParQuantity") or 0)
        if len(rows) < 5000:
            return out
        offset += 5000


def fetch_weekly(symbol, start, end):
    """{주 시작일: {"ats", "otc", "retail", "firms": {이름: 수량}}}"""
    out, offset = {}, 0
    while True:
        rows = _post("weeklySummary", {"limit": 5000, "offset": offset,
                                        "compareFilters": [{"compareType": "equal", "fieldName": "issueSymbolIdentifier", "fieldValue": symbol}],
                                        "dateRangeFilters": [{"fieldName": "weekStartDate", "startDate": start, "endDate": end}]})
        for r in rows:
            w = out.setdefault(r["weekStartDate"], {"ats": 0.0, "otc": 0.0, "retail": 0.0, "firms": {}})
            q, code = float(r.get("totalWeeklyShareQuantity") or 0), r.get("summaryTypeCode")
            if code == "ATS_W_SMBL":
                w["ats"] = q
            elif code == "OTC_W_SMBL":
                w["otc"] = q
            elif code == "OTC_W_SMBL_FIRM":
                name = (r.get("marketParticipantName") or "").upper()
                w["firms"][name] = q
                if any(k in name for k in WHOLESALERS):
                    w["retail"] += q
        if len(rows) < 5000:
            return out
        offset += 5000


def load_finra(entity, symbol, bars, refresh=False):
    """캐시(finra.json)가 오늘 것이면 그대로, 아니면 다시 받는다. 받지 못하면 캐시를 쓰고 그것도 없으면 빈 값"""
    p = company_dir(entity) / "finra.json"
    cache = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    today = date.today().isoformat()
    if cache.get("retrieved") == today and not refresh:
        return cache
    start = bars[0]["date"] if bars else (date.today() - timedelta(days=400)).isoformat()
    try:
        cache = {"retrieved": today, "symbol": symbol, "source": "FINRA api.finra.org regShoDaily·weeklySummary(공개)",
                 "daily": fetch_daily(symbol, start, today), "weekly": fetch_weekly(symbol, start, today)}
        p.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
    except Exception as exc:
        cache.setdefault("error", f"{type(exc).__name__}: {exc}"[:160])
    return cache


# ---------- 계산 ----------
def week_start(d):
    x = date.fromisoformat(d)
    return (x - timedelta(days=x.weekday())).isoformat()


def third_friday(y, m):
    d = date(y, m, 15)
    return d + timedelta(days=(4 - d.weekday()) % 7)


def clv(b):
    rng = b["h"] - b["l"]
    return ((b["c"] - b["l"]) - (b["h"] - b["c"])) / rng if rng > 0 else 0.0


def zscore(x, xs):
    if len(xs) < 10:
        return None
    sd = statistics.pstdev(xs)
    return (x - statistics.mean(xs)) / sd if sd > 0 else 0.0


def decompose(bars, daily, weekly):
    """날짜별 행: 전체·장외·리테일·기관·공매도 비율 — FINRA 일별이 있는 날만(장중 미확정 봉은 빠진다)"""
    ratios = {w: (v["retail"] / (v["ats"] + v["otc"])) for w, v in weekly.items() if (v["ats"] + v["otc"]) > 0}
    recent = [ratios[w] for w in sorted(ratios)[-4:]]
    fallback = sum(recent) / len(recent) if recent else None
    rows = []
    for b in bars:
        f = daily.get(b["date"])
        if not f or b["v"] <= 0:
            continue
        r_w = ratios.get(week_start(b["date"]), fallback)
        trf = min(f["trf"], b["v"])
        retail = trf * r_w if r_w is not None else None
        rows.append({**b, "trf": trf, "short": f["short"], "off_share": trf / b["v"], "sr": f["short"] / f["trf"] if f["trf"] else None,
                     "retail": retail, "inst": b["v"] - retail if retail is not None else None, "ratio_week": r_w,
                     "ratio_est": week_start(b["date"]) not in ratios})
    return rows


def cmf(rows, n=CMF_N):
    out = []
    for i in range(len(rows)):
        win = [r for r in rows[max(0, i - n + 1):i + 1] if r["inst"] is not None]
        den = sum(r["inst"] for r in win)
        out.append(sum(clv(r) * r["inst"] for r in win) / den if den and len(win) >= n // 2 else None)
    return out


def pressure(rows, n=PRESSURE_N, smooth=PRESSURE_SMOOTH):
    zs = []
    for i, r in enumerate(rows):
        hist = [x["sr"] for x in rows[max(0, i - n):i] if x["sr"] is not None]
        zs.append(zscore(r["sr"], hist) if r["sr"] is not None else None)
    out = []
    for i in range(len(zs)):
        win = [z for z in zs[max(0, i - smooth + 1):i + 1] if z is not None]
        out.append(sum(win) / len(win) if win else None)
    return out


def inbox_counts(entity, dates):
    out = {}
    for d in dates:
        folder = ROOT / "radar" / "inbox" / d.replace("-", "")
        n = 0
        if folder.exists():
            for f in folder.glob("*.json"):
                try:
                    it = json.loads(f.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                n += isinstance(it, dict) and entity in (it.get("entities_matched") or [])
        out[d] = n
    return out


def tags_for(d, prev_d, events, news):
    x = date.fromisoformat(d)
    tags = []
    for e in events:
        if e["date"] == d:
            tags.append(e["tag"])
        elif e.get("kind") == "earnings" and prev_d and e["date"] == prev_d:
            tags.append(f"{e['tag']} 다음 날")
    tf = third_friday(x.year, x.month)
    if x == tf:
        tags.append("분기 만기·지수 정기 변경" if x.month in (3, 6, 9, 12) else "월 옵션 만기")
    nxt = x + timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += timedelta(days=1)
    if nxt.month != x.month:
        tags.append("월말")
    if news.get(d):
        tags.append(f"레이더 기사 {news[d]}건")
    return tags or ["원인 미확인(공개 사건 없음)"]


def events_of(dp):
    ev = []
    call = (dp or {}).get("call") or {}
    for k in ("date", "prev_date"):
        if call.get(k):
            ev.append({"date": call[k], "tag": "실적 발표", "kind": "earnings"})
    for e in (dp or {}).get("events") or []:
        if e.get("date") and e.get("tag"):
            ev.append({"date": e["date"], "tag": e["tag"], "kind": e.get("kind", "event")})
    return ev


def resolve_symbol(entity, dp=None):
    """미국 티커 — datapack ticker → 감시 목록 code(PWR.US → PWR)"""
    s = (dp or {}).get("ticker") or ((dp or {}).get("profile") or {}).get("ticker")
    if s:
        return s
    import yaml
    for f in ("config/earnings_watch.yaml", "config/valuation.yaml"):
        d = yaml.safe_load((ROOT / f).read_text(encoding="utf-8")) or {}
        for u in (d.get("extra") or []) + (d.get("universe") or []):
            if u.get("id") == entity and str(u.get("code", "")).endswith(".US"):
                return str(u["code"])[:-3]
    return None


def analyze(entity, dp=None, symbol=None, refresh=False, finra=None):
    bars = load_ohlcv(entity)
    if len(bars) < 60:
        return None
    symbol = symbol or resolve_symbol(entity, dp)
    fin = finra if finra is not None else load_finra(entity, symbol, bars, refresh)
    rows = decompose(bars, fin.get("daily") or {}, fin.get("weekly") or {})
    if len(rows) < 40:
        return {"error": fin.get("error") or "FINRA 일별 자료 부족", "rows": rows}
    cm, pr = cmf(rows), pressure(rows)
    vols = [b["v"] for b in bars]
    idx = {b["date"]: i for i, b in enumerate(bars)}
    events = events_of(dp)
    news = inbox_counts(entity, [r["date"] for r in rows[-120:]])
    abn = []
    for k, r in enumerate(rows):
        i = idx[r["date"]]
        if i < 50 or k < len(rows) - 120:
            continue
        hist = vols[i - 50:i]
        med = statistics.median(hist)
        z = zscore(r["v"], hist)
        rv = r["v"] / med if med else None
        if rv is None or not (rv >= RVOL_MIN or (z or 0) >= Z_MIN):
            continue
        base_r = [x["retail"] for x in rows[max(0, k - 50):k] if x["retail"] is not None]
        d_all = r["v"] - med
        d_ret = (r["retail"] - statistics.median(base_r)) if (r["retail"] is not None and base_r) else None
        abn.append({"date": r["date"], "rvol": rv, "z": z, "delta": d_all, "d_retail": d_ret,
                    "d_inst": (d_all - d_ret) if d_ret is not None else None,
                    "chg": r["c"] / bars[i - 1]["c"] - 1, "clv": clv(r),
                    "tags": tags_for(r["date"], bars[i - 1]["date"], events, news)})
    last20, prev60 = rows[-20:], rows[-80:-20]
    share = lambda rs: (sum(x["retail"] for x in rs if x["retail"] is not None) / sum(x["v"] for x in rs if x["retail"] is not None)) if any(x["retail"] is not None for x in rs) else None
    weeks = sorted((fin.get("weekly") or {}).items())[-6:]
    wk_rows = []
    for w, v in weeks:
        tot = sum(b["v"] for b in bars if week_start(b["date"]) == w)
        if tot <= 0:
            continue
        off = v["ats"] + v["otc"]
        wk_rows.append({"week": w, "total": tot, "lit": max(tot - off, 0) / tot, "ats": v["ats"] / tot, "retail": v["retail"] / tot,
                        "other_otc": max(v["otc"] - v["retail"], 0) / tot})
    up_inst = [a for a in abn if a["d_inst"] is not None and a["delta"] > 0]
    inst_share_abn = (sum(max(a["d_inst"], 0) for a in up_inst) / sum(a["delta"] for a in up_inst)) if up_inst else None
    return {"symbol": symbol, "rows": rows, "cmf": cm, "pressure": pr, "abnormal": abn, "weeks": wk_rows,
            "retail_share_20": share(last20), "retail_share_prev60": share(prev60), "cmf_now": cm[-1], "pressure_now": pr[-1],
            "inst_share_abn": inst_share_abn, "latest_week": weeks[-1][0] if weeks else None, "finra_error": fin.get("error"),
            "last_date": rows[-1]["date"]}


# ---------- 리포트 절 ----------
def _p(x, d=1):
    return "-" if x is None else f"{x * 100:.{d}f}%"


def _k(x):
    if x is None:
        return "-"
    return f"{x / 1e6:.2f}M" if abs(x) >= 1e6 else f"{x / 1e3:.0f}K"


def report_section(entity, dp=None, refresh=False, finra=None, symbol=None):
    a = analyze(entity, dp, symbol=symbol, refresh=refresh, finra=finra)
    if not a or a.get("error"):
        return None
    rows, cm, pr = a["rows"], a["cmf"], a["pressure"]
    blocks = []
    rs_now, rs_prev = a["retail_share_20"], a["retail_share_prev60"]
    lean = ("기관 매집 쪽" if (a["cmf_now"] or 0) > 0.05 else "기관 분산 쪽" if (a["cmf_now"] or 0) < -0.05 else "기관 중립")
    rp = a["pressure_now"]
    rlean = "리테일 순매수 정황" if (rp or 0) >= 0.5 else "리테일 순매도 정황" if (rp or 0) <= -0.5 else "리테일 방향 뚜렷하지 않음"
    blocks.append({"type": "hl", "text": f"**한 줄:** 최근 20거래일 거래의 리테일 몫은 {_p(rs_now)}(직전 60일 {_p(rs_prev)}) — 거래는 주로 기관이 만든다. "
                                         f"기관 자금 흐름(CMF 20일) {cm[-1]:+.2f}로 {lean}, 리테일 매수 압력 z {rp:+.2f}로 {rlean}. "
                                         + (f"이상 거래일에 늘어난 거래량의 {_p(a['inst_share_abn'], 0)}가 기관 몫." if a["inst_share_abn"] is not None else "")})
    # 쌓인 막대 — 최근 60일
    tail = rows[-60:]
    blocks.append({"type": "chart", "chart": {"kind": "bars", "stack": True, "title": "일별 거래량 분해 — 리테일 근사(도매 체결사) vs 기관(거래소·다크풀) (천 주)", "unit": "K",
                                               "categories": [r["date"][5:] for r in tail],
                                               "series": [{"name": "기관", "color": "c", "values": [round(r["inst"] / 1e3) if r["inst"] is not None else None for r in tail]},
                                                          {"name": "리테일(근사)", "color": "b", "values": [round(r["retail"] / 1e3) if r["retail"] is not None else None for r in tail]}],
                                               "note": "리테일 = 장외(TRF) 거래량 × 그 주 FINRA 비ATS 리테일 도매 체결사 비중(최근 2주는 직전 4주 평균 — 추정). 기관 = 전체 − 리테일."}})
    pts_c = [[r["date"][5:], round(c, 3)] for r, c in zip(rows[-90:], cm[-90:]) if c is not None]
    pts_p = [[r["date"][5:], round(p / 4, 3)] for r, p in zip(rows[-90:], pr[-90:]) if p is not None]
    blocks.append({"type": "chart", "chart": {"kind": "line", "title": "기관 자금 흐름(CMF 20일)과 리테일 매수 압력(z ÷ 4로 같은 눈금)", "unit": "",
                                               "series": [{"name": "기관 CMF(20일)", "color": "c", "points": pts_c},
                                                          {"name": "리테일 매수 압력 z÷4(정황)", "color": "b", "points": pts_p}],
                                               "note": "CMF > 0: 기관 거래가 몰린 날 종가가 고가 쪽(매집). 리테일 압력: 장외 공매도 비율의 60일 z — 마켓메이커가 리테일 매수에 공매도로 물량을 대는 구조라 높을수록 리테일 순매수 쪽(정황)."}})
    if a["abnormal"]:
        trs = []
        for x in sorted(a["abnormal"], key=lambda x: -x["rvol"])[:8]:
            split = (f"기관 {x['d_inst'] / x['delta'] * 100:.0f}% · 리테일 {x['d_retail'] / x['delta'] * 100:.0f}%" if x["d_inst"] is not None and x["delta"] > 0 else "-")
            trs.append([x["date"], f"{x['rvol']:.1f}배", f"{x['chg'] * 100:+.1f}%", f"{x['clv']:+.2f}", _k(x["delta"]), split, " · ".join(x["tags"])])
        blocks.append({"type": "table", "title": "이상 거래일 — 왜 늘었나, 누가 늘렸나(최근 120거래일, RVOL ≥ 1.8 또는 z ≥ 2)",
                       "headers": ["날짜", "RVOL", "주가", "종가 위치", "늘어난 거래량", "증가분 분해", "원인 태그"], "rows": trs})
    if a["weeks"]:
        blocks.append({"type": "table", "title": f"주간 체결 장소별 비중 — FINRA 확정치(최신 주 {a['latest_week']}, 약 2주 지연)",
                       "headers": ["주 시작", "전체(주)", "거래소", "ATS(다크풀)", "리테일 도매", "기타 장외"],
                       "rows": [[w["week"], _k(w["total"]), _p(w["lit"]), _p(w["ats"]), _p(w["retail"]), _p(w["other_otc"])] for w in a["weeks"]]})
    blocks.append({"type": "p", "text": "**읽는 법:** 리테일 몫이 늘면서 주가가 오르면 리테일 주도 랠리(되돌림 위험 큼), 기관 CMF가 +로 돌며 거래량이 늘면 기관 매집 쪽이다. "
                                        "근거: 리테일 식별은 Boehmer·Jones·Zhang·Zhang(2021, JF)의 장외 도매 체결 방식, 자금 흐름은 Chaikin Money Flow. "
                                        "한계: 도매 체결사 물량에 일부 기관 주문이 섞이고, 리테일 지정가 주문 일부는 거래소로 간다 — 근사치다. 지표일 뿐 매매 권유가 아니다."})
    return {"h2": "수급 — 누가 왜 샀나(Chiip Flow)", "blocks": blocks, "_summary": {
        "retail_share_20": rs_now, "retail_share_prev60": rs_prev, "cmf": cm[-1], "pressure": rp, "inst_share_abn": a["inst_share_abn"],
        "abnormal": a["abnormal"][-5:], "last_date": a["last_date"]}}


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    entity = argv[0]
    dpp = company_dir(entity) / "datapack.json"
    dp = json.loads(dpp.read_text(encoding="utf-8")) if dpp.exists() else {}
    sec = report_section(entity, dp, refresh="--refresh" in argv)
    if not sec:
        print("[Chiip Flow] 재료 부족(ohlcv.csv 60일 이상·FINRA 자료)")
        return 1
    s = sec["_summary"]
    print(f"[Chiip Flow] {entity} {s['last_date']} · 리테일 20일 {_p(s['retail_share_20'])}(직전 {_p(s['retail_share_prev60'])}) · 기관 CMF {s['cmf']:+.2f} · 리테일 압력 z {s['pressure']:+.2f}")
    for x in s["abnormal"]:
        print(f"  {x['date']} RVOL {x['rvol']:.1f} {x['chg'] * 100:+.1f}% — {' · '.join(x['tags'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
