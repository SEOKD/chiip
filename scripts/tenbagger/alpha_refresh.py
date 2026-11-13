"""알파 상승 리포트 갱신 대기열 (마스터 지시 2026-11-13 "이미 Analysis 리포트를 쓴 종목의 알파가 마지막 리포트 시점 대비 +1.0 이상
오르면 리포트 갱신 대기열에 등록", 설계 근거 docs/decisions/ADR-022-alpha-report-refresh.md) — 결정론, 글은 모델

기준 알파 = 종목별 최신 리포트 JSON의 verdict.alpha(발행 때 latest.json 값이 기록된다). 없으면 그 날짜까지의 판단 파일로 재구성
(관심 요소 제외 — 이때는 현재 값도 같은 방식으로 재서 비교한다).
등록 조건(모두):
  ① 상승 = 현재 알파 − 기준 알파 − 동시 재산정 쏠림(같은 날 10종목 이상 재산정되고 그 중앙 변화가 +0.5 이상이면 그 중앙값) ≥ RISE(+1.0)
  ② 최소 간격: 마지막 리포트(정기·갱신·실적 업데이트 모두)에서 MIN_GAP_DAYS(14일) 이상
  ③ 유지: 처음 충족한 산정(scored_on) 다음 산정에서도 ①이 유지되거나, 다음 산정 없이 HOLD_DAYS(7일)가 지나도 그대로(주 1회 전체 산정 주기)
  처음 충족 = '관찰'(알파 감지 메시지에 표시), ③ 통과 = '대기'(등록).
처리 순서(예약 작업 chiip-tenbagger-report, 정기 리포트·이미지 예산 우선):
  하루 DAILY_MAX(1)건, 그날 마지막 회차(20시 이후) 또는 정기 후보가 없을 때만, 이번 달 이미지 지출이 한도의 IMAGE_RESERVE(80%)
  이하이고 월 진행률 대비 앞서지 않을 때만. 실적 업데이트·전문 반영 재발행(report_refresh.py)이 먼저다.
갱신 리포트 = 새 파일(오늘 날짜 stem) + 맨 앞 '갱신 사유' 절(이전 판 링크·핵심 수치 비교) — `--inject <새 json>`이 넣는다.
GitHub+노션 동시 게시는 publish_tenbagger.py 그대로, 텔레그램은 `send … --update`(머리 '갱신').
상태: outputs/tenbagger/reports/alpha_refresh.json
사용: py scripts/tenbagger/alpha_refresh.py --scan            # 상태 갱신(알파 감지 매시간 루프가 부른다)
      py scripts/tenbagger/alpha_refresh.py --status          # 관찰·대기·완료 목록
      py scripts/tenbagger/alpha_refresh.py --due [--force-window]   # 지금 처리할 1건(없으면 [])
      py scripts/tenbagger/alpha_refresh.py --start <id>      # 처리 시작 — 이전 판 정보(JSON)
      py scripts/tenbagger/alpha_refresh.py --inject <새 json> <id>   # 새 리포트 맨 앞에 '갱신 사유' 절
      py scripts/tenbagger/alpha_refresh.py --done <id> <새 stem>
"""
import csv
import json
import statistics
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REP = ROOT / "outputs" / "tenbagger" / "reports"
STATE_FILE = REP / "alpha_refresh.json"
DELIVERY = REP / "delivery"
KST = timezone(timedelta(hours=9))

RISE = 1.0            # 마스터 지시 값
MIN_GAP_DAYS = 14     # ADR-022: 판단 재산정 간격 중앙 9일 → 두 번의 주간 산정이 지나야 한다
HOLD_DAYS = 7         # 주 1회 전체 산정 주기 — 그동안 되돌림이 없으면 유지로 본다
COHORT_MIN = 10       # 같은 날 재산정 종목 수가 이 이상이면 쏠림(채점 기준 변화)을 뺀다
COHORT_DRIFT = 0.5
DAILY_MAX = 1
LAST_RUN_HOUR = 20    # chiip-tenbagger-report 06·13·20시 중 마지막 회차
IMAGE_RESERVE = 0.80
HEAD = "갱신 사유"

sys.path.insert(0, str(ROOT / "scripts" / "alpha"))


def now_kst():
    return datetime.now(KST)


def load(path=None):
    p = path or STATE_FILE
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"watch": {}, "queue": [], "done": []}


def save(st, path=None):
    p = path or STATE_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def latest_reports(root=REP):
    """종목(id)별 최신 리포트 log 행(날짜 최신, 같은 날이면 나중 행)"""
    log = root / "log.csv"
    if not log.exists():
        return {}
    out = {}
    with log.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r.get("id") and r.get("html") and (r["id"] not in out or r["date"] >= out[r["id"]]["date"]):
                out[r["id"]] = r
    return out


def report_json(rep, root=REP):
    p = ROOT / Path(rep["html"]).with_suffix(".json") if not Path(rep["html"]).is_absolute() else Path(rep["html"]).with_suffix(".json")
    if not p.exists():
        p = root / (Path(rep["html"]).stem + ".json")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def reconstruct(eid, day):
    """판단 파일(day 이하)로 알파 재구성 — 관심 요소 제외. 없으면 None"""
    import score
    files = sorted((score.DIR / "judgments").glob("*.csv"))
    j = {}
    for f in files:
        if f.stem[:8] > day.replace("-", ""):
            continue
        with f.open(encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                if r.get("id") != eid:
                    continue
                try:
                    s = float(r["score"])
                except (TypeError, ValueError):
                    continue
                j.setdefault(eid, {})[r["component"]] = {"score": max(0.0, min(10.0, s)), "day": f.stem}
    if not j:
        return None
    return score.combine(j, score.cfg(), social={}).get(eid, {}).get("total")


def baseline(rep, root=REP):
    """(기준 알파, 근거) — 리포트 JSON verdict.alpha 우선"""
    v = (report_json(rep, root).get("verdict") or {}).get("alpha")
    if isinstance(v, (int, float)):
        return float(v), "리포트 기록"
    r = reconstruct(rep["id"], rep["date"])
    return (r, "판단 파일 재구성(관심 요소 제외)") if r is not None else (None, "기준 없음")


def cohort_drift(rows, scored_on):
    """같은 산정일에 재산정된 종목들의 중앙 변화(쏠림). 표본이 적거나 작으면 0"""
    ds = [r["delta"] for r in rows.values() if r.get("scored_on") == scored_on and isinstance(r.get("delta"), (int, float))]
    if len(ds) < COHORT_MIN:
        return 0.0
    m = statistics.median(ds)
    return m if m >= COHORT_DRIFT else 0.0


def current(eid, basis, rows):
    """(현재 알파, scored_on)"""
    r = rows.get(eid) or {}
    if basis.startswith("판단 파일"):
        return reconstruct(eid, "99991231"), r.get("scored_on")
    return r.get("total"), r.get("scored_on")


def evaluate(eid, rep, rows, today, root=REP):
    """한 종목 판정 dict"""
    base, basis = baseline(rep, root)
    cur, scored = current(eid, basis, rows)
    out = {"id": eid, "name": (rows.get(eid) or {}).get("name", eid), "stem": Path(rep["html"]).stem, "report_date": rep["date"],
           "base_alpha": base, "basis": basis, "alpha": cur, "scored_on": scored}
    if base is None or cur is None:
        return {**out, "rise": None, "ok": False, "why": "알파 기준 또는 현재값 없음"}
    drift = cohort_drift(rows, scored)
    rise = round(cur - base - drift, 2)
    gap = (today - date.fromisoformat(rep["date"])).days
    out.update({"rise": rise, "drift": drift, "gap_days": gap})
    if rise < RISE:
        return {**out, "ok": False, "why": f"상승 {rise:+.1f} < +{RISE:.1f}"}
    if gap < MIN_GAP_DAYS:
        return {**out, "ok": False, "why": f"마지막 리포트 {gap}일 전 < {MIN_GAP_DAYS}일"}
    return {**out, "ok": True, "why": ""}


def scan(now=None, root=REP, state_path=None, rows=None):
    """관찰·대기열 갱신. (새로 관찰, 새로 등록) 수"""
    import score
    now = now or now_kst()
    today = now.date()
    if rows is None:
        _, rows = score.load_latest(today)
    st = load(state_path)
    queued = {x["id"] for x in st["queue"] if x.get("status") in ("대기", "진행")}
    done_stems = {(x["id"], x.get("from_stem")) for x in st.get("done", [])}
    n_watch = n_reg = 0
    for eid, rep in latest_reports(root).items():
        if eid in queued or (eid, Path(rep["html"]).stem) in done_stems:
            continue
        ev = evaluate(eid, rep, rows, today, root)
        w = st["watch"].get(eid)
        if not ev["ok"]:
            st["watch"].pop(eid, None)
            continue
        if not w or w.get("stem") != ev["stem"]:
            st["watch"][eid] = {**ev, "first_seen": now.isoformat(timespec="seconds"), "first_scored_on": ev["scored_on"]}
            n_watch += 1
            continue
        held = (now - datetime.fromisoformat(w["first_seen"])).days
        if ev["scored_on"] != w["first_scored_on"]:
            how = f"다음 산정({ev['scored_on']})에서도 +{ev['rise']:.1f} 유지"
        elif held >= HOLD_DAYS:
            how = f"{held}일 동안 재산정 없이 유지"
        else:
            continue
        st["queue"].append({**ev, "status": "대기", "registered": now.isoformat(timespec="seconds"), "confirmed": how,
                            "first_seen": w["first_seen"]})
        st["watch"].pop(eid, None)
        n_reg += 1
    save(st, state_path)
    return n_watch, n_reg


def alert_line(eid, state_path=None):
    """알파 감지 메시지 끝줄 — 대기열 등록·관찰 중이면 한 줄, 아니면 None"""
    st = load(state_path)
    for x in st["queue"]:
        if x["id"] == eid and x.get("status") in ("대기", "진행"):
            return (f"리포트 갱신 대기열 등록 — 마지막 리포트({x['report_date']}) 알파 {x['base_alpha']:.1f} → {x['alpha']:.1f}"
                    f"({x['confirmed']})")
    w = st["watch"].get(eid)
    if w:
        return (f"리포트 갱신 관찰 — 마지막 리포트({w['report_date']}) 알파 {w['base_alpha']:.1f} → {w['alpha']:.1f}, "
                f"다음 산정에서 유지되면 대기열 등록")
    return None


def image_ok(today=None):
    """(가능, 사유) — 이번 달 이미지 지출이 한도의 IMAGE_RESERVE 이하이고 월 진행률보다 앞서지 않을 때"""
    try:
        import product_images as PI
        c = PI.cfg()
        spent, cap = PI.month_spend(), float(c["monthly_budget_usd"])
    except Exception as exc:
        return True, f"이미지 예산 확인 불가({type(exc).__name__}) — 이미지 없이 갱신"
    today = today or date.today()
    nxt = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
    pace = today.day / (nxt - timedelta(days=1)).day
    if spent > cap * IMAGE_RESERVE:
        return False, f"이미지 지출 ${spent:.1f} > 한도 ${cap:.0f}의 {IMAGE_RESERVE:.0%} — 정기 리포트 몫"
    if spent > cap * pace:
        return False, f"이미지 지출 ${spent:.1f}가 월 진행률({pace:.0%}) 대비 앞섬"
    return True, ""


def done_today(st, today):
    return sum(1 for x in st.get("done", []) if str(x.get("at", ""))[:10] == today.isoformat())


def due(now=None, state_path=None, force_window=False, regular_left=None):
    """지금 처리할 갱신(최대 DAILY_MAX − 오늘 완료). regular_left: 오늘 남은 정기 후보 수(모르면 None = 시간 규칙만)"""
    now = now or now_kst()
    st = load(state_path)
    if done_today(st, now.date()) >= DAILY_MAX:
        return {"items": [], "why": f"오늘 갱신 {DAILY_MAX}건 완료"}
    if not force_window and now.hour < LAST_RUN_HOUR and regular_left != 0:
        return {"items": [], "why": f"정기 리포트 우선 — {LAST_RUN_HOUR}시 회차 또는 정기 후보 소진 때"}
    ok, why = image_ok(now.date())
    items = sorted((x for x in st["queue"] if x.get("status") == "대기"), key=lambda x: (-x["rise"], x["registered"]))
    return {"items": items[:max(0, DAILY_MAX - done_today(st, now.date()))], "image_ok": ok, "image_why": why}


def start(eid, state_path=None, delivery=DELIVERY):
    st = load(state_path)
    x = next((q for q in st["queue"] if q["id"] == eid and q.get("status") in ("대기", "진행")), None)
    if not x:
        raise SystemExit(f"대기열에 없음: {eid}")
    x["status"] = "진행"
    x["started"] = now_kst().isoformat(timespec="seconds")
    save(st, state_path)
    dl = {}
    p = delivery / f"{x['stem']}.json"
    if p.exists():
        dl = json.loads(p.read_text(encoding="utf-8"))
    return {**x, "prev_artifact": (dl.get("artifact") or {}).get("url"), "prev_notion": (dl.get("notion") or {}).get("page"),
            "prev_github_md": (dl.get("github") or {}).get("md")}


def _v(d, k):
    return (d.get("verdict") or {}).get(k)


def _fmt(x, kind):
    if x is None or x == "":
        return "미기재"
    if kind == "pct":
        return f"{x:+.0%}"
    if kind == "num":
        return f"{x:,.2f}" if abs(x) < 1000 else f"{x:,.0f}"
    return str(x)


def compare_rows(old, new):
    """이전 판 대비 핵심 수치 [(항목, 이전, 지금)]"""
    keys = [("알파", "alpha", "num"), ("주가", "price", "num"), ("목표주가", "target_text", "str"), ("업사이드", "upside", "pct"),
            ("다운사이드", "downside", "pct"), ("구매등급", "rating", "str"), ("손익비(강세÷약세)", "rr", "num"), ("DCF 상방", "dcf_up", "pct")]
    return [(lab, _fmt(_v(old, k), t), _fmt(_v(new, k), t)) for lab, k, t in keys if _v(old, k) is not None or _v(new, k) is not None]


def section(x, old, new, links):
    """맨 앞 '갱신 사유' 절(report JSON sections 형식)"""
    rows = compare_rows(old, new)
    link = " · ".join(f"[{k}]({v})" for k, v in links if v) or "이전 판 링크 없음"
    lead = (f"**알파가 마지막 리포트({x['report_date']}) {x['base_alpha']:.1f}에서 {x['alpha']:.1f}로 올라 다시 썼다.** "
            f"{x['confirmed']}. 기준은 {x['basis']}" + (f", 같은 날 재산정 쏠림 {x['drift']:+.1f}를 뺐다" if x.get("drift") else "") + ".")
    return {"h2": HEAD, "blocks": [{"type": "hl", "text": lead}, {"type": "p", "text": f"이전 판: {link}"},
                                   {"type": "table", "headers": ["항목", "이전 판", "이번 판"], "rows": [list(r) for r in rows]}]}


def inject(new_json, eid, state_path=None, delivery=DELIVERY, root=REP):
    st = load(state_path)
    x = next((q for q in st["queue"] if q["id"] == eid and q.get("status") == "진행"), None)
    if not x:
        raise SystemExit(f"진행 중인 갱신 없음: {eid} — --start 먼저")
    p = Path(new_json)
    new = json.loads(p.read_text(encoding="utf-8"))
    old_p = root / f"{x['stem']}.json"
    old = json.loads(old_p.read_text(encoding="utf-8")) if old_p.exists() else {}
    info = _links(x, delivery)
    sec = section(x, old, new, info)
    new["sections"] = [s for s in new.get("sections") or [] if s.get("h2") != HEAD]
    new["sections"].insert(0, sec)
    new["refresh"] = {"kind": "알파 상승 갱신", "from_stem": x["stem"], "base_alpha": x["base_alpha"], "alpha": x["alpha"]}
    p.write_text(json.dumps(new, ensure_ascii=False, indent=1), encoding="utf-8")
    return sec


def _links(x, delivery=DELIVERY):
    p = delivery / f"{x['stem']}.json"
    dl = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    # 옛 GitHub 날짜분은 prune_reports가 브랜치에서 지운다(2026-11-04) — 그래서 Artifact와 커밋 고정 GitHub 주소(blob/<커밋>/…)만 쓴다.
    # 노션은 종목당 한 페이지를 덮어쓰므로(2026-11-02) 이전 판 링크가 될 수 없다
    return [("이전 판 보기", (dl.get("artifact") or {}).get("url")), ("이전 판 GitHub(커밋 고정)", (dl.get("github") or {}).get("md"))]


def done(eid, new_stem, state_path=None, root=REP):
    st = load(state_path)
    x = next((q for q in st["queue"] if q["id"] == eid and q.get("status") == "진행"), None)
    if not x:
        raise SystemExit(f"진행 중인 갱신 없음: {eid}")
    d = json.loads((root / f"{new_stem}.json").read_text(encoding="utf-8"))
    if not d.get("sections") or d["sections"][0].get("h2") != HEAD:
        raise SystemExit(f"새 리포트 맨 앞에 '{HEAD}' 절이 없다 — --inject 먼저")
    st["queue"] = [q for q in st["queue"] if q is not x]
    st.setdefault("done", []).append({"id": eid, "from_stem": x["stem"], "to_stem": new_stem, "base_alpha": x["base_alpha"],
                                      "alpha": x["alpha"], "at": now_kst().isoformat(timespec="seconds")})
    save(st, state_path)
    return "완료"


def status(state_path=None):
    st = load(state_path)
    return {"관찰": list(st["watch"].values()), "대기열": st["queue"], "완료": st.get("done", [])[-20:]}


def candidates(today=None, root=REP, rows=None):
    """지금 ①·② 조건을 넘는 종목(관찰·등록 전, 보고용)"""
    import score
    today = today or date.today()
    if rows is None:
        _, rows = score.load_latest(today)
    return [ev for eid, rep in latest_reports(root).items() if (ev := evaluate(eid, rep, rows, today, root))["ok"]]


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    if "--scan" in argv:
        print("관찰 %d · 등록 %d" % scan())
    elif "--status" in argv:
        print(json.dumps(status(), ensure_ascii=False, indent=1))
    elif "--candidates" in argv:
        print(json.dumps(candidates(), ensure_ascii=False, indent=1))
    elif "--due" in argv:
        print(json.dumps(due(force_window="--force-window" in argv), ensure_ascii=False, indent=1))
    elif "--start" in argv:
        print(json.dumps(start(argv[argv.index("--start") + 1]), ensure_ascii=False, indent=1))
    elif "--inject" in argv:
        i = argv.index("--inject")
        print(json.dumps(inject(argv[i + 1], argv[i + 2]), ensure_ascii=False, indent=1))
    elif "--done" in argv:
        i = argv.index("--done")
        print(done(argv[i + 1], argv[i + 2]))
    else:
        print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
