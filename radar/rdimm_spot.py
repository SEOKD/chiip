"""Chiip RDIMM Spot — DDR5 RDIMM 32GB·64GB 현물가와 64GB 계약가 추이 (마스터 지시 2026-11-23 "DDR5 RDIMM 32GB & 64GB Spot Prices와
Contract Prices Trend와 동일한 데이터를 가져오는 파이프라인을 설계하고 이를 반영한 그래프를 제시하라").

원천은 하나다 — 공개 텔레그램 채널 Badonions(config/tg_channels.yaml 수집 대상)의 주간 'RDIMM Spot Price' 글.
  ① 글자: 'DDR5 RDIMM 32GB: $1,645 → WoW -11.80%' 두 줄(정확한 주간 값). WoW로 한 주 전 값도 되짚는다(파생).
  ② 그림: 2024-10부터의 32GB·64GB 현물 선, 64GB 계약가 점선, 현물−계약 막대. 과거 이력과 계약가는 여기에만 있다 → 그림을 판독한다(digitize).
     판독 = 그림의 그래프 영역을 찾고, 파란 선(32GB)·청록 선(64GB)·아래쪽 청록 점선(계약가)의 화소 위치를 값으로 바꾼다.
     세로 눈금은 글자 값(이번 주·지난주 32GB·64GB)에 맞춰 정한다. 오차는 대략 ±$30(800px 그림 한 화소 ≈ $14) — 요약에 잔차로 남긴다.
  같은 수치를 내주는 다른 원천은 없다: Easyconomics·TrendForce 수집분은 칩 현물(DDR5 16Gb)뿐이고 모듈(RDIMM) 값이 없다.
  badonion.co.kr 사이트는 robots.txt가 ClaudeBot·anthropic-ai를 막아 직접 읽지 않는다(텔레그램 공개 미리보기만).
  사이트가 안내하는 '나쁜양파 MCP'를 마스터가 연결하면 판독 대신 원값을 받을 수 있다(docs/TODO_MASTER.md).
저장: radar/inbox/rdimm_spot/(git 제외 — 남의 유료 성격 자료의 파생 수치라 커밋하지 않는다). 그래프·피드는 마스터 개인 봇으로만.
사용: py radar/rdimm_spot.py --backfill [2026-01-01]   # 채널 미리보기를 거슬러 읽어 지난 RDIMM 글(숫자·그림)을 채운다
      py radar/rdimm_spot.py --update                  # 수집기(radar/inbox/tg_channels/Badonions.jsonl)의 새 글 반영
      py radar/rdimm_spot.py --digitize [그림 경로]      # 최신 글 그림(또는 지정 그림)을 판독해 이력을 만든다
      py radar/rdimm_spot.py --chart                   # 그래프 PNG + 요약
      py radar/rdimm_spot.py --status                  # Pulse 관문 — 새 RDIMM 글이 오면 due
      py radar/rdimm_spot.py --send [풀이]              # 그래프 1장 + 풀이를 개인 봇으로
"""
import csv
import json
import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

OUT = common.ROOT / "radar" / "inbox" / "rdimm_spot"
POSTS = OUT / "posts.csv"
SERIES = OUT / "series.json"
STATE = "rdimm_spot"
CHANNEL = "Badonions"
START = date(2024, 10, 7)          # 그림 부제의 시작일('2024-10-07 to …') — 바뀌면 config로 옮긴다
P_FIELDS = ["post_id", "posted_at", "obs_date", "gb32", "gb64", "wow32", "wow64", "image", "image_file", "url"]
HEAD_RE = re.compile(r"RDIMM Spot Price\s*\n\s*(\d{2})년\s*(\d{1,2})월\s*(\d{1,2})일")
VAL_RE = re.compile(r"RDIMM\s*(32|64)GB:\s*\$([\d,]+(?:\.\d+)?)(?:\s*→\s*WoW\s*([+\-−]?[\d.]+)%)?")
PLOT_BG, TOL = (15, 27, 49), 7


# ---------- ① 글자 값 ----------
def parse_post(p):
    """텔레그램 글 → 관측 한 줄(없으면 None). 숫자 없이 그림만 있는 옛 글도 날짜·그림은 남긴다"""
    m = HEAD_RE.search(p.get("text") or "")
    if not m:
        return None
    row = {"post_id": p["id"], "posted_at": p.get("at", ""), "obs_date": date(2000 + int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat(),
           "gb32": "", "gb64": "", "wow32": "", "wow64": "", "image": p.get("image") or "", "image_file": (p.get("image_files") or [""])[0], "url": p.get("url", "")}
    for size, usd, wow in VAL_RE.findall(p["text"]):
        row[f"gb{size}"] = float(usd.replace(",", ""))
        row[f"wow{size}"] = float(wow.replace("−", "-")) if wow else ""
    return row


def read_posts():
    if not POSTS.exists():
        return []
    with POSTS.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_posts(rows):
    best = {}
    for r in rows:   # 같은 글은 한 줄 — 숫자·그림 파일이 있는 쪽을 남긴다
        k = str(r["post_id"])
        old = best.get(k)
        if not old or (not old.get("gb64") and r.get("gb64")) or (not old.get("image_file") and r.get("image_file")):
            best[k] = {**(old or {}), **{a: b for a, b in r.items() if b not in ("", None)}} if old else r
    OUT.mkdir(parents=True, exist_ok=True)
    with POSTS.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, P_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(best.values(), key=lambda r: r["obs_date"]))
    return len(best)


def update():
    from pollers import tg_channels as T
    got = [r for r in (parse_post(p) for p in T.load(CHANNEL).values()) if r]
    return write_posts(read_posts() + got)


def backfill(since="2026-01-01", pause=1.2, max_pages=600):
    """공개 미리보기 t.me/s/Badonions?before=<번호>를 거슬러 읽는다(로그인 없음). 그림은 그 자리에서 내려받는다(주소가 며칠 뒤 만료)"""
    from pollers import tg_channels as T
    got, url, pages = [], f"https://t.me/s/{CHANNEL}", 0
    while pages < max_pages:
        page = T.parse(T.fetch(url))
        pages += 1
        if not page:
            break
        for p in page:
            r = parse_post(p)
            if r:
                if r["image"] and not r["image_file"]:
                    try:
                        f = OUT / "images" / f"{CHANNEL}_{p['id']}.jpg"
                        f.parent.mkdir(parents=True, exist_ok=True)
                        f.write_bytes(common.http_get(r["image"], timeout=25))
                        r["image_file"] = f.relative_to(common.ROOT).as_posix()
                    except Exception:
                        pass
                got.append(r)
        low = min(p["id"] for p in page)
        if min(p["at"] for p in page)[:10] < since or low <= 1:
            break
        url = f"https://t.me/s/{CHANNEL}?before={low}"
        time.sleep(pause)
    n = write_posts(read_posts() + got)
    print(f"[RDIMM Spot] {pages}쪽 · RDIMM 글 {len(got)}건(누적 {n})", flush=True)
    return len(got)


def exact_points(posts=None):
    """글자 값 → {날짜: (32GB, 64GB, 근거)}. WoW로 한 주 전도 되짚는다(그 주 글에 숫자가 없을 때만)"""
    out = {}
    for r in posts if posts is not None else read_posts():
        if not r.get("gb32") or not r.get("gb64"):
            continue
        d = date.fromisoformat(r["obs_date"])
        out[d] = (float(r["gb32"]), float(r["gb64"]), "글자")
        if r.get("wow32") not in ("", None) and r.get("wow64") not in ("", None):
            prev = d - timedelta(days=7)
            out.setdefault(prev, (round(float(r["gb32"]) / (1 + float(r["wow32"]) / 100)), round(float(r["gb64"]) / (1 + float(r["wow64"]) / 100)), "WoW 역산"))
    return dict(sorted(out.items()))


# ---------- ② 그림 판독 ----------
def _is_cyan(c):
    return c[1] > 150 and c[2] > 150 and c[0] < 135 and abs(c[1] - c[2]) < 45


def _is_blue(c):
    return c[2] > 150 and c[1] < 165 and c[0] < 135 and c[2] - c[1] > 45


def _clusters(ys, gap):
    """세로 화소 위치들을 이어진 묶음으로 → [(가운데, 높이)]"""
    out, run = [], []
    for y in ys:
        if run and y - run[-1] > gap:
            out.append((sum(run) / len(run), run[-1] - run[0] + 1))
            run = []
        run.append(y)
    if run:
        out.append((sum(run) / len(run), run[-1] - run[0] + 1))
    return out


def trace(path):
    """그림 → 화소 좌표의 선들. {"rect": (x0, y0, x1, y1), "blue": {x: y}, "cyan": {x: y}, "contract": {x: y}, "end_x": x}"""
    import pymupdf
    pix = pymupdf.Pixmap(str(path))
    if pix.n > 3:
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
    w, h, n, s = pix.width, pix.height, pix.n, pix.samples
    px = lambda x, y: (s[(y * w + x) * n], s[(y * w + x) * n + 1], s[(y * w + x) * n + 2])   # noqa: E731
    bg = lambda c: all(abs(a - b) <= TOL for a, b in zip(c, PLOT_BG))                          # noqa: E731
    rows = [y for y in range(h) if sum(bg(px(x, y)) for x in range(0, w, 4)) > w / 4 * 0.3]
    cols = [x for x in range(w) if sum(bg(px(x, y)) for y in range(0, h, 4)) > h / 4 * 0.2]
    if not rows or not cols:
        raise SystemExit("[RDIMM Spot] 그래프 영역을 찾지 못했다 — 그림 양식이 바뀌었는지 확인")
    x0, x1, y0, y1 = cols[0], cols[-1], rows[0], rows[-1]
    gap = max(3, round(h / 100))
    blue, cyan, contract, bh = {}, {}, {}, {}
    for x in range(x0, x1 + 1):
        col = [px(x, y) for y in range(y0, y1 + 1)]
        b = _clusters([y0 + i for i, c in enumerate(col) if _is_blue(c)], gap)
        c = _clusters([y0 + i for i, c in enumerate(col) if _is_cyan(c)], gap)
        if b:
            top = max(b, key=lambda t: t[1])
            blue[x], bh[x] = top[0], top[1]
        if c:
            cyan[x] = c[0][0]                       # 맨 위 묶음 = 64GB 현물
            if len(c) > 1 and c[-1][0] - c[0][0] > 3 * gap:
                contract[x] = c[-1][0]              # 그 아래 묶음 = 64GB 계약가(점선)
    if len(blue) < 50 or len(cyan) < 50:
        raise SystemExit("[RDIMM Spot] 선을 찾지 못했다 — 색·양식이 바뀌었는지 확인")
    last = max(blue)
    tail = [bh[x] for x in range(last - 3 * gap, last + 1) if x in bh]
    end_x = last - max(tail) / 2                   # 끝점 표식(동그라미) 가운데
    return {"rect": (x0, y0, x1, y1), "blue": blue, "cyan": cyan, "contract": contract, "start_x": min(blue), "end_x": end_x, "size": (w, h)}


def _at(line, x):
    """선의 x 위치 값(화소 y) — 빈 열은 이웃으로 잇는다"""
    xs = sorted(line)
    if x <= xs[0]:
        return line[xs[0]]
    if x >= xs[-1]:
        return line[xs[-1]]
    lo = max(k for k in xs if k <= x)
    hi = min(k for k in xs if k >= x)
    return line[lo] if hi == lo else line[lo] + (line[hi] - line[lo]) * (x - lo) / (hi - lo)


def digitize(path, end, anchors, start=START):
    """그림 → {"spot": [[날짜, 32GB, 64GB]…주간], "contract": [[월말, 값]…], "fit": {…}}.
    anchors = {날짜: (32GB, 64GB)} 글자 값 — 세로 배율을 여기에 맞춘다(끝점 표식은 모양 때문에 덜 믿는다)"""
    t = trace(path)
    y_zero = t["rect"][3]
    span = (end - start).days
    use = {d: v for d, v in anchors.items() if start <= d <= end}
    if not use:
        raise SystemExit("[RDIMM Spot] 배율을 맞출 글자 값이 없다 — --update로 주간 글을 먼저 넣는다")

    def fit(end_x):
        xo = lambda d: t["start_x"] + (end_x - t["start_x"]) * (d - start).days / span   # noqa: E731
        obs = []
        for d, (v32, v64) in use.items():
            obs += [(y_zero - _at(t["blue"], xo(d)), v32), (y_zero - _at(t["cyan"], xo(d)), v64)]
        k = sum(p * v for p, v in obs) / sum(p * p for p, v in obs)   # 값 = k × (0선에서의 화소 높이)
        res = [k * p - v for p, v in obs]
        return sum(r * r for r in res), k, res, xo

    # 끝점 표식(동그라미·세모) 때문에 마지막 날짜의 가로 위치가 한두 화소 어긋난다 — 글자 값과 가장 잘 맞는 위치를 ±1% 폭 안에서 고른다
    w = t["size"][0]
    _, k, resid, x_of = min((fit(t["end_x"] + dx / 2) for dx in range(-round(w / 50), round(w / 50) + 1)), key=lambda r: r[0])
    obs = resid
    val = lambda y: round(k * (y_zero - y))                                      # noqa: E731
    spot, d = [], start
    while d <= end:
        x = x_of(d)
        spot.append([d.isoformat(), val(_at(t["blue"], x)), val(_at(t["cyan"], x))])
        d += timedelta(days=7)
    contract = []
    if t["contract"]:
        cx0, cx1 = min(t["contract"]), max(t["contract"])
        d_of = lambda x: start + timedelta(days=round((x - t["start_x"]) / (t["end_x"] - t["start_x"]) * span))   # noqa: E731
        m = d_of(cx0).replace(day=1)
        while True:
            nxt = (m.replace(day=28) + timedelta(days=4)).replace(day=1)
            eom = nxt - timedelta(days=1)
            if x_of(eom) > cx1 + 2:
                break
            if x_of(eom) >= cx0 - t["size"][0] / 200:   # 점선 첫 점이 한두 화소 어긋나도 그 달을 놓치지 않는다(800px 그림에서 2025-12가 빠졌다)
                contract.append([eom.isoformat(), val(_at(t["contract"], x_of(eom)))])
            m = nxt
    return {"spot": spot, "contract": contract, "image": str(path), "end": end.isoformat(),
            "fit": {"usd_per_px": round(k, 2), "anchors": len(obs), "max_abs_resid": round(max(abs(r) for r in resid)), "resid": [round(r) for r in resid]}}


def latest_image(posts):
    for r in sorted(posts, key=lambda r: r["obs_date"], reverse=True):
        f = common.ROOT / r["image_file"] if r.get("image_file") else None
        if f and f.exists():
            return f, date.fromisoformat(r["obs_date"])
    return None, None


def run_digitize(path=None, end=None):
    posts = read_posts()
    ex = exact_points(posts)
    img, d = (Path(path), date.fromisoformat(end) if end else max(ex)) if path else latest_image(posts)
    if not img:
        raise SystemExit("[RDIMM Spot] 판독할 그림이 없다 — --update/--backfill 먼저")
    out = digitize(img, d, {k: v[:2] for k, v in ex.items()})
    OUT.mkdir(parents=True, exist_ok=True)
    SERIES.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def merged():
    """판독 이력 + 글자 값(글자 값이 그 주를 덮는다) → (현물 [[날짜, 32, 64, 근거]], 계약 [[월말, 값]], 판독 요약)"""
    dg = json.loads(SERIES.read_text(encoding="utf-8")) if SERIES.exists() else {"spot": [], "contract": [], "fit": {}}
    pts = {date.fromisoformat(d): (a, b, "그림 판독") for d, a, b in dg["spot"]}
    pts.update(exact_points())
    spot = [[d, v[0], v[1], v[2]] for d, v in sorted(pts.items())]
    return spot, [[date.fromisoformat(d), v] for d, v in dg["contract"]], dg.get("fit") or {}


# ---------- 그래프 ----------
def chart(path=None):
    import pymupdf
    from memory_spot import _txt
    spot, contract, fit = merged()
    if len(spot) < 4:
        raise SystemExit("[RDIMM Spot] 자료 부족 — --update, --digitize 먼저")
    BG, PL, FG, MUT = (0.043, 0.075, 0.125), (0.059, 0.106, 0.192), (0.93, 0.94, 0.96), (0.58, 0.62, 0.70)
    BLUE, CYAN, BAR = (0.31, 0.51, 0.87), (0.27, 0.80, 0.78), (0.24, 0.27, 0.33)
    W, H = 960, 480
    doc = pymupdf.open()
    page = doc.new_page(width=W, height=H)
    page.draw_rect(page.rect, color=None, fill=BG)
    x0, y0, x1, y1 = 78, 104, W - 82, H - 62
    page.draw_rect((x0, y0, x1, y1), color=None, fill=PL)
    d0, d1 = spot[0][0], spot[-1][0]
    span = (d1 - d0).days * 1.04
    X = lambda d: x0 + (x1 - x0) * (d - d0).days / span                      # noqa: E731
    top = max(max(a, b) for _, a, b, _ in spot)
    ymax = (int(top / 800) + 1) * 800 if top % 800 > 480 else int(top / 800) * 800 + 480
    Y = lambda v: y1 - (y1 - y0) * v / ymax                                   # noqa: E731
    at64 = lambda d: min(spot, key=lambda r: abs((r[0] - d).days))[2]         # noqa: E731
    spread = [(d, at64(d) - v) for d, v in contract]
    smax = max([s for _, s in spread] + [1]) * 1.12
    smax = (int(smax / 400) + 1) * 400
    YS = lambda v: y1 - (y1 - y0) * v / smax                                  # noqa: E731
    bw = (x1 - x0) * 22 / span
    for d, sp in spread:                                                      # 막대 = 64GB 현물 − 계약(월말)
        cx = X(d)   # 원본처럼 월말 날짜에 막대를 둔다
        page.draw_rect((cx - bw / 2, YS(sp), cx + bw / 2, y1), color=None, fill=BAR)
    for v in range(0, int(ymax) + 1, 800):
        _txt(page, (x0 - 8, Y(v) + 3), f"{v:,}", 8.5, MUT, right=True)
        page.draw_line((x0, Y(v)), (x1, Y(v)), color=(0.10, 0.16, 0.26), width=0.5)
    for v in range(0, int(smax) + 1, 400):
        _txt(page, (x1 + 8, YS(v) + 3), f"{v:,}", 8.5, MUT)
    m = d0.replace(day=1)
    while m <= d1:
        if m >= d0 and m.month % 2 == 0:
            _txt(page, (X(m) - 11, y1 + 16), f"{m.year % 100}.{m.month:02d}", 8.5, MUT)
        m = (m.replace(day=28) + timedelta(days=4)).replace(day=1)
    for idx, col in ((2, CYAN), (1, BLUE)):
        pts = [pymupdf.Point(X(r[0]), Y(r[idx])) for r in spot]
        page.draw_polyline(pts, color=col, width=2.0, lineJoin=1, lineCap=1)
        page.draw_circle(pts[-1], 3.2, color=col, fill=col)
    if contract:
        page.draw_polyline([pymupdf.Point(X(d), Y(v)) for d, v in contract], color=CYAN, width=1.8, dashes="[5 4] 0")
    last = spot[-1]
    _txt(page, (28, 34), "DDR5 RDIMM 현물·계약가와 64GB 현물-계약 차이", 16, FG)
    sub = f"{d0.isoformat()} ~ {d1.isoformat()}" + (f" | 계약가: {contract[-1][0].strftime('%Y-%m')}까지" if contract else "")
    _txt(page, (28, 52), sub, 9, MUT)
    head = f"32GB ${last[1]:,.0f} | 64GB ${last[2]:,.0f}" + (f" | 차이 ${spread[-1][1]:,.0f}({contract[-1][0].strftime('%m/%d')})" if spread else "")
    _txt(page, (W - 28, 52), head, 9.5, CYAN, right=True)
    lx = 150
    for name, col, dash in (("32GB 현물", BLUE, None), ("64GB 현물", CYAN, None), ("64GB 계약가", CYAN, "[5 4] 0")):
        page.draw_line((lx, 78), (lx + 40, 78), color=col, width=2.0, dashes=dash)
        _txt(page, (lx + 48, 82), name, 9.5, FG)
        lx += 150
    page.draw_rect((lx, 71, lx + 40, 85), color=None, fill=BAR)
    _txt(page, (lx + 48, 82), "64GB 현물 - 계약", 9.5, FG)
    page.insert_text((22, (y0 + y1) / 2 + 60), "Price (USD/module)", fontsize=9, color=MUT, rotate=90)
    page.insert_text((W - 16, (y0 + y1) / 2 + 80), "64GB Spot - Contract (USD/module)", fontsize=9, color=MUT, rotate=90)
    n_exact = sum(1 for r in spot if r[3] != "그림 판독")
    note = (f"자료: 공개 텔레그램 채널 Badonions 주간 'RDIMM Spot Price' — 글자 값 {n_exact}주(정확), 그 밖 이력·계약가는 그림 판독"
            + (f"(글자 값 대비 최대 ±${fit['max_abs_resid']})" if fit.get("max_abs_resid") is not None else "") + " · Chiip 재구성, 원자료 아님")
    _txt(page, (28, H - 18), note, 7.8, MUT)
    OUT.mkdir(parents=True, exist_ok=True)
    path = Path(path or OUT / f"rdimm_{d1.strftime('%Y%m%d')}.png")
    page.get_pixmap(dpi=160).save(str(path))
    prev = spot[-2]
    summ = {"png": str(path), "as_of": d1.isoformat(), "gb32": last[1], "gb64": last[2],
            "wow32": round((last[1] / prev[1] - 1) * 100, 2), "wow64": round((last[2] / prev[2] - 1) * 100, 2),
            "peak64": max(((r[2], r[0].isoformat()) for r in spot), key=lambda t: t[0]),
            "contract_last": [contract[-1][0].isoformat(), contract[-1][1]] if contract else None,
            "spread_last": spread[-1][1] if spread else None, "weeks": len(spot), "exact_weeks": n_exact, "fit": fit}
    (OUT / "summary.json").write_text(json.dumps(summ, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return path, summ


def caption(summ, read=""):
    pk = summ["peak64"]
    lines = [f"[Chiip RDIMM Spot] DDR5 RDIMM 현물 — {summ['as_of']}",
             f"32GB ${summ['gb32']:,.0f}(주간 {summ['wow32']:+.1f}%) · 64GB ${summ['gb64']:,.0f}(주간 {summ['wow64']:+.1f}%)",
             f"64GB 고점 ${pk[0]:,.0f}({pk[1]}) 대비 {(summ['gb64'] / pk[0] - 1) * 100:+.1f}%"
             + (f" · 계약가 ${summ['contract_last'][1]:,.0f}({summ['contract_last'][0][:7]}, 그림 판독)" if summ.get("contract_last") else "")]
    if read.strip():
        lines += ["", read.strip()]
    return "\n".join(lines + ["", "자료: 공개 텔레그램 채널 주간 값 + 그림 판독(Chiip 재구성)"])


def status():
    """Pulse 관문 — 아직 보내지 않은 새 RDIMM 글(숫자 있음)이 있으면 due"""
    st = common.load_state(STATE, {})
    try:
        update()
        ex = exact_points()
        newest = max((d for d, v in ex.items() if v[2] == "글자"), default=None)
        if not newest or st.get("sent") == newest.isoformat():
            return {"due": False}
        run_digitize()
        png, summ = chart()
    except (Exception, SystemExit) as e:
        return {"due": False, "error": f"{type(e).__name__}: {str(e)[:120]}"}
    return {"due": True, "png": str(png), "summary": summ}


def send(read=""):
    import notify
    update()
    run_digitize()
    png, summ = chart()
    ok = notify.send_photo(png, caption(summ, read)[:1000], "P1")
    if ok:
        st = common.load_state(STATE, {})
        st["sent"] = summ["as_of"]
        common.save_state(STATE, st)
    return ok


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if argv[:1] == ["--backfill"]:
        backfill(argv[1] if len(argv) > 1 else "2026-01-01")
    elif argv[:1] == ["--update"]:
        print(f"[RDIMM Spot] RDIMM 글 {update()}건")
    elif argv[:1] == ["--digitize"]:
        out = run_digitize(*argv[1:3])
        print(f"[RDIMM Spot] 판독 {len(out['spot'])}주 · 계약가 {len(out['contract'])}개월 · {out['fit']}")
    elif argv[:1] == ["--chart"]:
        png, summ = chart()
        print(png)
        print(json.dumps(summ, ensure_ascii=False, default=str))
    elif argv[:1] == ["--status"]:
        print(json.dumps(status(), ensure_ascii=False, default=str))
    elif argv[:1] == ["--send"]:
        print("[RDIMM Spot] 발송" if send(" ".join(argv[1:])) else "[RDIMM Spot] 발송 실패")
    else:
        print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
