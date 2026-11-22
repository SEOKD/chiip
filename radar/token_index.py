"""Silicon Data LLM 토큰 지출 가중 가격 지수(SDLLMTK) — 매일 수집, 매주 일요일 18:00 KST 이후 첫 Pulse 회차에 1통
(마스터 지시 2026-11-22 "Token Price Index도 수집해봐. 매주 일요일 오후 6시에 보내줘.")

원천: silicondata.com/products/silicon-index/llm-token-expenditure-index — 공개 페이지(robots Allow: /) 헤드라인 값만 '인용'.
  데이터셋·API는 유료 계약 대상이라 쓰지 않는다(config/gpu_rental.yaml Silicon Data 원칙과 같다). 하루 1점만 쌓는다(페이지의 최신 관측일·값).
  단위: 혼합 추론 토큰 가격(USD/100만 토큰, 정규화 지수 — Silicon Data 설명).
저장: knowledge/models/token_index.csv (date, value, source_url, fetched_at)
결정론: --collect(run_hourly 6시간) · --status(due = 일요일 18:00 이후, 이번 주 미발송) · --send <파일>({"read": "풀이"}) → 그림 + 캡션 1통.
모델 몫: 풀이 1~3문장 — 주간 변화와 방향, 근거가 있을 때만 원인(모델 가격 인하·새 모델 출시 등), GPU 렌털료·추론 수요 판단에 주는 뜻.
사용: py radar/token_index.py --collect | --status | --chart | --send <파일>
"""
import csv
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

URL = "https://www.silicondata.com/products/silicon-index/llm-token-expenditure-index"
CSV = common.ROOT / "knowledge" / "models" / "token_index.csv"
PNG = common.ROOT / "radar" / "state" / "token_index.png"
STATE = "token_index"
FIELDS = ["date", "value", "open", "proprietary", "wk_ago_date", "wk_ago", "source_url", "fetched_at"]   # value = 종합 지수


SERIES = {"": "blended", "?series=open-llm": "open", "?series=proprietary-llm": "proprietary"}   # 종합(개방형+독점 모델)·개방형·독점형


def latest(text):
    """페이지 카드마다 최신 관측일·값 하나 → {"date", "blended", "open", "proprietary"}. 헤드라인 값만 쓴다(7일 보기의 나머지 점은 저장하지 않는다)"""
    t = text.replace('\\"', '"')
    out = {}
    for m in re.finditer(r'"date":"(\d{4}-\d{2}-\d{2})","price":([0-9.]+)\}\],"href":"/products/silicon-index/llm-token-expenditure-index([^"]*)"', t):
        k = SERIES.get(m.group(3))
        if k:
            out[k] = float(m.group(2))
            if k == "blended":
                out["date"] = m.group(1)
                # 같은 카드의 '7일 보기' 첫 점 — 전주 대비 계산에만 쓴다(계열로 저장하지 않는다)
                card = t[max(0, m.start() - 1200):m.end()]
                first = re.findall(r'"points":\[\{"date":"(\d{4}-\d{2}-\d{2})","price":([0-9.]+)', card)
                if first:
                    out["wk_ago_date"], out["wk_ago"] = first[-1][0], float(first[-1][1])
    return out if "blended" in out else None


def rows():
    if not CSV.exists():
        return []
    with CSV.open(encoding="utf-8") as f:
        return [dict(r, value=float(r["value"])) for r in csv.DictReader(f)]


def collect(get=None):
    import gpu_rental
    t = (get or gpu_rental._get)(URL)
    got = latest(t)
    if not got:
        print("token_index: 헤드라인 값을 찾지 못함(페이지 구조 변경?)")
        return None
    have = {r["date"] for r in rows()}
    if got["date"] in have:
        print(f"token_index: {got['date']} 이미 있음 {got['blended']}")
        return got
    new = not CSV.exists()
    CSV.parent.mkdir(parents=True, exist_ok=True)
    with CSV.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, FIELDS)
        if new:
            w.writeheader()
        w.writerow({"date": got["date"], "value": got["blended"], "open": got.get("open", ""), "proprietary": got.get("proprietary", ""),
                    "wk_ago_date": got.get("wk_ago_date", ""), "wk_ago": got.get("wk_ago", ""), "source_url": URL, "fetched_at": common.iso(common.now_kst())})
    print(f"token_index: {got['date']} 종합 {got['blended']} · 개방형 {got.get('open')} · 독점형 {got.get('proprietary')} 저장")
    return got


def backfill(since="2025-11-01"):
    """인터넷 아카이브(web.archive.org, robots 허용) 스냅숏마다 그날 페이지의 헤드라인 값 1점 — gpu_daily 지수 역수집과 같은 방식.
    스냅숏이 하루 1장보다 드물면 빈 날은 비워 둔다(지어내지 않는다)"""
    import gpu_daily
    q = f"{gpu_daily.CDX}?url=www.silicondata.com/products/silicon-index/llm-token-expenditure-index&from={since.replace('-', '')}&output=json&filter=statuscode:200&collapse=timestamp:8&fl=timestamp,original"
    snaps = json.loads(gpu_daily._wb_get(q))[1:]
    have = {r["date"] for r in rows()}
    add = []
    for ts, orig in snaps:
        try:
            got = latest(gpu_daily._wb_get(f"https://web.archive.org/web/{ts}id_/{orig}").decode("utf-8", "ignore"))
        except Exception:
            continue
        if got and got["date"] not in have:
            have.add(got["date"])
            add.append({"date": got["date"], "value": got["blended"], "open": got.get("open", ""), "proprietary": got.get("proprietary", ""),
                        "source_url": f"https://web.archive.org/web/{ts}/{orig}", "fetched_at": common.iso(common.now_kst())})
    allr = sorted([{k: r.get(k, "") for k in FIELDS} for r in rows()] + add, key=lambda r: r["date"])
    CSV.parent.mkdir(parents=True, exist_ok=True)
    with CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, FIELDS)
        w.writeheader()
        w.writerows(allr)
    print(f"token_index: 스냅숏 {len(snaps)}장 · 새 관측일 {len(add)}")


def week_key(now):
    y, w, _ = now.isocalendar()
    return f"{y}-W{w:02d}"


def status(now=None):
    now = now or common.now_kst()
    st = common.load_state(STATE, {})
    rs = rows()
    due = now.weekday() == 6 and now.hour >= 18 and st.get("sent_week") != week_key(now) and bool(rs)
    out = {"due": due, "week": week_key(now), "n": len(rs)}
    if rs:
        last = rs[-1]
        cut = (date.fromisoformat(last["date"]) - timedelta(days=7)).isoformat()
        prev = next((r for r in reversed(rs) if r["date"] <= cut), None)
        peak = max(rs, key=lambda r: r["value"])
        out.update({"open": last.get("open"), "proprietary": last.get("proprietary")})
        ap = approx_rows()
        if ap:
            out.update({"ytd_base": ap[0]["value"], "ytd": round(last["value"] / ap[0]["value"] - 1, 4)})
        if not prev and last.get("wk_ago"):   # 쌓인 지 1주 미만 — 페이지 '7일 보기'의 첫 점으로
            prev = {"date": last["wk_ago_date"], "value": float(last["wk_ago"])}
        out.update({"last": last["date"], "value": last["value"],
                    "wow": round(last["value"] / prev["value"] - 1, 4) if prev else None, "wow_base": prev["date"] if prev else None,
                    "peak": peak["value"], "peak_date": peak["date"], "from_peak": round(last["value"] / peak["value"] - 1, 4),
                    "since": rs[0]["date"]})
    return out


APPROX = common.ROOT / "knowledge" / "models" / "token_index_ytd_approx.csv"   # 2026-01-01~11-19 — 마스터 제공 그래프 판독 근사(실측 아님, 2026-11-22)
YTD_START = "2026-01-01"   # 마스터 지시 2026-11-22 "Token Price Index의 YTD 그래프를 그리고 11월 22일부터 집계하라"


def approx_rows():
    if not APPROX.exists():
        return []
    with APPROX.open(encoding="utf-8") as f:
        return [{"date": r["date"], "value": float(r["value"])} for r in csv.DictReader(f)]


def chart(path=PNG):
    """YTD 한 장 — 회색 점선 = 판독 근사(1/1~11/19), 빨간 실선 = Chiip 수집(11/22 수집 시작, 하루 1점)"""
    import pymupdf
    from memory_spot import _nice, _txt
    rs, ap = rows(), approx_rows()
    d0 = date.fromisoformat(YTD_START)
    d1 = max(date.fromisoformat(rs[-1]["date"]) if rs else d0, date.fromisoformat(ap[-1]["date"]) if ap else d0) + timedelta(days=3)
    doc = pymupdf.open()
    page = doc.new_page(width=720, height=420)
    page.draw_rect(page.rect, color=None, fill=(1, 1, 1))
    _txt(page, (36, 34), "LLM 토큰 가격 지수 YTD(Silicon Data SDLLMTK)", 15, (0.05, 0.05, 0.05))
    _txt(page, (36, 52), f"혼합 추론 토큰 가격 지수 · {YTD_START} ~ {rs[-1]['date'] if rs else ''}", 8.5, (0.4, 0.4, 0.4))
    x0, y0, x1, y1 = 60, 80, 640, 360
    ys = [r["value"] for r in rs + ap]
    step = _nice(max(max(ys) - min(ys), 0.2) / 5)
    bot, top = (min(ys) // step) * step, (max(ys) // step + 1) * step
    X = lambda d: x0 + (x1 - x0) * (date.fromisoformat(d) - d0).days / max((d1 - d0).days, 1)   # noqa: E731
    Y = lambda v: y1 - (y1 - y0) * (v - bot) / (top - bot)   # noqa: E731
    v = bot
    while v <= top + 1e-9:
        page.draw_line((x0, Y(v)), (x1, Y(v)), color=(0.9, 0.9, 0.9), width=0.5)
        _txt(page, (x0 - 6, Y(v) + 3), f"{v:.2f}", 7, (0.45, 0.45, 0.45), right=True)
        v += step
    for m in range(1, 13):
        dm = date(d0.year, m, 1)
        if dm <= d1:
            _txt(page, (X(dm.isoformat()) - 6, y1 + 14), f"{m}월", 7, (0.45, 0.45, 0.45))
    for a, b in zip(ap, ap[1:]):
        page.draw_line((X(a["date"]), Y(a["value"])), (X(b["date"]), Y(b["value"])), color=(0.6, 0.6, 0.6), width=1.2, dashes="[3 2] 0")
    red = (0.85, 0.15, 0.2)
    for a, b in zip(rs, rs[1:]):
        page.draw_line((X(a["date"]), Y(a["value"])), (X(b["date"]), Y(b["value"])), color=red, width=1.8)
    for r in rs[-1:]:
        page.draw_circle((X(r["date"]), Y(r["value"])), 2.6, color=red, fill=red)
        _txt(page, (X(r["date"]) + 6, Y(r["value"]) + 3), f"{r['value']:.4f}", 8, red)
    page.draw_line((x0, 382), (x0 + 22, 382), color=(0.6, 0.6, 0.6), width=1.2, dashes="[3 2] 0")
    _txt(page, (x0 + 28, 385), "1/1~11/19 판독 근사(마스터 제공 그래프 눈금 판독, 실측 아님)", 7.5, (0.4, 0.4, 0.4))
    page.draw_line((x0 + 300, 382), (x0 + 322, 382), color=red, width=1.8)
    _txt(page, (x0 + 328, 385), "Chiip 수집(11/22부터, 공개 헤드라인 값 하루 1점)", 7.5, (0.4, 0.4, 0.4))
    _txt(page, (36, 408), "자료: Silicon Data LLM Token Expenditure Index 공개 페이지 헤드라인 값 인용(데이터셋·API 미사용)", 7, (0.5, 0.5, 0.5))
    page.get_pixmap(dpi=150).save(str(path))
    return path


def caption(s, read):
    pct = lambda x: f"{x:+.1%}" if x is not None else "비교 불가(쌓인 지 1주 미만)"   # noqa: E731
    lines = [f"[Chiip Pulse] LLM 토큰 가격 지수 — {s['last']} {s['value']:.4f}",
             f"■ 전주 대비 {pct(s['wow'])}" + (f"({s['wow_base']} 대비)" if s.get("wow_base") else ""),
             f"■ 개방형 모델 {s.get('open') or '-'} · 독점형 모델 {s.get('proprietary') or '-'}",
             f"■ 연초 대비 {pct(s['ytd'])}(1/1 판독 근사 {s['ytd_base']:.2f} 기준)" if s.get("ytd") is not None else "",
             *([f"■ 추적 이후 고점 {s['peak']:.4f}({s['peak_date']}) 대비 {pct(s['from_peak'])}"] if s.get("n", 0) >= 5 else [])]
    if read:
        lines += ["", read.strip()]
    lines += ["", "■ 자료: Silicon Data LLM Token Expenditure Index(SDLLMTK) 공개 헤드라인 값 — 혼합 추론 토큰 가격(USD/100만 토큰 정규화)"]
    text = "\n".join(lines)
    return text if len(text) <= 1000 else text[:997] + "…"


def send(path, now=None):
    import notify
    now = now or common.now_kst()
    s = status(now)
    if not s.get("value"):
        print("token_index: 값 없음 — 보내지 않음")
        return False
    read = json.loads(Path(path).read_text(encoding="utf-8")).get("read", "") if path else ""
    # 쌓인 점이 3개 미만이면 그림 없이 글만(점 하나짜리 그림은 뜻이 없다)
    ok = notify.send_photo(chart(), caption(s, read), "P2")   # YTD 그림(판독 근사 + 수집값, 2026-11-22 마스터 지시)
    if ok:
        st = common.load_state(STATE, {})
        st["sent_week"] = week_key(now)
        common.save_state(STATE, st)
    print("token_index 발송:", ok)
    return ok


def run():
    """run_hourly 6시간 주기"""
    got = collect()
    return 1 if got else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    a = sys.argv[1:]
    if not a or a[0] == "--status":
        print(json.dumps(status(), ensure_ascii=False))
    elif a[0] == "--collect":
        collect()
    elif a[0] == "--backfill":
        backfill()
    elif a[0] == "--chart":
        print(chart())
    elif a[0] == "--send":
        send(a[1] if len(a) > 1 else None)
