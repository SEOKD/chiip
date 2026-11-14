"""소비재 KPI 나우캐스트 — 설계안 C단계(knowledge/methods/consumer_trends_design.md, 마스터 승인 2026-11-14)

질문: 공개 대체 데이터(위키 조회·나라별 수입)가 발표 전 분기 매출 성장률을 '지난 분기 성장률'보다 잘 맞히는가.
  목표 y   = ln(이번 분기 매출 ÷ 전년 같은 분기)                     (회사 회계 분기 그대로)
  기본     y = a + ρ·y₋₁                                             (지난 분기 YoY — 발표 전 시장이 아는 것)
  확장     y = a + ρ·y₋₁ + β·s                                       (파라미터 1개 추가, scripts/fit/stepwise.py 원칙)
  신호 s   위키 = ln(그 분기 기간 문서 조회 합 ÷ 전년 같은 기간)      — 일별 radar/state/wiki_views.sqlite(옛 제목 포함)
           수입 = ln(그 분기 앞 두 달 나라별 미국 수입 ÷ 전년 같은 달) — 마지막 달은 Census 공표(약 5주 뒤)가 발표보다 늦을 수 있어 뺀다
           |s|는 CLIP에서 자른다(출시·바이럴의 0→N 폭주가 회귀를 지배하지 않게)
검정: 여러 회사를 묶은 패널, 시간 순 walk-forward(검증 분기보다 앞선 분기로만 학습). 같은 관측끼리 짝지은 표본 외 제곱 오차를
      harness.nested_test(본페로니: 시도한 신호 수)로 비교. 통과한 신호만 채택. 회사별 적합(확장 손실 < 기본 손실 5% 이상·표본 외 4개 이상)은 따로 표시.
      채택되지 않으면 나우캐스트 숫자를 내지 않는다(관심 지표로만 남긴다).
출력: knowledge/models/consumer/nowcast.json — 검정 결과, 회사별 적합, 진행 중 분기 나우캐스트(채택 신호·적합 회사만)와 범위(표본 외 RMSE).
      매출 이력 knowledge/models/consumer/revenue_q.csv(Fiscal.ai 44개 분기 · 한국 TradingView 16개 분기 · 일본은 fundamentals.json 株探 표).
금지표: 관심 증가 → 매출, 수출입 급증 → 특정 기업 매출 — 이 스크립트는 그 연결을 '표본 외로 맞혔는가'로만 판정한다. 매수 권유 아님.
사용: py scripts/discovery/consumer_nowcast.py --put-fiscal <회사키→[[기말일, 매출, 발표일]] JSON>
      py scripts/discovery/consumer_nowcast.py --put-tv <id→{symbol, first_label, last_label, revenue:[[값, yoy_pct]]} JSON>   # 한국(TradingView, 라벨 검증)
      py scripts/discovery/consumer_nowcast.py --dart [종목 id…]   # 한국 OpenDART 2015~ 분기 매출(겹치는 분기 대조 후 교체)
      py scripts/discovery/consumer_nowcast.py            # 검정·나우캐스트
      py scripts/discovery/consumer_nowcast.py --consensus <회사키→{period, revenue} JSON>   # Fiscal.ai 다음 분기 매출 컨센서스 붙이기
"""
import csv
import json
import math
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "radar"))
sys.path.insert(0, str(ROOT / "scripts" / "fit"))
from pollers import common  # noqa: E402
import harness  # noqa: E402

OUT = ROOT / "knowledge" / "models" / "consumer"
REV = OUT / "revenue_q.csv"
FUND = OUT / "fundamentals.json"
TRADE = OUT / "trade_partner.csv"
WIKI_DB = ROOT / "radar" / "state" / "wiki_views.sqlite"
NOWCAST = OUT / "nowcast.json"
CLIP = 1.0            # prm-consumer-nowcast-clip — |ln 비율| 상한
MIN_TRAIN = 40        # 학습 관측 최소(패널 전체)
COVER = 0.9           # 분기 기간 중 위키 자료가 있어야 하는 날 비율(문서 생성 전·중간 결측 제외)
COMPANY_GAIN = 0.05
COMPANY_MIN_OOS = 4


def d(s):
    return date.fromisoformat(s[:10])


# ── 매출 이력 ─────────────────────────────────────────────

def cfg():
    return common.load_yaml("config/consumer.yaml") or {}


def put_fiscal(path):
    by_key = {co.get("fiscal"): co["id"] for co in cfg().get("companies") or [] if co.get("fiscal")}
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = load_rev()
    rows = [r for r in rows if r["id"] not in {by_key.get(k) for k in raw}]
    for k, qs in raw.items():
        cid = by_key.get(k)
        if not cid:
            continue
        for period, rev, ed in qs:
            if rev:
                rows.append({"id": cid, "period": period, "revenue": float(rev), "earnings_date": ed or "", "source": "Fiscal.ai company_financials_standardized"})
    save_rev(rows)
    return len(rows)


def _qend(label):
    """'Q3 2026' → date(2026, 9, 30)"""
    q, y = int(label[1]), int(label[-4:])
    return date(y, 3 * q, 30 if q in (2, 3) else 31)


def _qshift(dt, k):
    m = dt.month + 3 * k
    y, m = dt.year + (m - 1) // 12, (m - 1) % 12 + 1
    return date(y, m, 30 if m in (6, 9) else 31)


def tv_quarters(rec, tol=0.6):
    """TradingView mcp-tv-get-financial-history(fq) 매출 → [(기말일, 매출)]. 라벨은 믿지 않는다(2026-11-14 확인: 한국 종목 라벨이 중복·누락 —
    'Q3 2023' 두 번·'Q1 2023' 없음). 값은 오래된 순 연속 분기이므로 ① 첫 라벨부터 개수만큼 센 분기가 마지막 라벨과 같고
    ② 4개 뒤 값의 YoY가 함께 준 yoy_pct와 tol%p 안에서 맞을 때만 받는다. 맞지 않으면 ValueError"""
    vals = rec["revenue"]
    first = _qend(rec["first_label"])
    if _qshift(first, len(vals) - 1) != _qend(rec["last_label"]):
        raise ValueError(f"{rec.get('symbol')}: 분기 수 {len(vals)}가 라벨 범위 {rec['first_label']}~{rec['last_label']}와 다르다")
    for i in range(4, len(vals)):
        mine = (vals[i][0] / vals[i - 4][0] - 1) * 100
        if vals[i][1] is not None and abs(mine - vals[i][1]) > tol:
            raise ValueError(f"{rec.get('symbol')}: {i}번째 YoY {mine:.1f}% ≠ 제공 {vals[i][1]}% — 순서가 어긋났다")
    return [(_qshift(first, i).isoformat(), v) for i, (v, _) in enumerate(vals)]


def put_tv(path):
    """한국 등 Fiscal.ai·Easyconomics에 분기 재무가 없는 종목(DART 키 없음, TODO_MASTER 2026-11-06) — config/data_sources.yaml quarters 원천"""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = [r for r in load_rev() if r["id"] not in raw]
    for cid, rec in raw.items():
        for period, v in tv_quarters(rec):
            rows.append({"id": cid, "period": period, "revenue": float(v), "earnings_date": "",
                         "source": f"TradingView financial-history {rec.get('symbol', '')}(마지막 분기는 잠정실적일 수 있다)"})
    save_rev(rows)
    return len(rows)


DART_ACC = ("매출액", "수익(매출액)", "영업수익", "매출")
DART_REPORTS = (("11013", 1), ("11012", 2), ("11014", 3), ("11011", 4))   # 1분기·반기·3분기·사업보고서


def _amt(s):
    s = (s or "").replace(",", "").strip()
    return float(s) if s not in ("", "-") else None


def dart_revenue(js):
    """fnlttSinglAcnt 응답 → (3개월 매출, 누적 매출) — 연결(CFS) 우선, 없으면 별도(OFS). 없으면 (None, None)"""
    rows = [r for r in (js.get("list") or []) if r.get("sj_div") == "IS" and (r.get("account_nm") or "").strip() in DART_ACC]
    for fs in ("CFS", "OFS"):
        for r in rows:
            if r.get("fs_div") == fs:
                return _amt(r.get("thstrm_amount")), _amt(r.get("thstrm_add_amount"))
    return None, None


def dart_quarters(fetch, corp, years):
    """연도별 네 보고서 → [(기말일, 3개월 매출)]. 4분기 = 사업보고서 연간 − 3분기 누적. fetch(corp, 연도, 보고서) → 응답 JSON"""
    out = []
    for y in years:
        got = {}
        for code, q in DART_REPORTS:
            js = fetch(corp, y, code)
            if (js or {}).get("status") != "000":
                continue
            got[q] = dart_revenue(js)
        for q in (1, 2, 3):
            if q in got and got[q][0]:
                out.append((_qend(f"Q{q} {y}").isoformat(), got[q][0]))
        if 4 in got and 3 in got and got[4][0] and got[3][1]:
            out.append((date(y, 12, 31).isoformat(), got[4][0] - got[3][1]))
    return out


def put_dart(ids=None, years=range(2015, 2027)):
    """한국 지도 종목 분기 매출 — OpenDART 단일회사 주요계정(fnlttSinglAcnt, 2015~). 키 DART_API_KEY(load_env)
    겹치는 분기는 기존 TradingView 값과 1.5% 안에서 맞는지 대조해 결과를 돌려준다(어긋나면 그 회사는 넣지 않는다)"""
    import io
    import time
    import xml.etree.ElementTree as ET
    import zipfile
    key = common.load_env().get("DART_API_KEY")
    if not key:
        raise RuntimeError("DART_API_KEY 값이 비어 있다(D:\\local-only\\secrets\\.env)")
    want = {co["code"]: co["id"] for co in cfg().get("companies") or [] if co.get("market") == "kr" and (not ids or co["id"] in ids)}
    raw = common.http_get("https://opendart.fss.or.kr/api/corpCode.xml", {"crtfc_key": key}, timeout=90)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        xml = z.read(z.namelist()[0])
    corp = {want[s]: el.findtext("corp_code").strip() for el in ET.fromstring(xml).iter("list")
            if (s := (el.findtext("stock_code") or "").strip()) in want}

    def fetch(c, y, code):
        time.sleep(0.15)
        try:
            return json.loads(common.http_get("https://opendart.fss.or.kr/api/fnlttSinglAcnt.json",
                                              {"crtfc_key": key, "corp_code": c, "bsns_year": str(y), "reprt_code": code}, timeout=30))
        except Exception:
            return None
    rows, report = load_rev(), {}
    old = {(r["id"], r["period"]): r["revenue"] for r in rows}
    for cid, c in corp.items():
        qs = dart_quarters(fetch, c, years)
        diffs = [abs(v / old[(cid, p)] - 1) for p, v in qs if (cid, p) in old and old[(cid, p)]]
        bad = [x for x in diffs if x > 0.015]
        report[cid] = {"quarters": len(qs), "first": qs[0][0] if qs else None, "overlap": len(diffs), "max_diff": round(max(diffs), 4) if diffs else None, "accepted": not bad and bool(qs)}
        if report[cid]["accepted"]:
            keep = {p for p, _ in qs}
            rows = [r for r in rows if not (r["id"] == cid and r["period"] in keep)]
            rows += [{"id": cid, "period": p, "revenue": v, "earnings_date": "", "source": "OpenDART fnlttSinglAcnt(연결 우선, 4분기=연간−3분기 누적)"} for p, v in qs]
    save_rev(rows)
    return report


def load_rev():
    if not REV.exists():
        return []
    with REV.open(encoding="utf-8", newline="") as f:
        return [dict(r, revenue=float(r["revenue"])) for r in csv.DictReader(f)]


def save_rev(rows):
    rows = sorted(rows, key=lambda r: (r["id"], r["period"]))
    with REV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "period", "revenue", "earnings_date", "source"])
        w.writeheader()
        for r in rows:
            w.writerow({k: (int(r[k]) if k == "revenue" and float(r[k]).is_integer() else r[k]) for k in w.fieldnames})


def series_by_company():
    """{id: [(기말일, 매출, 발표일)]} — Fiscal 이력이 있으면 그것, 없으면 fundamentals.json(일본 株探 등). 같은 분기 중복 제거"""
    out = {}
    for r in load_rev():
        out.setdefault(r["id"], {})[r["period"]] = (r["revenue"], r["earnings_date"])
    fund = json.loads(FUND.read_text(encoding="utf-8")) if FUND.exists() else {}
    for cid, f in fund.items():
        if cid in out:
            continue
        for q in f.get("q") or []:
            if q.get("revenue"):
                out.setdefault(cid, {})[q["period"]] = (float(q["revenue"]), q.get("earnings_date") or "")
    return {cid: sorted((p, v, e) for p, (v, e) in s.items()) for cid, s in out.items()}


def quarters(seq):
    """분기 열 → 관측 후보. 직전 분기 간격 70~130일, 전년 같은 분기 간격 340~390일인 것만(반기·결측·회계 변경 제외)"""
    out = []
    for i, (p, v, e) in enumerate(seq):
        if i < 5:
            continue
        p1, p4, p5 = seq[i - 1], seq[i - 4], seq[i - 5]
        ok = 70 <= (d(p) - d(p1[0])).days <= 130 and 340 <= (d(p) - d(p4[0])).days <= 390 and 340 <= (d(p1[0]) - d(p5[0])).days <= 390
        if ok and min(v, p1[1], p4[1], p5[1]) > 0:
            out.append({"period": p, "start": seq[i - 1][0], "ly_period": p4[0], "ly_start": p5[0], "y": math.log(v / p4[1]),
                        "y1": math.log(p1[1] / p5[1]), "rev": v, "rev_ly": p4[1], "earnings_date": e})
    return out


# ── 신호 ─────────────────────────────────────────────────

def _titles(co):
    import re
    out = []
    for key, title in (co.get("wiki") or {}).items():
        lang = re.sub(r"\d+$", "", key)
        out.append((lang, [title] + list((co.get("wiki_old") or {}).get(key, []))))
    return out


def wiki_window(con, lang, titles, a, b):
    """(a, b] 기간 조회 합과 자료 있는 날 수 — 지금·옛 제목 합"""
    q = "select count(distinct day), coalesce(sum(views),0) from views where lang=? and title in (%s) and day>? and day<=?" % ",".join("?" * len(titles))
    n, v = con.execute(q, (lang, *titles, a.strftime("%Y%m%d"), b.strftime("%Y%m%d"))).fetchone()
    return v, n


def wiki_signal(con, co, start, end, ly_start, ly_end):
    """그 분기와 전년 같은 분기의 위키 조회 비율(로그) — 두 기간 모두 자료가 COVER 이상인 문서만 더한다"""
    now = prev = 0
    for lang, titles in _titles(co):
        v1, n1 = wiki_window(con, lang, titles, start, end)
        v0, n0 = wiki_window(con, lang, titles, ly_start, ly_end)
        if n1 >= COVER * (end - start).days and n0 >= COVER * (ly_end - ly_start).days and v0 > 0:
            now, prev = now + v1, prev + v0
    return clip(math.log(now / prev)) if now > 0 and prev > 0 else None


def trade_series(co_id):
    """{월: 달러} — 회사에 연결된 첫 품목의 한 나라(primary 지정, 없으면 partners 첫 나라). 여러 품목·나라를 더하지 않는다"""
    items = [it for it in (cfg().get("trade") or {}).get("items") or [] if co_id in (it.get("ids") or [])]
    if not items or not TRADE.exists():
        return None
    it = items[0]
    ptn = (it.get("primary") or {}).get(co_id) or it["partners"][0]
    s = {}
    with TRADE.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r["hs"] == it["hs"] and r["partner"] == ptn:
                s[r["month"]] = float(r["usd"])
    return {"hs": it["hs"], "partner": ptn, "s": s}


def months_in(a, b):
    """(a, b] 안에 끝나는 달 — 'YYYY-MM' 목록"""
    out, y, m = [], a.year, a.month
    while True:
        last = (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1))
        if last > b:
            break
        if last > a:
            out.append(f"{y}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def trade_signal(ts, start, end, ly_start, ly_end):
    if not ts:
        return None
    mo, ly = months_in(start, end)[:-1], months_in(ly_start, ly_end)[:-1]   # 마지막 달 제외(공표 시차)
    if not mo or len(mo) != len(ly) or not all(m in ts["s"] for m in mo + ly):
        return None
    a, b = sum(ts["s"][m] for m in mo), sum(ts["s"][m] for m in ly)
    return clip(math.log(a / b)) if a > 0 and b > 0 else None


def clip(x):
    return max(-CLIP, min(CLIP, x))


# ── 패널 ─────────────────────────────────────────────────

def panel():
    cos = {co["id"]: co for co in cfg().get("companies") or []}
    con = sqlite3.connect(WIKI_DB) if WIKI_DB.exists() else None
    obs = []
    for cid, seq in series_by_company().items():
        co = cos.get(cid)
        if not co:
            continue
        ts = trade_series(cid)
        for q in quarters(seq):
            a, b, la, lb = d(q["start"]), d(q["period"]), d(q["ly_start"]), d(q["ly_period"])
            q.update(id=cid, wiki=wiki_signal(con, co, a, b, la, lb) if con else None, trade=trade_signal(ts, a, b, la, lb))
            obs.append(q)
    return sorted(obs, key=lambda o: o["period"])


def ols(X, y):
    """최소제곱(정규방정식, 가우스 소거) — 계수 목록, 특이하면 None"""
    k = len(X[0])
    A = [[sum(r[i] * r[j] for r in X) for j in range(k)] + [sum(r[i] * t for r, t in zip(X, y))] for i in range(k)]
    for c in range(k):
        p = max(range(c, k), key=lambda r: abs(A[r][c]))
        if abs(A[p][c]) < 1e-12:
            return None
        A[c], A[p] = A[p], A[c]
        for r in range(k):
            if r != c:
                f = A[r][c] / A[c][c]
                A[r] = [x - f * z for x, z in zip(A[r], A[c])]
    return [A[i][k] / A[i][i] for i in range(k)]


def qkey(p):
    dt = d(p)
    return dt.year * 4 + (dt.month - 1) // 3


def walk(obs, sig):
    """신호가 있는 관측만 — 검증 분기마다 그보다 앞선 분기로 기본·확장을 함께 학습. [(관측, 기본 오차², 확장 오차²)]"""
    rows = [o for o in obs if o[sig] is not None]
    out = []
    for qk in sorted({qkey(o["period"]) for o in rows}):
        train = [o for o in rows if qkey(o["period"]) < qk]
        test = [o for o in rows if qkey(o["period"]) == qk]
        if len(train) < MIN_TRAIN:
            continue
        cb = ols([[1, o["y1"]] for o in train], [o["y"] for o in train])
        ce = ols([[1, o["y1"], o[sig]] for o in train], [o["y"] for o in train])
        if not cb or not ce:
            continue
        for o in test:
            eb = o["y"] - (cb[0] + cb[1] * o["y1"])
            ee = o["y"] - (ce[0] + ce[1] * o["y1"] + ce[2] * o[sig])
            out.append((o, eb * eb, ee * ee))
    return out


def evaluate(obs, sigs=("wiki", "trade"), trials=None):
    trials = trials or len(sigs)
    res = {}
    for sig in sigs:
        w = walk(obs, sig)
        ok, why, st = harness.nested_test([b for _, b, _ in w], [e for _, _, e in w], trials=trials)
        rows = [o for o in obs if o[sig] is not None]
        coef = ols([[1, o["y1"], o[sig]] for o in rows], [o["y"] for o in rows]) if len(rows) >= MIN_TRAIN else None
        per = {}
        for o, b, e in w:
            p = per.setdefault(o["id"], [0.0, 0.0, 0])
            p[0] += b; p[1] += e; p[2] += 1
        fit = {cid: {"n_oos": n, "rmse_base": round(math.sqrt(b / n), 4), "rmse_ext": round(math.sqrt(e / n), 4),
                     "fits": n >= COMPANY_MIN_OOS and b > 0 and (b - e) / b >= COMPANY_GAIN} for cid, (b, e, n) in sorted(per.items())}
        res[sig] = {"adopted": ok, "reason": why, "stats": st, "n_obs": len(rows), "companies": len({o["id"] for o in rows}),
                    "coef": None if not coef else {"a": round(coef[0], 4), "rho": round(coef[1], 4), "beta": round(coef[2], 4)},
                    "rmse_oos_ext": round(math.sqrt(sum(e for _, _, e in w) / len(w)), 4) if w else None,
                    "rmse_oos_base": round(math.sqrt(sum(b for _, b, _ in w) / len(w)), 4) if w else None, "per_company": fit}
    return res


# ── 진행 중 분기 나우캐스트 ───────────────────────────────

def nowcast(res, today=None):
    """채택 신호 × 적합 회사만 — 마지막 발표 분기 다음 분기를, 오늘까지 경과한 같은 날 수의 신호로(부분 기간 표시)"""
    today = today or common.now_kst().date()
    cos = {co["id"]: co for co in cfg().get("companies") or []}
    con = sqlite3.connect(WIKI_DB) if WIKI_DB.exists() else None
    seqs = series_by_company()
    out = []
    for sig, r in res.items():
        if not r["adopted"] or not r["coef"]:
            continue
        c = r["coef"]
        for cid, f in r["per_company"].items():
            if not f["fits"] or cid not in seqs:
                continue
            seq = seqs[cid]
            if len(seq) < 4:
                continue
            last, ly = seq[-1], seq[-4]          # 다음 분기의 전년 같은 분기 = 끝에서 네 번째 분기 다음 → seq[-4]
            start, ly_start = d(last[0]), d(seq[-5][0]) if len(seq) >= 5 else None
            end = min(today - timedelta(days=1), start + (d(ly[0]) - ly_start).days * timedelta(days=1)) if ly_start else None
            if not end or end <= start:
                continue
            ly_end = ly_start + (end - start)
            y1 = math.log(last[1] / seq[-5][1]) if len(seq) >= 5 else None
            s = wiki_signal(con, cos[cid], start, end, ly_start, ly_end) if sig == "wiki" else trade_signal(trade_series(cid), start, end, ly_start, ly_end)
            if s is None or y1 is None:
                continue
            g = c["a"] + c["rho"] * y1 + c["beta"] * s
            band = f["rmse_ext"]
            out.append({"id": cid, "name": cos[cid]["name"], "signal": sig, "quarter_ly_period": ly[0], "window": [start.isoformat(), end.isoformat()],
                        "elapsed_share": round((end - start).days / max(1, (d(ly[0]) - ly_start).days), 2), "s": round(s, 3), "y1": round(y1, 3),
                        "yoy_nowcast": round(math.exp(g) - 1, 3), "yoy_band": [round(math.exp(g - band) - 1, 3), round(math.exp(g + band) - 1, 3)],
                        "revenue_ly": ly[1], "revenue_nowcast": round(ly[1] * math.exp(g)), "expected_report": _next_report(ly)})
    return out


def _next_report(ly):
    return (d(ly[2]) + timedelta(days=364)).isoformat() if ly[2] else None


def attach_consensus(path):
    """Fiscal.ai 다음 분기 매출 컨센서스 {회사키: {period, revenue}} → 나우캐스트와의 차이(로그)와 범위 밖 여부"""
    nc = json.loads(NOWCAST.read_text(encoding="utf-8"))
    by_key = {co["id"]: co.get("fiscal") for co in cfg().get("companies") or []}
    cons = json.loads(Path(path).read_text(encoding="utf-8"))
    for r in nc.get("nowcast") or []:
        c = cons.get(by_key.get(r["id"]) or "")
        if not c or not c.get("revenue"):
            continue
        gap = math.log(r["revenue_nowcast"] / c["revenue"])
        band = nc["tests"][r["signal"]]["per_company"][r["id"]]["rmse_ext"]
        r["consensus"] = {"revenue": c["revenue"], "period": c.get("period"), "gap_log": round(gap, 3), "outside_band": abs(gap) > band,
                          "consensus_yoy": round(c["revenue"] / r["revenue_ly"] - 1, 3)}
    NOWCAST.write_text(json.dumps(nc, ensure_ascii=False, indent=1), encoding="utf-8")
    return nc


def prior_trials():
    """같은 가설을 다시 본 횟수도 시도로 센다(선택적 중단 보정, 보수적) — changelog.csv의 나우캐스트 계수 검정 기록 수"""
    f = ROOT / "knowledge" / "models" / "params" / "changelog.csv"
    if not f.exists():
        return 0
    with f.open(encoding="utf-8", newline="") as fh:
        return sum(1 for r in csv.DictReader(fh) if (r.get("param_id") or "").startswith("prm-consumer-nowcast-beta-"))


def run():
    obs = panel()
    trials = prior_trials() + 2
    res = evaluate(obs, trials=trials)
    nc = nowcast(res)
    doc = {"as_of": common.iso(common.now_kst()), "method": f"패널 walk-forward, 기본 y=a+ρy₋₁ vs 확장 +βs, harness.nested_test(본페로니 {trials} — 다시 본 검정 포함, 개선은 MSE 기준)", "trials": trials,
           "clip": CLIP, "min_train": MIN_TRAIN, "n_obs": len(obs), "companies": sorted({o["id"] for o in obs}), "tests": res, "nowcast": nc,
           "note": "채택되지 않은 신호는 나우캐스트를 내지 않는다. 범위 = 회사별 표본 외 RMSE(로그). 매수 권유 아님."}
    NOWCAST.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return doc


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if argv[:1] == ["--put-fiscal"]:
        print(f"매출 이력 {put_fiscal(argv[1])}행")
        return 0
    if argv[:1] == ["--dart"]:
        print(json.dumps(put_dart(argv[1:] or None), ensure_ascii=False, indent=1))
        return 0
    if argv[:1] == ["--put-tv"]:
        print(f"매출 이력 {put_tv(argv[1])}행")
        return 0
    if argv[:1] == ["--consensus"]:
        nc = attach_consensus(argv[1])
        print(json.dumps([{k: r.get(k) for k in ("id", "yoy_nowcast", "yoy_band", "consensus")} for r in nc["nowcast"]], ensure_ascii=False, indent=1))
        return 0
    doc = run()
    for sig, r in doc["tests"].items():
        print(f"{sig}: {'채택' if r['adopted'] else '불채택'} — {r['reason']} · 관측 {r['n_obs']}·{r['companies']}개사 · 표본 외 RMSE 기본 {r['rmse_oos_base']} → 확장 {r['rmse_oos_ext']} · 계수 {r['coef']}")
        print("   적합 회사:", ", ".join(f"{k}({v['rmse_base']}→{v['rmse_ext']}, n{v['n_oos']})" for k, v in r["per_company"].items() if v["fits"]) or "없음")
    for r in doc["nowcast"]:
        print(r["id"], r["signal"], f"YoY {r['yoy_nowcast']:+.1%} [{r['yoy_band'][0]:+.1%}, {r['yoy_band'][1]:+.1%}]", f"경과 {r['elapsed_share']:.0%}", r["expected_report"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
