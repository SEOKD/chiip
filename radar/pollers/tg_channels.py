"""공개 텔레그램 채널 수집 (마스터 지시 2026-11-01 "아래 채널들에 올라오는 모든 피드를 다 수집하고 실시간으로 파악하라")

공개 웹 미리보기 t.me/s/<채널>만 GET으로 읽는다. 봇·API·로그인·개인 계정을 쓰지 않는다. 미리보기가 꺼진 채널은 읽지 못하고 상태에 남긴다.
5분마다 모든 글을 radar/inbox/tg_channels/<채널>.jsonl(git 제외)에 쌓는다. 인박스 항목을 만들지 않아 모델 판정을 부르지 않는다.
판단은 radar/pulse.py fetch_telegram이 맡는다 — 감시 종목·기술 키워드가 걸린 글만 회차를 열고, 나머지는 회차가 열릴 때 목록으로 넘긴다.
사용: py radar/pollers/tg_channels.py --status
      py radar/pollers/tg_channels.py --recent 24 [--channel marketfeed]   # 최근 N시간
      py radar/pollers/tg_channels.py --about GE Vernova GEV              # 이름이 나온 글
"""
import argparse
import html
import json
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pollers import common  # noqa: E402

DIR = common.ROOT / "radar" / "inbox" / "tg_channels"
SOURCE_ID = "src-tg-channels"
STATE = "tg_channels"
MAX_PAGES = 3      # 한 번에 거슬러 읽는 쪽 수(쪽당 약 20개)
BACKFILL_DAYS = 7  # 처음 수집 때 거슬러 올라가는 기간


def config():
    return common.load_yaml("config/tg_channels.yaml")


def fetch(url):
    return common.http_get(url, timeout=25).decode("utf-8", "replace")


def parse(page, seen=""):
    """미리보기 한 쪽 → 글 목록. 글자 없는 미디어 글도 남긴다"""
    out = []
    for b in re.split(r'(?=<div class="tgme_widget_message_wrap)', page)[1:]:
        post, ts = re.search(r'data-post="([^"/]+)/(\d+)"', b), re.search(r'<time[^>]*datetime="([^"]+)"', b)
        if not post or not ts:
            continue
        m = re.search(r'js-message_text[^>]*>(.*?)</div>', b, re.S)
        raw = m.group(1) if m else ""
        text = html.unescape(re.sub(r"<[^>]+>", "", re.sub(r"<br\s*/?>", "\n", raw))).strip()
        fwd = re.search(r'forwarded_from_name[^>]*>(?:<span[^>]*>)?([^<]+)', b)
        link = next((u for u in re.findall(r'href="(https?://[^"]+)"', raw) if "t.me/" not in u), "")
        out.append({"id": int(post.group(2)), "channel": post.group(1), "at": common.iso(datetime.fromisoformat(ts.group(1)).astimezone(common.KST)), "text": text, "url": f"https://t.me/{post.group(1)}/{post.group(2)}",
                    "forwarded_from": html.unescape(fwd.group(1)).strip() if fwd else "", "link": html.unescape(link), "media": "photo_wrap" in b or "document_wrap" in b, "seen": seen})
    return out


def path_of(handle):
    return DIR / f"{handle}.jsonl"


def load(handle):
    p = path_of(handle)
    if not p.exists():
        return {}
    return {r["id"]: r for r in (json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip())}


def save(handle, posts):
    DIR.mkdir(parents=True, exist_ok=True)
    path_of(handle).write_text("".join(json.dumps(posts[k], ensure_ascii=False) + "\n" for k in sorted(posts)), encoding="utf-8")


def collect(handle, get=fetch, pause=1.0, now=None):
    """새 글 수. 고쳐진 글은 덮어쓰되 처음 본 시각은 지킨다. 미리보기가 없으면 None"""
    now = now or common.now_kst()
    posts = load(handle)
    known, new = max(posts, default=0), 0
    url = f"https://t.me/s/{handle}"
    cutoff = common.iso(now - timedelta(days=BACKFILL_DAYS))
    for i in range(MAX_PAGES):
        page = parse(get(url), common.iso(now))
        if not page:
            if i == 0:
                return None
            break
        for p in page:
            if p["id"] in posts:
                p["seen"] = posts[p["id"]].get("seen") or p["seen"]
            else:
                new += 1
            posts[p["id"]] = p
        low = min(p["id"] for p in page)
        if (known and low <= known) or low <= 1 or min(p["at"] for p in page) < cutoff:
            break
        url = f"https://t.me/s/{handle}?before={low}"
        time.sleep(pause)
    save(handle, posts)
    return new


def poll(env=None):
    """run_poll용. 인박스 항목은 돌려주지 않는다"""
    st = common.load_state(STATE, {})
    fails, closed, total = [], [], 0
    for c in config()["channels"]:
        try:
            n = collect(c["handle"])
            if n is None:
                closed.append(c["handle"])
            else:
                total += n
        except Exception as exc:
            fails.append(f"{c['handle']}: {type(exc).__name__}")
        time.sleep(1.0)
    st.update({"at": common.iso(common.now_kst()), "new": total, "closed": closed, "fails": fails})
    common.save_state(STATE, st)
    common.record_health(SOURCE_ID, not fails or len(fails) < len(config()["channels"]), "; ".join(fails) or None)
    return []


def since(mark):
    """mark 뒤에 처음 본 글, 시간순"""
    rows = [r for c in config()["channels"] for r in load(c["handle"]).values() if r.get("seen", "") > mark]
    return sorted(rows, key=lambda r: r["at"])


def _key(text):
    return re.sub(r"\W+", "", text.lower())[:80]


def dedupe(rows):
    """같은 글이 여러 채널에 올라오면 한 건으로 묶고 처음 올린 채널을 남긴다 — 재전송은 독립 확인이 아니다"""
    out, seen = [], {}
    for r in rows:
        k = _key(r["text"])
        if len(k) >= 30 and k in seen:
            seen[k].setdefault("also", []).append(r["channel"])
            continue
        if len(k) >= 30:
            seen[k] = r
        out.append(r)
    return out


def relevant(r, cfg, tech_re):
    """회차를 열 만한 글 — 감시 종목, 기술 키워드, 또는 전문 채널"""
    text = r["text"]
    if len(text) < cfg["min_chars"]:
        return False
    if r["channel"].lower() in {c["handle"].lower() for c in cfg["channels"] if c.get("always")}:
        return True
    return bool(common.match_entities(text) or tech_re.search(text) or any(k.lower() in text.lower() for k in cfg["keywords"]))


def recent(hours=24, channel=None, now=None):
    start = common.iso((now or common.now_kst()) - timedelta(hours=hours))
    rows = [r for c in config()["channels"] if not channel or c["handle"].lower() == channel.lower() for r in load(c["handle"]).values() if r["at"] >= start]
    return sorted(rows, key=lambda r: r["at"], reverse=True)


def about(terms, hours=24 * 30):
    pats = [re.compile(rf"(?<![A-Za-z]){re.escape(t)}(?![A-Za-z])", re.I) for t in terms]
    return [r for r in recent(hours) if any(p.search(r["text"]) for p in pats)]


def show(rows, chars=300):
    return "\n\n".join(f"[{r['at'][:16]} @{r['channel']}] {r['url']}\n{r['text'][:chars]}" for r in rows)


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--recent", type=int)
    ap.add_argument("--channel")
    ap.add_argument("--about", nargs="+")
    ap.add_argument("--top", type=int, default=20)
    a = ap.parse_args(argv)
    if a.about:
        print(show(about(a.about)[:a.top]) or "해당 글 없음")
    elif a.recent:
        print(show(recent(a.recent, a.channel)[:a.top]) or "해당 글 없음")
    else:
        st = common.load_state(STATE, {})
        for c in config()["channels"]:
            rows = load(c["handle"])
            print(f"{c['handle']}: 누적 {len(rows)}건 · 마지막 {max((r['at'] for r in rows.values()), default='없음')[:16]}" + (" · 미리보기 꺼짐" if c["handle"] in (st.get("closed") or []) else ""))
        print(f"마지막 수집 {st.get('at')} · 실패 {st.get('fails') or '없음'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
