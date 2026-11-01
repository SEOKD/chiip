"""일본 상장사 컨센서스 (마스터 지시 2026-11-02 "일본 상장회사의 실적을 정리할 때 컨센서스 데이터를 넣을 수 있도록 다양한 경로에서 찾아봐라. 이를 지속적으로 고민하라")

Fiscal.ai·Zacks·Easyconomics는 일본 추정이 없다. TradingView 종목 칸에 분기 매출·EPS 추정과 서프라이즈가 엔화로 있다(66곳 중 매출 65곳).
결정론 스크립트는 TradingView MCP를 부를 수 없어 '대상 → 모델 호출 → 넣기'로 돈다. 경로 평가는 knowledge/methods/jp_consensus_routes.md.
  대상: 다음 발표가 DAYS_AHEAD일 안이거나 최근 DAYS_BACK일 안에 발표한 회사. 일요일은 전 회사. 호출은 50종목당 1회
  발표 직후엔 TradingView가 아직 지난 분기를 보여 줄 수 있다. 그때는 저장해 둔 다음 분기 추정이 이번 분기 est.다
  EPS는 서프라이즈가 EPS_LIMIT%를 넘으면 기준이 다른 값(일회성·GAAP)으로 보고 쓰지 않는다
저장: knowledge/models/estimates/jp_consensus.csv(값이 바뀔 때만 한 줄, 금액은 백만 엔)
사용: py radar/jp_consensus.py --targets                       # 이번에 부를 종목 묶음과 칸
      py radar/jp_consensus.py --put <파일> [<파일>...]         # get_symbol_data_batch 출력 저장
      py radar/jp_consensus.py --line <코드> [--date YYYY-MM-DD] [--guide <다음 분기 매출 억 엔>]   # 실적 ① 줄
      py radar/jp_consensus.py --coverage                      # 커버리지
"""
import csv
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

STORE = common.ROOT / "knowledge" / "models" / "estimates" / "jp_consensus.csv"
KST = timezone(timedelta(hours=9))
BATCH = 50
DAYS_AHEAD = 3
DAYS_BACK = 3
EPS_LIMIT = 100
M = 1e6
FIELDS = ["saved", "code", "release", "revenue", "revenue_est", "eps", "eps_est", "next_revenue", "next_eps", "fy_revenue", "fy_eps", "next_release"]
COLUMNS = {"revenue": "revenue_fq", "revenue_est": "revenue_forecast_fq", "eps": "earnings_per_share_fq", "eps_est": "earnings_per_share_forecast_fq",
           "next_revenue": "revenue_forecast_next_fq", "next_eps": "earnings_per_share_forecast_next_fq",
           "fy_revenue": "revenue_forecast_next_fy", "fy_eps": "earnings_per_share_forecast_next_fy"}
MONEY = ("revenue", "revenue_est", "next_revenue", "fy_revenue")


def day(ts):
    return datetime.fromtimestamp(ts, KST).date().isoformat() if ts else ""


def read(path=None):
    path = path or STORE
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def latest(rows=None):
    out = {}
    for r in read() if rows is None else rows:
        out[r["code"]] = r
    return out


def row_of(sym, d, saved):
    r = {"saved": saved, "code": sym.split(":")[1], "release": day(d.get("earnings_release_date")), "next_release": day(d.get("earnings_release_next_date"))}
    for k, col in COLUMNS.items():
        v = d.get(col)
        r[k] = "" if v is None else str(round(v / M) if k in MONEY else round(v, 2))
    return r


def put(paths, today=None, store=None):
    """get_symbol_data_batch 출력 파일들을 저장한다. 값이 바뀐 회사만 한 줄"""
    store = store or STORE
    saved = (today or date.today()).isoformat()
    rows, cur = read(store), latest(read(store))
    new = []
    for p in paths:
        text = Path(p).read_text(encoding="utf-8")
        for sym, d in (json.loads(text[text.index("{"):text.rindex("}") + 1]).get("data") or {}).items():
            r = row_of(sym, d, saved)
            if any(r[k] != (cur.get(r["code"]) or {}).get(k) for k in FIELDS[2:]):
                new.append(r)
    store.parent.mkdir(parents=True, exist_ok=True)
    with store.open("w" if not rows else "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if not rows:
            w.writeheader()
        w.writerows(new)
    return len(new)


def codes():
    watch = {c["id"]: c for c in (common.load_yaml("config/jp_watch.yaml") or {}).get("companies") or []}
    return [watch[i]["code"] for i in (common.load_yaml("config/jp_ir.yaml") or {}).get("companies") or {} if watch.get(i, {}).get("code")]


def targets(today=None, all_codes=None, cur=None):
    today = today or date.today()
    all_codes = codes() if all_codes is None else all_codes
    cur = latest() if cur is None else cur
    if today.weekday() == 6:
        picked = all_codes
    else:
        def near(c):
            r = cur.get(c) or {}
            if not r.get("next_release"):
                return True
            ahead = (date.fromisoformat(r["next_release"]) - today).days
            back = (today - date.fromisoformat(r["release"])).days if r.get("release") else 99
            return ahead <= DAYS_AHEAD or back <= DAYS_BACK
        picked = [c for c in all_codes if near(c)]
    syms = [f"TSE:{c}" for c in picked]
    return {"batches": [syms[i:i + BATCH] for i in range(0, len(syms), BATCH)],
            "columns": ["earnings_release_date", "earnings_release_next_date", *COLUMNS.values()]}


def num(x):
    return float(x) if x not in (None, "") else None


def est_for(r, event=None):
    """이번 발표의 (매출 est, EPS est, 실적 매출, 실적 EPS, 다음 분기 매출 est, 다음 분기 EPS est). 금액은 백만 엔"""
    cut = (date.fromisoformat(event) - timedelta(days=1)).isoformat() if event else ""
    if r.get("release", "") >= cut:   # TradingView가 이번 분기로 넘어갔다
        return num(r["revenue_est"]), num(r["eps_est"]), num(r["revenue"]), num(r["eps"]), num(r["next_revenue"]), num(r["next_eps"])
    return num(r["next_revenue"]), num(r["next_eps"]), None, None, None, None


def yen(m):
    """백만 엔 → '2조 4,800억 엔'"""
    eok = round(m / 100)
    jo, rest = divmod(abs(eok), 10000)
    sign = "-" if eok < 0 else ""
    if jo:
        return f"{sign}{jo}조 {rest:,}억 엔" if rest else f"{sign}{jo}조 엔"
    return f"{sign}{rest:,}억 엔"


def pct(a, b):
    return f"{(a / b - 1) * 100:+.1f}%"


def lines(r, event=None, guide=None):
    """실적 ①에 넣을 줄. 없는 칸은 줄을 만들지 않는다"""
    rev_e, eps_e, rev, eps, next_rev, next_eps = est_for(r, event)
    out = []
    if rev_e:
        out.append(f"- 매출 {yen(rev)} (est. {yen(rev_e)}, {pct(rev, rev_e)})" if rev else f"- 매출 est. {yen(rev_e)}")
    if eps_e and eps is None:
        out.append(f"- EPS est. ¥{eps_e:,.2f}")
    elif eps_e and eps_e > 0 and eps > 0 and abs(eps / eps_e - 1) * 100 <= EPS_LIMIT:
        out.append(f"- EPS ¥{eps:,.2f} (est. ¥{eps_e:,.2f}, {pct(eps, eps_e)})")
    if guide and next_rev:
        out.append(f"- 다음 분기 매출 가이던스 {yen(guide * 100)} (est. {yen(next_rev)}, {pct(guide * 100, next_rev)})")
    elif next_rev:
        out.append(f"- 다음 분기 매출 est. {yen(next_rev)}" + (f" · EPS est. ¥{next_eps:,.2f}" if next_eps else ""))
    return out


def coverage(cur=None):
    cur = latest() if cur is None else cur
    rows = list(cur.values())
    return {"companies": len(rows), "revenue_est": sum(1 for r in rows if r["revenue_est"]), "eps_est": sum(1 for r in rows if r["eps_est"]),
            "next_revenue": sum(1 for r in rows if r["next_revenue"]), "saved": max((r["saved"] for r in rows), default="")}


def arg(argv, name):
    return argv[argv.index(name) + 1] if name in argv else None


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if "--targets" in argv:
        print(json.dumps(targets(), ensure_ascii=False))
    elif "--put" in argv:
        print(f"[일본 컨센서스] 저장 {put(argv[argv.index('--put') + 1:])}건")
    elif "--line" in argv:
        r = latest().get(arg(argv, "--line"))
        print("\n".join(lines(r, arg(argv, "--date"), float(arg(argv, "--guide")) if "--guide" in argv else None)) if r else "컨센서스 기록 없음")
    else:
        print(json.dumps(coverage(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
