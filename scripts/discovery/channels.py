"""발굴 채널 선별 — 단서 장부(leads.csv)의 채널 신호를 종목별로 모아 겹침·적신호·관문으로 거르고, 판단 카드 대기열·발굴 선별 합류·Pulse 경보를 만든다
(마스터 지시 2026-11-15 "산업·섹터 전반에서 알파가 높은 종목을 찾는 프로세스 … 월스트리트 IB 리서치 하우스의 접근 방법", 설계 knowledge/methods/discovery_engine.md)

IB식 깔때기(아이디어 → 선별 → 심층 → 위원회 → 커버리지)에서 이 모듈은 '채널 단서 → 채널 선별'까지만 한다. 판단은 모델이 판단 카드(채널 렌즈)와
위원회 메모(scripts/discovery/screen.py 경로)로 한다. 점수는 판단 보조이지 매수 권유가 아니다.
  점수 = 종목의 채널별 최고 강도 중 최댓값 + 겹침 가점(다른 채널 하나당 confluence_bonus, 상한 confluence_cap) − 적신호(국장 희석 공시·투자조합 경영권 단서)
  단계: ① 단서 → ② 채널 선별(점수 ≥ pass_min) → 판단 카드(knowledge/models/discovery/lens_cards, 채널 렌즈 knowledge/methods/sector_lenses/<렌즈>.md)
       → 카드 edge 6 이상이면 발굴 선별(screen.py)의 '② 선별 통과' 후보가 된다(펀더멘털 확보 조건은 그대로)
출력: knowledge/models/discovery/channels_latest.json(screen.py가 '채널: <이름>' 테마로 합류) · channel_alerts.json(Pulse) · outputs/discovery/channels_<날짜>.md
금지 연결: 채널 신호 → 경쟁우위·매출이 아니다. 행동주의 진입 → 요구 관철이 아니다. 구루 매입 → 주가 상승이 아니다. 공개매수 신고 → 성사가 아니다.
사용: py scripts/discovery/channels.py [--days N] · --show
"""
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import leads  # noqa: E402

DISC = ROOT / "knowledge" / "models" / "discovery"
LATEST = DISC / "channels_latest.json"
ALERTS = DISC / "channel_alerts.json"
FLAGS = DISC / "kr_flags.json"
OUTD = ROOT / "outputs" / "discovery"
FLAG_DAYS = 180       # 이 기간 안의 희석 공시(CB·BW·EB·유상증자)는 국장 적신호
FLAG_PENALTY = 1.5
RED_PENALTY = 1.0


def sid(market, code):
    """발굴 id — 기존 지도 규칙(us-<소문자 티커>, kr-<6자리>, jp-<4자리>)을 따른다"""
    c = re.sub(r"[^A-Za-z0-9.]", "", str(code or "")).lower()
    return f"{market}-{c}" if c else ""


def kr_flags(today):
    d = json.loads(FLAGS.read_text(encoding="utf-8")) if FLAGS.exists() else {}
    lo = (today - timedelta(days=FLAG_DAYS)).isoformat()
    return {code: [f for f in fs if f["date"] >= lo] for code, fs in (d.get("rows") or {}).items() if any(f["date"] >= lo for f in fs)}


def cards():
    try:
        import sector_rotation
        return sector_rotation.cards()
    except Exception:  # noqa: BLE001 — 카드 장부는 보조 입력이다
        return {}


def triage(days=None, today=None):
    today = today or leads.today_kst()
    c = leads.cfg()
    tc = c.get("triage") or {}
    chans = c.get("channels") or {}
    days = days or int(tc.get("days", 45))
    rows = leads.recent(days, today=today)
    flags = kr_flags(today)
    card = cards()
    by = {}
    for r in rows:
        k = (r["market"], (r.get("ticker") or r.get("name") or "").upper())
        g = by.setdefault(k, {"market": r["market"], "code": r.get("ticker") or "", "name": r.get("name") or "", "tv": r.get("tv") or "", "leads": []})
        g["leads"].append(r)
        if r.get("tv") and not g["tv"]:
            g["tv"] = r["tv"]
    out = []
    for (m, code), g in by.items():
        per = {}
        red = False
        for r in g["leads"]:
            s = leads._num(r["strength"]) or 0.0
            if s > per.get(r["channel"], (0, None))[0]:
                per[r["channel"]] = (s, r)
            red = red or bool(leads.extra(r).get("red_flag"))
        top_ch, (top_s, top_r) = max(per.items(), key=lambda x: x[1][0])
        conf = min(float(tc.get("confluence_cap", 1.5)), float(tc.get("confluence_bonus", 0.75)) * (len(per) - 1))
        pen, why_pen = 0.0, []
        if m == "kr" and flags.get(g["code"]) and top_ch not in ("special",):
            pen += FLAG_PENALTY
            why_pen.append(f"희석 공시 {len(flags[g['code']])}건(최근 {FLAG_DAYS}일: " + ", ".join(sorted({f['kind'] for f in flags[g['code']]})) + ")")
        if red:
            pen += RED_PENALTY
            why_pen.append("적신호 단서(투자조합 경영권 변동 등)")
        score = round(max(0.0, min(10.0, top_s + conf - pen)), 1)
        cid = sid(m, g["code"]) if g["code"] else ""
        lens = (chans.get(top_ch) or {}).get("lens", "")
        stage = "② 채널 선별" if score >= float(tc.get("pass_min", 6.0)) else "① 단서"
        if cid in card:
            stage = "③ 판단 카드" if card[cid] >= 6 else stage
        kinds = sorted({f"{r['channel']}/{r['kind']}" for r in g["leads"]})
        out.append({"id": cid, "name": g["name"], "market": m, "code": g["code"], "tv": g["tv"], "score": score, "stage": stage,
                    "channels": sorted(per), "kinds": kinds, "top": {"channel": top_ch, "kind": top_r["kind"], "strength": top_s, "signal": top_r["signal"],
                    "url": top_r["url"], "date": top_r["date"], "lead_id": top_r["lead_id"]}, "confluence": round(conf, 2), "penalty": round(pen, 2),
                    "penalty_why": why_pen, "lens": lens, "edge": card.get(cid), "n_leads": len(g["leads"]),
                    "signals": [f"{r['date']} {chans.get(r['channel'], {}).get('name', r['channel'])}·{(chans.get(r['channel'], {}).get('kinds') or {}).get(r['kind'], r['kind'])}: {r['signal']}"
                                for r in sorted(g["leads"], key=lambda x: x["date"], reverse=True)[:4]]})
    out.sort(key=lambda r: (-r["score"], -len(r["channels"]), r["name"]))
    return out


def card_queue(rows, n):
    """판단 카드가 필요한 채널 선별 통과 종목 — 카드 없음·id 있음, 점수순(겹침 많은 것 먼저)"""
    return [r for r in rows if r["stage"] == "② 채널 선별" and r["id"] and r["edge"] is None][:n]


def alerts(today=None):
    """오늘(또는 어제 늦게) 들어온 단서 중 채널 경보 규칙(kinds·min_strength)을 통과한 것 — Pulse가 lead_id로 한 번만 보낸다"""
    today = today or leads.today_kst()
    c = leads.cfg()
    chans = c.get("channels") or {}
    out = []
    for r in leads.recent(2, today=today):
        a = (chans.get(r["channel"]) or {}).get("alert") or {}
        if r["kind"] in (a.get("kinds") or []) and (leads._num(r["strength"]) or 0) >= float(a.get("min_strength", 10.1)):
            out.append({"lead_id": r["lead_id"], "date": r["date"], "channel": r["channel"], "channel_name": chans[r["channel"]].get("name", r["channel"]),
                        "kind": r["kind"], "kind_name": (chans[r["channel"]].get("kinds") or {}).get(r["kind"], r["kind"]), "market": r["market"],
                        "ticker": r["ticker"], "name": r["name"], "strength": leads._num(r["strength"]), "signal": r["signal"], "url": r["url"]})
    out.sort(key=lambda x: -(x["strength"] or 0))
    return out[: int((c.get("triage") or {}).get("pulse_max", 5)) * 3]


def render(rows, q, today):
    chans = leads.cfg().get("channels") or {}
    L = [f"# 발굴 채널 선별 {today.isoformat()}", "",
         "채널 단서(행동주의·구루·특수 상황·내부자·국장 테마·저관심 텐배거 조짐·기존 채널)를 종목별로 모아 겹침 가점·적신호 감점을 붙였다. "
         "점수는 판단 보조이고, 판단 카드(채널 렌즈)와 위원회 메모를 거친 종목만 커버리지 후보가 된다.", ""]
    by_ch = {}
    for r in rows:
        by_ch.setdefault(r["top"]["channel"], []).append(r)
    L += ["## ■ 채널별 단서 수", "", "| 채널 | 종목 | ② 채널 선별 | 상위 |", "|---|---|---|---|"]
    for ch, rs in sorted(by_ch.items(), key=lambda x: -len(x[1])):
        L.append(f"| {chans.get(ch, {}).get('name', ch)} | {len(rs)} | {sum(1 for r in rs if r['stage'] != '① 단서')} | "
                 + ", ".join(f"{r['name']}({r['code']}) {r['score']}" for r in rs[:3]) + " |")
    multi = [r for r in rows if len(r["channels"]) >= 2]
    if multi:
        L += ["", "## ■ 여러 채널이 겹친 종목", ""] + [f"- {r['name']}({r['market']} {r['code']}) {r['score']} — " + " / ".join(r["signals"][:3]) for r in multi[:12]]
    L += ["", "## ■ 판단 카드 대기열(채널 렌즈로 카드를 쓰면 발굴 선별 후보가 된다)", ""]
    L += [f"- {r['id']} {r['name']}({r['market']} {r['code']}) · 점수 {r['score']} · 렌즈 {r['lens']} · {r['top']['signal']}" for r in q] or ["- 없음"]
    L += ["", "## ■ 상위 30", "", "| 순위 | 종목 | 시장·코드 | 점수 | 단계 | 채널 | 겹침 | 감점 | 최근 신호 |", "|---|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(rows[:30], 1):
        L.append(f"| {i} | {r['name']} | {r['market']} {r['code']} | **{r['score']}** | {r['stage']} | {', '.join(chans.get(c, {}).get('name', c) for c in r['channels'])} | "
                 f"+{r['confluence']} | {('−' + str(r['penalty']) + ' ' + '; '.join(r['penalty_why'])) if r['penalty'] else '-'} | {r['top']['signal'][:70]} |")
    L += ["", "연구 후보이지 매수 권유 아님 · 1차 판정, 미검증 · 채널 성적표는 `py scripts/discovery/leads.py --scorecard`"]
    return "\n".join(L) + "\n"


def mark_passed(rows, today):
    """채널 선별을 처음 통과한 종목의 대표 단서에 'triage_pass' 사건을 남긴다 — 성적표가 통과/기각 단서의 이후 성과를 나눠 잰다(기각의 후회 측정)"""
    done = {e["lead_id"] for e in leads.read(leads.EVENTS) if e.get("event") == "triage_pass"}
    new = [r["top"]["lead_id"] for r in rows if r["stage"] != "① 단서" and r["top"]["lead_id"] not in done]
    for lid in new:
        leads.event(lid, "triage_pass", "", today)
    return len(new)


def run(days=None, today=None, write=True):
    today = today or leads.today_kst()
    rows = triage(days, today)
    n = int((leads.cfg().get("triage") or {}).get("card_queue", 6))
    q = card_queue(rows, n)
    al = alerts(today)
    if write:
        mark_passed(rows, today)
        DISC.mkdir(parents=True, exist_ok=True)
        LATEST.write_text(json.dumps({"as_of": today.isoformat(), "rows": rows, "card_queue": [r["id"] for r in q]}, ensure_ascii=False, indent=1), encoding="utf-8")
        ALERTS.write_text(json.dumps({"as_of": today.isoformat(), "alerts": al}, ensure_ascii=False, indent=1), encoding="utf-8")
        OUTD.mkdir(parents=True, exist_ok=True)
        (OUTD / f"channels_{today.strftime('%Y%m%d')}.md").write_text(render(rows, q, today), encoding="utf-8")
    return rows, q, al


def rows_for_screen(have_ids, have_codes):
    """screen.py 합류 — 지도에 이미 있는 종목(시장·코드 일치)은 그 행에 채널 표시만, 없는 종목은 새 행(채널 선별 통과만)"""
    d = json.loads(LATEST.read_text(encoding="utf-8")) if LATEST.exists() else {}
    tags, new = {}, []
    for r in d.get("rows") or []:
        k = (r["market"], str(r["code"]).upper())
        label = ", ".join(r["channels"])
        if k in have_codes:
            tags[have_codes[k]] = {"channels": r["channels"], "score": r["score"], "signal": r["top"]["signal"]}
        elif r["id"] and r["id"] not in have_ids and r["stage"] != "① 단서":
            new.append({**r, "label": label})
    return tags, new


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    days = int(argv[argv.index("--days") + 1]) if "--days" in argv else None
    if "--show" in argv:
        d = json.loads(LATEST.read_text(encoding="utf-8")) if LATEST.exists() else {}
        for r in (d.get("rows") or [])[:30]:
            print(f"{r['score']:>4} {r['stage']} {r['market']} {r['code']} {r['name']} — {', '.join(r['channels'])} · {r['top']['signal'][:60]}")
        return 0
    rows, q, al = run(days)
    print(f"[발굴 채널] 종목 {len(rows)} · 채널 선별 {sum(1 for r in rows if r['stage'] != '① 단서')} · 카드 대기 {len(q)} · 경보 후보 {len(al)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
