"""텐배거 리포트 발행 — GitHub(보는 마크다운) → 노션 Stocks → 텔레그램을 한 묶음으로 (마스터 지시 2026-10-30 "리포트 결과물을 볼 수 있는
github 링크를 제공해야지 … 노션에도 결과물이 Github와 동시에 올라와야 한다. 엔진 아키텍처를 다시 점검해 설계하라" → 설계 승인 "설계대로 구현해")

순서(텔레그램은 마지막 한 번 — GitHub·노션 결과가 모두 기록된 뒤):
  1. prepare <json> [--extra <파일>...]  마크다운·차트(report_md)·노션 본문(report_notion)·Artifact 판(<이름>_artifact.html) 생성 → claude/reports 브랜치에
                                       HTML·JSON·MD·차트(+extra) 게시(보관) → 상태 파일 outputs/tenbagger/reports/delivery/<이름>.json
  2. (모델) Artifact 도구로 <이름>_artifact.html을 claude.ai 비공개 페이지로 게시 → artifact <json> --url <URL>
     (마스터 지시 2026-10-30 "리포트 링크는 html로" — 비공개 저장소 HTML은 GitHub에서 소스로만 보여서, 모바일에서 그대로 보이는 HTML 링크)
  3. (모델) 노션 커넥터로 HTML 임베드 + 본문을 종목 페이지 아래 하위 페이지로 → notion <json> --page <URL>  (실패면 --fail "<이유>")
  4. send <json> --caption <파일>         GitHub 게시 기록이 없으면 보내지 않는다. 보기 링크 = Artifact(없으면 GitHub 마크다운 + '보기 링크 게시 실패'),
                                       노션이 성공이면 캡션 + 리포트 보기 + 노션 링크,
                                       노션이 실패·미기록이면 '노션 게시 실패 — 다음 회차 재시도'를 붙여 보내고 상태를 notion_pending으로 남긴다.
                                       이미 보낸 리포트의 노션이 나중에 성공하면 send가 '노션 게시 완료' 한 줄만 따로 보낸다.
  pending                               노션 미완료·텔레그램 미발송 리포트 목록(다음 회차 시작 때 먼저 처리)
기록: outputs/tenbagger/reports/delivery.csv(time,stem,ticker,step,status,detail)
"""
import argparse
import csv
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish_report  # noqa: E402
import report_md  # noqa: E402
import report_html  # noqa: E402
import report_notion  # noqa: E402

REP = ROOT / "outputs" / "tenbagger" / "reports"
STATE = REP / "delivery"
LEDGER = REP / "delivery.csv"
NOTION_LOG = REP / "notion_log.csv"
KST = timezone(timedelta(hours=9))


def now():
    return datetime.now(KST).isoformat(timespec="seconds")


def rel(p):
    p = Path(p).resolve()
    return p.relative_to(ROOT).as_posix() if p.is_relative_to(ROOT) else str(p)


def state_path(src):
    return STATE / f"{Path(src).stem}.json"


def load(src):
    p = state_path(src)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def save(src, st):
    STATE.mkdir(parents=True, exist_ok=True)
    state_path(src).write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def log(stem, ticker, step, status, detail=""):
    new = not LEDGER.exists()
    with LEDGER.open("a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["time", "stem", "ticker", "step", "status", "detail"])
        w.writerow([now(), stem, ticker, step, status, detail[:300]])


def existing_notion(date_, ticker):
    """같은 날 같은 종목 하위 페이지가 이미 있으면 그 URL(정정은 새로 만들지 않고 갱신)"""
    if not NOTION_LOG.exists():
        return None
    with NOTION_LOG.open(encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r.get("date") == date_ and (r.get("ticker") or "").upper() == ticker.upper()]
    return (rows[-1].get("report_page"), rows[-1].get("stock_page")) if rows else None


def prepare(src, extra=(), title=None, dry=False):
    src = Path(src)
    d = json.loads(src.read_text(encoding="utf-8"))
    html = src.with_suffix(".html")
    if not html.exists():
        raise SystemExit(f"HTML 없음: {html} — report_html.py 먼저")
    built = report_md.build(src)
    files = [html, src, Path(built["md"]), *map(Path, built["charts"]), *[Path(e) for e in extra if Path(e).exists()]]
    ttl = title or f"텐배거 리포트 {d.get('date')} {d.get('company')}({d.get('ticker')})"
    if dry:
        links, commit = [f"(dry) {rel(f)}" for f in files], "dry"
    else:
        links, commit = publish_report.publish([str(f) for f in files], ttl)
    by = dict(zip([rel(f) for f in files], links))
    gh_md, gh_html = by.get(rel(built["md"])), by.get(rel(html))
    art = src.with_name(src.stem + "_artifact.html")
    art.write_text(report_html.artifact_html(d), encoding="utf-8")
    body = src.with_name(src.stem + "_notion.md")
    body.write_text(report_notion.render(d, gh_md), encoding="utf-8")
    old = existing_notion(str(d.get("date")), str(d.get("ticker")))
    st = load(src) or {}
    st.update({"stem": src.stem, "date": d.get("date"), "ticker": d.get("ticker"), "company": d.get("company"),
               "github": {"md": gh_md, "html": gh_html, "commit": commit, "at": now()},
               "artifact": st.get("artifact"),
               "notion": st.get("notion") if (st.get("notion") or {}).get("status") == "ok" else {"status": "pending"},
               "telegram": st.get("telegram")})
    save(src, st)
    log(src.stem, d.get("ticker"), "github", "ok", gh_md or "")
    return {"github_md": gh_md, "github_html": gh_html, "artifact_page": rel(art), "artifact_url": (st.get("artifact") or {}).get("url"), "notion_title": report_notion.title(d), "notion_body": rel(body),
            "notion_embed_html": rel(html), "html_kib": round(html.stat().st_size / 1024, 1),
            "notion_existing_page": old[0] if old else None, "notion_stock_page": old[1] if old else None, "state": rel(state_path(src))}


def artifact(src, url=None, fail=None):
    """claude.ai 비공개 Artifact 보기 링크 기록 — 정정 재발행은 같은 URL로(상태 파일의 url을 Artifact 도구 url 인자로)"""
    st = load(src)
    if not st or not (st.get("github") or {}).get("md"):
        raise SystemExit("prepare 먼저(GitHub 게시 기록 없음)")
    st["artifact"] = {"status": "ok", "url": url, "at": now()} if url else {"status": "fail", "error": (fail or "")[:300], "at": now()}
    log(st["stem"], st["ticker"], "artifact", "ok" if url else "fail", url or fail or "")
    save(src, st)
    return st["artifact"]


def notion(src, page=None, fail=None, stock=None):
    st = load(src)
    if not st or not (st.get("github") or {}).get("md"):
        raise SystemExit("prepare 먼저(GitHub 게시 기록 없음)")
    if page:
        st["notion"] = {"status": "ok", "page": page, "stock_page": stock, "at": now()}
        log(st["stem"], st["ticker"], "notion", "ok", page)
        if not existing_notion(str(st["date"]), str(st["ticker"])):
            new = not NOTION_LOG.exists()
            with NOTION_LOG.open("a", encoding="utf-8", newline="") as f:
                w = csv.writer(f)
                if new:
                    w.writerow(["date", "id", "ticker", "stock_page", "report_page"])
                w.writerow([st["date"], "", st["ticker"], stock or "", page])
    else:
        n = (st.get("notion") or {}).get("tries", 0) + 1
        st["notion"] = {"status": "fail", "error": (fail or "")[:300], "tries": n, "at": now()}
        log(st["stem"], st["ticker"], "notion", "fail", fail or "")
    save(src, st)
    return st["notion"]


def message(st, caption):
    gh, nt, ar = st["github"]["md"], st.get("notion") or {}, st.get("artifact") or {}
    view = f"📄 리포트 보기: {ar['url']}" if ar.get("status") == "ok" else f"📄 리포트(GitHub, HTML 보기 링크 게시 실패): {gh}"
    lines = [caption.strip(), "", view]
    lines.append(f"🗂 노션: {nt['page']}" if nt.get("status") == "ok" else "🗂 노션 게시 실패 — 다음 회차에 다시 올립니다")
    return "\n".join(x for x in lines if x is not None)


def send(src, caption="", dry=False, resend=False):
    st = load(src)
    if not st or not (st.get("github") or {}).get("md"):
        raise SystemExit("GitHub 게시 기록 없음 — 텔레그램을 보내지 않는다")
    tg = {} if resend else (st.get("telegram") or {})   # resend = 발행 경로가 바뀐 리포트를 새 링크로 다시 보낼 때
    ok = (st.get("notion") or {}).get("status") == "ok"
    if tg.get("sent") and tg.get("notion_ok"):
        return {"skipped": "이미 GitHub·노션 링크와 함께 발송함"}
    if tg.get("sent"):   # 앞서 노션 없이 보낸 리포트 — 노션이 이제 올라갔으면 한 줄만
        if not ok:
            return {"skipped": "노션 아직 실패 — 재시도 후 다시"}
        text = f"[Chiip Ten-bagger Report] {st['company']}({st['ticker']}) 노션 게시 완료\n🗂 {st['notion']['page']}"
    else:
        cap = Path(caption).read_text(encoding="utf-8") if caption and Path(caption).exists() else (caption or f"[Chiip Ten-bagger Report] {st['company']}({st['ticker']})")
        text = message(st, cap)
    sent = True
    if not dry:
        sys.path.insert(0, str(ROOT / "radar"))
        import notify
        sent = bool(notify.send(text, "REPORT"))
        notify.run_ledger.record("publish", "chiip-tenbagger-report", output=st["stem"], ok=sent)
    st["telegram"] = {"sent": tg.get("sent") or sent, "notion_ok": ok and sent, "at": now()}
    save(src, st)
    log(st["stem"], st["ticker"], "telegram", "ok" if sent else "fail", "노션 포함" if ok else "노션 실패 표시")
    return {"sent": sent, "notion_ok": ok, "text": text}


def pending():
    out = []
    for p in sorted(STATE.glob("*.json")) if STATE.exists() else []:
        st = json.loads(p.read_text(encoding="utf-8"))
        tg = st.get("telegram") or {}
        if (st.get("notion") or {}).get("status") != "ok" or (st.get("artifact") or {}).get("status") != "ok" or not tg.get("sent") or not tg.get("notion_ok"):
            out.append({"stem": st["stem"], "ticker": st.get("ticker"), "notion": (st.get("notion") or {}).get("status"),
                        "artifact": (st.get("artifact") or {}).get("status"), "telegram": bool(tg.get("sent")), "json": rel(REP / (st["stem"] + ".json"))})
    return out


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["prepare", "artifact", "notion", "send", "pending"])
    ap.add_argument("json", nargs="?")
    ap.add_argument("--extra", nargs="*", default=[])
    ap.add_argument("--title")
    ap.add_argument("--page")
    ap.add_argument("--url", help="Artifact 보기 링크(claude.ai)")
    ap.add_argument("--stock-page")
    ap.add_argument("--fail")
    ap.add_argument("--caption", default="")
    ap.add_argument("--dry", action="store_true", help="GitHub 게시·텔레그램 없이 흐름만")
    ap.add_argument("--resend", action="store_true", help="이미 보낸 리포트를 새 링크로 다시 보낸다")
    a = ap.parse_args(argv)
    if a.cmd == "pending":
        r = pending()
    elif not a.json:
        ap.error("리포트 json 경로가 필요")
    elif a.cmd == "prepare":
        r = prepare(a.json, a.extra, a.title, a.dry)
    elif a.cmd == "artifact":
        if not a.url and not a.fail:
            ap.error("--url 또는 --fail")
        r = artifact(a.json, a.url, a.fail)
    elif a.cmd == "notion":
        if not a.page and not a.fail:
            ap.error("--page 또는 --fail")
        r = notion(a.json, a.page, a.fail, a.stock_page)
    else:
        r = send(a.json, a.caption, a.dry, a.resend)
    print(json.dumps(r, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
