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
    """Pulse 관문 — 평일 10~11시 KST, 하루 1회"""
    now = now or common.now_kst()
    st = common.load_state(STATE, {})
    today = now.date().isoformat()
    if now.weekday() >= 5 or not (WINDOW[0] <= now.hour < WINDOW[1]) or st.get("sent") == today:
        return {"due": False}
    try:
        update()
        png, summ = chart()
    except (Exception, SystemExit) as e:
        return {"due": False, "error": f"{type(e).__name__}: {str(e)[:120]}"}
    out = {"due": True, "png": str(png), "summary": summ}
    try:   # TrendForce 공개 현물가 그림(따로 보냄, 2026-11-19 마스터 지시) — 실패해도 메리츠 그림은 나간다
        tpng, tsumm, _ = trendforce()
        out["trendforce"] = {"png": str(tpng), "series": tsumm["series"]}
    except (Exception, SystemExit) as e:
        out["trendforce"] = {"error": f"{type(e).__name__}: {str(e)[:120]}"}
    return out


def trendforce():
    """→ (png, 요약, 설명) — radar/trendforce_spot.py 그림 + 메리츠 기반 추정과의 같은 날 대조 한 줄.
    메리츠 글(D+1일 아침)은 D일 세션 값이라 TrendForce D일 값은 D 다음 4일 안의 첫 메리츠 점과 맞춘다"""
    import trendforce_spot as T
    png, ts = T.chart()
    comp = []
    try:
        cfg = config()
        s = series(read_rows(), cfg.get("dram", "DDR5 16Gb"), ts["since"], cfg.get("anchors"))
        d, tv = ts["series"][0]["last"]
        d = date.fromisoformat(d)
        nxt = [(x, v) for x, v in s["points"] if d < x <= d + timedelta(days=4)] if s and s["unit"] == "USD" else []
        if nxt and tv:
            comp.append(f"· 같은 세션 메리츠 변화율 기반 Chiip 추정 DDR5 16Gb ${nxt[0][1]:,.2f} — TrendForce 대비 {(nxt[0][1] / tv - 1) * 100:+.1f}%")
    except Exception:
        pass
    return png, ts, T.caption(ts, comp)


def caption(summ, read=""):
    L = ["[Chiip Memory Spot]", f"DRAM·NAND 현물가격 추정 ({summ['since'][:4]} YTD)", ""]
    for s in summ["series"]:
        v = s["last"][1]
        lab = f"${v:,.2f}" if s["unit"] == "USD" else f"지수 {v:,.1f}"
        c = " · ".join(f"{k} {x:+.1f}%" for k, x in s["chg"].items() if x is not None)
        L.append(f"■ {s['product']}: {lab} ({s['last'][0][5:].replace('-', '/')}) — {c}")
    if read:
        L += ["", "■ 풀이", read.strip()]
    L += ["", "변화율 출처는 공개 텔레그램 채널(D램익스체인지 인용), 가격은 Chiip 추정"]
    return "\n".join(L)


def send(read=""):
    import notify
    update()
    png, summ = chart()
    cap = caption(summ, read)
    ok = notify.send_photo(png, cap[:1000], "P1") if len(cap) <= 1000 else (notify.send_photo(png, caption(summ)[:1000], "P1") and notify.send(cap, "P1"))
    if ok:
        st = common.load_state(STATE, {})
        st["sent"] = common.now_kst().date().isoformat()
        common.save_state(STATE, st)
        try:   # TrendForce 그림은 따로 한 장(개인 봇 한정 — 약관 서면 동의 조항, 마스터 결정 2026-11-19)
            tpng, _, tcap = trendforce()
            notify.send_photo(tpng, tcap[:1000], "P1")
        except (Exception, SystemExit) as e:
            print(f"[Memory Spot] TrendForce 그림 생략 {type(e).__name__}")
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
