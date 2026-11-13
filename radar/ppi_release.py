"""BLS PPI 발표 직후 수집·개정 기록·알림 (마스터 지시 2026-11-13 "고쳐라" — 10월 PPI가 22:30 발표됐는데 하루 늦게 들어왔다)

결정론(모델 없음). run_hourly가 10분마다 부르지만, 실제로는 knowledge/calendar.csv의 'BLS PPI' 발표일에만
발표 시각(08:30 ET = KST 22:30, 미국 서머타임 21:30) + 10분 뒤부터 새 달이 들어올 때까지(최대 발표 뒤 3시간) BLS API만 묻는다.
  ① config/trade_ppi.yaml의 미국 PPI 시계열 + 최종 수요(WPUFD4)를 BLS API로 받는다(한 번 호출, 키 있으면 v2)
  ② knowledge/models/trade_ppi/history.json·latest.json의 미국 값을 갱신한다 — 이미 있던 달의 값이 바뀌면 '개정'으로
     history["revisions"]에 이전 값을 남기고 latest의 그 칸에 revision 필드를 단다(trade_ppi.run 일일 회차도 같은 함수로 개정을 남긴다)
  ③ 새 달이 들어오면 inbox src-ppi-release 한 건(한두 문장: 최종 수요와 핵심 품목 전월·전년 대비, 직전 달 개정) → Pulse·다음 Portfolio Daily
일일 trade-ppi 회차(1440분)는 그대로 둔다. 발표 일정 원천: bls.gov/schedule/news_release/ppi.htm(자동 접근은 403 — 사람이 읽어 calendar.csv에 적고, 해마다 갱신).
"""
import csv
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402
import trade_ppi  # noqa: E402

CAL = common.ROOT / "knowledge" / "calendar.csv"
STATE = "ppi_release"
FINAL_DEMAND = "WPUFD4"
KEY_SERIES = {FINAL_DEMAND: "최종 수요", "PCU334413334413": "반도체", "PCU334412334412": "PCB", "PCU335311335311": "변압기", "PCU335313335313": "개폐기"}
AFTER_MIN, GIVE_UP_H = 10, 3


def us_dst(d):
    """미국 서머타임(3월 둘째 일요일 ~ 11월 첫 일요일) — tzdata 없이"""
    def nth_sunday(y, m, n):
        first = date(y, m, 1)
        return first + timedelta(days=(6 - first.weekday()) % 7 + 7 * (n - 1))
    return nth_sunday(d.year, 3, 2) <= d < nth_sunday(d.year, 11, 1)


def release_kst(d):
    """08:30 ET 발표의 KST 시각"""
    h = 21 if us_dst(d) else 22
    return datetime(d.year, d.month, d.day, h, 30, tzinfo=common.KST)


def releases(event="BLS PPI"):
    """calendar.csv의 발표일(KST 날짜) — event는 'BLS PPI'·'BLS CPI' 등(cpi_release.py도 쓴다)"""
    if not CAL.exists():
        return []
    with CAL.open(encoding="utf-8", newline="") as f:
        return [date.fromisoformat(r["date"]) for r in csv.DictReader(f) if r.get("entity_or_event") == event and r.get("date")]


def window(now):
    """지금 BLS를 물어야 하는 발표일(KST 날짜 기준) 또는 None"""
    for d in releases():
        t = release_kst(d)
        if t + timedelta(minutes=AFTER_MIN) <= now <= t + timedelta(hours=GIVE_UP_H):
            return d
    return None


def series_ids(cfg):
    return sorted({v["ppi"]["us"] for v in cfg["inputs"].values() if v["ppi"].get("us")} | {FINAL_DEMAND})


def record_revisions(old, new, at, label="us"):
    """old·new = {시계열: {YYYYMM: 값}} → 바뀐 칸 [{series, period, old, new, at}]"""
    out = []
    for sid, s in new.items():
        for p, v in s.items():
            o = (old.get(sid) or {}).get(p)
            if o is not None and abs(o - v) > 1e-9:
                out.append({"series": sid, "market": label, "period": p, "old": o, "new": v, "at": at})
    return out


def _mom(s, p):
    keys = sorted(k for k in s if k < p)
    return s[p] / s[keys[-1]] - 1 if keys and s.get(keys[-1]) else None


def summary(us, revs, month):
    """한두 문장 — 숫자를 늘어놓지 않는다"""
    def pc(x):
        return "미확인" if x is None else f"{x * 100:+.1f}%"
    fd = us.get(FINAL_DEMAND) or {}
    prev_y = f"{int(month[:4]) - 1}{month[4:]}"   # 'YYYY-MM'
    head = f"미국 {int(month[5:])}월 PPI가 나왔다 — 최종 수요는 전월 대비 {pc(_mom(fd, month))}, 전년 대비 {pc(fd[month] / fd[prev_y] - 1 if fd.get(month) and fd.get(prev_y) else None)}다."
    moves = []
    for sid, name in KEY_SERIES.items():
        s = us.get(sid) or {}
        if sid == FINAL_DEMAND or month not in s:
            continue
        m = _mom(s, month)
        if m is not None:
            moves.append((abs(m), f"{name} {pc(m)}"))
    moves = [t for _, t in sorted(moves, reverse=True)[:2]]
    tail = (" 핵심 품목은 전월 대비 " + "·".join(moves) + "로 가장 크게 움직였다.") if moves else ""
    rv = [r for r in revs if r["series"] in KEY_SERIES]
    if rv:
        r = max(rv, key=lambda r: abs(r["new"] / r["old"] - 1))
        tail += f" 직전 달 {KEY_SERIES[r['series']]}는 {r['old']:g} → {r['new']:g}로 개정됐다."
    return head + tail


def update_us(now=None, cfg=None, fetch=None):
    """BLS만 받아 미국 PPI를 갱신 — (새 달, 개정 목록, 요약) 또는 (None, 개정, None)"""
    now, cfg = now or common.now_kst(), cfg or trade_ppi.config()
    fetch = fetch or (lambda ids: trade_ppi.ppi_bls(ids, now.date(), common.load_env().get("BLS_API_KEY")))
    us = fetch(series_ids(cfg))
    hist = json.loads(trade_ppi.HISTORY.read_text(encoding="utf-8")) if trade_ppi.HISTORY.exists() else {"inputs": {}}
    old_us = dict(hist.setdefault("us_raw", {}))
    for k, v in cfg["inputs"].items():   # 처음 실행 때는 일일 회차가 입력별로 쌓은 미국 값을 기준으로 개정을 잰다
        sid = v["ppi"].get("us")
        if sid and sid not in old_us and ((hist.get("inputs") or {}).get(k) or {}).get("ppi", {}).get("us"):
            old_us[sid] = hist["inputs"][k]["ppi"]["us"]
    before = max((p for s in old_us.values() for p in s), default="")
    revs = record_revisions(old_us, us, common.iso(now))
    hist["us_raw"] = {**old_us, **{k: v for k, v in us.items() if v}}
    hist.setdefault("revisions", []).extend(revs)
    for k, v in cfg["inputs"].items():   # 입력별 미국 칸도 같은 값으로
        sid = v["ppi"].get("us")
        if sid and us.get(sid):
            hist["inputs"].setdefault(k, {"ppi": {}, "trade": {}})["ppi"]["us"] = us[sid]
    trade_ppi.HISTORY.write_text(json.dumps(hist, ensure_ascii=False), encoding="utf-8")
    latest = trade_ppi.load()
    for k, v in (latest.get("inputs") or {}).items():
        sid = cfg["inputs"].get(k, {}).get("ppi", {}).get("us")
        if sid and us.get(sid):
            m = trade_ppi.ppi_metric(us[sid])
            r = [x for x in revs if x["series"] == sid]
            if r:
                m["revision"] = {"period": r[-1]["period"], "old": r[-1]["old"], "new": r[-1]["new"]}
            v.setdefault("ppi", {})["us"] = m
    if latest:
        latest["us_updated_at"] = common.iso(now)
        trade_ppi.LATEST.write_text(json.dumps(latest, ensure_ascii=False, indent=1), encoding="utf-8")
    after = max((p for s in us.values() for p in s), default="")
    month = after if after > before else None
    return month, revs, summary(us, revs, month) if month else None


def run(now=None):
    now = now or common.now_kst()
    d = window(now)
    if not d:
        return "발표 창 아님"
    st = common.load_state(STATE, {})
    if st.get("done") == d.isoformat():
        return f"{d} 발표분 이미 반영"
    month, revs, text = update_us(now)
    if not month:
        common.record_health("ppi-release", True, None)
        return f"{d} 발표 창 — 아직 새 달 없음(개정 {len(revs)}건), 다음 회차에 다시"
    item = common.make_item("src-ppi-release", f"ppi:{month}", "https://www.bls.gov/ppi/", f"[지표 발표] 미국 PPI {month}", common.iso(now),
                            "지표", "ko", text, extra={"tier": "T1", "kind": "ppi_release", "revisions": revs[:10]})
    common.save_new_items([item])
    st["done"] = d.isoformat()
    st["last"] = {"month": month, "at": common.iso(now), "text": text, "revisions": len(revs)}
    common.save_state(STATE, st)
    common.record_health("ppi-release", True, None)
    return f"PPI {month} 반영 · 개정 {len(revs)}건 · {text}"


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if "--now" in sys.argv:   # 발표 창과 무관하게 지금 BLS를 받아 반영(수동)
        m, r, t = update_us()
        print(json.dumps({"month": m, "revisions": r, "text": t}, ensure_ascii=False, indent=1))
    else:
        print(run())
