"""Chiip Trade — 매일 아침 품목 하나의 수출입 추이 (마스터 지시 2026-11-21, 설정 config/trade_daily.yaml)

"매일 아침 특정 재화 품목에 대한 수출입 데이터 추이를 가져와라. 한국에서 미국이든, 미국에서 한국이든, 한국에서 일본이든 국가는 시장 관심사에 따라 임의로 정해라."
  원천  us = USITC DataWeb API(radar/usitc_dataweb.py monthly — 미국 수입·수출 월간 나라별), jp = 일본 무역통계(trade_hs.sqlite, 천 엔)
  고르기 새 달 통계가 나온 품목 > 최근 2일 Chiip 발송 글에 keywords가 많이 나온 품목 > 가장 오래 안 보낸 품목(결정론 — 모델 없음)
  보내기 그래프 1장(나라 금액·전체 대비 비중) + 최근 6개월 표. 마스터 개인 봇으로만. 하루 1회(window 시간대의 첫 실행)
  저장  knowledge/models/trade_daily/<key>.csv(월·나라 값·전체 값·수량), 상태 radar/state/trade_daily.json
월간 통관 통계다 — 매일 값이 바뀌지 않는다. 그래서 품목을 날마다 바꿔 본다. 나라·품목 합계이지 회사 매출이 아니다(금지표: 산업 성장 → 기업 이익).
메모리 현물가 보고(radar/memory_spot.py)는 memory_line()으로 한국산 DRAM·플래시 대미 통관액을 한 줄 참조한다.
사용: py radar/trade_daily.py [--force] [--key <품목>] [--dry]   ·   --memory-line
"""
import csv
import json
import math
import sqlite3
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

SOURCE_ID = "trade-daily"
DIR = common.ROOT / "knowledge" / "models" / "trade_daily"
STATE = common.ROOT / "radar" / "state" / "trade_daily.json"
SENT = common.ROOT / "radar" / "state" / "sent"
DB = common.ROOT / "radar" / "state" / "trade_hs.sqlite"
OUT = common.ROOT / "radar" / "inbox" / "trade_daily"
KST = timezone(timedelta(hours=9))
COLS = ["month", "value", "world", "qty"]


def cfg():
    return common.load_yaml("config/trade_daily.yaml")


def state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load(key):
    p = DIR / f"{key}.csv"
    if not p.exists():
        return {}
    with p.open(encoding="utf-8", newline="") as f:
        return {r["month"]: r for r in csv.DictReader(f)}


def save(key, rows):
    DIR.mkdir(parents=True, exist_ok=True)
    with (DIR / f"{key}.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, COLS)
        w.writeheader()
        w.writerows(rows[m] for m in sorted(rows))


def fetch(it, c, today):
    """품목 한 개의 월간 시계열 → {월: {value, world, qty}} (0뿐인 뒤쪽 달은 뺀다). us는 DataWeb 1회 호출(올해 포함 4개 연도)"""
    out = {}
    if it["src"] == "us":
        import usitc_dataweb as dw
        d = dw.monthly(it["flow"], it["code"], range(today.year - 3, today.year + 1))
        if d is None:
            raise RuntimeError("USITC_DATAWEB_TOKEN 없음")
        world = {}
        for (ctry, m), (v, _) in d.items():
            world[m] = world.get(m, 0.0) + v
        for (ctry, m), (v, q) in d.items():
            if ctry == it["partner"]:
                out[m] = {"month": m, "value": int(v), "world": int(world[m]), "qty": "" if q is None else int(q)}
        time.sleep(float(c.get("dataweb_gap_sec", 2)))
    else:   # 일본 무역통계(천 엔) — trade_hs가 하루 1회 채운다
        con = sqlite3.connect(DB)
        w = dict(con.execute("SELECT period, value FROM obs WHERE reporter='jp' AND flow=? AND hs=? AND partner='WORLD'", (it["flow"], it["code"])))
        for m, v in con.execute("SELECT period, value FROM obs WHERE reporter='jp' AND flow=? AND hs=? AND partner=?", (it["flow"], it["code"], it["partner"])):
            out[m] = {"month": m, "value": int(v), "world": int(w.get(m) or 0), "qty": ""}
        con.close()
    last = max((m for m, r in out.items() if r["world"] > 0), default=None)   # 아직 발표 전인 달(0)은 뺀다
    return {m: r for m, r in out.items() if last and it.get("valid_from", "") <= m <= last}


def buzz(it, days=2, now=None):
    """최근 발송 글에 품목 keywords가 나온 횟수 — '시장 관심사'의 대리 지표"""
    now = now or datetime.now(KST)
    n = 0
    for k in range(days + 1):
        p = SENT / f"{(now - timedelta(days=k)).strftime('%Y%m%d')}.jsonl"
        if p.exists():
            text = p.read_text(encoding="utf-8", errors="replace")
            n += sum(text.count(w) for w in it.get("keywords") or [])
    return n


def pick(c, st, now=None, key=None):
    """오늘 품목 — (품목, 이유). 새 달 > 관심 > 오래 안 보낸 순. min_gap_days 안에 보낸 품목은 새 달이 아니면 제외"""
    now = now or datetime.now(KST)
    items = c["items"]
    if key:
        return next(i for i in items if i["key"] == key), "지정"
    sent = st.get("sent") or {}
    cand = []
    for i, it in enumerate(items):
        s = sent.get(it["key"]) or {}
        gap = (now.date() - date.fromisoformat(s["date"])).days if s.get("date") else 999
        cand.append({"it": it, "gap": gap, "buzz": buzz(it, now=now), "order": i})
    fresh = [x for x in cand if x["gap"] >= int(c.get("min_gap_days", 6))] or cand
    hot = max(fresh, key=lambda x: (x["buzz"], x["gap"], -x["order"]))
    if hot["buzz"] > 0:
        return hot["it"], f"최근 이틀 Chiip 발송 글에 관련 낱말 {hot['buzz']}회"
    old = max(fresh, key=lambda x: (x["gap"], -x["order"]))
    return old["it"], "순번(가장 오래 안 본 품목)"


def unit(it):
    return ("천 엔", 1e6, "억 엔", 100) if it["src"] == "jp" else ("달러", 1e6, "$M", 1)


def money(it, v):
    if it["src"] == "jp":
        return f"{v / 1e5:,.0f}억 엔"   # 천 엔 → 억 엔
    return f"${v / 1e9:.2f}B" if v >= 1e9 else f"${v / 1e6:.1f}M"


def summary(it, rows, n=6):
    """최근 n개월 줄과 3개월 합 전년 대비"""
    ms = sorted(rows)[-n:]
    lines = []
    for m in ms:
        r = rows[m]
        v, w = int(r["value"]), int(r["world"])
        ya = rows.get(f"{int(m[:4]) - 1}{m[4:]}")
        yoy = f" · 전년 대비 {v / int(ya['value']) - 1:+.0%}" if ya and int(ya["value"]) else ""
        share = f" · 비중 {v / w:.0%}" if w else ""
        up = f" · 개당 ${v / int(r['qty']):,.2f}" if r.get("qty") not in ("", None, 0, "0") and it["code"].startswith("8542") else ""
        lines.append(f"{m[2:]}  {money(it, v)}{yoy}{share}{up}")
    last3, prev3 = sorted(rows)[-3:], [f"{int(m[:4]) - 1}{m[4:]}" for m in sorted(rows)[-3:]]
    a, b = sum(int(rows[m]["value"]) for m in last3), sum(int(rows[m]["value"]) for m in prev3 if m in rows)
    trend = f"최근 3개월 합 {money(it, a)}, 전년 같은 기간 대비 {a / b - 1:+.0%}" if b and len([m for m in prev3 if m in rows]) == 3 else f"최근 3개월 합 {money(it, a)}"
    return lines, trend


def chart(it, rows, path):
    """위: 상대국 금액(월), 아래: 전체 대비 비중(%) — PyMuPDF(새 패키지 없음, memory_spot과 같은 방식)"""
    import pymupdf
    import memory_spot as ms
    months = sorted(rows)[-36:]
    doc = pymupdf.open()
    page = doc.new_page(width=720, height=560)
    page.draw_rect(page.rect, color=None, fill=(1, 1, 1))
    ms._txt(page, (36, 34), f"{it['route']} {it['name']} — 월간", 15, (0.05, 0.05, 0.05))
    src = "USITC DataWeb(미국 통관 통계)" if it["src"] == "us" else "일본 재무성 무역통계"
    ms._txt(page, (36, 52), f"{src} · HS {it['code']} · {months[0]} ~ {months[-1]}", 8.5, (0.4, 0.4, 0.4))
    div = 1e5 if it["src"] == "jp" else 1e6
    lab = "억 엔" if it["src"] == "jp" else "백만 달러"
    series = [(f"{it['route']} 금액({lab})", [int(rows[m]["value"]) / div for m in months], (0.13, 0.36, 0.75), (80, 95, 690, 290)),
              ("전체 대비 비중(%)", [100 * int(rows[m]["value"]) / int(rows[m]["world"]) if int(rows[m]["world"]) else 0 for m in months], (0.80, 0.33, 0.10), (80, 350, 690, 515))]
    for title, ys, col, (x0, y0, x1, y1) in series:
        hi = max(ys) or 1
        step = ms._nice(hi / 4)
        top = math.ceil(hi * 1.1 / step) * step
        X = lambda i: x0 + (x1 - x0) * i / max(len(ys) - 1, 1)   # noqa: E731
        Y = lambda v: y1 - (y1 - y0) * v / top                   # noqa: E731
        ms._txt(page, (x0, y0 - 12), title, 11, (0.1, 0.1, 0.1))
        v = 0
        while v <= top + 1e-9:
            page.draw_line((x0, Y(v)), (x1, Y(v)), color=(0.88, 0.88, 0.88), width=0.6)
            ms._txt(page, (x0 - 6, Y(v) + 3), f"{v:,.0f}", 8, (0.45, 0.45, 0.45), right=True)
            v += step
        for i, m in enumerate(months):
            if m.endswith("-01") or i == 0:
                ms._txt(page, (X(i) - 10, y1 + 13), m[2:], 8, (0.45, 0.45, 0.45))
        page.draw_rect((x0, y0, x1, y1), color=(0.75, 0.75, 0.75), width=0.6)
        page.draw_polyline([(X(i), Y(v)) for i, v in enumerate(ys)], color=col, width=1.8)
        page.draw_circle((X(len(ys) - 1), Y(ys[-1])), 2.6, color=col, fill=col)
        ms._txt(page, (x1 - 4, y0 + 14), f"{months[-1][2:]} {ys[-1]:,.1f}", 10, col, right=True)
    ms._txt(page, (36, 545), "월간 통관 통계 — 나라·품목 합계이지 회사 매출이 아니다. Chiip Trade(개인 연구용).", 7.5, (0.45, 0.45, 0.45))
    path.parent.mkdir(parents=True, exist_ok=True)
    page.get_pixmap(dpi=150).save(str(path))
    return path


def caption(it, rows, why, c):
    lines, trend = summary(it, rows, int(c.get("months_shown", 6)))
    src = f"USITC DataWeb · 미국 {'수입' if it['flow'] == 'Import' else '수출'} · HTS {it['code']}" if it["src"] == "us" else f"일본 무역통계 · 대한국 {'수출' if it['flow'] == 'export' else '수입'} · HS {it['code']}"
    # '오늘 고른 이유' 줄은 내보내지 않는다(2026-11-22 마스터 지시) — 고른 이유는 상태 기록에만. '자료' 앞 ■, '대한국' → '대한민국'
    text = "\n".join([f"[Chiip Trade] {it['route']} {it['name']} — {sorted(rows)[-1]}", it["why"], "", *lines, "", trend,
                      f"■ 자료: {src}. 월간 통관 통계(나라·품목 합계, 회사 매출 아님)"])
    return text.replace("대한국", "대한민국")


def memory_line():
    """메모리 현물가 보고에 붙일 참조 한 줄 — 한국산 DRAM·플래시 대미 통관액(저장된 시계열만 읽는다, 호출 없음)"""
    parts = []
    for it in [i for i in cfg()["items"] if i.get("memory")]:
        rows = load(it["key"])
        if not rows:
            continue
        m = sorted(rows)[-1]
        r, ya = rows[m], rows.get(f"{int(sorted(rows)[-1][:4]) - 1}{sorted(rows)[-1][4:]}")
        yoy = f"(전년 대비 {int(r['value']) / int(ya['value']) - 1:+.0%})" if ya and int(ya["value"]) else ""
        up = f", 개당 ${int(r['value']) / int(r['qty']):,.2f}" if r.get("qty") not in ("", None, "0") else ""
        parts.append(f"{it['name']} {m[2:]} ${int(r['value']) / 1e6:,.0f}M{yoy}{up}")
    return ("참고 — 한국산 대미 통관(USITC DataWeb, 월간): " + " · ".join(parts) + ". 통관 단가는 제품 구성에 따라 움직여 현물가와 직접 비교하지 않는다") if parts else ""


def refresh_memory(c, today, skip=None):
    """메모리 참조 품목은 주 1회 갱신(월간 통계 — 매일 부를 필요 없다)"""
    st = state()
    for it in [i for i in c["items"] if i.get("memory") and i["key"] != skip]:
        p = DIR / f"{it['key']}.csv"
        if p.exists() and time.time() - p.stat().st_mtime < 7 * 86400:
            continue
        try:
            rows = fetch(it, c, today)
            if rows:
                save(it["key"], rows)
        except Exception:
            pass
    return st


def run(force=False, key=None, dry=False, now=None):
    c = cfg()
    now = now or datetime.now(KST)
    st = state()
    today = now.date().isoformat()
    if not force and (st.get("last") == today or not (c["window"][0] <= now.hour < c["window"][1])):
        return {"skipped": "오늘 보냈거나 발송 시간대 밖"}, 0
    it, why = pick(c, st, now, key)
    try:
        rows = fetch(it, c, now.date())
    except Exception as e:
        common.record_health(SOURCE_ID, False, f"{it['key']}: {type(e).__name__} {str(e)[:60]}")
        return {"error": f"{it['key']}: {type(e).__name__}"}, 0
    if len(rows) < 6:
        common.record_health(SOURCE_ID, False, f"{it['key']}: 시계열 {len(rows)}개월")
        return {"error": f"{it['key']}: 시계열 부족"}, 0
    old = load(it["key"])
    if old and sorted(rows)[-1] > sorted(old)[-1]:
        why = f"새 달 통계({sorted(rows)[-1]}) 발표"
    save(it["key"], rows)
    refresh_memory(c, now.date(), skip=it["key"])
    cap = caption(it, rows, why, c)
    png = chart(it, rows, OUT / f"{it['key']}_{today.replace('-', '')}.png")
    if dry:
        return {"dry": cap, "png": str(png)}, 0
    import notify
    ok = notify.send_photo(png, cap[:1000], "P1")
    if ok:
        st["last"] = today
        st.setdefault("sent", {})[it["key"]] = {"date": today, "month": sorted(rows)[-1]}
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    common.record_health(SOURCE_ID, bool(ok), None if ok else "텔레그램 발송 실패")
    return {"sent": bool(ok), "item": it["key"], "month": sorted(rows)[-1], "why": why}, 0


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if "--memory-line" in argv:
        print(memory_line())
        return
    res, _ = run(force="--force" in argv, key=argv[argv.index("--key") + 1] if "--key" in argv else None, dry="--dry" in argv)
    print(json.dumps(res, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
