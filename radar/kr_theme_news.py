"""국장 테마 언급 가속 — 공개 텔레그램 채널(이미 수집 중인 17곳) 글에서 테마 어휘가 나온 글 수를 하루 단위로 센다
(마스터 지시 2026-11-15 국장 테마 채널, 어휘 config/kr_themes.yaml buzz)

결정론(run_hourly 1440분, 네트워크 요청 없음). 입력 radar/inbox/tg_channels/<채널>.jsonl(radar/pollers/tg_channels.py가 t.me/s 공개 미리보기로 쌓는다 —
robots.txt 없음, docs/channels/telegram.md 승인 채널). 글 수만 저장한다 — 본문·작성자는 옮기지 않는다.
결과 knowledge/models/discovery/kr_theme/news.csv(날짜·테마·글 수) — 판정은 scripts/discovery/kr_theme.py(20일 평균 대비 배수).
Google News RSS는 쓰지 않는다: news.google.com robots.txt가 /rss를 모든 수집기에 막고 ClaudeBot을 전면 차단한다(2026-11-15 확인 — 마스터 결정 대기, TODO_MASTER).
금지 연결: 언급 수 → 수요·펀더멘털이 아니다. 채널 구성이 한국 셀사이드·리테일 위주라 기울어 있다(가속으로만 읽는다).
사용: py radar/kr_theme_news.py [--backfill 일수]
"""
import csv
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

TG = common.ROOT / "radar" / "inbox" / "tg_channels"
OUT = common.ROOT / "knowledge" / "models" / "discovery" / "kr_theme" / "news.csv"
FIELDS = ["date", "theme", "count", "source"]
SOURCE_ID = "src-kr-theme-news"


def messages(since):
    """[(KST 날짜, 본문)] — since 이후, 같은 채널·글 번호는 한 번만"""
    out, seen = [], set()
    for p in sorted(TG.glob("*.jsonl")) if TG.exists() else []:
        with p.open(encoding="utf-8") as f:
            for line in f:
                try:
                    m = json.loads(line)
                except ValueError:
                    continue
                k = (m.get("channel"), m.get("id"))
                if k in seen:
                    continue
                seen.add(k)
                try:
                    d = datetime.fromisoformat(m.get("at") or "").date()
                except ValueError:
                    continue
                if d >= since:
                    out.append((d, m.get("text") or ""))
    return out


def counts(msgs, themes):
    """{(날짜, 테마): 글 수} — 테마 어휘 하나라도 나온 글"""
    out = {}
    for d, text in msgs:
        for t in themes:
            terms = t.get("buzz") or []
            if terms and any(w in text for w in terms):
                out[(d.isoformat(), t["id"])] = out.get((d.isoformat(), t["id"]), 0) + 1
    return out


def run(today=None, backfill=None):
    today = today or common.now_kst().date()
    themes = (common.load_yaml("config/kr_themes.yaml") or {}).get("themes") or []
    days = backfill or 2
    since = today - timedelta(days=days)
    c = counts(messages(since), themes)
    have = {}
    if OUT.exists():
        with OUT.open(encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                have[(r["date"], r["theme"])] = r
    rows = []
    d = since
    while d < today:   # 끝난 날만(오늘은 아직 쌓이는 중)
        for t in themes:
            k = (d.isoformat(), t["id"])
            if t.get("buzz") and k not in have:
                rows.append({"date": k[0], "theme": t["id"], "count": c.get(k, 0), "source": "telegram"})
        d += timedelta(days=1)
    if rows:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        new = not OUT.exists() or OUT.stat().st_size == 0
        with OUT.open("a", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            if new:
                w.writeheader()
            w.writerows(rows)
    common.record_health(SOURCE_ID, True, None)
    return f"테마 언급 {len(rows)}행(텔레그램 {len(list(TG.glob('*.jsonl'))) if TG.exists() else 0}개 채널)", 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    b = int(sys.argv[sys.argv.index("--backfill") + 1]) if "--backfill" in sys.argv else None
    print(run(backfill=b)[0])
