"""리서치·투자자 감시 (BUILD_PROMPT §21.11) — config/research_watch.yaml

두 채널:
  poll_feeds — 리서치 기관·독립 애널리스트의 공개 RSS (src-research-feeds, 지금 가동)
  poll_x     — X 공식 API 사용자 타임라인 (src-research-x, 비용 승인·키 입력 전엔 꺼짐)
X 웹 화면 수집은 하지 않는다(robots.txt 전면 차단). 글은 의견·추정이며 사실이 아니다 — 제목·링크·200자 요지만 저장.
사용: py radar/pollers/research_watch.py --digest [--hours 16]
"""
import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from pollers import common, rss
else:
    from . import common, rss

FEED_SRC = "src-research-feeds"
X_SRC = "src-research-x"
FEED_MAX_AGE_DAYS = 3  # 첫 실행·장애 복구 때 옛 글이 판정 대기열을 덮지 않게


def load_cfg():
    return common.load_yaml("config/research_watch.yaml") or {}


def _extra(acc):
    return {"research_id": acc["id"], "research_kind": acc.get("kind"), "publisher": acc["name"], "tier": "글로벌"}


def _recent(iso_s, days):
    if not iso_s:
        return True
    try:
        dt = datetime.fromisoformat(iso_s.replace("Z", "+00:00"))
    except ValueError:
        return True
    return common.now_kst() - dt <= timedelta(days=days)


# ---------- 공개 RSS ----------
def poll_feeds(env=None):
    items, errors = [], []
    accs = [a for a in load_cfg().get("accounts", []) if a.get("feed")]
    for acc in accs:
        try:
            entries = rss.parse_feed(common.http_get(acc["feed"], timeout=25))
        except Exception as exc:  # 피드 하나가 죽어도 나머지는 계속
            errors.append(f"{acc['id']}: {type(exc).__name__}")
            continue
        for e in entries:
            pub = rss.to_iso(e["date"])
            if not e["link"] or not _recent(pub, FEED_MAX_AGE_DAYS):
                continue
            items.append(common.make_item(
                FEED_SRC, hashlib.sha1(e["link"].encode()).hexdigest()[:16], e["link"],
                common.strip_tags(e["title"]), pub, "리서치", "en", common.strip_tags(e["desc"])[:200],
                extra=_extra(acc)))
    if errors and len(errors) == len(accs):
        raise RuntimeError("리서치 피드 전부 실패: " + ", ".join(errors[:5]))
    if errors:
        print("리서치 피드 일부 실패:", ", ".join(errors))
    return items


# ---------- X 공식 API ----------
def _x_get(base, path, token, params):
    url = f"{base}{path}?{urllib.parse.urlencode(params)}"
    try:
        return json.loads(common.http_get(url, headers={"Authorization": f"Bearer {token}"}, timeout=30))
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise RuntimeError(f"X API 인증·권한 거부(HTTP {exc.code}) — 키·크레딧 확인") from exc
        if exc.code == 402:
            raise RuntimeError("X API 크레딧 부족(HTTP 402)") from exc
        raise


def _resolve_ids(base, token, handles, state):
    ids = state.setdefault("ids", {})
    todo = [h for h in handles if h.lower() not in ids and h.lower() not in state.get("missing", [])]
    for i in range(0, len(todo), 100):
        chunk = todo[i:i + 100]
        data = _x_get(base, "/users/by", token, {"usernames": ",".join(chunk)})
        found = {u["username"].lower(): u["id"] for u in data.get("data", [])}
        ids.update(found)
        state.setdefault("missing", []).extend(h.lower() for h in chunk if h.lower() not in found)
    return ids


def poll_x(env=None):
    cfg = load_cfg()
    xc = cfg.get("x_api") or {}
    token = (env or common.load_env()).get(xc.get("key_env", "X_BEARER_TOKEN"))
    if not token:
        raise RuntimeError("X_BEARER_TOKEN 없음 (D:\\local-only\\secrets\\.env)")
    state = common.load_state("research_x", {})
    month = common.now_kst().strftime("%Y-%m")
    if state.get("month") != month:
        state.update(month=month, posts=0)
    cap = int(xc.get("monthly_post_cap", 10000))
    base = xc.get("base", "https://api.x.com/2")
    accs = [a for a in cfg.get("accounts", []) if a.get("x_handle")]
    ids = _resolve_ids(base, token, [a["x_handle"] for a in accs], state)
    since = state.setdefault("since", {})
    items = []
    try:
        for acc in accs:
            h = acc["x_handle"].lower()
            if h not in ids:
                continue
            if state["posts"] >= cap:
                print(f"X 월 상한 {cap}건 도달, 이번 달 수집 중단")
                break
            params = {"max_results": xc.get("max_results", 20), "post.fields": "created_at,note_post,public_metrics",
                      "exclude": ",".join(xc.get("exclude", ["replies", "retweets"]))}
            if since.get(h):
                params["since_id"] = since[h]
            else:  # 첫 실행은 하루치만
                params["start_time"] = (common.now_kst() - timedelta(days=1)).astimezone(
                    timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            try:
                data = _x_get(base, f"/users/{ids[h]}/tweets", token, params)
            except urllib.error.HTTPError as exc:
                if exc.code == 429:
                    print("X API 호출 제한(429), 다음 주기에 이어서")
                    break
                raise
            posts = data.get("data", [])
            state["posts"] += len(posts)
            if data.get("meta", {}).get("newest_id"):
                since[h] = data["meta"]["newest_id"]
            for p in posts:
                text = ((p.get("note_post") or {}).get("text") or p.get("text") or "").replace("\n", " ")
                m = p.get("public_metrics") or {}
                extra = _extra(acc)
                extra.update(author=f"@{acc['x_handle']}",
                             engagement={k: m.get(k) for k in ("like_count", "repost_count", "quote_count")})
                items.append(common.make_item(
                    X_SRC, p["id"], f"https://x.com/{acc['x_handle']}/status/{p['id']}",
                    f"@{acc['x_handle']}: {text[:120]}", common.iso(_utc(p.get("created_at"))), "SNS", "en",
                    text[:200], extra=extra))
    finally:
        common.save_state("research_x", state)
    return items


def _utc(s):
    if not s:
        return common.now_kst()
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(common.KST)


# ---------- 브리프용 요약 ----------
def digest(hours=16):
    names = {a["id"]: a for a in load_cfg().get("accounts", [])}
    rows = []
    for day in sorted(common.INBOX.glob("20*"))[-3:]:
        for f in day.glob("*.json"):
            try:
                it = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if it.get("source_id") not in (FEED_SRC, X_SRC):
                continue
            if not _recent(it.get("detected_at"), hours / 24):
                continue
            rows.append(it)
    rows.sort(key=lambda r: r.get("published_at") or "", reverse=True)
    out = [f"### 리서치·투자자 동향 (최근 {hours}시간, {len(rows)}건 — 의견·추정, 사실 아님)"]
    if not rows:
        out.append("- 새 글 없음")
    by = {}
    for r in rows:
        by.setdefault(r.get("research_id"), []).append(r)
    for rid, rs in by.items():
        acc = names.get(rid, {})
        out.append(f"- **{acc.get('name', rid)}** ({acc.get('kind', '')})")
        for r in rs[:5]:
            ent = ",".join(r.get("entities_matched", [])) or "-"
            out.append(f"  - {r.get('published_at', '')[5:16]} [{r['doc_type']}] {r['title'][:110]} | {ent} | {r['url']}")
    xs = common.load_state("research_x", {})
    if xs.get("month"):
        out.append(f"- X API 이번 달 수신 {xs.get('posts', 0)}건 (상한 {(load_cfg().get('x_api') or {}).get('monthly_post_cap')})")
    return "\n".join(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--digest", action="store_true")
    ap.add_argument("--hours", type=int, default=16)
    ap.add_argument("--feeds", action="store_true", help="피드만 한 번 수집해 개수 출력(저장 안 함)")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if a.feeds:
        its = poll_feeds()
        print(f"최근 {FEED_MAX_AGE_DAYS}일 글 {len(its)}건")
        for it in its[:15]:
            print("-", it["publisher"], "|", it["title"][:80])
    else:
        print(digest(a.hours))
