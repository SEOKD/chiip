"""Chiip Memory Spot — DRAM·NAND 현물가격 추정 그래프 (마스터 지시 2026-11-19 "Pulse는 주중에 매일 아침 10~11시 사이 DRAM 및 NAND
Spot Price 가격을 추정해 그래프로 그려라. 데이터 파이프라인을 구축하고 t.me/merITz_tech 같은 채널에 올라오는 스팟 데이터를 참조하라.
보통 D램익스체인지처럼 유료 데이터인 경우가 많아 이렇게 텔레그램 채널을 활용하면 좋다").

원천: 공개 텔레그램 채널(config/memory_spot.yaml channels — 지금은 merITz_tech)의 평일 아침 '메모리 스팟가격' 줄.
  제품별 1D·1W·1M 변화율(%)만 있고 달러 가격은 없다(원자료 D램익스체인지는 유료).
추정: 게시일 t의 로그 가격 x_t를 미지수로 두고
  1D: x_t − x_(직전 게시일) = ln(1+1D)   — 사이에 빠진 거래일이 없을 때만(한국 휴일로 글이 빠진 날은 1D가 마지막 하루만 담는다)
  1W: x_t − x_(7일 전)     = ln(1+1W)
  1M: x_t − x_(한 달 전)   = ln(1+1M)
  을 모두 제약으로 놓고 가중 최소제곱(1D 1, 1W 0.5, 1M 0.25)으로 푼다. 1W·1M이 휴일 공백을 메우고, 잔차가 추정 품질이다.
  달러 환산: config/memory_spot.yaml anchors(공개 보도에 나온 현물 평균가·날짜·출처)로 배율을 정한다. 기준점이 없으면 지수(기간 첫날=100)만.
저장: radar/inbox/memory_spot/(git 제외 — 유료 원자료의 파생 수치라 저장소에 커밋하지 않는다). 그래프·피드는 마스터 개인 봇으로만.
Pulse: 평일 10:00~11:00 KST 첫 회차가 연다(status due, 하루 1회).
NAND 일별(2026-11-23 마스터 지시 "메모리 현물 가격 트렌드 추이는 NAND도 DRAM처럼 일일 추이를 파악할 수 있도록 해라"):
  합친 그림(combined_chart)의 NAND 칸은 주 1회 관측점 사이를 채널 글의 1D 변화율을 그대로 쌓은 경로(raw_path)로 채운다.
  NAND 현물 고시는 대부분의 날에 그대로라 선이 계단처럼 보인다 — 자료 누락이 아니다. config/memory_spot.yaml nand_daily: false면 옛 방식.
사용: py radar/memory_spot.py --backfill 2026-01-01      # 채널 공개 미리보기를 거슬러 읽어 지난 줄 채우기(로그인 없음)
      py radar/memory_spot.py --update                    # 수집기(radar/inbox/tg_channels/*.jsonl)의 새 줄 반영
      py radar/memory_spot.py --chart [시작일]              # 그래프 PNG + 요약 JSON
      py radar/memory_spot.py --status                    # Pulse 관문
      py radar/memory_spot.py --send <json>               # {"read": "풀이 2~4문장"} → 그래프 1장 + 풀이
"""
import csv
import json
import math
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

STATE = "memory_spot"
OUT = common.ROOT / "radar" / "inbox" / "memory_spot"
ROWS = OUT / "rows.csv"
FIELDS = ["post_id", "channel", "posted_at", "product", "d1", "w1", "m1", "url"]
NUM = r"([+-]?\d+(?:\.\d+)?)\s*%"
LINE = re.compile(r"((?:LP)?DDR\d\w*\s*\d+\s*Gb|(?:SLC|MLC|TLC|QLC)\s*\d+\s*Gb)\s*:\s*1D\s*" + NUM + r"\s*,\s*1W\s*" + NUM + r"\s*,\s*1M\s*" + NUM, re.I)
W = {"d1": 1.0, "w1": 0.5, "m1": 0.25}
WINDOW = (10, 11)   # KST 시 — 이 사이 첫 Pulse 회차


def config():
    return common.load_yaml("config/memory_spot.yaml") or {}


def parse_post(p):
    """채널 글 1건 → [{product, d1, w1, m1}] (스팟 줄이 없으면 빈 목록)"""
    out = []
    for m in LINE.finditer(p.get("text") or ""):
        prod = re.sub(r"\s+", " ", m.group(1)).strip()
        prod = re.sub(r"(\d+)\s*gb$", r"\1Gb", prod, flags=re.I)
        out.append({"post_id": p["id"], "channel": p["channel"], "posted_at": p["at"], "product": prod,
                    "d1": float(m.group(2)), "w1": float(m.group(3)), "m1": float(m.group(4)), "url": p["url"]})
    return out


def read_rows():
    if not ROWS.exists():
        return []
    with ROWS.open(encoding="utf-8") as f:
        return [{**r, "post_id": int(r["post_id"]), "d1": float(r["d1"]), "w1": float(r["w1"]), "m1": float(r["m1"])} for r in csv.DictReader(f)]


def write_rows(rows):
    OUT.mkdir(parents=True, exist_ok=True)
    rows = sorted({(r["channel"], r["post_id"], r["product"]): r for r in rows}.values(), key=lambda r: (r["posted_at"], r["product"]))
    with ROWS.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows({k: r[k] for k in FIELDS} for r in rows)
    return rows


def update():
    """수집기가 쌓은 채널 글에서 새 스팟 줄을 더한다 → 더한 줄 수"""
    have = {(r["channel"], r["post_id"]) for r in read_rows()}
    new = []
    for ch in config().get("channels") or []:
        f = common.ROOT / "radar" / "inbox" / "tg_channels" / f"{ch}.jsonl"
        if not f.exists():
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                p = json.loads(line)
            except ValueError:
                continue
            if (p.get("channel"), p.get("id")) not in have:
                new += parse_post(p)
    if new:
        write_rows(read_rows() + new)
    return len(new)


def backfill(since, channel=None, pause=1.2, max_pages=600):
    """공개 미리보기 t.me/s/<채널>?before=<번호>를 거슬러 읽어 since(YYYY-MM-DD)까지의 스팟 줄을 채운다(본문은 저장하지 않는다)"""
    from pollers import tg_channels as T
    got = []
    for ch in ([channel] if channel else config().get("channels") or []):
        url, pages = f"https://t.me/s/{ch}", 0
        while pages < max_pages:
            page = T.parse(T.fetch(url))
            pages += 1
            if not page:
                break
            for p in page:
                got += parse_post(p)
            low = min(p["id"] for p in page)
            if min(p["at"] for p in page)[:10] < since or low <= 1:
                break
            url = f"https://t.me/s/{ch}?before={low}"
            time.sleep(pause)
        print(f"[Memory Spot] {ch}: {pages}쪽 · 스팟 줄 누적 {len(got)}", flush=True)
    write_rows(read_rows() + got)
    return len(got)


def _d(s):
    return date.fromisoformat(s[:10])


def _month_back(d):
    y, m = (d.year, d.month - 1) if d.month > 1 else (d.year - 1, 12)
    for day in range(d.day, 0, -1):
        try:
            return date(y, m, day)
        except ValueError:
            continue


def _weekdays_between(a, b):
    """a < b 사이(양끝 제외) 평일 수"""
    n, d = 0, a + timedelta(days=1)
    while d < b:
        n += d.weekday() < 5
        d += timedelta(days=1)
    return n


def estimate(rows, product, since=None):
    """→ {dates, x(로그), resid_pct, n_eq, gaps}. 같은 날 글이 둘이면 뒤 글"""
    import numpy as np
    by = {}
    for r in sorted((r for r in rows if r["product"] == product), key=lambda r: r["posted_at"]):
        by[_d(r["posted_at"])] = r
    ds = sorted(d for d in by if not since or d >= _d(since) - timedelta(days=40))   # 1M 제약을 위해 40일 앞부터
    if len(ds) < 2:
        return None
    ix = {d: i for i, d in enumerate(ds)}
    A, b, w, kind = [], [], [], []

    def eq(t, s, val, wt, k):
        row = [0.0] * len(ds)
        row[ix[t]], row[ix[s]] = 1.0, -1.0
        A.append(row)
        b.append(math.log1p(val / 100))
        w.append(wt)
        kind.append(k)

    gaps = []
    for i, t in enumerate(ds):
        r = by[t]
        if i and _weekdays_between(ds[i - 1], t) == 0:
            eq(t, ds[i - 1], r["d1"], W["d1"], "d1")
        elif i:
            gaps.append(t.isoformat())
        if t - timedelta(days=7) in ix:
            eq(t, t - timedelta(days=7), r["w1"], W["w1"], "w1")
        mb = _month_back(t)
        if mb in ix:
            eq(t, mb, r["m1"], W["m1"], "m1")
    row = [0.0] * len(ds)
    row[0] = 1.0
    A.append(row)
    b.append(0.0)
    w.append(100.0)
    kind.append("anchor")
    A, b, w = np.array(A), np.array(b), np.array(w)
    x, *_ = np.linalg.lstsq(A * w[:, None], b * w, rcond=None)
    res = (A @ x - b)[:-1]
    return {"dates": ds, "x": x, "resid_pct": float(np.sqrt(np.mean(res ** 2)) * 100) if len(res) else 0.0,
            "n_eq": len(res), "gaps": gaps, "kinds": kind}


def series(rows, product, since, anchors=None):
    """→ {product, points[(date, 값)], unit, anchors_used, misfit_pct, resid_pct, gaps, last, chg}"""
    e = estimate(rows, product, since)
    if not e:
        return None
    pts = [(d, x) for d, x in zip(e["dates"], e["x"]) if d >= _d(since)]
    if not pts:
        return None
    anc = [a for a in (anchors or []) if a.get("product") == product]
    used, logs = [], []
    for a in anc:
        ad = _d(str(a["date"]))
        # 아침 글은 전 거래일 세션 값이다 → 기준점 날짜 다음 게시일 노드에 맞춘다
        near = next((d for d in e["dates"] if d > ad), None)
        if near and (near - ad).days <= 4:
            xi = float(e["x"][list(e["dates"]).index(near)])
            logs.append(math.log(float(a["usd"])) - xi)
            used.append({**a, "node": near.isoformat()})
    if logs:
        k = sorted(logs)[len(logs) // 2]
        vals = [(d, math.exp(x + k)) for d, x in pts]
        unit = "USD"
        mis = max(abs(math.exp(l - k) - 1) * 100 for l in logs)
    else:
        base = pts[0][1]
        vals = [(d, 100 * math.exp(x - base)) for d, x in pts]
        unit = "지수"
        mis = None
    last, first = vals[-1], vals[0]

    def back(days):
        tgt = last[0] - timedelta(days=days)
        old = [v for v in vals if v[0] <= tgt]
        return (last[1] / old[-1][1] - 1) * 100 if old else None
    return {"product": product, "points": vals, "unit": unit, "anchors_used": used, "misfit_pct": mis,
            "resid_pct": e["resid_pct"], "gaps": [g for g in e["gaps"] if g >= since], "last": last,
            "chg": {"1W": back(7), "1M": back(30), "YTD": (last[1] / first[1] - 1) * 100}}


def _nice(x):
    e = 10 ** math.floor(math.log10(x))
    return next(m * e for m in (1, 2, 2.5, 5, 10) if m * e >= x)


# ---------- 그래프(PyMuPDF로 그린다 — 새 패키지 없이) ----------
FONT = "C:/Windows/Fonts/malgun.ttf"


def _txt(page, xy, s, size=9, color=(0.2, 0.2, 0.2), right=False):
    import pymupdf
    kw = {"fontname": "malgun", "fontfile": FONT} if Path(FONT).exists() else {"fontname": "korea"}
    if right:
        f = pymupdf.Font(fontfile=FONT) if Path(FONT).exists() else pymupdf.Font("korea")
        xy = (xy[0] - f.text_length(s, fontsize=size), xy[1])
    page.insert_text(xy, s, fontsize=size, color=color, **kw)


def _panel(page, box, s, color, title):
    x0, y0, x1, y1 = box
    ys = [v for _, v in s["points"]]
    lo, hi = min(ys), max(ys)
    step = _nice((hi - lo) / 4 or hi * 0.05 or 1)
    lo, hi = math.floor(lo / step) * step, math.ceil(hi * 1.12 / step) * step   # 위 12%는 이름표 자리
    d0, d1 = s["points"][0][0], s["points"][-1][0]
    span = max((d1 - d0).days, 1)

    def X(d):
        return x0 + (x1 - x0) * (d - d0).days / span

    def Y(v):
        return y1 - (y1 - y0) * (v - lo) / (hi - lo)
    _txt(page, (x0, y0 - 22), title, 12, (0.1, 0.1, 0.1))
    v = lo
    while v <= hi + 1e-9:   # 가로 눈금(반올림한 값)
        page.draw_line((x0, Y(v)), (x1, Y(v)), color=(0.88, 0.88, 0.88), width=0.6)
        lab = f"${v:,.0f}" if s["unit"] == "USD" else f"{v:,.0f}"
        _txt(page, (x0 - 6, Y(v) + 3), lab, 8, (0.45, 0.45, 0.45), right=True)
        v += step
    m = date(d0.year, d0.month, 1)
    while m <= d1:   # 월 눈금
        if m >= d0:
            page.draw_line((X(m), y0), (X(m), y1), color=(0.93, 0.93, 0.93), width=0.5)
            _txt(page, (X(m) - 8, y1 + 13), f"{m.month}월", 8, (0.45, 0.45, 0.45))
        m = date(m.year + (m.month == 12), m.month % 12 + 1, 1)
    page.draw_rect((x0, y0, x1, y1), color=(0.75, 0.75, 0.75), width=0.6)
    pts = [(X(d), Y(v)) for d, v in s["points"]]
    page.draw_polyline(pts, color=color, width=1.8)
    lx, ly = pts[-1]
    page.draw_circle((lx, ly), 2.6, color=color, fill=color)
    last = s["last"][1]
    lab = f"${last:,.2f}" if s["unit"] == "USD" else f"{last:,.1f}"
    c = s["chg"]
    parts = [f"{k} {v:+.1f}%" for k, v in c.items() if v is not None]
    _txt(page, (x0 + 8, y0 + 16), f"{s['last'][0].strftime('%m/%d')} {lab}   " + " · ".join(parts), 10, color)
    for a in s.get("anchors_used") or []:   # 달러 기준점(공개 보도)
        ad = date.fromisoformat(a["node"])
        page.draw_circle((X(ad), Y(float(a["usd"]))), 3, color=(0.1, 0.1, 0.1), width=0.8)


def chart(since=None, dram=None, nand=None, path=None):
    """→ (png 경로, 요약 dict)"""
    import pymupdf
    cfg = config()
    since = since or f"{common.now_kst().year}-01-01"
    rows = read_rows()
    dram, nand = dram or cfg.get("dram", "DDR5 16Gb"), nand or cfg.get("nand", "MLC 64Gb")
    S = [series(rows, p, since, cfg.get("anchors")) for p in (dram, nand)]
    if not all(S):
        raise SystemExit(f"[Memory Spot] 자료 부족 — {dram}·{nand} 줄을 먼저 채운다(--backfill/--update)")
    doc = pymupdf.open()
    page = doc.new_page(width=720, height=640)
    page.draw_rect(page.rect, color=None, fill=(1, 1, 1))
    _txt(page, (36, 34), f"메모리 현물가격 추정 — {since[:4]} YTD", 15, (0.05, 0.05, 0.05))
    _txt(page, (36, 52), f"기준 {S[0]['last'][0].isoformat()} · 일별 변화율(1D·1W·1M)을 최소제곱으로 이어 붙인 추정치", 8.5, (0.4, 0.4, 0.4))
    for s, box, col in ((S[0], (80, 100, 690, 320), (0.13, 0.36, 0.75)), (S[1], (80, 390, 690, 590), (0.80, 0.33, 0.10))):
        unit = "달러, ○ = 공개 보도 기준점" if s["unit"] == "USD" else f"지수, {s['points'][0][0].strftime('%m/%d')}=100"
        _panel(page, box, s, col, f"{'DRAM' if s is S[0] else 'NAND'} {s['product']} 현물 ({unit})")
    note = (f"자료: 공개 텔레그램 채널({', '.join(cfg.get('channels') or [])})의 D램익스체인지 현물 변화율 → Chiip 추정. "
            f"잔차 {S[0]['resid_pct']:.2f}%p·{S[1]['resid_pct']:.2f}%p. 달러 원자료 아님.")
    _txt(page, (36, 622), note, 7.5, (0.45, 0.45, 0.45))
    OUT.mkdir(parents=True, exist_ok=True)
    path = Path(path or OUT / f"spot_{S[0]['last'][0].strftime('%Y%m%d')}.png")
    page.get_pixmap(dpi=150).save(str(path))
    summ = {"since": since, "png": str(path),
            "series": [{k: (v if k != "points" else len(v)) for k, v in s.items() if k not in ("last",)} | {"last": [s["last"][0].isoformat(), s["last"][1]]}
                       for s in S]}
    return path, json.loads(json.dumps(summ, default=str))


def status(now=None):
    """Pulse 관문 — 평일 10~11시 KST, 하루 1회. 그림은 합친 한 장(combined_chart)"""
    now = now or common.now_kst()
    st = common.load_state(STATE, {})
    today = now.date().isoformat()
    if now.weekday() >= 5 or not (WINDOW[0] <= now.hour < WINDOW[1]) or st.get("sent") == today:
        return {"due": False}
    try:
        update()
        png, summ = combined_chart()
    except (Exception, SystemExit) as e:
        return {"due": False, "error": f"{type(e).__name__}: {str(e)[:120]}"}
    return {"due": True, "png": str(png), "summary": summ}


# ---------- 합친 한 장 (마스터 지시 2026-11-20 "트렌드포스 파이프라인을 기본으로 하되 메리츠에서 제공하는 D램익스체인지 데이터로 보강하는 식으로
# 하나의 그래프만 제공하라") ----------
# 뼈대 = TrendForce 공개 현물표 Session Average(달러, 관측일). 관측이 없는 세션(아카이브 공백·공개 페이지 갱신 지연)은
# 직전 TrendForce 관측값 × 메리츠 채널 변화율로 이은 비율(같은 기간 메리츠 추정 시계열의 상대 변화)로 채운다 — 다음 TrendForce 관측이 오면 그 값으로 돌아간다.
# 메리츠 글(D+1일 아침)은 D일 세션 값 → 메리츠 점의 세션 날짜 = 글 날짜의 직전 평일.
# NAND는 주 1회 갱신이고 공개 페이지 날짜 표기가 한 주씩 늦게 남는 때가 있어(톱니 원인) 관측 사이는 보강하지 않고 마지막 관측 뒤만 보강한다
PAIRS = (("DDR5 16Gb", "DDR5 16Gb (2Gx8) 4800/5600", "DRAM", True), ("MLC 64Gb", "MLC 64Gb 8GBx8", "NAND", False))
# 2026-11-23 마스터 지시 "DRAM 스팟은 DDR4 8Gb도, NAND 스팟에도 1Tb TLC 현물을 같이 — 일일 집계, DRAM 두 추이는 한 그래프에, NAND도":
# 칸마다 두 품목을 한 그래프에 그린다. 1Tb TLC 웨이퍼는 TrendForce 공개 웨이퍼표(512·256·128Gb TLC)에 없다 — 자료가 생기면 바로 그리고, 없으면 그림에 '공개 원천 없음'
SERIES = (("DDR5 16Gb", "DDR5 16Gb (2Gx8) 4800/5600", "DRAM", True), ("DDR4 8Gb", "DDR4 8Gb (1Gx8) 3200", "DRAM", True),
          (None, "Wafer 512Gb TLC", "NAND", False), (None, "Wafer 1Tb TLC", "NAND", False))


def raw_path(rows, product):
    """채널 글의 1D 변화율을 그대로 곱해 만든 일별 경로 [(글 날짜, 배율)] — 고시가 바뀐 날에만 움직인다.
    estimate()의 최소제곱 경로는 1W·1M 제약을 함께 맞추느라 변화를 여러 날에 퍼뜨린다. NAND처럼 며칠에 한 번 바뀌는 값은
    1D를 그대로 쌓아야 '어느 날 바뀌었나'가 보인다(2026-11-23 마스터 지시 "NAND도 DRAM처럼 일일 추이"). 글이 빠진 날의 변화는
    여기에 없다 — blend가 다음 관측값과 만나게 보정한다"""
    x, out = 1.0, []
    for r in sorted((r for r in rows if r["product"] == product), key=lambda r: r["posted_at"]):
        try:
            x *= 1 + float(r["d1"] or 0) / 100
        except ValueError:
            continue
        out.append((_d(r["posted_at"]), x))
    return out


def _prev_weekday(d):
    d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def blend(tf_pts, m_pts, interior=True):
    """tf_pts [(세션일, $)], m_pts [(글 날짜, 추정값)] → [(날짜, $, 'tf'|'mz')].
    두 TrendForce 관측 a·b 사이의 빈 세션은 메리츠 모양을 쓰되 b에서 TrendForce 값과 만나게 로그 선형으로 보정한다
    (보정 없이 이으면 다음 관측에서 값이 되돌아가 톱니가 생긴다 — 2026-11-20 첫 그림). 마지막 관측 뒤는 메리츠 변화율 그대로"""
    import bisect
    tf = sorted(tf_pts)
    mz = {_prev_weekday(x): v for x, v in m_pts}   # 세션일 기준
    mk = sorted(mz)

    def m_at(d):   # d 이하 마지막 메리츠 값
        i = bisect.bisect_right(mk, d)
        return mz[mk[i - 1]] if i else None
    out = []
    for i, (a, va) in enumerate(tf):
        out.append((a, va, "tf"))
        b = tf[i + 1] if i + 1 < len(tf) else None
        ma = m_at(a)
        if not ma:
            continue
        gap = [d for d in mk if d > a and (b is None or d < b[0])] if (interior or b is None) else []   # interior=False면 관측 사이는 관측끼리 잇는다
        corr = 1.0
        if b:
            mb = m_at(b[0])
            corr = (b[1] / va) / (mb / ma) if mb else 1.0
        for d in gap:
            f = (d - a).days / (b[0] - a).days if b else 0.0
            out.append((d, va * mz[d] / ma * corr ** f, "mz"))
    return out


def hold_daily(pts, until):
    """[(날짜, $, src)] → 평일마다 한 점. 관측 없는 평일은 직전 값을 'hold'로 유지(새 값을 지어내지 않는다)"""
    by = {d: (v, s) for d, v, s in pts}
    out, d, cur = [], pts[0][0], None
    while d <= max(until, pts[-1][0]):
        if d in by:
            cur = by[d][0]
            out.append((d, cur, by[d][1]))
        elif d.weekday() < 5 and cur is not None:
            out.append((d, cur, "hold"))
        d += timedelta(days=1)
    return out


def relabel_last(tf_pts, trow_chg, mrows, product):
    """TrendForce 공개 페이지의 NAND 'Last Update' 날짜가 한 주 늦게 남는 경우가 있다(2026-11-19 확인: 11-09 표기에 11/16 변화율 +0.42%).
    마지막 관측의 변화율이 그 뒤 메리츠 세션의 1D 변화율과 같으면(±0.02%p, 0이 아닌 값) 그 세션 값으로 날짜를 옮겨 이중 계산을 막는다"""
    if not tf_pts or trow_chg in (None, "", 0) or float(trow_chg) == 0:
        return tf_pts
    t, v = tf_pts[-1]
    for r in sorted(mrows, key=lambda r: r["posted_at"]):
        s = _prev_weekday(_d(r["posted_at"]))
        if r["product"] == product and t < s <= t + timedelta(days=10) and float(r["d1"] or 0) and abs(float(r["d1"]) - float(trow_chg)) <= 0.02:
            return tf_pts[:-1] + [(s, v)]
    return tf_pts


def combined(since=None):
    import trendforce_spot as T
    cfg = config()
    since = since or f"{common.now_kst().year}-01-01"
    rows, trows = read_rows(), T.read_rows()
    out, missing = [], []
    pairs = list(SERIES)
    if not T.series(T.NAND, since, trows):   # 웨이퍼표가 없으면 옛 MLC 64Gb 칩 현물로
        pairs = [p for p in pairs if p[2] == "DRAM"] + [PAIRS[1]]
    for mprod, tprod, kind, interior in pairs:
        ts = T.series(tprod, since, trows)
        ms = series(rows, mprod, since, cfg.get("anchors")) if mprod else None
        if not ts:
            missing.append((kind, tprod))
            continue
        last_row = max((r for r in trows if r["item"] == tprod), key=lambda r: r["date"], default={})
        tf_pts = relabel_last(ts["points"], last_row.get("chg"), rows, mprod)
        if tf_pts[-1][0] != ts["last"][0]:
            ts["last"] = tf_pts[-1]
        daily = kind == "NAND" and bool(mprod) and cfg.get("nand_daily", True)   # NAND도 관측 사이를 일별로 채운다(2026-11-23) — 1D를 그대로 쌓은 경로로
        pts = blend(tf_pts, raw_path(rows, mprod), True) if daily else blend(tf_pts, ms["points"] if ms else [], interior)
        if kind == "NAND" and not mprod:   # 웨이퍼는 주 1회 고시 — 일별 축에 고시값을 다음 고시까지 그대로 둔다(2026-11-23 "NAND도 DRAM처럼 일일 기준 집계")
            pts = hold_daily(pts, min(common.now_kst().date(), pts[-1][0] + timedelta(days=10)))
            daily = True
        pts = [p for p in pts if p[0] >= ts["points"][0][0]]
        last = max((p for p in pts if p[2] != "hold"), key=lambda p: p[0])

        def back(days, pts=pts, last=last):
            ref = last[0] - timedelta(days=days)
            old = [p for p in pts if p[0] <= ref]
            return (last[1] / old[-1][1] - 1) * 100 if old and (ref - old[-1][0]).days <= 10 else None   # NAND는 주 1회 관측
        base = ts["base"]
        out.append({"kind": kind, "product": tprod, "points": pts, "base": base, "last": last, "tf_last": ts["last"], "daily": kind == "DRAM" or daily,
                    "n_tf": sum(1 for p in pts if p[2] == "tf"), "n_mz": sum(1 for p in pts if p[2] == "mz"),
                    "chg": {"1W": back(7), "1M": back(30), "YTD": (last[1] / base[1] - 1) * 100}})
    if {s["kind"] for s in out} != {"DRAM", "NAND"}:
        raise SystemExit("[Memory Spot] TrendForce 자료 부족 — radar/trendforce_spot.py --backfill/run")
    combined.missing = missing
    return since, out


def combined_chart(since=None, path=None):
    import pymupdf
    from trendforce_spot import INK, INK2, MUTED, GRID, SURF
    since, S = combined(since)
    blue = (0.165, 0.471, 0.839)
    doc = pymupdf.open()
    page = doc.new_page(width=720, height=670)
    page.draw_rect(page.rect, color=None, fill=SURF)
    _txt(page, (36, 34), f"메모리 현물가격 — {since[:4]} YTD", 15, INK)
    _txt(page, (36, 52), "점 = TrendForce 공개 현물표 Session Average(관측) · 점 없는 구간 = 메리츠 채널 D램익스체인지 변화율로 직전 관측에서 이어 붙인 보강값", 8, INK2)
    colors = (blue, (0.902, 0.494, 0.133))   # 칸마다 두 품목을 한 그래프에(2026-11-23 마스터 지시)
    short = lambda p: p.replace("Wafer ", "").replace(" (2Gx8) 4800/5600", "").replace(" (1Gx8) 3200", "")   # noqa: E731
    for kind, box in (("DRAM", (80, 112, 690, 320)), ("NAND", (80, 412, 690, 620))):
        G = [s for s in S if s["kind"] == kind]
        if not G:
            continue
        x0, y0, x1, y1 = box
        ys = [v for s in G for _, v, _ in s["points"]]
        lo, hi = min(ys), max(ys)
        step = _nice((hi - lo) / 4 or hi * 0.05 or 1)
        lo, hi = math.floor(lo / step) * step, math.ceil(hi * 1.25 / step) * step
        d0, d1 = min(s["points"][0][0] for s in G), max(s["points"][-1][0] for s in G)
        span = max((d1 - d0).days, 1)
        X = lambda d: x0 + (x1 - x0) * (d - d0).days / span   # noqa: E731
        Y = lambda v: y1 - (y1 - y0) * (v - lo) / (hi - lo)    # noqa: E731
        wafer = any("Wafer" in s["product"] for s in G)
        unit = "일별 — 주간 고시값을 다음 고시까지 유지" if wafer else "일별"
        _txt(page, (x0, y0 - 34), f"{kind} 현물 — {' · '.join(short(s['product']) for s in G)} (달러, {unit})", 12, INK)
        v = lo
        while v <= hi + 1e-9:
            page.draw_line((x0, Y(v)), (x1, Y(v)), color=GRID, width=0.6)
            _txt(page, (x0 - 6, Y(v) + 3), f"${v:,.0f}", 8, MUTED, right=True)
            v += step
        m = date(d0.year, d0.month, 1)
        while m <= d1:
            if m >= d0:
                _txt(page, (X(m) - 8, y1 + 13), f"{m.month}월", 8, MUTED)
            m = date(m.year + (m.month == 12), m.month % 12 + 1, 1)
        page.draw_line((x0, y1), (x1, y1), color=MUTED, width=0.6)
        for i, (s, col) in enumerate(zip(G, colors)):
            page.draw_polyline([(X(d), Y(v)) for d, v, _ in s["points"]], color=col, width=1.6)
            tfp = [(X(d), Y(v)) for d, v, src in s["points"] if src == "tf"]
            if len(tfp) <= 140:
                for p in tfp:
                    page.draw_circle(p, 1.3, color=col, fill=col)
            ld, lv, lsrc = s["last"]
            page.draw_circle((X(ld), Y(lv)), 3.2, color=SURF if lsrc == "tf" else col, fill=col if lsrc == "tf" else SURF, width=1.2)
            c = " · ".join(f"{k} {x:+.1f}%" for k, x in s["chg"].items() if x is not None)
            ty = y0 - 16 + i * 14
            page.draw_line((x0 + 8, ty - 3), (x0 + 22, ty - 3), color=col, width=2.4)
            tl = s["tf_last"]
            tail = f" · TrendForce 마지막 {tl[0].strftime('%m/%d')}" if lsrc == "mz" else ""
            _txt(page, (x0 + 28, ty), f"{short(s['product'])}  {ld.strftime('%m/%d')} ${lv:,.2f}{' (보강)' if lsrc == 'mz' else ''}   {c}{tail}", 9, INK)
        gone = [short(p) for k, p in getattr(combined, "missing", []) if k == kind]
        if gone:
            _txt(page, (x0 + 8, y1 - 8), f"{' · '.join(gone)}: 공개 원천 없음(TrendForce 공개 웨이퍼표는 512·256·128Gb TLC만) — 자료가 생기면 이 그래프에 함께 그린다", 8, INK2)
    _txt(page, (36, 658), "자료: TrendForce(DRAMeXchange) 공개 현물가격표 + 공개 텔레그램 채널(merITz_tech)의 D램익스체인지 변화율. 보강값은 Chiip 계산. 개인 열람용.", 7.5, MUTED)
    OUT.mkdir(parents=True, exist_ok=True)
    path = Path(path or OUT / f"spot_combined_{S[0]['last'][0].strftime('%Y%m%d')}.png")
    page.get_pixmap(dpi=150).save(str(path))
    summ = {"since": since, "png": str(path), "series": [{"kind": s["kind"], "product": s["product"], "last": [s["last"][0].isoformat(), s["last"][1], s["last"][2]],
                                                          "tf_last": [s["tf_last"][0].isoformat(), s["tf_last"][1]], "chg": s["chg"], "n_tf": s["n_tf"], "n_mz": s["n_mz"]} for s in S],
            "missing": [p for _, p in getattr(combined, "missing", [])]}
    return path, summ


def caption(summ, read=""):
    L = ["[Chiip Memory Spot]", f"DRAM·NAND 현물가격 ({summ['since'][:4]} YTD · TrendForce 기본, 메리츠 변화율 보강)", ""]
    for s in summ["series"]:
        d, v, src = s["last"]
        c = " · ".join(f"{k} {x:+.1f}%" for k, x in s["chg"].items() if x is not None)
        tag = "보강" if src == "mz" else "TrendForce"
        L.append(f"■ {s['product'].replace('Wafer ', 'NAND 웨이퍼 ')}: ${v:,.2f} ({d[5:].replace('-', '/')}, {tag}) — {c}")
        if src == "mz":
            L.append(f"  · TrendForce 마지막 공개 {s['tf_last'][0][5:].replace('-', '/')} ${s['tf_last'][1]:,.2f}에서 메리츠 변화율로 이어 붙임")
    for p in summ.get("missing") or []:
        L.append(f"■ {p.replace('Wafer ', 'NAND 웨이퍼 ')}: 공개 원천 없음(미확인)")
    if read:
        L += ["", "■ 풀이", read.strip()]
    try:   # 한국산 DRAM·플래시 대미 통관액 참조(USITC DataWeb 월간, 2026-11-21 마스터 지시 "현물가 보고에도 DataWeb을 참조할 수 있으면 참조하라")
        import trade_daily
        ref = trade_daily.memory_line()
        if ref:
            L += ["", ref]
    except Exception:
        pass
    L += ["", "자료: TrendForce 공개 현물표(개인 열람용, 재배포 금지) + 공개 텔레그램 채널 D램익스체인지 변화율"]
    return "\n".join(L)


def send(read=""):
    import notify
    update()
    png, summ = combined_chart()
    cap = caption(summ, read)
    # 그림과 풀이는 한 통(사진 설명)으로만 — 따로 글을 보내지 않는다(마스터 지시 2026-11-20 "풀이 피드를 따로 내지 말고 그래프 제공하는 피드에 같이 설명을 넣어라")
    base = caption(summ)
    room = 1000 - len(base) - 2
    cap = caption(summ, read if len(read.strip()) <= room else read.strip()[:max(room - 1, 0)].rsplit(' ', 1)[0] + '…') if read and room > 20 else base
    ok = notify.send_photo(png, cap[:1000], "P1")
    if ok:
        st = common.load_state(STATE, {})
        st["sent"] = common.now_kst().date().isoformat()
        common.save_state(STATE, st)
    return ok


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if argv[:1] == ["--backfill"]:
        print(f"[Memory Spot] 스팟 줄 {backfill(argv[1] if len(argv) > 1 else '2026-01-01')}건")
        return 0
    if argv[:1] == ["--update"]:
        print(f"[Memory Spot] 새 줄 {update()}건")
        return 0
    if argv[:1] == ["--chart"]:
        png, summ = chart(argv[1] if len(argv) > 1 else None)
        print(json.dumps(summ, ensure_ascii=False, indent=1))
        return 0
    if argv[:1] == ["--send"]:
        d = json.loads(Path(argv[1]).read_text(encoding="utf-8")) if len(argv) > 1 else {}
        if re.search(r"(사라[.!\s]|사라$|팔아라|매수하라|매도하라|비중 확대|비중 축소)", d.get("read", "")):
            raise SystemExit("Memory Spot 관문 — 매매 지시 표현")
        print("[Memory Spot] 발송" if send(d.get("read", "")) else "[Memory Spot] 발송 실패")
        return 0
    print(json.dumps(status(), ensure_ascii=False, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
