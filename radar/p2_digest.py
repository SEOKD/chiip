"""P2 하루 1통 요약 (2026-10-29 마스터 지시 — 아침·저녁 브리프 중단 뒤 P2·막힌 P0/P1이 읽히지 않는 대기열에 쌓이던 문제)

radar/state/brief_queue.jsonl(run_triage가 P2·매체 제한으로 막힌 P0/P1·미판정을 적는 곳)에서 지난 요약 이후 항목을
같은 제목 묶어 점수순 상위 TOP건만 텔레그램 1통으로 보낸다. 모델을 부르지 않는다.
점수: 막힌 P0 5 · 막힌 P1 4 · 미판정 2 · P2 1, 주요 매체(alert_rules allowed_publishers) +2,
      보유 종목·관련 기업(config/portfolio.yaml) +2, T0 +1.
발송: 매일 08:00~10:00 첫 실행 때 1회(run_hourly가 30분마다 부른다). 첫 요약은 지난 24시간만.
사용: py radar/p2_digest.py [--send] [--dry-run]
"""
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

QUEUE = common.STATE / "brief_queue.jsonl"
STATE = "p2_digest"
TOP = 10
LEVEL_SCORE = {"P0": 5, "P1": 4, "미판정": 2, "P2": 1}
WINDOW = (8, 10)
MAX_CHARS = 3800          # 텔레그램 한 통 4096자 — 링크는 이 안에 들어갈 때만 붙인다
HANGUL = re.compile(r"[가-힣]")   # 국내 언론 기사는 보내지 않는다(마스터 지시 2026-10-28·29)


def _publisher(title):
    return title.rsplit(" - ", 1)[1].strip() if " - " in title else ""


def _key(title):
    words = re.sub(r"\W+", " ", title.rsplit(" - ", 1)[0].lower()).split()
    return " ".join(words[:10])


def _context():
    rules = common.load_yaml("config/alert_rules.yaml") or {}
    pubs = {p.lower() for p in (rules.get("telegram_filter") or {}).get("allowed_publishers", [])}
    pf = common.load_yaml("config/portfolio.yaml") or {}
    held_ids, names = set(), []
    for h in pf.get("holdings") or []:
        if h.get("status", "보유") != "보유":
            continue
        held_ids.add(h.get("id"))
        names += (h.get("names") or []) + (h.get("related") or [])
    name_re = re.compile("|".join(rf"\b{re.escape(n)}\b" for n in names), re.I) if names else None
    wl = common.load_watchlist()
    return pubs, held_ids, name_re, wl


def score(entry, pubs, held_ids, name_re, wl=None):
    s = LEVEL_SCORE.get(entry.get("level"), 1)
    title = entry.get("title") or ""
    if _publisher(title).lower() in pubs:
        s += 2
    ents = entry.get("entities") or []
    if held_ids & set(ents) or (name_re and name_re.search(title)):
        s += 2
    if any(common.tier_of(e, wl) == "T0" for e in ents):
        s += 1
    return s


def load(since):
    out = []
    if not QUEUE.exists():
        return out
    for line in QUEUE.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("at") and datetime.fromisoformat(e["at"]) > since:
            out.append(e)
    return out


def build(entries, now):
    pubs, held_ids, name_re, wl = _context()
    groups = {}
    entries = [e for e in entries if not HANGUL.search(e.get("title") or "")]
    for e in entries:
        k = _key(e.get("title") or "")
        if not k:
            continue
        sc = score(e, pubs, held_ids, name_re, wl)
        g = groups.setdefault(k, {"entry": e, "score": sc, "n": 0})
        g["n"] += 1
        if sc > g["score"]:
            g["entry"], g["score"] = e, sc
    if not groups:
        return None
    ranked = sorted(groups.values(), key=lambda g: (-g["score"], -g["n"], g["entry"].get("at", "")))
    lv = {}
    for e in entries:
        lv[e.get("level")] = lv.get(e.get("level"), 0) + 1
    head = " · ".join(f"{k} {v}" for k, v in sorted(lv.items(), key=lambda x: -LEVEL_SCORE.get(x[0], 0)))
    lines = [f"[치입 P2 요약 {now.month}/{now.day}] 대기열 {len(entries)}건({head}) — 같은 제목 묶어 {len(groups)}건 중 상위 {min(TOP, len(groups))}"]
    body = []
    for i, g in enumerate(ranked[:TOP], 1):
        e = g["entry"]
        tag = e.get("level") if e.get("level") in ("P2", "미판정") else f"막힌 {e.get('level')}"
        note = (e.get("note") or "")[:40]
        body.append([f"{i}. [{tag}] {e.get('title', '')[:140]}" + (f" (+{g['n'] - 1}건)" if g["n"] > 1 else "") +
                     (f"\n   사유: {note}" if note else ""), e.get("url", "")])
    foot = "1차 판정, 미검증 · 제목 기준(원문 미확인) · 국내 언론 제외"
    used = len("\n".join(lines + [b[0] for b in body] + [foot]))
    for b in body:   # 점수 높은 것부터 링크를 붙이고, 한 통 길이를 넘으면 그 뒤는 제목만
        if b[1] and used + len(b[1]) + 4 <= MAX_CHARS:
            b[0] += f"\n   {b[1]}"
            used += len(b[1]) + 4
    lines += [b[0] for b in body] + [foot]
    return "\n".join(lines)


def run(send=None, now=None):
    """run_hourly용. (대상 건수, 발송 여부)"""
    now = now or common.now_kst()
    st = common.load_state(STATE, {})
    if send is None:
        send = WINDOW[0] <= now.hour < WINDOW[1] and st.get("sent_day") != now.date().isoformat()
    if not send:
        return 0, False
    last = st.get("last_at")
    since = datetime.fromisoformat(last) if last else now - timedelta(hours=24)
    entries = load(since)
    text = build(entries, now)
    sent = False
    if text:
        import notify
        sent = notify.send(text, "DIGEST")
    st.update({"sent_day": now.date().isoformat(), "last_at": common.iso(now)})
    common.save_state(STATE, st)
    return len(entries), sent


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if "--dry-run" in argv:
        now = common.now_kst()
        st = common.load_state(STATE, {})
        since = datetime.fromisoformat(st["last_at"]) if st.get("last_at") else now - timedelta(hours=24)
        print(build(load(since), now) or "대상 없음")
        return 0
    print(run(send=True if "--send" in argv else None))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
