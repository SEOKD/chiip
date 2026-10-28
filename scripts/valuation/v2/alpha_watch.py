"""핵심 루프 (마스터 지시 2026-10-28): 실시간 정보 → 알파 잠재력 ≥ 기준 감지 → v2 밸류에이션 → 3요인 텔레그램

감지(결정론, 모델 호출 없음):
  ① 텔레그램으로 나간 P0·P1 알림(radar/state/alerts.json — 실적·보도자료·공시·정책 등)의 종목이 알파 기준 이상
  ② 알파 점수가 새로 기준 이상으로 올라옴(첫 실행은 기준선만 저장 — 소급 알림 없음)
  ③ 알파 기준 이상 종목의 실적 발표일·다음 날(knowledge/models/earnings/upcoming.json)
  ④ 레이더 inbox의 실적·공시·보도자료(텔레그램 등급과 무관) — 알파 점수가 없는 감시 종목이면 '알파 산정' 대기열
처리: 종목 동인(knowledge/models/companies/<id>/drivers.yaml)이 있으면 v2 실행 → 3요인 텔레그램(⭐ 노션 버튼).
      동인이 없거나 오래됐거나(drivers_stale_days) 실적 뒤면 radar/state/v2_queue.json에 올려 예약 작업
      chiip-valuation-queue(모델)가 동인을 작성·갱신한 뒤 `--entity <id> --send`로 다시 부른다.
같은 종목은 하루 한 번(P0 알림은 예외). 투자자문 아님 — 지표·확률만 보낸다.
사용: py scripts/valuation/v2/alpha_watch.py [--dry]           # 감지만 출력
      py scripts/valuation/v2/alpha_watch.py --entity co-innio --send [--reason "..."]
"""
import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "radar"))
sys.path.insert(0, str(ROOT / "scripts" / "alpha"))
from pollers import common  # noqa: E402

STATE = "alpha_watch"
QUEUE = common.STATE / "v2_queue.json"
DISCLAIMER = "투자자문 아님 — 판단을 돕는 정량 지표이며 매수·매도 권유가 아님"


def cfg():
    return yaml.safe_load((ROOT / "config" / "valuation_v2.yaml").read_text(encoding="utf-8"))


def drivers_path(eid):
    return ROOT / "knowledge" / "models" / "companies" / eid / "drivers.yaml"


def _ts(s):
    try:
        return datetime.fromisoformat(str(s))
    except ValueError:
        return None


EVENT_TYPES = ("실적", "공시", "보도자료")


def recent_items(since, now):
    """radar/inbox의 오늘·어제 폴더에서 since 이후 수집된 실적·공시·보도자료 항목"""
    out = []
    for k in range(2):
        day = common.INBOX / (now - timedelta(days=k)).strftime("%Y%m%d")
        if not day.exists():
            continue
        for f in day.glob("*.json"):
            try:
                it = json.loads(f.read_text(encoding="utf-8"))
            except ValueError:
                continue
            t = _ts(it.get("detected_at"))
            if t and t > since and it.get("doc_type") in EVENT_TYPES:
                out.append(it)
    return out


def detect(now, st, passed, alerts, events, c, items=None):
    """{id: [이유...]} 와 P0 포함 종목 집합. items: 실적·공시·보도자료 수집 항목(텔레그램 등급과 무관하게 직접 감지)"""
    out, p0 = {}, set()
    since = _ts(st.get("last_run")) or (now - timedelta(hours=c["lookback_hours"]))
    for it in items or []:
        for e in it.get("entities_matched") or []:
            if e in passed:
                out.setdefault(e, []).append(f"{it['doc_type']}: {it.get('title', '')[:90]}")
    for a in alerts.values():
        t = _ts(a.get("sent_at"))
        if not t or t <= since or a.get("level") not in c["levels"]:
            continue
        for e in a.get("entities") or []:
            if e in passed:
                what = (a.get("what") or a.get("title") or "").replace("\n", " ")
                out.setdefault(e, []).append(f"{a['level']} {a.get('doc_type') or ''}: {what[:90]}")
                if a["level"] == "P0":
                    p0.add(e)
    seen = st.get("alpha_seen")
    if seen is not None:
        for e, total in passed.items():
            if e not in seen:
                out.setdefault(e, []).append(f"알파 {total:.1f} 기준 진입")
    today = now.date()
    window = {(today - timedelta(days=k)).isoformat() for k in range(c["earnings_days_after"] + 1)}
    for ev in events:
        if ev["id"] in passed and ev["date"] in window:
            out.setdefault(ev["id"], []).append(f"실적 발표({ev['date']} {ev.get('time_kst') or ''})".strip())
    return out, p0


def load_queue():
    return json.loads(QUEUE.read_text(encoding="utf-8")) if QUEUE.exists() else []


def enqueue(eid, name, reason, kind):
    q = load_queue()
    if any(x["id"] == eid and x["kind"] == kind for x in q):
        return False
    q.append({"id": eid, "name": name, "kind": kind, "reason": reason, "added": common.iso(common.now_kst())})
    QUEUE.write_text(json.dumps(q, ensure_ascii=False, indent=1), encoding="utf-8")
    return True


def needs_update(eid, reasons, c, today):
    """(작성 필요 종류 또는 None). 동인 없음 → '작성', 오래됨·실적 뒤 → '갱신'"""
    p = drivers_path(eid)
    if not p.exists():
        return "작성"
    co = yaml.safe_load(p.read_text(encoding="utf-8"))
    as_of = str(co.get("as_of", ""))
    try:
        age = (today - date.fromisoformat(as_of)).days
    except ValueError:
        return "갱신"
    if age > c["drivers_stale_days"]:
        return "갱신"
    if any(r.startswith("실적 발표") for r in reasons):
        ev_dates = [r.split("(")[1][:10] for r in reasons if r.startswith("실적 발표")]
        if any(d >= as_of for d in ev_dates):
            return "갱신"
    return None


def message(r, name, alpha_total, reasons, update_note=None):
    import decision
    L = [f"[알파 감지] {name} — 알파 {alpha_total:.1f}" if alpha_total is not None else f"[알파 감지] {name}"]
    L += [f"· 근거: {x}" for x in reasons[:3]]
    if r.get("decision"):
        L += decision.lines(r["decision"])
    u = r["upside"]
    if u.get("implied_cagr") is not None:
        pct = u["implied_pct"][0]
        L.append(f"시장 내포 5년 매출 CAGR {u['implied_cagr']:.0%}" + (f"(기저율 상위 {100 - pct:.0f}%)" if pct is not None else ""))
    L.append(f"가정: 동인 {r.get('drivers_as_of') or '미상'} · 시가 {r['market'].get('date', '미상')} · WACC {r['coc']['wacc']:.1%} · 몬테카를로 {u.get('n', 0):,}회")
    if not r.get("ronic_spread"):
        L.append("보수 가정: 계속가치 RONIC=WACC(장기 성장의 가치 0)·장기 마진 페이드 — 해자 큰 기업은 과소평가될 수 있음(종목별 스프레드는 백테스트로 보정 예정)")
    if update_note:
        L.append(update_note)
    L.append(DISCLAIMER)
    return "\n".join(L)


def evaluate_and_send(eid, reasons, alpha_total, send, c_all, update_note=None):
    import run as v2run
    r = v2run.evaluate(eid, c_all["decision"]["watch_draws"])
    text = message(r, r["name"], alpha_total, reasons, update_note)
    od = ROOT / "outputs" / "invest" / "valuation_v2"
    od.mkdir(parents=True, exist_ok=True)
    (od / f"{common.now_kst().strftime('%Y%m%d')}_{eid}.md").write_text(v2run.render(r), encoding="utf-8")
    sent = False
    if send:
        import notify
        item = {"item_id": f"v2:{eid}:{common.now_kst().strftime('%Y%m%d%H')}", "title": f"[알파 감지] {r['name']}",
                "url": "", "doc_type": "밸류에이션", "entities_matched": [eid], "source_id": "src-alpha-watch",
                "published_at": common.iso(common.now_kst())}
        ref = notify.remember_alert(item, "ALPHA", what=f"{r['name']} 알파 감지 3요인", impact=" / ".join(reasons[:2]))
        sent = notify.send(text, "ALPHA", ref=ref)
    return text, sent


def run(send=True, now=None):
    """run_hourly용 — (감지 수, 발송 수, 대기열 추가 수)"""
    import score as alpha
    c_all = cfg()
    c = c_all["alpha_watch"]
    now = now or common.now_kst()
    st = common.load_state(STATE, {})
    passed, rows = alpha.load_latest(now.date())
    alerts = common.load_state("alerts", {})
    up = ROOT / "knowledge" / "models" / "earnings" / "upcoming.json"
    events = json.loads(up.read_text(encoding="utf-8"))["events"] if up.exists() else []
    since = _ts(st.get("last_run")) or (now - timedelta(hours=c["lookback_hours"]))
    items = recent_items(since, now)
    found, p0 = detect(now, st, passed, alerts, events, c, items)
    evaluated = st.get("evaluated", {})
    n_sent = n_q = 0
    # 알파 점수가 없는 감시 종목에 실적·공시가 나오면 점수부터(모델) — 점수가 5 이상이면 그다음 동인·3요인
    import gate_ids
    for it in items:
        for e in it.get("entities_matched") or []:
            if e in gate_ids.watch() and (rows.get(e) or {}).get("total") is None:
                n_q += enqueue(e, e, f"{it['doc_type']}: {it.get('title', '')[:90]}", "알파 산정")
    for eid, reasons in found.items():
        if evaluated.get(eid) == now.date().isoformat() and eid not in p0:
            continue
        name = (rows.get(eid) or {}).get("name", eid)
        kind = needs_update(eid, reasons, c, now.date())
        if kind == "작성":
            n_q += enqueue(eid, name, " / ".join(reasons), "작성")
            continue
        note = None
        if kind == "갱신":
            n_q += enqueue(eid, name, " / ".join(reasons), "갱신")
            note = "※ 동인이 이번 정보 이전 가정 — 모델이 갱신 후 다시 보냄"
        try:
            _, sent = evaluate_and_send(eid, reasons, passed.get(eid), send, c_all, note)
            n_sent += bool(sent)
            evaluated[eid] = now.date().isoformat()
        except Exception as exc:
            common.record_health("src-alpha-watch", False, f"{eid}: {type(exc).__name__}: {exc}")
    st.update({"last_run": common.iso(now), "alpha_seen": {k: v for k, v in passed.items()},
               "evaluated": {k: v for k, v in evaluated.items() if v >= (now.date() - timedelta(days=7)).isoformat()}})
    common.save_state(STATE, st)
    common.record_health("src-alpha-watch", True, None)
    return len(found), n_sent, n_q


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--entity")
    ap.add_argument("--reason", default="수동 실행")
    ap.add_argument("--send", action="store_true")
    ap.add_argument("--dry", action="store_true", help="감지만 출력(상태 저장·발송 없음)")
    a = ap.parse_args(argv)
    if a.entity:
        import score as alpha
        passed, rows = alpha.load_latest()
        total = (rows.get(a.entity) or {}).get("total")
        text, sent = evaluate_and_send(a.entity, [a.reason], total, a.send, cfg())
        print(text)
        print("발송" if sent else "(발송 안 함)")
        if a.send:   # 대기열에서 처리 완료로 제거
            q = [x for x in load_queue() if x["id"] != a.entity]
            QUEUE.write_text(json.dumps(q, ensure_ascii=False, indent=1), encoding="utf-8")
        return 0
    if a.dry:
        import score as alpha
        now = common.now_kst()
        st = common.load_state(STATE, {})
        passed, _ = alpha.load_latest(now.date())
        up = ROOT / "knowledge" / "models" / "earnings" / "upcoming.json"
        events = json.loads(up.read_text(encoding="utf-8"))["events"] if up.exists() else []
        cw = cfg()["alpha_watch"]
        since = _ts(st.get("last_run")) or (now - timedelta(hours=cw["lookback_hours"]))
        found, p0 = detect(now, st, passed, common.load_state("alerts", {}), events, cw, recent_items(since, now))
        print(f"[알파 감지(시험)] 알파 기준 이상 {len(passed)}종목 · 감지 {len(found)}")
        for e, rs in found.items():
            print(f"- {e}: {' / '.join(rs)} · 동인 {'있음' if drivers_path(e).exists() else '없음'}")
        return 0
    n, s, q = run(send=a.send)
    print(f"[알파 감지] 감지 {n} · 발송 {s} · 동인 대기열 추가 {q}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
