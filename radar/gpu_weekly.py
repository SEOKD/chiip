"""Chiip Pulse — GPU 렌털료 주간 점검 (마스터 지시 2026-11-14 "GPU 렌탈료 변화는 Weekly Review 항목에서 제외하고 Pulse로 이관해
Pulse에서 매주 월요일 아침 6시마다 렌탈료의 전주 대비 변화율을 점검하고 이 현상에 대해 풀이하도록 해")

결정론: 매주 월요일 06:00 KST 이후 첫 Pulse 회차에 due. 숫자는 모두 여기서 계산한다(원천 knowledge/models/gpu_rental.csv, radar/gpu_rental.py 6시간마다).
  GPU별 Nebius 온디맨드 · CoreWeave 온디맨드·스팟 · Lambda 온디맨드(8x) · Silicon Data 지수 — 기준일(월요일) 값과 7일 전 이전 마지막 값 대비 변화율.
  Nebius 선점형은 15분 단위 스팟 변동가의 공개 하한이라 주간 비교에 쓰지 않는다(Weekly 블록과 같은 원칙).
모델 몫: 풀이 2~4문장(read) — 무엇이 얼마나 움직였고, 왜(공급·수요·세대 교체·가격표 개편 등 근거가 있을 때만), 무엇을 바꾸나.
  값이 하나도 안 움직였으면 '변화 없음'과 그 의미 한 문장. 근거 없는 원인은 쓰지 않는다.
사용: py radar/gpu_weekly.py --status        # 이번 주 점검 표(JSON)
      py radar/gpu_weekly.py --send <파일>    # {"read": "풀이"} → 마스터 개인 봇 1통, 이번 주 완료 표시
"""
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

sys.path.insert(0, str(common.ROOT / "scripts" / "weekly"))
import gpu_rent  # noqa: E402   # 시세 읽기·변화율 함수(원래 Weekly 블록) 재사용

STATE = "gpu_weekly"
HOUR = 6          # 월요일 06:00 KST 이후
READ_MAX = 600
COLS = [("Nebius", "Nebius", lambda r: r["term"].startswith("온디맨드")),
        ("CoreWeave", "CoreWeave", lambda r: r["term"].startswith("온디맨드")),
        ("CoreWeave 스팟", "CoreWeave", lambda r: r["term"] == "스팟"),
        ("Lambda", "Lambda", lambda r: r["term"].startswith("온디맨드") and "8x" in r.get("config", "")),
        ("지수", "Silicon Data 지수", lambda r: True)]


def week_key(now):
    y, w, _ = now.isocalendar()
    return f"{y}-W{w:02d}"


def _effective(term):
    """'온디맨드(시행 November 16, 2026)' → 2026-11-16. 없으면 None"""
    m = re.search(r"시행 ([A-Za-z]+ \d{1,2}, \d{4})", term or "")
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%B %d, %Y").date().isoformat()
    except ValueError:
        return None


def _lambda_series(rows, g, pick):
    """Lambda 가격표는 시행일이 미리 공지된다 — 시행 전 가격은 수집일부터, 새 가격은 시행일부터 적용"""
    out = {}
    for r in rows:
        if r["provider"] != "Lambda" or r["gpu"] != g or not pick(r):
            continue
        v = gpu_rent._num(r["usd_per_gpu_hr"])
        if v is None:
            continue
        eff = _effective(r["term"])
        key = max(r["date"], eff) if eff else r["date"]
        if eff:
            out[key] = v                      # 시행분이 그날 값을 정한다
        else:
            out.setdefault(key, v)            # 같은 날 시행분이 있으면 그 값을 둔다
    return out


def table(as_of, rows=None):
    """GPU × 원천 — (지금, 7일 전, 변화율 %). 7일 전 값이 없으면(추적 첫 주) 추적 시작일 값과 비교하고 그 날짜를 적는다"""
    rows = rows if rows is not None else gpu_rent._rows()
    day = str(as_of)[:10]
    prev = (date.fromisoformat(day) - timedelta(days=7)).isoformat()
    out = []
    for g in gpu_rent.GPUS:
        cells = {}
        for label, prov, pick in COLS:
            s = _lambda_series(rows, g, pick) if prov == "Lambda" else gpu_rent._series(rows, prov, g, pick)
            d_now, now = gpu_rent._at(s, day)
            d_then, then = gpu_rent._at(s, prev)
            base = None
            if not d_then and s and min(s) < (d_now or day):   # 추적 첫 주 — 시작일 대비
                d_then, then, base = min(s), s[min(s)], min(s)
            cells[label] = {"now": now, "then": then, "wk": gpu_rent._chg(now, then) if d_then else None, "day": d_now, "base": base}
        if any(c["now"] is not None for c in cells.values()):
            out.append({"gpu": g, **cells})
    moved = [(r["gpu"], k, r[k]["wk"]) for r in out for k, *_ in COLS if r[k]["wk"] not in (None, 0.0)]
    compared = sum(1 for r in out for k, *_ in COLS if r[k]["wk"] is not None)
    bases = sorted({r[k]["base"] for r in out for k, *_ in COLS if r[k].get("base")})
    return {"as_of": day, "prev": prev, "rows": out, "moved": moved, "compared": compared, "base": bases[0] if bases else None}


def status(now=None):
    """Pulse 관문 — 월요일 06:00 이후, 이번 주 미완료면 due"""
    now = now or common.now_kst()
    st = common.load_state(STATE, {})
    if now.weekday() != 0 or now.hour < HOUR or st.get("done") == week_key(now):
        return {"due": False}
    try:
        t = table(now.date().isoformat())
    except Exception as e:
        return {"due": False, "error": type(e).__name__}
    if not t["rows"]:
        return {"due": False, "error": "시세 없음"}
    return {"due": True, "week": week_key(now), **t, "preview": message(t, "")}


def _cell(c):
    if c["now"] is None:
        return None
    if c["wk"] is None:
        return f"${c['now']:.2f}(전주 값 없음)"
    wk = "변화 없음" if c["wk"] == 0 else f"{c['wk']:+.1f}%"
    return f"${c['now']:.2f}({wk})"


def _md(d):
    return date.fromisoformat(d).strftime("%m/%d")


def message(t, read):
    """텔레그램 본문 — 결론(풀이) → GPU별 한 줄. 표는 휴대폰에서 깨져서 줄글로"""
    d0 = date.fromisoformat(t["as_of"])
    since = t.get("base") or t["prev"]
    head = f"[Chiip Pulse] GPU 렌털료 주간 점검 ({_md(since)} → {d0.strftime('%m/%d')})"
    if t["moved"]:
        moved = "움직인 곳: " + ", ".join(f"{g} {k} {v:+.1f}%" for g, k, v in t["moved"][:6])
    elif t.get("compared"):
        moved = "전주 대비 모든 가격 변화 없음"
    else:
        moved = "비교할 전주 값이 아직 없다"
    if t.get("base"):
        moved += f" (추적 첫 주라 {_md(t['base'])} 대비)"
    lines = [head, "", moved]
    if read:
        lines += ["", read.strip()]
    lines.append("")
    for r in t["rows"]:
        parts = [f"{k} {_cell(r[k])}" for k, *_ in COLS if _cell(r[k])]
        lines.append(f"{r['gpu']}: " + " · ".join(parts))
    lines += ["", "단위 $/GPU·시. CoreWeave 스팟은 변동가, 지수는 Silicon Data 공개 지수, 나머지는 온디맨드 정가다. Nebius 선점형은 스팟 하한이라 비교에서 뺐다."]
    return "\n".join(lines)


def send(path, now=None, deliver=None):
    now = now or common.now_kst()
    read = (json.loads(Path(path).read_text(encoding="utf-8")).get("read") or "").strip()
    if not read:
        raise ValueError("read(풀이) 없음")
    if len(read) > READ_MAX:
        raise ValueError(f"read {len(read)}자 — {READ_MAX}자 이내")
    t = table(now.date().isoformat())
    text = message(t, read)
    if deliver is None:
        import notify
        deliver = lambda s: notify.send(s, "P2")
    ok = deliver(text)
    if ok:
        st = common.load_state(STATE, {})
        st["done"] = week_key(now)
        st["sent_at"] = common.iso(now)
        common.save_state(STATE, st)
    return {"sent": bool(ok), "text": text}


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if "--status" in argv:
        print(json.dumps(status(), ensure_ascii=False, indent=1, default=str))
    elif "--send" in argv:
        print(json.dumps(send(argv[argv.index("--send") + 1]), ensure_ascii=False, indent=1))
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
