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
import re
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
DISCLAIMER_SHORT = "투자자문 아님"


def cfg():
    return yaml.safe_load((ROOT / "config" / "valuation_v2.yaml").read_text(encoding="utf-8"))


def drivers_path(eid):
    return ROOT / "knowledge" / "models" / "companies" / eid / "drivers.yaml"


def front(text):
    """내러티브 파일 머리(--- 사이)를 읽는다. YAML이 깨졌으면(따옴표 안 닫힘 등) 줄 단위 'key: 값'으로 읽는다 —
    한 줄 오류로 알림에 '파일 형식 오류'만 남던 문제(2026-11-08 마스터 지시 "파일 형식 오류가 뭔지 알려주고 해결")"""
    parts = text.split("\n---")
    if not text.startswith("---") or len(parts) < 2:
        return None
    head = parts[0][3:]
    try:
        fm = yaml.safe_load(head)
        if isinstance(fm, dict):
            return fm
    except yaml.YAMLError:
        pass
    fm = {}
    for line in head.splitlines():
        k, sep, v = line.partition(":")
        if not sep or not k.strip().isidentifier():
            continue
        v = v.split("  #")[0].strip()
        try:
            val = yaml.safe_load(v)
        except yaml.YAMLError:
            val = None
        fm[k.strip()] = val if isinstance(val, (dict, list, int, float)) else v
    return fm or None


def check_front(text):
    """머리가 YAML로 바로 읽히는지 — narrative-premium 스킬이 저장 직후 부른다(오류 문구, 없으면 None)"""
    parts = text.split("\n---")
    if not text.startswith("---") or len(parts) < 2:
        return "머리(--- … ---)가 없다"
    try:
        fm = yaml.safe_load(parts[0][3:])
    except yaml.YAMLError as e:
        m = getattr(e, "problem_mark", None)
        return f"YAML 오류 {m.line + 2 if m else '?'}번째 줄 — 값에 따옴표·콜론이 섞이면 값 전체를 큰따옴표로 감싸고 안쪽 따옴표는 ‘ ’로 쓴다"
    return None if isinstance(fm, dict) and fm.get("summary") else "summary가 없다"


def narrative_line(eid, today=None, stale_days=30):
    """스킬 narrative-premium 결과(knowledge/narratives/companies/<id>.md) 한 줄 — 없거나 오래되면 그렇게 적는다"""
    p = ROOT / "knowledge" / "narratives" / "companies" / f"{eid}.md"
    if not p.exists():
        return "내러티브: 작성 대기 — chiip-valuation-queue 다음 회차(08:10·18:10)가 쓴다"
    fm = front(p.read_text(encoding="utf-8"))
    if not fm:
        return "내러티브: 머리말 없음 — chiip-valuation-queue 다음 회차가 다시 쓴다"
    as_of = str(fm.get("as_of") or "")
    try:
        age = ((today or date.today()) - date.fromisoformat(as_of)).days
    except ValueError:
        age = None
    eff = fm.get("alpha_effect") or {}
    tail = ""   # 알파 보정 제안(gap·upside)은 피드에서 뺀다(2026-11-09 마스터 지시) — 값은 머리말 alpha_effect에 남는다
    stale = f" — {age}일 전, 갱신 필요" if age is not None and age > stale_days else ""
    return f"내러티브({fm.get('stage', '미판정')}·과밀 {fm.get('crowding', '미상')}): {fm.get('summary', '')}{tail} [{as_of}{stale}]"


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
            t = _ts(it.get("saved_at") or it.get("detected_at"))   # 저장 시각 기준(2026-11-01 Pulse와 같은 누락)
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


EVENT_RE = re.compile(r"실적|공시|가이던스|上方修正|下方修正|業績予想|決算|설비투자|수주|8-K")


def enqueue(eid, name, reason, kind):
    q = load_queue()
    for x in q:
        if x["id"] == eid and x["kind"] == kind:   # 이미 있으면 새 사건 이유만 덧붙이고 사건 시각을 새로 — 우선순위가 올라간다(2026-11-08 닛토보)
            if reason and reason not in x["reason"]:
                x["reason"] = f"{reason} / {x['reason']}"[:400]
                if EVENT_RE.search(reason):
                    x["event_at"] = common.iso(common.now_kst())
                QUEUE.write_text(json.dumps(q, ensure_ascii=False, indent=1), encoding="utf-8")
            return False
    row = {"id": eid, "name": name, "kind": kind, "reason": reason, "added": common.iso(common.now_kst())}
    if EVENT_RE.search(reason or ""):
        row["event_at"] = row["added"]
    q.append(row)
    QUEUE.write_text(json.dumps(q, ensure_ascii=False, indent=1), encoding="utf-8")
    return True


def priority(x, alpha, now, c=None):
    """대기열 우선순위(높을수록 먼저) — 먼저 온 순이면 적체 때 새 사건 종목이 열흘 넘게 밀린다(2026-11-08: 50건 적체, 닛토보 최고익 상향·증설 공시가 3일째 대기).
    알파 점수 + 최근 사건 가산(event_bonus, event_days일에 걸쳐 0으로) + 대기 일수 가산(age_per_day, 오래 묵은 것도 결국 나온다)"""
    q = (c or cfg()).get("queue") or {}
    s = float(alpha.get(x["id"]) or 0)
    ev = x.get("event_at")
    if ev:
        days = (now - datetime.fromisoformat(ev)).total_seconds() / 86400
        s += q.get("event_bonus", 2.0) * max(0.0, 1 - days / q.get("event_days", 5))
    s += q.get("age_per_day", 0.05) * (now - datetime.fromisoformat(x["added"])).total_seconds() / 86400
    return round(s, 2)


def ordered(now=None, c=None):
    """대기열을 우선순위 순으로 — chiip-valuation-queue가 이 순서로 처리한다(`--queue-order`)"""
    import score as alpha_mod
    _, rows = alpha_mod.load_latest()
    alpha = {k: v.get("total") for k, v in rows.items()}
    now = now or common.now_kst()
    return sorted(load_queue(), key=lambda x: -priority(x, alpha, now, c))


def prune(c, today):
    """동인이 이미 새 '작성'·'갱신' 건을 대기열에서 뺀다(리포트 회차가 동인을 먼저 쓴 경우, 2026-11-02 41건 적체). (남은 수, 뺀 수)"""
    q = load_queue()
    keep = [x for x in q if x["kind"] not in ("작성", "갱신") or needs_update(x["id"], [], c, today)]
    if len(keep) != len(q):
        QUEUE.write_text(json.dumps(keep, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(keep), len(q) - len(keep)


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
    # 2026-11-11 마스터 지시 "근거는 자세하게 풀이, 매수 매력·위험 예산·상방은 %같은 수치만, 내러티브도 자세히, 마지막 가정 부분은 제외"
    L = [f"[알파 감지] {name} — 알파 {alpha_total:.1f}" if alpha_total is not None else f"[알파 감지] {name}"]
    import notify   # 무엇을 하는 회사인지 1줄(2026-11-08 마스터 지시)
    biz = notify.company_line([r.get("entity") or ""])
    L.append(f"☞ {biz}" if biz else "☞ 기업 설명 미확인")
    L += ["", "**왜 감지됐나**"] + [f"· {explain_reason(x)}" for x in reasons[:3]]
    if r.get("decision"):
        L += [""] + factor_lines(r["decision"])
    u = r["upside"]
    if u.get("implied_cagr") is not None:
        pct = u["implied_pct"][0]
        L.append(f"주가 내포 5년 매출 성장 연 {u['implied_cagr']:.0%}" + (f"(과거 기업 상위 {100 - pct:.0f}%)" if pct is not None else ""))
    L += [""] + narrative_block(r.get("entity") or "")
    L += ["", DISCLAIMER_SHORT]
    return "\n".join(L)


def explain_reason(x):
    """감지 근거 한 줄을 풀어 쓴다 — 무엇이 나왔고 왜 알파 감지로 이어졌는지"""
    import re
    m = re.match(r"알파 ([\d.]+) 기준 진입", x)
    if m:
        return (f"알파 잠재력 점수가 {m[1]}점으로 기준(5.0)을 처음 넘었다 — 시장 관심도·내러티브 매력·펀더멘털 상하방 여지·"
                "멀티플 프리미엄을 합친 10점 만점 점수다")
    m = re.match(r"실적 발표\((.*)\)", x)
    if m:
        return f"실적 발표 직후({m[1]}) — 발표 숫자가 동인(매출·이익 가정)을 바꿀 수 있어 3요인을 다시 계산했다"
    m = re.match(r"(P0|P1) (\S*): (.*)", x)
    if m:
        lvl = "가장 중요한 실시간 알림(P0)" if m[1] == "P0" else "중요 실시간 알림(P1)"
        return f"{lvl}으로 나간 {m[2] or '소식'}: {m[3]} — 사건이 가치 입력을 바꿀 수 있어 다시 계산했다"
    m = re.match(r"(\S+): (.*)", x)
    if m:
        return f"새 {m[1]} 자료: {m[2]} — 감시 종목에 1차 자료가 들어와 다시 계산했다"
    return x


def factor_lines(d):
    """3요인을 수치만(설명 없이) — decision.lines는 리포트용 풀어 쓴 판으로 그대로 둔다"""
    a, rb, u, h = d["attractiveness"], d["risk_budget"], d["upside"], d["horizon"]
    budget = 0 if rb.get("gated") else rb["budget"]
    return [f"① 매수 매력: 연 기대수익 {a['exp_return']:+.1%} · 요구수익률 {a['ke']:.1%} 대비 {a['excess']:+.1%}p · 넘을 확률 {a['p_beat_ke']:.0%} · 안전마진 {a['margin_of_safety']:.0%}",
            f"② 위험 예산: {budget:.1%} · 하위 10% {rb['p10_loss']:+.0%} · −30% 이상 확률 {rb['p_loss_30']:.0%}",
            f"③ 상방({h}년): 평균 {u['exp_multiple']:.2f}배 · 2배↑ {u['p2']:.0%} · 3배↑ {u['p3']:.0%} · 10배↑ {u['p10']:.0%} · 상위 10% {u['p90_multiple']:.2f}배"]


def narrative_block(eid, today=None):
    """내러티브를 풀어 쓴다 — 요약 + 단계·과밀 뜻 + 프리미엄·디스카운트 요인 + 확인할 지표(knowledge/narratives/companies/<id>.md)"""
    import re
    head = narrative_line(eid, today)
    p = ROOT / "knowledge" / "narratives" / "companies" / f"{eid}.md"
    fm = front(p.read_text(encoding="utf-8")) if p.exists() else None
    if not fm:
        return ["**내러티브**", head.split(": ", 1)[-1]]
    body = p.read_text(encoding="utf-8").split("---", 2)[-1]
    stage = {"초기": "아직 소수만 말하는 이야기", "확산": "커뮤니티·IB로 퍼지는 중", "컨센서스": "시장 다수가 이미 믿는 이야기",
             "과열": "기대가 숫자를 앞선 상태", "소멸": "힘을 잃는 중"}.get(str(fm.get("stage")), "")
    crowd = {"낮음": "아직 붐비지 않음", "중간": "어느 정도 알려짐", "높음": "이미 많이 알려져 가격 반영 가능성 큼"}.get(str(fm.get("crowding")), "")
    out = ["**내러티브**", str(fm.get("summary") or ""),
           f"· 단계 {fm.get('stage', '미판정')}" + (f"({stage})" if stage else "") + f" · 과밀 {fm.get('crowding', '미상')}" + (f"({crowd})" if crowd else "")]

    def items(label):
        m = re.search(r"\*\*" + label + r"\*\*\s*\n((?:\s*\d+\..*\n?)+)", body)
        return [re.sub(r"^\s*\d+\.\s*", "", x).strip() for x in m[1].strip().splitlines()][:2] if m else []
    for lab, word in (("프리미엄 요인", "＋"), ("디스카운트 요인", "－")):
        out += [f"{word} {x}" for x in items(lab)]
    k = re.search(r"## 반증 조건·확인할 KPI\s*\n-\s*(.+)", body)
    if k:
        out.append(f"· 확인할 것: {k[1].strip()}")
    if "갱신 필요" in head:
        out.append("· " + head.rsplit("— ", 1)[-1].rstrip("]"))
    return out


def evaluate_and_send(eid, reasons, alpha_total, send, c_all, update_note=None):
    import run as v2run
    r = v2run.evaluate(eid, c_all["decision"]["watch_draws"])
    if not (ROOT / "knowledge" / "narratives" / "companies" / f"{eid}.md").exists():   # 내러티브가 없으면 작성 일을 대기열에 올린다(2026-11-07 — 대기만 표시되고 아무도 쓰지 않던 구멍)
        enqueue(eid, r.get("name") or eid, "내러티브 미작성 — 알파 감지 3요인 발송 뒤", "내러티브")
    text = message(r, r["name"], alpha_total, reasons, update_note)
    if send:   # 알파 감지 목록에 처음 오르면 리포트 이미지를 일괄로 미리 주문(가격 절반, 마스터 지시 2026-11-08) — 실패해도 알림은 간다
        try:
            sys.path.insert(0, str(ROOT / "scripts" / "tenbagger"))
            import product_images as PI
            if PI.cfg().get("batch_supported", True) and (PI.company_dir(eid) / "datapack.json").exists():   # Vertex는 버킷 전까지 일괄 불가 — 리포트 때 즉시 생성
                todo = [t for t in PI.targets_company(eid) if not PI.cached(t) and PI.budget_ok(t, True)[0]]
                if todo:
                    PI.order_batch(todo)
        except Exception as exc:
            print(f"[이미지 선주문 건너뜀] {eid}: {type(exc).__name__}")
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
    prune(c, now.date())
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
    ap.add_argument("--check-narrative", nargs="*", metavar="ID", help="내러티브 파일 머리 점검(id 없으면 전부)")
    ap.add_argument("--queue-order", action="store_true", help="동인 대기열을 우선순위 순으로 출력")
    a = ap.parse_args(argv)
    if a.queue_order:
        import score as alpha_mod
        _, rows = alpha_mod.load_latest()
        alpha = {k: v.get("total") for k, v in rows.items()}
        now = common.now_kst()
        for x in ordered(now):
            print(f"{priority(x, alpha, now):5.2f}  {x['kind']}  {x['id']}  {x['reason'][:70]}")
        return 0
    if a.check_narrative is not None:
        d = ROOT / "knowledge" / "narratives" / "companies"
        bad = 0
        for p in sorted(d.glob("*.md")) if not a.check_narrative else [d / f"{x}.md" for x in a.check_narrative]:
            err = check_front(p.read_text(encoding="utf-8")) if p.exists() else "파일 없음"
            if err:
                bad += 1
                print(f"[내러티브 머리] {p.stem}: {err}")
        print(f"[내러티브 머리] 오류 {bad}건")
        return 1 if bad else 0
    if a.entity:
        import score as alpha
        passed, rows = alpha.load_latest()
        total = (rows.get(a.entity) or {}).get("total")
        text, sent = evaluate_and_send(a.entity, [a.reason], total, a.send, cfg())
        print(text)
        print("발송" if sent else "(발송 안 함)")
        if a.send:   # 대기열에서 처리 완료로 제거 + 오늘 처리함으로 기록(매시간 루프의 같은 날 중복 발송 방지)
            q = [x for x in load_queue() if x["id"] != a.entity]
            QUEUE.write_text(json.dumps(q, ensure_ascii=False, indent=1), encoding="utf-8")
            st = common.load_state(STATE, {})
            st.setdefault("evaluated", {})[a.entity] = common.now_kst().date().isoformat()
            if total is not None and total >= 5.0:
                st.setdefault("alpha_seen", {})[a.entity] = total
            common.save_state(STATE, st)
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
