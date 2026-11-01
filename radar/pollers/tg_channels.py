"""공개 텔레그램 채널 수집 (마스터 지시 2026-11-01 "아래 채널들에 올라오는 모든 피드를 다 수집하고 실시간으로 파악하라")

공개 웹 미리보기 t.me/s/<채널>만 GET으로 읽는다. 봇·API·로그인·개인 계정을 쓰지 않는다. 미리보기가 꺼진 채널은 읽지 못하고 상태에 남긴다.
5분마다 모든 글을 radar/inbox/tg_channels/<채널>.jsonl(git 제외)에 쌓는다. 인박스 항목을 만들지 않아 모델 판정을 부르지 않는다.
판단은 radar/pulse.py fetch_telegram이 맡는다 — 감시 종목·기술 키워드가 걸린 글만 회차를 열고, 나머지는 회차가 열릴 때 목록으로 넘긴다.
사용: py radar/pollers/tg_channels.py --status
      py radar/pollers/tg_channels.py --recent 24 [--channel marketfeed]   # 최근 N시간
      py radar/pollers/tg_channels.py --about GE Vernova GEV              # 이름이 나온 글
      py radar/pollers/tg_channels.py --score                             # 수집 점수 10점
      py radar/pollers/tg_channels.py --image <주소>                      # 사진 글을 내려받아 모델이 읽는다
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
MAX_PAGES = 15     # 지난번 글에 닿으면 멈춘다 — PC가 꺼졌던 뒤에도 빠진 글이 없게 넉넉히(쪽당 약 20개)
FRESH_S = 120      # 이보다 최근에 읽었으면 다시 읽지 않는다
BASELINE = "2000-01-01T00:00:00+09:00"
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
        extra = [html.unescape(x).strip() for x in re.findall(r'(?:link_preview_title|link_preview_description|document_title)[^>]*>([^<]+)', b)]
        if not text and extra:   # 글 없이 링크·첨부만 올린 글
            text = " · ".join(dict.fromkeys(extra))
        img = re.search(r"message_photo_wrap[^>]*background-image:url\('([^']+)'\)", b)
        fwd = re.search(r'forwarded_from_name[^>]*>(?:<span[^>]*>)?([^<]+)', b)
        link = next((u for u in re.findall(r'href="(https?://[^"]+)"', raw) if "t.me/" not in u), "")
        out.append({"id": int(post.group(2)), "channel": post.group(1), "at": common.iso(datetime.fromisoformat(ts.group(1)).astimezone(common.KST)), "text": text, "url": f"https://t.me/{post.group(1)}/{post.group(2)}",
                    "forwarded_from": html.unescape(fwd.group(1)).strip() if fwd else "", "link": html.unescape(link), "media": "photo_wrap" in b or "document_wrap" in b, "seen": seen,
                    "image": img.group(1) if img else "", "unsupported": "message_media_not_supported" in b})
    return out


def og_text(page):
    """글 하나의 공개 페이지에서 본문 — 목록 미리보기가 지원하지 않는 형식이나 목록이 꺼진 채널도 여기서 읽힌다"""
    m = re.search(r'<meta property="og:description" content="(.*?)">', page, re.S)
    return html.unescape(m.group(1)).strip() if m else ""


def fill_unsupported(handle, posts, get, pause=0.5, limit=30):
    """목록에 본문이 없는 글을 글별 공개 페이지로 채운다. 새 글부터. 거기도 없으면 no_text로 두고 다시 묻지 않는다"""
    todo = [p for p in sorted(posts.values(), key=lambda x: -x["id"]) if not p["text"] and not p.get("image") and not p.get("no_text")][:limit]
    for p in todo:
        p["text"] = og_text(get(p["url"]))
        p["no_text"] = not p["text"]
        time.sleep(pause)
    return len(todo)


def read_post(handle, pid, base, get, seen):
    """글 번호 하나 → 글. 없는 번호는 채널 소개가 나온다"""
    url = f"https://t.me/{handle}/{pid}"
    page = get(url)
    text = og_text(page)
    if not text or text == base:
        return None
    ts = re.search(r'<time[^>]*datetime="([^"]+)"', page) or re.search(r'<time[^>]*datetime="([^"]+)"', get(url + "?embed=1"))   # 공개 페이지에 시각이 없으면 임베드에서
    at = common.iso(datetime.fromisoformat(ts.group(1)).astimezone(common.KST)) if ts else seen
    return {"id": pid, "channel": handle, "at": at, "text": text, "url": url, "forwarded_from": "", "link": "", "media": False, "seen": seen, "image": "", "unsupported": False}


def latest_id(handle, base, get, pause=0.3, top=200000):
    """목록이 꺼진 채널의 마지막 글 번호를 찾는다"""
    alive = lambda i: any(og_text(get(f"https://t.me/{handle}/{j}")) not in ("", base) for j in range(i, i + 4))
    low, high = 1, 1024
    while high < top and alive(high):
        low, high = high, high * 2
        time.sleep(pause)
    while high - low > 3:
        mid = (low + high) // 2
        low, high = (mid, high) if alive(mid) else (low, mid)
        time.sleep(pause)
    return low + 3


def collect_by_id(handle, get=fetch, pause=0.5, now=None, tail=30, misses=8, step=40):
    """글 번호를 차례로 읽는다 — 웹 목록이 꺼진 공개 채널. 처음에는 최근 tail개만 기준선으로 받는다"""
    now = now or common.now_kst()
    posts = load(handle)
    base = og_text(get(f"https://t.me/{handle}"))
    first = not posts
    start = max(1, latest_id(handle, base, get) - tail) if first else max(posts) + 1
    new, miss, i = 0, 0, start
    while miss < misses and i < start + (tail + misses if first else step):
        p = read_post(handle, i, base, get, BASELINE if first else common.iso(now))
        miss = 0 if p else miss + 1
        if p:
            posts[i] = p
            new += 1
        i += 1
        time.sleep(pause)
    save(handle, posts)
    return new


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
        page = parse(get(url), common.iso(now) if known else BASELINE)   # 처음 읽는 채널의 지난 글은 새 글이 아니다
        if not page:
            if i == 0:
                return None
            break
        for p in page:
            if p["id"] in posts:
                old = posts[p["id"]]
                p["seen"] = old.get("seen") or p["seen"]
                if not p["text"]:   # 글별 페이지에서 채운 본문을 빈 목록으로 덮지 않는다
                    p["text"], p["no_text"] = old.get("text", ""), old.get("no_text", False)
            else:
                new += 1
            posts[p["id"]] = p
        low = min(p["id"] for p in page)
        if (known and low <= known) or low <= 1 or min(p["at"] for p in page) < cutoff:
            break
        url = f"https://t.me/s/{handle}?before={low}"
        time.sleep(pause)
    fill_unsupported(handle, posts, get)
    save(handle, posts)
    return new


def poll(env=None):
    """run_poll용. 인박스 항목은 돌려주지 않는다"""
    st = common.load_state(STATE, {})
    fails, closed, total = [], [], 0
    for c in config()["channels"]:
        try:
            n = collect_by_id(c["handle"]) if c.get("mode") == "by_id" else collect(c["handle"])
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


def poll_if_stale(now=None):
    """Pulse 관문이 부른다. run_poll은 순차 실행이라 느린 수집기가 돌면 20분 넘게 밀린다(2026-11-01 점검)"""
    now = now or common.now_kst()
    at = common.load_state(STATE, {}).get("at")
    if at and (now - datetime.fromisoformat(at)).total_seconds() < FRESH_S:
        return False
    poll()
    return True


def score(now=None):
    """수집 점수 10점 — 채널·신선도·본문·오류·Pulse 전달 각 2점. Proviser가 매일 본다"""
    import glob
    now = now or common.now_kst()
    cfg, st = config(), common.load_state(STATE, {})
    rows = {c["handle"]: load(c["handle"]) for c in cfg["channels"]}
    live = sum(1 for r in rows.values() if r)
    age = (now - datetime.fromisoformat(st["at"])).total_seconds() / 60 if st.get("at") else 1e9
    fresh = 2.0 if age <= 10 else 1.5 if age <= 20 else 1.0 if age <= 60 else 0.0
    cut = common.iso(now - timedelta(days=7))
    week = [p for r in rows.values() for p in r.values() if p["at"] >= cut]
    body = sum(1 for p in week if p["text"] or p.get("image") or p.get("no_text")) / max(len(week), 1)   # 사진은 주소를 쥐고 있으면 필요할 때 읽을 수 있다
    cut2 = common.iso(now - timedelta(hours=24))
    mark = common.load_state("pulse", {}).get("tg_start") or cut2
    lag = common.iso(now - timedelta(minutes=15))   # 다음 Pulse 회차를 기다리는 글은 아직 판정하지 않는다
    recent = [p for r in rows.values() for p in r.values() if max(cut2, mark) <= p.get("seen", "") < lag and (p["text"] or p.get("image"))]   # 첫 수집이 거슬러 받은 과거 글은 빼고 Pulse가 받기 시작한 뒤의 글만
    sent = "".join(open(f, encoding="utf-8").read() for f in sorted(glob.glob(str(common.ROOT / "radar" / "pulse" / "*.json")))[-60:])
    fed = sum(1 for p in recent if p["url"] in sent) / len(recent) if recent else 1   # 새 글이 없는 시간대는 감점하지 않는다
    axes = {"채널": round(2 * live / len(rows), 1), "신선도": fresh, "본문": round(2 * body, 1), "오류": 2.0 if not st.get("fails") else 1.0, "Pulse 전달": round(2 * fed, 1)}
    return round(sum(axes.values()), 1), axes, {"수집 후 분": round(age, 1), "7일 글": len(week), "글자 없음(사진 포함)": sum(1 for p in week if not p["text"]), "사진 주소도 없음": sum(1 for p in week if not p["text"] and not p.get("image")), "24시간 새 글": len(recent)}


def save_image(url):
    """사진만 있는 글을 모델이 볼 수 있게 내려받는다 — 판단에 필요한 건만"""
    d = DIR / "images"
    d.mkdir(parents=True, exist_ok=True)
    p = d / (re.sub(r"\W+", "", url)[-40:] + ".jpg")
    p.write_bytes(common.http_get(url, timeout=25))
    return p


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
    ap.add_argument("--score", action="store_true")
    ap.add_argument("--image")
    a = ap.parse_args(argv)
    if a.image:
        print(save_image(a.image))
    elif a.score:
        print(score())
    elif a.about:
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
