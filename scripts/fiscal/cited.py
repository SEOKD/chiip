"""기사 인용 컨센서스 장부 (마스터 지시 2026-11-01, config/consensus_channels.yaml, ADR-014)

기사에 인용된 Visible Alpha·LSEG·FactSet 등의 컨센서스를 주장처럼 출처와 함께 쌓는다. 제공사 직접 데이터가 아니므로 est. 비교에 넣지 않고 대조값으로만 둔다.
같은 제공사·기간·지표·값이 다른 기사에 또 나오면 재인용이다 — origin_id를 첫 행에 묶어 독립 확인으로 세지 않는다. 제공사별 값은 평균 내지 않고 나란히 둔다.
사용: py scripts/fiscal/cited.py --add <json 파일>                     # [{ticker, period, metric, value, unit, basis, vendor, outlet, url, published, route}]
      py scripts/fiscal/cited.py --show <티커> <기간> [--before YYYY-MM-DD]   # 발표 전 값만 보려면 --before 발표일
      py scripts/fiscal/cited.py --review                               # Proviser 회차 시작: 수집 대기 종목·채널 재확인
      py scripts/fiscal/cited.py --log <채널> <판단> <근거>              # 채널 검토 기록
"""
import argparse
import csv
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "radar"))
sys.path.insert(0, str(ROOT / "scripts" / "fiscal"))
from pollers import common  # noqa: E402
import estimates  # noqa: E402

STORE = ROOT / "knowledge" / "models" / "estimates" / "cited.csv"
REVIEW = ROOT / "knowledge" / "models" / "estimates" / "channel_review.csv"
FIELDS = ["id", "saved", "ticker", "period", "metric", "value", "unit", "basis", "vendor", "outlet", "url", "published", "route", "origin_id"]
REVIEW_FIELDS = ["date", "channel", "decision", "evidence"]
NEED = ("ticker", "period", "metric", "value", "unit", "basis", "vendor", "outlet", "url", "published", "route")


def config():
    return common.load_yaml("config/consensus_channels.yaml")


def read(path=STORE):
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def problems(r, cfg):
    """저장할 수 없는 이유 목록 — 출처·시각이 없는 값은 받지 않는다"""
    out = [f"{k} 없음" for k in NEED if r.get(k) in (None, "")]
    if out:
        return out
    if r["vendor"] not in cfg["vendors"]:
        out.append(f"제공사 {r['vendor']}")
    if r["metric"] not in cfg["metrics"]:
        out.append(f"지표 {r['metric']}")
    if r["basis"] not in cfg["basis"]:
        out.append(f"기준 {r['basis']}")
    if r["route"] != "mcp" and not str(r["url"]).startswith("https://"):
        out.append("기사 주소")
    try:
        float(r["value"])
    except (TypeError, ValueError):
        out.append("값이 수가 아니다")
    try:
        date.fromisoformat(str(r["published"])[:10])
    except ValueError:
        out.append("게재 시각")
    return out


def merge(rows, stored, today):
    """(새 행, 재인용 수, 거절 목록). 같은 기사 같은 값은 건너뛴다"""
    cfg, new, again, bad = config(), [], 0, []
    have = list(stored)
    for r in rows:
        why = problems(r, cfg)
        if why:
            bad.append(f"{r.get('ticker')} {r.get('metric')}: {', '.join(why)}")
            continue
        same = [x for x in have if (x["ticker"], x["period"], x["metric"], x["vendor"]) == (r["ticker"], r["period"], r["metric"], r["vendor"]) and float(x["value"]) == float(r["value"])]
        if any(x["url"] == r["url"] for x in same):
            continue
        row = {k: r[k] for k in NEED}
        row.update({"id": f"CC-{today.replace('-', '')}-{len(have) + 1:04d}", "saved": today})
        row["origin_id"] = same[0]["origin_id"] if same else row["id"]
        again += bool(same)
        have.append(row)
        new.append(row)
    return new, again, bad


def add(path, store=STORE, today=None):
    text = Path(path).read_text(encoding="utf-8")
    rows = json.loads(text[text.index("["):text.rindex("]") + 1])
    new, again, bad = merge(rows, read(store), today or common.now_kst().date().isoformat())
    store.parent.mkdir(parents=True, exist_ok=True)
    head = not store.exists()
    with store.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if head:
            w.writeheader()
        w.writerows(new)
    return len(new), again, bad


def latest(rows, ticker, period, before=None):
    """{(지표, 제공사): 최신 행} — before가 있으면 그 날짜 전에 게재된 값만"""
    out = {}
    for r in sorted((x for x in rows if x["ticker"] == ticker and x["period"] == period), key=lambda x: x["published"]):
        if not before or str(r["published"])[:10] < before:
            out[(r["metric"], r["vendor"])] = r
    return out


def independent(rows, ticker, period, metric):
    """서로 다른 원출처 수"""
    return len({r["origin_id"] for r in rows if (r["ticker"], r["period"], r["metric"]) == (ticker, period, metric)})


def queue(rows, keys, n):
    """발표가 다가왔는데 인용값이 없는 종목부터"""
    have = {r["ticker"] for r in rows}
    ticks = [k.split("_", 1)[-1] for k in keys]
    return ([t for t in ticks if t not in have] + [t for t in ticks if t in have])[:n]


def stale(channels, today, days):
    cut = (today - timedelta(days=days)).isoformat()
    return [c["name"] for c in channels if str(c.get("checked") or "") < cut]


def review(today=None):
    today = today or common.now_kst().date()
    cfg, rows = config(), read()
    recent = [r for r in rows if r["saved"] >= (today - timedelta(days=30)).isoformat()]
    tally = {}
    for r in recent:
        tally[r["vendor"]] = tally.get(r["vendor"], 0) + 1
    print(f"[컨센서스 채널] 30일 인용값 {len(recent)}건 · 제공사별 {tally or '없음'} · 원출처 {len({r['origin_id'] for r in recent})}개")
    print("이번 회차 찾아볼 종목: " + (" ".join(queue(rows, estimates.upcoming_keys(today), cfg["queue_size"])) or "없음"))
    print("검토 후보: " + " · ".join(c["name"] for c in cfg["channels"] if c["status"] == "candidate"))
    old = stale(cfg["channels"], today, cfg["recheck_days"])
    if old:
        print("약관·robots 재확인 필요: " + " · ".join(old))
    logged = read(REVIEW)
    if logged:
        last = logged[-1]
        print(f"직전 검토: {last['date']} {last['channel']} → {last['decision']}")


def log(channel, decision, evidence, path=REVIEW, today=None):
    head = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=REVIEW_FIELDS)
        if head:
            w.writeheader()
        w.writerow({"date": today or common.now_kst().date().isoformat(), "channel": channel, "decision": decision, "evidence": evidence})


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--add")
    ap.add_argument("--show", nargs=2, metavar=("TICKER", "PERIOD"))
    ap.add_argument("--before")
    ap.add_argument("--review", action="store_true")
    ap.add_argument("--log", nargs=3, metavar=("CHANNEL", "DECISION", "EVIDENCE"))
    a = ap.parse_args(argv)
    if a.add:
        n, again, bad = add(a.add)
        print(f"[기사 인용] 새 값 {n}건(재인용 {again}건)" + (f" · 거절 {bad}" if bad else ""))
        return 0
    if a.show:
        rows = read()
        for (m, v), r in sorted(latest(rows, *a.show, a.before).items()):
            print(f"{m} | {v} | {r['value']} {r['unit']} | {r['basis']} | {r['outlet']} {str(r['published'])[:10]} | 원출처 {independent(rows, *a.show, m)}개 | {r['url']}")
        return 0
    if a.review:
        review()
        return 0
    if a.log:
        log(*a.log)
        print("[채널 검토] 기록")
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
