"""딘스티커 읽기 전용 수집 (마스터 지시 2026-10-31 "내가 딘스티커 채널에 올리는 인사이트를 너가 참고하도록 … 오로지 읽기 기능만") — 결정론

공개 웹 미리보기 t.me/s/d_ticker만 GET으로 읽는다. 봇·API·로그인을 쓰지 않아 이 모듈로는 채널에 쓸 수 없다.
발송 차단은 notify.private_chat이 맡는다(개인 대화방 외 전부 거부).
저장: radar/dticker/posts.jsonl (git 제외, 다시 받을 수 있다) · 상태: radar/state/dticker.json
사용: py radar/dticker.py                         # 수집
      py radar/dticker.py --recent 14 [--columns]  # 최근 글
      py radar/dticker.py --about 인텔 INTC        # 이름·티커가 나온 글
"""
import argparse
import html
import json
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

HANDLE = "d_ticker"
PAGE = f"https://t.me/s/{HANDLE}"
OUT = common.ROOT / "radar" / "dticker" / "posts.jsonl"
SOURCE_ID = "src-dticker"
STATE = "dticker"
BACKFILL_DAYS, MAX_PAGES = 365, 120   # 첫 수집은 1년치까지, 이후에는 지난번 글까지만
COLUMN_CHARS = 200   # 이보다 긴 글을 칼럼(마스터 해석)으로 본다. 그 아래는 속보·표
AGENT_MARK = "에이전트 결과물"   # 마스터가 치입 글을 올릴 때 붙이는 표시 — 마스터 의견으로 되읽으면 자기 인용이 된다


def fetch(url):
    return common.http_get(url, timeout=25).decode("utf-8", "replace")


def parse(page):
    """미리보기 한 쪽 → 글 목록. 글자 없는 사진 글은 빈 본문으로 남긴다"""
    out = []
    for b in re.split(r'(?=<div class="tgme_widget_message_wrap)', page)[1:]:
        pid, ts = re.search(rf'data-post="{HANDLE}/(\d+)"', b), re.search(r'<time[^>]*datetime="([^"]+)"', b)
        if not pid or not ts:
            continue
        m = re.search(r'js-message_text[^>]*>(.*?)</div>', b, re.S)
        text = html.unescape(re.sub(r"<[^>]+>", "", re.sub(r"<br\s*/?>", "\n", m.group(1)))).strip() if m else ""
        at = datetime.fromisoformat(ts.group(1)).astimezone(common.KST)
        out.append({"id": int(pid.group(1)), "at": common.iso(at), "text": text, "url": f"https://t.me/{HANDLE}/{pid.group(1)}",
                    "forwarded": "forwarded_from" in b, "photo": "photo_wrap" in b})
    return out


def load(path=None):
    p = path or OUT
    if not p.exists():
        return {}
    return {r["id"]: r for r in (json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip())}


def save(posts, path=None):
    p = path or OUT
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(posts[k], ensure_ascii=False) + "\n" for k in sorted(posts)), encoding="utf-8")


def collect(get=fetch, path=None, pause=1.0, now=None):
    """새 글 수. 최신 쪽의 글은 고쳐졌을 수 있어 덮어쓴다"""
    posts = load(path)
    cutoff = (now or common.now_kst()) - timedelta(days=BACKFILL_DAYS)
    known = max(posts, default=0)
    new, url = 0, PAGE
    for _ in range(MAX_PAGES):
        page = parse(get(url))
        if not page:
            break
        new += sum(p["id"] not in posts for p in page)
        posts.update({p["id"]: p for p in page})
        low = min(p["id"] for p in page)
        if (known and low <= known) or low <= 1 or min(p["at"] for p in page) < common.iso(cutoff):
            break
        url = f"{PAGE}?before={low}"
        time.sleep(pause)
    save(posts, path)
    return new


def run():
    """run_hourly용 — (신규 건수, 실패 목록). 알림은 보내지 않는다"""
    new = collect()
    common.record_health(SOURCE_ID, True)
    return new, []


def recent(days=14, columns=False, path=None, now=None):
    start = common.iso((now or common.now_kst()) - timedelta(days=days))
    rows = [p for p in load(path).values() if p["at"] >= start and AGENT_MARK not in p["text"]]
    return sorted((p for p in rows if not columns or len(p["text"]) >= COLUMN_CHARS), key=lambda p: p["at"], reverse=True)


def about(terms, days=365, path=None, now=None):
    pats = [re.compile(rf"(?<![A-Za-z]){re.escape(t)}(?![A-Za-z])", re.I) for t in terms]
    return [p for p in recent(days, path=path, now=now) if any(x.search(p["text"]) for x in pats)]


def show(rows, chars=400):
    return "\n\n".join(f"[{p['at'][:16]}] {p['url']}\n{p['text'][:chars]}" for p in rows)


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--recent", type=int)
    ap.add_argument("--columns", action="store_true")
    ap.add_argument("--about", nargs="+")
    ap.add_argument("--top", type=int, default=20)
    a = ap.parse_args(argv)
    if a.about:
        print(show(about(a.about)[:a.top]) or "해당 글 없음")
    elif a.recent:
        print(show(recent(a.recent, a.columns)[:a.top]) or "해당 글 없음")
    else:
        print(f"[딘스티커] 신규 {collect()}건 · 누적 {len(load())}건")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
