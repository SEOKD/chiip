"""Chiip Spot Report — DRAM·NAND 현물가 두 지표를 한 장에, 갱신될 때마다 보고
(마스터 지시 2026-11-23 "Badonions는 레퍼런스일 뿐이지 이를 소스로 쓰지 마라. 32GB 현물 가격만 TrendForce에서 수집이 된다면 이 수치가
 업데이트될 때마다 보고 … merITz_tech에서 우회적으로 확인하는 D램익스체인지 Spot 가격 추이도 DDR5 RDIMM 32GB 아래에 넣어라. 출처는
 DRAMeXchange … 두 DRAM Spot Price 지표가 업데이트될 때마다 보고 … NAND도 같은 경로 … 시계열은 지난 12개월")

양식(흰 바탕 두 칸, 12개월):
  DRAM  위 = DDR5 RDIMM 32GB 모듈 현물(TrendForce 공개 'Module Spot Price' 표의 세션 평균, 주 1회 — radar/rdimm_spot.py tf_update)
        아래 = DDR5 16Gb 칩 현물(DRAMeXchange — 공개 텔레그램 채널 merITz_tech의 일별 변화율을 이어 붙인 값, radar/memory_spot.py)
  NAND  위 = 512Gb TLC 웨이퍼 현물(TrendForce 공개 'Wafer Spot' 표 — radar/trendforce_spot.py)
        아래 = MLC 64Gb 현물(DRAMeXchange — 같은 채널, radar/memory_spot.py)
Badonions 채널 값·그림은 쓰지 않는다(레퍼런스). 보고 시점: 두 지표 중 하나라도 새 값이 오면 그 종류(DRAM·NAND) 그림 1통.
  TrendForce는 주 1회(모듈)·수시(웨이퍼), DRAMeXchange 쪽은 평일 아침 채널 글 — 그래서 평일 하루 1통씩이 보통이다.
저장: radar/inbox/spot_report/(git 제외), 개인 봇으로만(TrendForce 약관 — 기존 승인 조건).
사용: py radar/spot_report.py --chart dram|nand
      py radar/spot_report.py --status
      py radar/spot_report.py --send dram|nand [풀이]
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

OUT = common.ROOT / "radar" / "inbox" / "spot_report"
STATE = "spot_report"
SPEC = {
    "dram": {"title": "DRAM 현물가 추이", "tf_name": "DDR5 RDIMM 32GB 모듈 현물 (달러/모듈)", "dx_product": "DDR5 16Gb", "dx_name": "DDR5 16Gb 칩 현물"},
    "nand": {"title": "NAND 현물가 추이", "tf_name": "512Gb TLC 웨이퍼 현물 (달러)", "tf_item": "Wafer 512Gb TLC", "dx_product": "MLC 64Gb", "dx_name": "MLC 64Gb 칩 현물"},
}
INK, MUT, GRID = (0.05, 0.05, 0.05), (0.4, 0.4, 0.4), (0.88, 0.89, 0.91)
C_TF, C_DX = (0.13, 0.36, 0.75), (0.80, 0.33, 0.10)


def since_day(today=None):
    return (today or common.now_kst().date()) - timedelta(days=365)


def tf_points(kind, since):
    if kind == "dram":
        import rdimm_spot
        pts = [(date.fromisoformat(r["date"]), float(r["avg"])) for r in rdimm_spot.tf_read()]
    else:
        import trendforce_spot
        pts = [(date.fromisoformat(r["date"]), float(r["avg"])) for r in trendforce_spot.read_rows() if r["item"] == SPEC[kind]["tf_item"] and r["avg"] not in ("", None)]
    return sorted(p for p in set(pts) if p[0] >= since)


def dx_series(kind, since):
    import memory_spot
    s = memory_spot.series(memory_spot.read_rows(), SPEC[kind]["dx_product"], since.isoformat(), memory_spot.config().get("anchors"))
    return ([(d, v) for d, v in s["points"]], s["unit"]) if s else ([], "")


def _chg(pts, days):
    if len(pts) < 2:
        return None
    ref = pts[-1][0] - timedelta(days=days)
    old = [p for p in pts if p[0] <= ref]
    return (pts[-1][1] / old[-1][1] - 1) * 100 if old and (ref - old[-1][0]).days <= 10 else None


def _nice(v):
    import math
    e = 10 ** math.floor(math.log10(v))
    return next(m * e for m in (1, 2, 2.5, 5, 10) if m * e >= v)


def _panel(page, box, pts, color, title, source, d0, d1, money=True):
    import pymupdf
    from memory_spot import _txt
    x0, y0, x1, y1 = box
    _txt(page, (x0, y0 - 10), title, 10, INK)
    _txt(page, (x1, y0 - 10), f"자료: {source}", 8, MUT, right=True)
    if len(pts) < 2:
        _txt(page, (x0 + 10, (y0 + y1) / 2), "자료 부족 — 수집 중", 9, MUT)
        return
    hi = max(v for _, v in pts) * 1.12
    step = _nice(hi / 4)
    top = step * (int(hi / step) + 1)
    span = max((d1 - d0).days, 1)
    X = lambda d: x0 + (x1 - x0) * (d - d0).days / span      # noqa: E731
    Y = lambda v: y1 - (y1 - y0) * v / top                    # noqa: E731
    v = 0.0
    while v <= top + 1e-9:
        page.draw_line((x0, Y(v)), (x1, Y(v)), color=GRID, width=0.5)
        _txt(page, (x0 - 6, Y(v) + 3), f"{v:,.0f}" if step >= 1 else f"{v:,.1f}", 7.5, MUT, right=True)
        v += step
    m = d0.replace(day=1)
    while m <= d1:
        if m >= d0 and m.month % 2 == 1:
            page.draw_line((X(m), y1), (X(m), y1 + 3), color=MUT, width=0.5)
            _txt(page, (X(m) - 11, y1 + 13), f"{m.year % 100}.{m.month:02d}", 7.5, MUT)
        m = (m.replace(day=28) + timedelta(days=4)).replace(day=1)
    page.draw_line((x0, y1), (x1, y1), color=MUT, width=0.7)
    line = [pymupdf.Point(X(d), Y(val)) for d, val in pts]
    seg = [line[0]]   # 관측이 3주 넘게 빈 구간은 잇지 않는다 — 없는 값을 직선으로 그리지 않는다
    for i in range(1, len(pts)):
        if (pts[i][0] - pts[i - 1][0]).days > 21:
            if len(seg) > 1:
                page.draw_polyline(seg, color=color, width=1.6, lineJoin=1, lineCap=1)
            seg = []
        seg.append(line[i])
    if len(seg) > 1:
        page.draw_polyline(seg, color=color, width=1.6, lineJoin=1, lineCap=1)
    if len(pts) <= 60:   # 주간 관측은 점도 찍는다 — 관측이 드문 구간이 보이게
        for p in line:
            page.draw_circle(p, 1.5, color=color, fill=color)
    page.draw_circle(line[-1], 2.6, color=color, fill=color)
    last = pts[-1]
    val = f"${last[1]:,.0f}" if money and last[1] >= 100 else f"${last[1]:,.2f}" if money else f"{last[1]:,.1f}"
    _txt(page, (x1 + 6, line[-1].y + 3), f"{val} ({last[0].strftime('%m/%d')})", 8, color)
    pk = max(pts, key=lambda p: p[1])
    if pk != last:
        page.draw_circle(pymupdf.Point(X(pk[0]), Y(pk[1])), 2.2, color=color, fill=(1, 1, 1))
        pv = f"${pk[1]:,.0f}" if money and pk[1] >= 100 else f"${pk[1]:,.2f}" if money else f"{pk[1]:,.1f}"
        _txt(page, (X(pk[0]) - 4, Y(pk[1]) - 7), f"고점 {pv} ({pk[0].strftime('%m/%d')})", 7.5, MUT, right=True)


def chart(kind, today=None, path=None):
    import pymupdf
    from memory_spot import _txt
    sp = SPEC[kind]
    today = today or common.now_kst().date()
    since = since_day(today)
    tf = tf_points(kind, since)
    dx, unit = dx_series(kind, since)
    doc = pymupdf.open()
    page = doc.new_page(width=720, height=640)
    page.draw_rect(page.rect, color=None, fill=(1, 1, 1))
    _txt(page, (36, 34), sp["title"], 15, INK)
    _txt(page, (36, 52), f"기준 {today.isoformat()} · 지난 12개월", 8.5, MUT)
    _panel(page, (80, 100, 610, 320), tf, C_TF, sp["tf_name"], "TrendForce", since, today)
    dx_title = sp["dx_name"] + (" (달러)" if unit == "USD" else f" (지수, {dx[0][0].strftime('%y.%m.%d')}=100)" if dx else "")
    _panel(page, (80, 390, 610, 590), dx, C_DX, dx_title, "DRAMeXchange", since, today, money=unit == "USD")
    OUT.mkdir(parents=True, exist_ok=True)
    path = Path(path or OUT / f"{kind}_{today.strftime('%Y%m%d')}.png")
    page.get_pixmap(dpi=150).save(str(path))

    def side(pts):
        return {"last": [pts[-1][0].isoformat(), round(pts[-1][1], 2)], "n": len(pts), "first": pts[0][0].isoformat(),
                "chg_1w": _chg(pts, 7), "chg_1m": _chg(pts, 30), "peak": [max(pts, key=lambda p: p[1])[0].isoformat(), round(max(p[1] for p in pts), 2)]} if pts else None
    t_side = side(tf)
    if kind == "dram" and t_side and t_side["chg_1w"] is None:   # 지난주 관측이 없으면 TrendForce 표가 직접 주는 주간 변화율을 쓴다
        import rdimm_spot
        row = next((r for r in rdimm_spot.tf_read() if r["date"] == t_side["last"][0]), None)
        t_side["chg_1w"] = float(row["chg"]) if row and row.get("chg") not in ("", None) else None
    summ = {"kind": kind, "png": str(path), "as_of": today.isoformat(), "trendforce": t_side, "dramexchange": side(dx), "dx_unit": unit,
            "tf_name": sp["tf_name"], "dx_name": sp["dx_name"]}
    return path, summ


def _pct(v):
    return "미확인" if v is None else f"{v:+.1f}%"


def caption(summ, read=""):
    t, d = summ.get("trendforce"), summ.get("dramexchange")
    lines = [f"[Chiip Spot] {SPEC[summ['kind']]['title']} — {summ['as_of']}"]
    if t:
        lines.append(f"{summ['tf_name'].split(' (')[0]}: ${t['last'][1]:,.2f}({t['last'][0][5:]}) · 1주 {_pct(t['chg_1w'])} · 1개월 {_pct(t['chg_1m'])} — TrendForce")
    if d:
        v = f"${d['last'][1]:,.2f}" if summ["dx_unit"] == "USD" else f"지수 {d['last'][1]:,.1f}"
        lines.append(f"{summ['dx_name']}: {v}({d['last'][0][5:]}) · 1주 {_pct(d['chg_1w'])} · 1개월 {_pct(d['chg_1m'])} — DRAMeXchange")
    if read.strip():
        lines += ["", read.strip()]
    return "\n".join(lines)


def keys(kind):
    """지금 가진 두 지표의 마지막 관측일 — 이 값이 지난 보고와 다르면 보고한다"""
    since = since_day()
    tf, (dx, _) = tf_points(kind, since), dx_series(kind, since)
    return {"tf": tf[-1][0].isoformat() if tf else "", "dx": dx[-1][0].isoformat() if dx else ""}


def status():
    """Pulse 관문 — {"dram": {due, png, summary, updated}, "nand": {…}}. 새 값을 먼저 받아 온다"""
    out = {}
    try:
        import memory_spot
        memory_spot.update()
    except Exception:
        pass
    try:
        import rdimm_spot
        rdimm_spot.tf_update()
    except Exception:
        pass
    st = common.load_state(STATE, {})
    for kind in SPEC:
        try:
            k = keys(kind)
            sent = (st.get(kind) or {})
            upd = [n for n, lab in (("tf", "TrendForce"), ("dx", "DRAMeXchange")) if k[n] and k[n] != sent.get(n)]
            if not upd:
                out[kind] = {"due": False}
                continue
            png, summ = chart(kind)
            out[kind] = {"due": True, "png": str(png), "summary": summ, "updated": ["TrendForce" if n == "tf" else "DRAMeXchange" for n in upd]}
        except (Exception, SystemExit) as e:
            out[kind] = {"due": False, "error": f"{type(e).__name__}: {str(e)[:120]}"}
    return out


def send(kind, read=""):
    import notify
    png, summ = chart(kind)
    ok = notify.send_photo(png, caption(summ, read)[:1000], "P1")
    if ok:
        st = common.load_state(STATE, {})
        st[kind] = keys(kind)
        common.save_state(STATE, st)
    return ok


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if argv[:1] == ["--chart"] and len(argv) > 1:
        png, summ = chart(argv[1])
        print(png)
        print(json.dumps(summ, ensure_ascii=False, default=str))
    elif argv[:1] == ["--status"]:
        print(json.dumps(status(), ensure_ascii=False, default=str))
    elif argv[:1] == ["--send"] and len(argv) > 1:
        print("[Spot Report] 발송" if send(argv[1], " ".join(argv[2:])) else "[Spot Report] 발송 실패")
    else:
        print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
