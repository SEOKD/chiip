"""Chiip CFM 웨이퍼 — 중국 CFM 闪存市场 공개 시세의 NAND 웨이퍼 일별 종가(1Tb TLC·512Gb TLC)
(마스터 지시 2026-11-23 "NAND 1Tb TLC 파이프라인을 찾아봐. 그리고 NAND 512Gb TLC도 일일 집계 가능한 곳을 찾아봐" → 조사 보고 뒤 "Connect, personal bot only")

원천: https://www.chinaflashmarket.com/price/in/<id> — 중국 영업일마다 18:00(GMT+8) 게시. 페이지에 최근 반년 일별 기록(日低点·开盘价·收盘价)이 있다.
  robots.txt 허용(/file/·/uploads/만 금지). TrendForce 공개 웨이퍼표에는 1Tb TLC가 없고(512·256·128Gb TLC, 주 1회), 월간 계약가의 1Tb TLC는 유료 회원 전용이다.
약관: CFM 免责声明은 서면 허가 없는 데이터 복제·전재·편집(汇编)을 금하고, 제한적 사용에는 '来源：CFM闪存市场' 표기를 요구한다.
  → 마스터 결정(2026-11-23) = 개인 봇 한정. 숫자는 git 제외 radar/inbox/cfm_wafer/rows.csv에만 두고, 그림·설명은 Memory Spot 개인 텔레그램 봇 피드에만 쓴다.
  리포트·노션·공개 산출물·저장소 커밋에 넣지 않는다(INTERNAL_ONLY). 표기할 때는 SOURCE_NOTE를 붙인다.
성격: 중국 유통(무역) 쪽 호가로 보인다(추정). 값이 드물게 바뀐다(2026-05~11 반년 중 512Gb TLC 4회, 1Tb TLC 0회).
  TrendForce Session Average와 수준이 다르다(11월 512Gb TLC CFM $20.00 vs TrendForce $14.27) — 이어 붙이지 않고 별도 선으로만 그린다.
실행: Memory Spot 회차(radar/memory_spot.py status·send)가 하루 1회 부른다. 페이지 하나가 반년 이력을 주므로 첫 실행이 곧 백필이다.
  py radar/cfm_wafer.py            # 받기(오늘 이미 받았으면 건너뜀)
  py radar/cfm_wafer.py --force    # 오늘 받았어도 다시
"""
import csv
import html
import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

STATE = "cfm_wafer"
INTERNAL_ONLY = True   # 개인 봇 한정(2026-11-23 마스터 결정) — 리포트·노션·공개 산출물 금지
SOURCE_NOTE = "来源：CFM闪存市场"
URL = "https://www.chinaflashmarket.com/price/in/{}"
ITEMS = {"1Tb TLC": "100242", "512Gb TLC": "100170"}   # 1Tb QLC = 100257(지금은 받지 않는다)
OUT = common.ROOT / "radar" / "inbox" / "cfm_wafer"
ROWS = OUT / "rows.csv"
FIELDS = ["date", "item", "low", "open", "close", "fetched"]
ROW = re.compile(r"(20\d\d-\d\d-\d\d)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)")


def parse(page):
    """상세 페이지 HTML → [(날짜, 日低点, 开盘价, 收盘价)]. 표 머리 '日期 日低点 开盘价 收盘价' 뒤의 행만 읽는다"""
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", page or "", flags=re.S)
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text)))   # 태그 자리는 공백(칸 사이가 붙지 않게)
    i = text.find("日期 日低点 开盘价 收盘价")
    if i < 0:
        return []
    out = {}
    for d, lo, op, cl in ROW.findall(text[i:]):
        out[d] = (d, float(lo), float(op), float(cl))
    return sorted(out.values())


def read_rows():
    if not ROWS.exists():
        return []
    with ROWS.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def merge(new):
    rows = {(r["date"], r["item"]): r for r in read_rows()}
    added = sum(1 for r in new if (r["date"], r["item"]) not in rows)
    rows.update({(r["date"], r["item"]): r for r in new})
    OUT.mkdir(parents=True, exist_ok=True)
    with ROWS.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(rows.values(), key=lambda r: (r["item"], r["date"])))
    return added


def run(force=False, pause=2.0):
    """하루 1회 받기 → 요약 문자열"""
    st = common.load_state(STATE, {})
    today = common.now_kst().date().isoformat()
    if not force and st.get("fetched") == today:
        return "CFM 웨이퍼 오늘 받음"
    got, errs = [], []
    stamp = common.iso(common.now_kst())
    for k, (item, pid) in enumerate(ITEMS.items()):
        if k:
            time.sleep(pause)
        try:
            rows = parse(common.http_get(URL.format(pid), timeout=40).decode("utf-8", "ignore"))
            if not rows:
                errs.append(f"{item} 표 없음")
            got += [{"date": d, "item": item, "low": lo, "open": op, "close": cl, "fetched": stamp} for d, lo, op, cl in rows]
        except Exception as e:
            errs.append(f"{item} {type(e).__name__}")
    n = merge(got) if got else 0
    if got and not errs:
        st["fetched"] = today
    st["last_run"] = stamp
    common.save_state(STATE, st)
    return f"CFM 웨이퍼 {len(got)}행 · 새 날짜 {n}" + (f" · 문제 {', '.join(errs)}" if errs else "")


def series(item, since, rows=None):
    """[(날짜, 종가)] — since 이후. 연초 기준은 직전 연말 마지막 값(2주 이내)이 있을 때만"""
    rows = rows if rows is not None else read_rows()
    pts = sorted((date.fromisoformat(r["date"]), float(r["close"])) for r in rows if r["item"] == item and r["close"] not in ("", None))
    s = date.fromisoformat(since)
    before = [p for p in pts if p[0] < s]
    pts = [p for p in pts if p[0] >= s]
    if len(pts) < 2:
        return None
    ytd = before[-1] if before and (pts[0][0] - before[-1][0]).days <= 14 else (pts[0] if (pts[0][0] - s).days <= 14 else None)
    return {"item": item, "points": pts, "ytd_base": ytd, "first": pts[0], "last": pts[-1]}


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    print(run(force="--force" in argv))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
