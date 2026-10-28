"""AI 밸류체인 어닝 캘린더 (마스터 지시 2026-10-28) — 수집은 전부, 텔레그램은 알파 잠재력 5.0 이상만

원천(결정론):
  한국   KRX KIND IR 일정(corpgeneral/irschedule.do, searchIRScheduleSub) — robots.txt 없음, 법적고지상 무단 전재·
         사전 동의 없는 복제·배포 금지 → 회사·일시·제목·링크만 비공개 사용, 하루 2회·요청 사이 2초
  미·EU·영·일·대 EODHD /api/calendar/earnings (ALL-IN-ONE, EODHD_API_KEY 있을 때만) — 요청 1회 = 기간 전체
  (Yahoo Finance는 AI 수집기 전면 차단, Finviz·Investing.com은 약관상 자동 수집 금지로 알려져 쓰지 않는다.
   일본 TDnet·대만 MOPS(mopsov)는 robots.txt 차단. JPX 결산발표 예정일·TWSE 공개 데이터는 약관 확인 후 추가)
대상: config/earnings_watch.yaml(valuation universe + extra + 텐배거 추적 목록)
저장: knowledge/models/earnings/upcoming.json(git 제외) + knowledge/calendar.csv 실적발표 행 추가(중복 없이)
발송: 매일 07:00~09:00 KST 첫 실행 때 1회 — 오늘·내일(월요일엔 7일) 발표 중 알파 점수 ≥ 기준 종목만. 없으면 보내지 않음
사용: py radar/markets/earnings_calendar.py [--days 21] [--digest 2] [--send]
"""
import argparse
import csv
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pollers import common  # noqa: E402


def _alpha():
    """scripts/alpha/score.py — 포커스 점수(scripts/focus/score.py)와 모듈 이름이 겹치지 않게 고유 이름으로 불러온다"""
    import importlib.util
    if "alpha_score" not in sys.modules:
        spec = importlib.util.spec_from_file_location("alpha_score", common.ROOT / "scripts" / "alpha" / "score.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        sys.modules["alpha_score"] = mod
    return sys.modules["alpha_score"]

SOURCE_ID = "src-earnings-calendar"
KIND_URL = "https://kind.krx.co.kr/corpgeneral/irschedule.do"
EODHD_URL = "https://eodhd.com/api/calendar/earnings"
OUT = common.ROOT / "knowledge" / "models" / "earnings" / "upcoming.json"
CAL = common.ROOT / "knowledge" / "calendar.csv"
EARN_RE = re.compile(r"실적|결산|Earnings|Results|results|Financial|earnings", re.I)
WD = "월화수목금토일"


def watch():
    """[{id, name, kind_name, code, region}] — 중복 id는 첫 항목"""
    val = common.load_yaml("config/valuation.yaml") or {}
    ew = common.load_yaml("config/earnings_watch.yaml") or {}
    over = ew.get("kind_name_override") or {}
    seen, out = set(), []
    for u in (val.get("universe") or []) + (ew.get("extra") or []):
        if u["id"] in seen:
            continue
        seen.add(u["id"])
        kn = u.get("kind_name") or over.get(u["id"]) or (u["name"] if u.get("region") == "KR" else None)
        out.append({"id": u["id"], "name": u["name"], "kind_name": kn, "code": u.get("code"), "region": u.get("region")})
    tb = common.ROOT / "knowledge" / "models" / "tenbagger" / "watch.csv"
    if tb.exists():
        with tb.open(encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                if r.get("status") != "종료" and r.get("cand_id") and r["cand_id"] not in seen:
                    seen.add(r["cand_id"])
                    out.append({"id": r["cand_id"], "name": r["company"], "kind_name": r["company"] if r.get("region") == "KR" else None,
                                "code": r.get("ticker"), "region": r.get("region")})
    return out


# ---------- 한국: KIND ----------
def _kind_post(data):
    req = urllib.request.Request(KIND_URL, data=urllib.parse.urlencode(data).encode(),
                                 headers={"User-Agent": common.UA, "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def parse_kind(html):
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        cells = [common.strip_tags(c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if len(cells) < 6 or not re.match(r"\d{4}-\d{2}-\d{2}$", cells[4]):
            continue
        seq = re.search(r"fnPopupIRInfoDetail\('?(\d+)'?\)", tr)
        rows.append({"company": re.sub(r"\s+", " ", cells[1]), "title": re.sub(r"\s+", " ", cells[2]),
                     "place": cells[3], "date": cells[4], "time": cells[5], "ir_seq": seq.group(1) if seq else None})
    return rows


def fetch_kind(start, end, max_pages=5):
    out = []
    for page in range(1, max_pages + 1):
        html = _kind_post({"method": "searchIRScheduleSub", "forward": "searchirschedule_sub", "currentPageSize": "100",
                           "pageIndex": str(page), "orderMode": "1", "orderStat": "D", "marketType": "", "searchCorpName": "",
                           "fromDate": start.isoformat(), "toDate": end.isoformat()})
        rows = parse_kind(html)
        out += rows
        if len(rows) < 100:
            break
        time.sleep(2)
    return out


def kind_events(rows, wl):
    by_name = {w["kind_name"]: w for w in wl if w.get("kind_name")}
    ev = {}
    for r in rows:
        w = by_name.get(r["company"])
        if not w or not EARN_RE.search(r["title"]):
            continue
        key = (w["id"], r["date"])   # 국문·영문 중복 공시와 같은 날 두 번 공시(발표·설명회)는 하나로 — 이른 시각 우선
        t = r["time"] if re.match(r"\d{1,2}:\d{2}$", r["time"]) else ""
        cur = ev.get(key)
        if cur and (not t or (cur["time_kst"] and cur["time_kst"] <= t)):
            continue
        url = f"{KIND_URL}?method=searchIRSchedulePopup&irSeq={r['ir_seq']}" if r["ir_seq"] else KIND_URL
        ev[key] = {"id": w["id"], "name": w["name"], "date": r["date"], "time_kst": t, "local": "", "title": r["title"],
                   "source": "KIND IR일정", "url": url}
    return list(ev.values())


# ---------- 해외: EODHD ----------
def fetch_eodhd(start, end, wl, key):
    codes = {w["code"]: w for w in wl if w.get("code") and w.get("region") != "KR"}
    ev, sym = [], list(codes)
    for i in range(0, len(sym), 40):
        q = {"from": start.isoformat(), "to": end.isoformat(), "symbols": ",".join(sym[i:i + 40]), "api_token": key, "fmt": "json"}
        data = json.loads(common.http_get(EODHD_URL, q, timeout=40))
        for r in data.get("earnings", data if isinstance(data, list) else []):
            w = codes.get(r.get("code"))
            if not w:
                continue
            bam = {"BeforeMarket": "장전", "AfterMarket": "장후"}.get(r.get("before_after_market") or "", "")
            ev.append({"id": w["id"], "name": w["name"], "date": r["report_date"], "time_kst": "", "local": bam,
                       "title": f"분기 실적(기간 말 {r.get('date')})", "source": "EODHD", "url": ""})
        time.sleep(1)
    return ev


# ---------- 저장 ----------
def save(events):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"updated": common.iso(common.now_kst()), "events": sorted(events, key=lambda e: (e["date"], e["time_kst"]))},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    with CAL.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
        fields = list(rows[0].keys()) if rows else ["date", "time_kst", "type", "entity_or_event", "description", "expectation_note_ref", "status"]
    have = {(r["date"], r["type"], r["entity_or_event"]) for r in rows}
    added = 0
    for e in events:
        k = (e["date"], "실적발표", e["id"])
        if k in have:
            continue
        have.add(k)
        rows.append({"date": e["date"], "time_kst": e["time_kst"] or e["local"], "type": "실적발표", "entity_or_event": e["id"],
                     "description": f"{e['name']} {e['title']} ({e['source']} 자동)", "expectation_note_ref": "", "status": "예정"})
        added += 1
    if added:
        with CAL.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(sorted(rows, key=lambda r: r["date"]))
    return added


def digest(events, days, today=None):
    alpha = _alpha()
    today = today or common.now_kst().date()
    passed, rows = alpha.load_latest(today)
    end = today + timedelta(days=days - 1)
    win = [e for e in events if today.isoformat() <= e["date"] <= end.isoformat()]
    keep = [e for e in win if e["id"] in passed]
    unscored = sum(1 for e in win if (rows.get(e["id"]) or {}).get("total") is None)
    if not keep:
        return None
    span = "오늘·내일" if days == 2 else f"{days}일"
    lines = [f"[실적 일정 · 알파 5점 이상] {span} {len(keep)}건"]
    for e in sorted(keep, key=lambda e: (e["date"], e["time_kst"])):
        d = datetime.strptime(e["date"], "%Y-%m-%d").date()
        when = e["time_kst"] or e["local"] or "시각 미정"
        lines.append(f"- {d.month}/{d.day}({WD[d.weekday()]}) {when} {e['name']} — 알파 {passed[e['id']]:.1f}")
    lines.append(f"(같은 기간 발표 {len(win)}건 중 기준 미달 {len(win) - len(keep) - unscored}·미산정 {unscored}건은 생략)")
    lines.append("공개 자료 기반 분석이며 투자 권유가 아님")
    return "\n".join(lines)


COLLECT_EVERY_H = 6   # KIND 요청은 하루 최대 4회(06·12·18·24시 근처) — 그 사이 실행은 발송 확인만


def collect(days, wl, today):
    end = today + timedelta(days=days)
    events, errors = [], []
    try:
        events += kind_events(fetch_kind(today, end), wl)
    except Exception as exc:
        errors.append(f"KIND: {type(exc).__name__}")
    key = common.load_env().get("EODHD_API_KEY")
    if key:
        try:
            events += fetch_eodhd(today, end, wl, key)
        except Exception as exc:
            errors.append(f"EODHD: {type(exc).__name__}")
    return events, errors


def run(days=21, send=None, force_collect=False):
    """run_hourly용(30분마다 불림). 수집은 6시간마다, send=None이면 07~09시 첫 실행 때만 발송"""
    wl = watch()
    now = common.now_kst()
    today = now.date()
    st = common.load_state("earnings_calendar", {})
    last = st.get("collected_at")
    due = force_collect or not OUT.exists() or not last or \
        now - datetime.fromisoformat(last) >= timedelta(hours=COLLECT_EVERY_H)
    errors, added = [], 0
    if due:
        events, errors = collect(days, wl, today)
        added = save(events) if events else 0
        common.record_health(SOURCE_ID, not (errors and not events), "; ".join(errors) or None)
        if events:
            st["collected_at"] = common.iso(now)
    else:
        events = json.loads(OUT.read_text(encoding="utf-8"))["events"]
    if send is None:
        send = 7 <= now.hour < 9 and st.get("sent_day") != today.isoformat()
    sent = False
    if send:
        text = digest(events, 7 if today.weekday() == 0 else 2, today)
        if text:
            import notify
            sent = notify.send(text, "EARNINGS")
        st["sent_day"] = today.isoformat()
    common.save_state("earnings_calendar", st)
    return len(events), added, sent, errors


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=21)
    ap.add_argument("--digest", type=int, help="수집 후 N일 요약을 출력만(발송 안 함)")
    ap.add_argument("--send", action="store_true", help="시간대와 무관하게 지금 발송")
    a = ap.parse_args(argv)
    n, added, sent, errors = run(a.days, send=True if a.send else False, force_collect=True)
    print(f"[어닝 캘린더] 일정 {n}건(달력 신규 {added})" + (f", 실패: {'; '.join(errors)}" if errors else "") + (", 텔레그램 발송" if sent else ""))
    if a.digest:
        ev = json.loads(OUT.read_text(encoding="utf-8"))["events"] if OUT.exists() else []
        print(digest(ev, a.digest) or "(기준 이상 종목의 일정 없음)")
        for e in ev:
            print(f"  {e['date']} {e['time_kst'] or e['local']:5} {e['name']} | {e['title'][:40]} | {e['source']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
