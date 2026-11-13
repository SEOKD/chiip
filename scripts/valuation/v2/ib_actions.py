"""IB 목표가·투자의견 변경 장부 (마스터 지시 2026-11-13 — 알파 감지 '최근 커버리지: 최근 2~3건(날짜·기관·내용)')

장부: knowledge/models/estimates/ib_actions.csv
  date(발표일, YYYY-MM-DD), id(엔티티), firm(기관), action(상향·하향·유지·개시·의견 상향·의견 하향),
  rating(의견, 없으면 빈칸), target(새 목표가), prev_target(이전 목표가), currency(KRW·USD·JPY…), source(출처 종류), url
채우는 쪽: 모델(chiip-valuation-queue '작성·갱신·내러티브' 회차, narrative-premium 스킬이 IB 커버리지를 볼 때) — `--add`.
라이선스 IB 원문(마스터 노션)은 기관·날짜·목표가·의견 같은 메타데이터만 적고 url은 비운다(source에 '마스터 노션 IB 요지').
같은 (date, id, firm)은 한 줄 — 다시 넣으면 덮어쓴다.
사용: py scripts/valuation/v2/ib_actions.py --show <id>
      py scripts/valuation/v2/ib_actions.py --add <id> <date> <firm> <action> <target> [--prev X] [--rating R] [--cur KRW] [--source S] [--url U]
"""
import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LEDGER = ROOT / "knowledge" / "models" / "estimates" / "ib_actions.csv"
FIELDS = ["date", "id", "firm", "action", "rating", "target", "prev_target", "currency", "source", "url"]
SYM = {"KRW": "₩", "USD": "$", "JPY": "¥", "TWD": "NT$", "EUR": "€", "GBP": "£"}


def load(path=None):
    p = path or LEDGER
    if not p.exists():
        return []
    with p.open(encoding="utf-8", newline="") as fh:
        return [r for r in csv.DictReader(fh) if r.get("id") and r.get("date")]


def recent(eid, n=3, path=None):
    """최근 n건(발표일 내림차순)"""
    return sorted((r for r in load(path) if r["id"] == eid), key=lambda r: r["date"], reverse=True)[:n]


def _money(v, cur):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return ""
    s = SYM.get((cur or "").upper(), "")
    return f"{s}{x:,.0f}" if x >= 100 else f"{s}{x:,.2f}"


def fmt(r):
    """'10/28 Citi 목표가 ₩3,000,000(상향)' 한 덩어리"""
    d = r["date"][5:].replace("-", "/").lstrip("0").replace("/0", "/")
    tgt, prev = _money(r.get("target"), r.get("currency")), _money(r.get("prev_target"), r.get("currency"))
    body = f"목표가 {prev}→{tgt}" if prev and tgt else (f"목표가 {tgt}" if tgt else "")
    act = r.get("action") or ""
    rating = r.get("rating") or ""
    tail = ", ".join(x for x in (act if act not in body else "", rating) if x)
    return f"{d} {r['firm']} " + (body + (f"({tail})" if tail else "") if body else tail or "변경 내용 미기재")


def add(row, path=None):
    p = path or LEDGER
    rows = [r for r in load(p) if (r["date"], r["id"], r["firm"]) != (row["date"], row["id"], row["firm"])]
    rows.append({k: row.get(k, "") for k in FIELDS})
    rows.sort(key=lambda r: (r["id"], r["date"]))
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--show")
    ap.add_argument("--add", nargs=5, metavar=("ID", "DATE", "FIRM", "ACTION", "TARGET"))
    ap.add_argument("--prev", default="")
    ap.add_argument("--rating", default="")
    ap.add_argument("--cur", default="USD")
    ap.add_argument("--source", default="")
    ap.add_argument("--url", default="")
    a = ap.parse_args(argv)
    if a.show:
        for r in recent(a.show, 10):
            print(fmt(r), f"[{r.get('source') or ''}]")
        return 0
    if a.add:
        eid, d, firm, act, tgt = a.add
        n = add({"date": d, "id": eid, "firm": firm, "action": act, "rating": a.rating, "target": tgt, "prev_target": a.prev,
                 "currency": a.cur, "source": a.source, "url": a.url})
        print(f"[IB 장부] {n}줄")
        return 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
