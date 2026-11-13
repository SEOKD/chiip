"""BLS CPI 발표 직후 수집·개정 기록·알림 (마스터 지시 2026-11-13 "만들어라" — ppi_release.py와 같은 구조)

결정론(모델 없음). run_hourly 10분 — knowledge/calendar.csv 'BLS CPI' 발표일에만 발표(08:30 ET = KST 22:30, 미국 서머타임 21:30) 10분 뒤부터 3시간 BLS API만 묻는다.
시계열(근거: 포트폴리오 노출 — 전력·데이터센터 종목은 전기요금, 클럽·소비재는 주거·외식·여가, 금리 경로는 근원):
  전월 대비는 계절조정(CUSR), 전년 대비는 원계열(CUUR) — BLS 보도자료 관행과 같다.
실패하면 값을 지어내지 않는다(fail-closed): 상태에 '공백·이유'를 남기고 health 실패로 적는다.
저장: knowledge/models/macro/cpi.json {as_of, raw: {시계열: {YYYY-MM: 값}}, revisions: [...]}
"""
import json
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402
import ppi_release as pr  # noqa: E402
import trade_ppi  # noqa: E402

OUT = common.ROOT / "knowledge" / "models" / "macro" / "cpi.json"
STATE = "cpi_release"
EVENT = "BLS CPI"
SERIES = {   # 이름: (계절조정 — 전월 대비, 원계열 — 전년 대비)
    "헤드라인": ("CUSR0000SA0", "CUUR0000SA0"),
    "근원(식품·에너지 제외)": ("CUSR0000SA0L1E", "CUUR0000SA0L1E"),
    "전기요금": ("CUSR0000SEHF01", "CUUR0000SEHF01"),
    "주거비": ("CUSR0000SAH1", "CUUR0000SAH1"),
    "중고차": ("CUSR0000SETA02", "CUUR0000SETA02"),
    "항공료": ("CUSR0000SETG01", "CUUR0000SETG01"),
    "여가 서비스": ("CUSR0000SARS", "CUUR0000SARS"),   # Analysis 판매가 비교용(2026-11-13 — 회원제 클럽·여가 소비재)
    "클럽 회비·스포츠 참가비": ("CUSR0000SERF01", "CUUR0000SERF01"),
}
KEY_ITEMS = ("전기요금", "주거비", "중고차", "항공료")


def ids():
    return sorted({s for pair in SERIES.values() for s in pair})


def window(now):
    for d in pr.releases(EVENT):
        t = pr.release_kst(d)
        if t + timedelta(minutes=pr.AFTER_MIN) <= now <= t + timedelta(hours=pr.GIVE_UP_H):
            return d
    return None


def changes(raw, name, month):
    """(전월 대비, 전년 대비) — 값이 없으면 None"""
    sa, nsa = SERIES[name]
    s, n = raw.get(sa) or {}, raw.get(nsa) or {}
    keys = sorted(k for k in s if k < month)
    mom = s[month] / s[keys[-1]] - 1 if month in s and keys and s.get(keys[-1]) else None
    prev = f"{int(month[:4]) - 1}{month[4:]}"
    yoy = n[month] / n[prev] - 1 if n.get(month) and n.get(prev) else None
    return mom, yoy


def summary(raw, month, revs):
    pc = lambda x: "미확인" if x is None else f"{x * 100:+.1f}%"
    h, c = changes(raw, "헤드라인", month), changes(raw, "근원(식품·에너지 제외)", month)
    yo = lambda x: "전년 같은 달 값이 없어 전년 대비는 계산 불가" if x is None else f"전년 대비 {pc(x)}"   # 2025-10은 BLS 미발표(연방정부 셧다운)
    text = f"미국 {int(month[5:])}월 CPI가 나왔다 — 헤드라인은 전월 대비 {pc(h[0])}({yo(h[1])}), 근원은 전월 대비 {pc(c[0])}({yo(c[1])})다."
    moves = sorted(((abs(m), f"{k} {pc(m)}") for k in KEY_ITEMS for m in [changes(raw, k, month)[0]] if m is not None), reverse=True)[:2]
    if moves:
        text += " 포트폴리오 관련 품목은 전월 대비 " + "·".join(t for _, t in moves) + "가 가장 크게 움직였다."
    head = [r for r in revs if r["series"] in SERIES["헤드라인"] + SERIES["근원(식품·에너지 제외)"]]
    if head:
        r = head[-1]
        text += f" 직전 달 지수는 {r['old']:g} → {r['new']:g}로 개정됐다."
    return text   # 컨센서스는 공개 무료 원천이 없어 비교하지 않는다(있으면 붙인다)


def load():
    return json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"raw": {}, "revisions": []}


def update(now=None, fetch=None):
    now = now or common.now_kst()
    fetch = fetch or (lambda s: trade_ppi.ppi_bls(s, now.date(), common.load_env().get("BLS_API_KEY")))
    raw = fetch(ids())
    if not any(raw.values()):
        raise RuntimeError("BLS CPI 응답이 비었다")
    doc = load()
    before = max((p for s in doc["raw"].values() for p in s), default="")
    revs = pr.record_revisions(doc["raw"], raw, common.iso(now))
    doc["raw"] = {**doc["raw"], **{k: v for k, v in raw.items() if v}}
    doc["revisions"] = (doc.get("revisions") or []) + revs
    doc["as_of"] = common.iso(now)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    after = max((p for s in raw.values() for p in s), default="")
    month = after if after > before else None
    return month, revs, summary(doc["raw"], month, revs) if month else None


def run(now=None):
    now = now or common.now_kst()
    d = window(now)
    if not d:
        return "발표 창 아님"
    st = common.load_state(STATE, {})
    if st.get("done") == d.isoformat():
        return f"{d} 발표분 이미 반영"
    try:
        month, revs, text = update(now)
    except Exception as exc:   # fail-closed — 값을 지어내지 않고 공백·이유만
        st["gap"] = {"at": common.iso(now), "why": f"{type(exc).__name__}: {str(exc)[:120]}"}
        common.save_state(STATE, st)
        common.record_health("cpi-release", False, st["gap"]["why"])
        return f"CPI 수집 실패 — {st['gap']['why']}"
    if not month:
        common.record_health("cpi-release", True, None)
        return f"{d} 발표 창 — 아직 새 달 없음(개정 {len(revs)}건)"
    common.save_new_items([common.make_item("src-cpi-release", f"cpi:{month}", "https://www.bls.gov/cpi/", f"[지표 발표] 미국 CPI {month}", common.iso(now),
                                            "지표", "ko", text, extra={"tier": "T1", "kind": "cpi_release", "revisions": revs[:10]})])
    st.update({"done": d.isoformat(), "gap": None, "last": {"month": month, "at": common.iso(now), "text": text}})
    common.save_state(STATE, st)
    common.record_health("cpi-release", True, None)
    return f"CPI {month} 반영 · 개정 {len(revs)}건 · {text}"


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if "--now" in sys.argv:
        m, r, t = update()
        print(json.dumps({"month": m, "revisions": len(r), "text": t or summary(load()["raw"], max(p for s in load()["raw"].values() for p in s), [])}, ensure_ascii=False, indent=1))
    else:
        print(run())
