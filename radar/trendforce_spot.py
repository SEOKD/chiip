"""TrendForce 메모리 현물가격 일일 집계 (마스터 지시 2026-11-19 "DRAM 및 NAND Spot Price 일일 집계는 Trendforce 집계도 수집해
따로 그래프를 그려줘")

원천: TrendForce 공개 가격 페이지(로그인 없이 보이는 표) — trendforce.com/price/dram/dram_spot · /price/flash/flash_spot
  + 인터넷 아카이브(web.archive.org)에 남은 같은 페이지와 DRAMeXchange 첫 화면 스냅숏(--backfill, 연초 이후 이력).
약관: TrendForce 이용약관은 서면 동의 없는 크롤러 수집·복제·2차 저작물을 금지한다(robots.txt는 허용, 2026-11-19 확인).
  마스터 결정(2026-11-19 "켜라(개인 봇 한정)") — 수치는 git 제외 폴더(radar/inbox/trendforce_spot/)에만 두고,
  그림·수치는 마스터 개인 텔레그램으로만 보낸다. 노션·리포트·공개 산출물·커밋에 쓰지 않는다.
읽는 값: 현물표(Daily High가 있는 표)의 Session Average(달러)와 Last Update(대만 시각 GMT+8).
  같은 날 여러 번 갱신되면(11:00 장중·18:10 마감) 가장 늦은 값을 쓴다. NAND 현물표는 주 1회 갱신된다.
  아카이브 이력은 스냅숏이 있는 날만 있다 — 빈 날은 선으로 잇고 점은 관측일에만 찍는다.
run(): run_hourly 360분 — 공개 페이지 2쪽을 읽어 새 갱신분만 더한다(모델 없음).
그림: radar/memory_spot.py가 평일 10~11시 메리츠 기반 추정 그림 다음에 이 그림을 따로 보낸다.
사용: py radar/trendforce_spot.py              # 공개 페이지 읽기(run)
      py radar/trendforce_spot.py --backfill [2025-12-01]
      py radar/trendforce_spot.py --chart [시작일]
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

STATE = "trendforce_spot"
OUT = common.ROOT / "radar" / "inbox" / "trendforce_spot"
ROWS = OUT / "rows.csv"
FIELDS = ["date", "updated", "table", "item", "high", "low", "avg", "chg", "source", "url"]
PAGES = {"dram": "https://www.trendforce.com/price/dram/dram_spot", "flash": "https://www.trendforce.com/price/flash/flash_spot"}
WB_TARGETS = ["www.dramexchange.com/", "www.trendforce.com/price/dram/dram_spot", "www.trendforce.com/price/flash/flash_spot"]
DRAM = "DDR5 16Gb (2Gx8) 4800/5600"
NAND = "MLC 64Gb 8GBx8"
ITEM = re.compile(r"^(?:DDR\d|SLC|MLC|TLC|QLC)\b(?!.*DIMM)")
MON = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def canon(name):
    """'DDR5 16G (2Gx8) 4800/5600'(DRAMeXchange 표기)와 'DDR5 16Gb (2Gx8) 4800/5600'을 같게, 띄어쓰기 정리"""
    s = re.sub(r"\s+", " ", name).strip()
    s = re.sub(r"^(DDR\d\w*) (\d+)G\b", r"\1 \2Gb", s)
    s = re.sub(r"\)(\d)", r") \1", s)   # 'DDR4 16Gb (2Gx8)3200' → '… (2Gx8) 3200'
    return s


def _updated(cell):
    """'Last Update 2026-01-16 11:00 (GMT+8)' · 'Last Update: Jan.5 2026 18:10 (GMT+8)' → '2026-01-16 11:00'"""
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})\s+(\d{1,2}:\d{2})", cell)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)} {m.group(4):0>5}"
    m = re.search(r"([A-Za-z]{3})[a-z]*\.?\s*(\d{1,2}),?\s+(\d{4})\s+(\d{1,2}:\d{2})", cell)
    if m and m.group(1).lower() in MON:
        return f"{m.group(3)}-{MON[m.group(1).lower()]:02d}-{int(m.group(2)):02d} {m.group(4):0>5}"
    return None


def _num(s):
    try:
        return float(s.replace(",", ""))
    except (ValueError, AttributeError):
        return None


def parse(text):
    """페이지 본문 → [{date, updated, table, item, high, low, avg, chg}] — 'Daily High' 머리가 있는 현물표만"""
    import gpu_daily
    c = gpu_daily._cells(text)
    out, upd, daily, table = [], None, False, ""
    for i, x in enumerate(c):
        if x.startswith("Last Update"):
            upd = _updated(x)
            head = c[i + 1:i + 12]
            daily = "Daily High" in head
            prev = " ".join(c[max(0, i - 4):i])
            table = "NAND" if re.search(r"NAND|Flash", prev, re.I) else ("DRAM" if "DRAM" in prev else "")
            continue
        if not (upd and daily and ITEM.match(x)):
            continue
        nums, pct = [], None
        for y in c[i + 1:i + 10]:
            if re.fullmatch(r"[-+]?[0-9][0-9,]*\.?\d*", y):
                nums.append(_num(y))
            elif re.fullmatch(r"[-+]?[0-9.]+\s*%", y):
                pct = _num(y.rstrip("% "))
                break
            elif y in ("▲", "▼", "—", "-"):
                continue
            else:
                break
        if len(nums) < 5:
            continue
        item = canon(x)
        out.append({"date": upd[:10], "updated": upd, "table": table or ("NAND" if item.startswith(("SLC", "MLC", "TLC", "QLC")) else "DRAM"),
                    "item": item, "high": nums[2], "low": nums[3], "avg": nums[4], "chg": pct})
    return out


def read_rows():
    if not ROWS.exists():
        return []
    with ROWS.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def merge(new):
    """(날짜, 품목)마다 가장 늦은 갱신 하나 — 같은 갱신이면 먼저 있던 행을 둔다"""
    rows = {(r["date"], r["item"]): r for r in read_rows()}
    added = 0
    for r in new:
        k = (r["date"], r["item"])
        old = rows.get(k)
        if old is None or r["updated"] > old["updated"]:
            added += old is None
            rows[k] = r
    OUT.mkdir(parents=True, exist_ok=True)
    with ROWS.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(rows.values(), key=lambda r: (r["item"], r["date"])))
    return added


def run():
    got, errs = [], []
    for k, u in PAGES.items():
        try:
            for r in parse(common.http_get(u, timeout=40).decode("utf-8", "ignore")):
                got.append({**r, "source": "live", "url": u})
        except Exception as e:
            errs.append(f"{k} {type(e).__name__}")
    n = merge(got) if got else 0
    st = common.load_state(STATE, {})
    st["last_run"] = common.iso(common.now_kst())
    common.save_state(STATE, st)
    return f"TrendForce 현물 {len(got)}행 · 새 날짜 {n}" + (f" · 문제 {', '.join(errs)}" if errs else "")


def backfill(since="2025-12-01", pause=6.0):
    import gpu_daily
    st = common.load_state(STATE, {})
    done = set(st.get("wb_done") or [])
    total = 0
    for tgt in WB_TARGETS:
        q = f"{gpu_daily.CDX}?url={tgt}&from={since.replace('-', '')}&output=json&filter=statuscode:200&collapse=timestamp:8&fl=timestamp,original"
        try:
            snaps = json.loads(gpu_daily._wb_get(q))[1:]
        except Exception as e:
            print(f"[TrendForce] {tgt} 스냅숏 목록 실패 {type(e).__name__}")
            continue
        time.sleep(pause)
        for ts, orig in snaps:
            k = f"{tgt}|{ts}"
            if k in done:
                continue
            url = f"https://web.archive.org/web/{ts}id_/{orig}"
            try:
                got = [{**r, "source": f"wayback:{ts}", "url": url} for r in parse(gpu_daily._wb_get(url).decode("utf-8", "ignore"))]
            except Exception as e:
                print(f"[TrendForce] {ts} 실패 {type(e).__name__}")
                time.sleep(pause)
                continue
            n = merge(got)
            total += n
            done.add(k)
            st["wb_done"] = sorted(done)
            common.save_state(STATE, st)
            dd = sorted({r["date"] for r in got})
            print(f"[TrendForce] {tgt[:24]} {ts[:8]} → {len(got)}행 {dd} 새 {n}")
            time.sleep(pause)
    return total


# ---------- 시계열·그림 ----------
def series(item, since, rows=None):
    rows = rows if rows is not None else read_rows()
    pts = sorted((date.fromisoformat(r["date"]), float(r["avg"])) for r in rows if r["item"] == item and r["avg"] not in ("", None))
    before = [p for p in pts if p[0] < date.fromisoformat(since)]
    pts = [p for p in pts if p[0] >= date.fromisoformat(since)]
    if len(pts) < 2:
        return None
    base = before[-1] if before and (pts[0][0] - before[-1][0]).days <= 14 else pts[0]   # 연초 기준 = 직전 연말 마지막 관측(2주 이내)
    last = pts[-1]

    def back(days):
        ref = last[0] - timedelta(days=days)
        old = [p for p in pts if p[0] <= ref]
        return (last[1] / old[-1][1] - 1) * 100 if old and (ref - old[-1][0]).days <= 7 else None
    live = {date.fromisoformat(r["date"]) for r in rows if r["item"] == item and r["source"] == "live"}
    return {"item": item, "points": ([base] if base is not pts[0] else []) + pts, "base": base, "last": last, "n": len(pts),
            "n_live": sum(1 for d, _ in pts if d in live), "chg": {"1W": back(7), "1M": back(30), "YTD": (last[1] / base[1] - 1) * 100}}


INK, INK2, MUTED, GRID, SURF = (0.043, 0.043, 0.043), (0.322, 0.318, 0.306), (0.537, 0.529, 0.506), (0.882, 0.878, 0.851), (0.988, 0.988, 0.984)
BLUE = (0.165, 0.471, 0.839)   # 단일 계열 — 제목이 이름을 대신한다(범례 없음)


def _panel(page, box, s, title):
    from memory_spot import _nice, _txt
    x0, y0, x1, y1 = box
    ys = [v for _, v in s["points"]]
    lo, hi = min(ys), max(ys)
    step = _nice((hi - lo) / 4 or hi * 0.05 or 1)
    lo, hi = math.floor(lo / step) * step, math.ceil(hi * 1.12 / step) * step
    d0, d1 = s["points"][0][0], s["points"][-1][0]
    span = max((d1 - d0).days, 1)
    X = lambda d: x0 + (x1 - x0) * (d - d0).days / span   # noqa: E731
    Y = lambda v: y1 - (y1 - y0) * (v - lo) / (hi - lo)    # noqa: E731
    _txt(page, (x0, y0 - 22), title, 12, INK)
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
    pts = [(X(d), Y(v)) for d, v in s["points"]]
    page.draw_polyline(pts, color=BLUE, width=1.6)
    if s["n"] <= 120:   # 관측일 점(빈 날은 선만) — 점이 너무 빽빽하면 생략
        for p in pts:
            page.draw_circle(p, 1.4, color=BLUE, fill=BLUE)
    page.draw_circle(pts[-1], 3.2, color=SURF, fill=BLUE, width=1.2)
    c = " · ".join(f"{k} {v:+.1f}%" for k, v in s["chg"].items() if v is not None)
    _txt(page, (x0 + 8, y0 + 16), f"{s['last'][0].strftime('%m/%d')} ${s['last'][1]:,.2f}   {c}", 10, INK)
    _txt(page, (x0 + 8, y0 + 30), f"기준 {s['base'][0].strftime('%y/%m/%d')} ${s['base'][1]:,.2f} · 관측 {s['n']}일", 8, INK2)


def chart(since=None, path=None):
    import pymupdf
    from memory_spot import _txt
    since = since or f"{common.now_kst().year}-01-01"
    rows = read_rows()
    S = [series(DRAM, since, rows), series(NAND, since, rows)]
    if not all(S):
        raise SystemExit("[TrendForce] 자료 부족 — --backfill 또는 run 먼저")
    doc = pymupdf.open()
    page = doc.new_page(width=720, height=640)
    page.draw_rect(page.rect, color=None, fill=SURF)
    _txt(page, (36, 34), f"TrendForce 메모리 현물가격 — {since[:4]} YTD", 15, INK)
    _txt(page, (36, 52), "Session Average(달러) · 공개 가격 페이지와 인터넷 아카이브 스냅숏으로 모은 관측값", 8.5, INK2)
    _panel(page, (80, 100, 690, 320), S[0], f"DRAM {DRAM} 현물 (달러)")
    _panel(page, (80, 390, 690, 590), S[1], f"NAND {NAND} 현물 (달러, 주 1회 갱신)")
    _txt(page, (36, 622), "자료: TrendForce(DRAMeXchange) 공개 현물가격표. 아카이브 스냅숏이 없는 날은 선으로 이었다. 개인 열람용.", 7.5, MUTED)
    OUT.mkdir(parents=True, exist_ok=True)
    path = Path(path or OUT / f"tf_{S[0]['last'][0].strftime('%Y%m%d')}.png")
    page.get_pixmap(dpi=150).save(str(path))
    return path, json.loads(json.dumps({"since": since, "png": str(path), "series": [{k: v for k, v in s.items() if k != "points"} for s in S]}, default=str))


def value_on(item, d, rows=None):
    """그날 Session Average(없으면 None)"""
    for r in rows if rows is not None else read_rows():
        if r["item"] == item and r["date"] == d and r["avg"] not in ("", None):
            return float(r["avg"])
    return None


def caption(summ, compare=()):
    """compare = 메리츠 기반 추정과의 대조 줄(radar/memory_spot.py가 만든다)"""
    L = ["[Chiip Memory Spot · TrendForce]", f"TrendForce 현물가격 ({summ['since'][:4]} YTD, Session Average)", ""]
    for s in summ["series"]:
        d, v = s["last"]
        c = " · ".join(f"{k} {x:+.1f}%" for k, x in s["chg"].items() if x is not None)
        L.append(f"■ {s['item']}: ${v:,.2f} ({d[5:].replace('-', '/')}) — {c}")
    if compare:
        L += [""] + list(compare)
    L += ["", "자료: TrendForce 공개 가격표(개인 열람용, 재배포 금지)"]
    return "\n".join(L)


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if argv[:1] == ["--backfill"]:
        print(f"[TrendForce] 새 날짜 {backfill(argv[1] if len(argv) > 1 else '2025-12-01')}행")
    elif argv[:1] == ["--chart"]:
        print(json.dumps(chart(argv[1] if len(argv) > 1 else None)[1], ensure_ascii=False, indent=1))
    else:
        print(run())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
