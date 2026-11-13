"""실적 발표 옵션 내재 변동폭 — ATM 스트래들 ÷ 주가 (마스터 지시 2026-11-14 "옵션 내재 변동폭도 만들어라", ADR-033)

결정론(모델 없음). 실적일 직후 만기의 ATM(주가에 가장 가까운 행사가) 콜·풋 중간가 합 = 스트래들, ÷ 주가 = 시장이 가격에 넣은 실적일 변동폭.
원천: Cboe 지연 시세 JSON(cdn-api.cboe.com/api/global/delayed_quotes/options/<티커>.json — 일반 요청으로 열리고 IV·호가가 있다).
      자동 수집은 약관 판단이 애매해 마스터 승인 전까지 꺼 둔다(config/ops_view.yaml options.enabled: false — CLAUDE.md '애매하면 마스터에게 묻는다').
      꺼져 있어도 --put으로 손으로 넣은 값은 쓴다. User-Agent를 꾸미지 않는다.
저장: datapack "options_implied" = {"as_of", "spot", "expiry", "strike", "straddle", "iv", "source"} → scripts/tenbagger/ops_view.py implied_blocks
사용: py radar/options_implied.py <id> <티커> <실적일 YYYY-MM-DD> [--session after|before]   # enabled일 때만 받는다
      py radar/options_implied.py --parse <cboe json 파일> <실적일> [--session after]          # 시험·수동
      py radar/options_implied.py --put <id> <json>                                            # 손으로 넣기
"""
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

URL = "https://cdn-api.cboe.com/api/global/delayed_quotes/options/{t}.json"
SYM = re.compile(r"^([A-Z0-9]+?)(\d{6})([CP])(\d{8})$")


def cfg():
    return (yaml.safe_load((common.ROOT / "config" / "ops_view.yaml").read_text(encoding="utf-8")) or {}).get("options") or {}


def _mid(o):
    b, a = o.get("bid") or 0, o.get("ask") or 0
    return (a + b) / 2 if a and b else (o.get("last_trade_price") or None)


def parse(doc, earnings, session="after"):
    """Cboe 응답 → {expiry, strike, straddle, iv, spot}. 실적일 반응이 들어가는 첫 만기(장후 발표면 다음 날 이후)"""
    data = doc.get("data") or {}
    spot = data.get("current_price") or data.get("close")
    if not spot:
        return None
    e = date.fromisoformat(earnings) + timedelta(days=1 if session == "after" else 0)
    chain = {}
    for o in data.get("options") or []:
        m = SYM.match(str(o.get("option", "")))
        if not m:
            continue
        exp = date(2000 + int(m[2][:2]), int(m[2][2:4]), int(m[2][4:]))
        chain.setdefault(exp, {}).setdefault(int(m[4]) / 1000, {})[m[3]] = o
    exps = sorted(x for x in chain if x >= e)
    if not exps:
        return None
    exp = exps[0]
    strikes = [k for k, v in chain[exp].items() if "C" in v and "P" in v]
    if not strikes:
        return None
    k = min(strikes, key=lambda s: abs(s - spot))
    c, p = chain[exp][k]["C"], chain[exp][k]["P"]
    if _mid(c) is None or _mid(p) is None:
        return None
    ivs = [x.get("iv") for x in (c, p) if x.get("iv")]
    return {"spot": spot, "expiry": exp.isoformat(), "strike": k, "straddle": round(_mid(c) + _mid(p), 4),
            "iv": sum(ivs) / len(ivs) if ivs else None, "as_of": str(doc.get("timestamp", ""))[:16]}


def put(cid, rec):
    p = common.ROOT / "knowledge" / "models" / "companies" / cid / "datapack.json"
    dp = json.loads(p.read_text(encoding="utf-8"))
    dp["options_implied"] = rec
    p.write_text(json.dumps(dp, ensure_ascii=False, indent=1), encoding="utf-8")


def fetch(ticker):
    return json.loads(common.http_get(URL.format(t=ticker.upper()), timeout=30).decode("utf-8"))


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    sess = argv[argv.index("--session") + 1] if "--session" in argv else "after"
    if len(argv) >= 3 and argv[0] == "--parse":
        print(json.dumps(parse(json.loads(Path(argv[1]).read_text(encoding="utf-8")), argv[2], sess), ensure_ascii=False))
        return 0
    if len(argv) >= 3 and argv[0] == "--put":
        put(argv[1], json.loads(Path(argv[2]).read_text(encoding="utf-8")))
        print(f"[옵션 내재] {argv[1]} 저장")
        return 0
    if len(argv) >= 3:
        if not cfg().get("enabled"):
            print("옵션 수집 꺼짐(config/ops_view.yaml options.enabled: false — 원천 사용 마스터 승인 대기). --put으로 손으로 넣을 수 있다.")
            return 0
        rec = parse(fetch(argv[1 if len(argv) > 1 else 0]), argv[2], sess)
        if not rec:
            print("만기·ATM 짝 없음 — 값 없음")
            return 1
        put(argv[0], {**rec, "source": "Cboe 지연 시세(15분)"})
        print(json.dumps(rec, ensure_ascii=False))
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
