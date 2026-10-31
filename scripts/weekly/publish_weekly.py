"""Weekly Review 발행 — Artifact → 노션 Weekly 페이지 → 텔레그램을 한 묶음으로 (마스터 지시 2026-10-31 "Weekly 다시 썼으면 텔레그램 봇에
공유해줘야지", "Weekly Report를 작성한 뒤 텔레그램 봇에 공유할 때 Notion의 Weekly 페이지에도 올리도록 해라")

순서(텔레그램은 마지막 한 번 — 링크가 모두 기록된 뒤):
  1. (모델) Artifact 도구로 <주차>_weekly.html 게시 → artifact <주차> --url <URL>  (이미 있으면 같은 URL로 갱신)
  2. notion-body <주차>  → <주차>_notion.md 생성
  3. (모델) 노션 커넥터로 config/notion.yaml pages.weekly 아래 하위 페이지 생성·갱신 → notion <주차> --page <URL>  (실패면 --fail "이유")
  4. send <주차>  보고서가 바뀌었을 때만 보낸다. 다시 쓴 판은 '수정판'으로 다시 보낸다
  pending          발행이 끝나지 않은 주차
기록: outputs/brief/delivery/<주차>.json · outputs/brief/delivery.csv
"""
import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BRIEF = ROOT / "outputs" / "brief"
STATE = BRIEF / "delivery"
LEDGER = BRIEF / "delivery.csv"
KST = timezone(timedelta(hours=9))
DISCLAIMER = "공개 자료 기반 분석이며 투자 권유가 아님"


def now():
    return datetime.now(KST).isoformat(timespec="seconds")


def report(week):
    p = BRIEF / f"{week}_weekly.json"
    if not p.exists() or not p.with_suffix(".md").exists():
        raise SystemExit(f"보고서 없음: {p.name} — render.py 먼저")
    return json.loads(p.read_text(encoding="utf-8"))


def version(week):
    """보고서 판 — 다시 쓰면 바뀐다(줄바꿈 차이는 무시)"""
    return hashlib.sha256((BRIEF / f"{week}_weekly.md").read_bytes().replace(b"\r\n", b"\n")).hexdigest()[:16]


def load(week):
    p = STATE / f"{week}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"week": week}


def save(week, st):
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / f"{week}.json").write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def log(week, step, status, detail=""):
    new = not LEDGER.exists()
    with LEDGER.open("a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["time", "week", "step", "status", "detail"])
        w.writerow([now(), week, step, status, detail[:300]])


def artifact(week, url):
    report(week)
    st = load(week)
    st["artifact"] = {"url": url, "version": version(week), "at": now()}
    save(week, st)
    log(week, "artifact", "ok", url)
    links = BRIEF / "artifact_links.md"
    line = f"{week} 주간: {url}"
    if line not in links.read_text(encoding="utf-8"):
        with links.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    return st["artifact"]


def notion_title(week):
    d = report(week)
    return f"{d['week_no']}주차 Weekly Review — {d['headline']}"


def notion_body(week):
    """보고서 글을 노션 본문으로 — 제목 줄은 페이지 제목이 대신하고, 맨 위에 보기 링크를 둔다"""
    d = report(week)
    lines = (BRIEF / f"{week}_weekly.md").read_text(encoding="utf-8").splitlines()
    url = (load(week).get("artifact") or {}).get("url")
    body = "\n".join(lines[1:]).strip()
    head = f"[차트와 표 전체 보기]({url})\n\n" if url else ""
    out = BRIEF / f"{week}_notion.md"
    out.write_text(head + body + "\n", encoding="utf-8")
    return {"title": notion_title(week), "body": out.relative_to(ROOT).as_posix(), "week_no": d["week_no"], "existing_page": (load(week).get("notion") or {}).get("page")}


def notion(week, page=None, fail=None):
    report(week)
    st = load(week)
    if page:
        st["notion"] = {"status": "ok", "page": page, "version": version(week), "at": now()}
    else:
        st["notion"] = {"status": "fail", "error": (fail or "")[:300], "page": (st.get("notion") or {}).get("page"), "at": now()}
    save(week, st)
    log(week, "notion", st["notion"]["status"], page or fail or "")
    return st["notion"]


def message(week, st, resend):
    d = report(week)
    nt, ar = st.get("notion") or {}, st.get("artifact") or {}
    first = f"[Chiip Weekly Review] {d['week_no']}주차 {d['period']}" + (" 수정판" if resend else "")
    lines = [first, "", f"**{d['headline']}**", ""] + [f"· {b}" for b in d.get("bullets") or []] + [""]
    if ar.get("url"):
        lines.append(f"[리포트 보기]({ar['url']})")
    lines.append(f"[노션]({nt['page']})" if nt.get("status") == "ok" and nt.get("version") == version(week) else "노션 게시 실패 — 다음 회차에 다시 올립니다")
    return "\n".join(lines + ["", DISCLAIMER])


def send(week, dry=False):
    report(week)
    st, ver = load(week), version(week)
    ar = st.get("artifact") or {}
    if ar.get("version") != ver:
        raise SystemExit("Artifact가 이번 판이 아니다 — 게시 후 artifact 기록 먼저")
    tg = st.get("telegram") or {}
    if tg.get("version") == ver:
        return {"skipped": "이번 판은 이미 보냈다"}
    text = message(week, st, bool(tg.get("version")))
    sent = True
    if not dry:
        sys.path.insert(0, str(ROOT / "radar"))
        import notify
        sent = bool(notify.send(text, "WEEKLY", md=True))
        notify.run_ledger.record("publish", "chiip-weekly-review", output=week, ok=sent)
    if sent and not dry:
        st["telegram"] = {"version": ver, "at": now()}
        save(week, st)
    log(week, "telegram", "ok" if sent else "fail", "dry" if dry else ver)
    return {"sent": sent, "text": text}


def pending():
    out = []
    for p in sorted(BRIEF.glob("*_weekly.json")):
        week = p.name[:-len("_weekly.json")]
        st, ver = load(week), version(week)
        left = [k for k in ("artifact", "notion", "telegram") if (st.get(k) or {}).get("version") != ver]
        if left:
            out.append({"week": week, "left": left})
    return out


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["artifact", "notion-body", "notion", "send", "pending"])
    ap.add_argument("week", nargs="?")
    ap.add_argument("--url")
    ap.add_argument("--page")
    ap.add_argument("--fail")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args(argv)
    res = pending() if a.cmd == "pending" else artifact(a.week, a.url) if a.cmd == "artifact" else notion_body(a.week) if a.cmd == "notion-body" \
        else notion(a.week, a.page, a.fail) if a.cmd == "notion" else send(a.week, a.dry)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
