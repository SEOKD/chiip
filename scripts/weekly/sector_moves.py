"""Weekly Review '섹터 온도' — AI 밸류체인 + 그 주 크게 움직인 섹터(상승·하락 모두) (마스터 지시 2026-11-14
"Weekly Review 섹터 온도는 AI 밸류체인뿐 아니라 이번 주 변동이 컸던(상승과 하락 모두) 섹터를 모두 포함시켜줘")

후보 = Portfolio 섹터 선정과 같은 38개 묶음(config/sector_select.yaml groups — Chiip AI 바스켓 4 + 미국 11개 업종 + 산업·테마).
숫자는 scripts/portfolio/sector_select.py metrics()를 그대로 쓴다(구성 종목 주간 등락의 중앙값, SPY 대비, EPS 추정 변화).
Portfolio 상태(연속 횟수·스냅숏)는 건드리지 않는다 — 주간 시세만 따로 받아 계산한다.

  1. py scripts/weekly/sector_moves.py --symbols                  # TradingView get_symbol_data_batch로 받을 기호(50개씩), 열은 sector_select.COLS
  2. 응답을 {"as_of": "금요일", "q": {기호: [열 순서 값]}}로 저장 → py scripts/weekly/sector_moves.py --put <주차> <파일>
     → knowledge/models/weekly_sectors/<주차>.json
  3. 렌더러가 고른다: Chiip AI 바스켓(항상) + S&P 500 대비 주간 등락 차이 |rs5| ≥ config weekly_review.yaml sector_moves.big
     + 상승·하락 각 상위 top개(조용한 주에도 양쪽을 본다), 최대 max개.
     절대 등락이 아니라 S&P 대비로 고르는 이유: 시장 전체가 오른 주에 절대 기준이면 상승 섹터만 수십 개가 걸리고 하락 섹터가 밀려난다.
모델은 JSON sector_reads {섹터 id: 읽기 한 구절}만 쓴다. 없으면 '-'.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "knowledge" / "models" / "weekly_sectors"
sys.path.insert(0, str(ROOT / "scripts" / "portfolio"))
import sector_select as ss  # noqa: E402


def put(week, path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    q = {k: ss._row(v) for k, v in (data.get("q") or {}).items()}
    if not q:
        raise SystemExit(f"입력 없음: {path}")
    c = ss.cfg()
    gs = ss.groups(c)
    sec = ss._j(ss.DIR / "sector_latest.json")
    rev30 = {k: v.get("rev30") for k, v in (sec.get("sectors") or {}).items()}
    snap = ss._j(ss.SNAP)   # 읽기만 — eps_revision이 사본을 고쳐도 저장하지 않는다
    rev = ss.eps_revision(q, data.get("as_of"), c.get("eps_rev_days", 20), snap)
    mx, bench = ss.metrics(gs, q, c.get("bench", "AMEX:SPY"), rev30, rev, {}, c)
    out = {"week": week, "as_of": data.get("as_of"), "bench": bench,
           "sectors": {k: {**v, "chiip": gs[k]["chiip"]} for k, v in mx.items()}, "missing": sorted(set(ss.symbols(c)) - set(q))}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{week}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def load(week):
    p = OUT / f"{week}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def pick(data, conf=None):
    """[섹터 행] — Chiip 바스켓 + 크게 움직인 섹터, 주간 등락 내림차순"""
    conf = conf or {}
    big, top, cap = conf.get("big", 0.04), conf.get("top", 2), conf.get("max", 16)
    rows = [{"id": k, **v} for k, v in (data.get("sectors") or {}).items() if v.get("r5") is not None]
    keep = {r["id"] for r in rows if r.get("chiip")}
    keep |= {r["id"] for r in rows if r.get("rs5") is not None and abs(r["rs5"]) >= big}
    s = sorted(rows, key=lambda r: -r["r5"])
    keep |= {r["id"] for r in s[:top]} | {r["id"] for r in s[-top:]}
    chosen = [r for r in s if r["id"] in keep]
    if len(chosen) > cap:   # 넘치면 AI 바스켓은 두고 나머지는 움직임이 큰 순
        ai = [r for r in chosen if r.get("chiip")]
        rest = sorted([r for r in chosen if not r.get("chiip")], key=lambda r: -abs(r.get("rs5") or 0))[:max(cap - len(ai), 0)]
        chosen = sorted(ai + rest, key=lambda r: -r["r5"])
    for r in chosen:
        r["why_in"] = "AI 밸류체인" if r.get("chiip") else ("시장보다 크게 오름" if (r.get("rs5") or 0) > 0 else "시장보다 크게 내림")
    return chosen


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if "--symbols" in argv:
        syms = ss.symbols()
        for i in range(0, len(syms), 50):
            print(json.dumps(syms[i:i + 50]))
        print(json.dumps({"columns": ss.COLS, "n": len(syms)}))
    elif "--put" in argv:
        i = argv.index("--put")
        out = put(argv[i + 1], argv[i + 2])
        print(f"[섹터 온도] {out['week']} 섹터 {len(out['sectors'])}개 · 누락 기호 {len(out['missing'])}")
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
