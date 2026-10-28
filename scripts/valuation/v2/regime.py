"""M7 시장 체제 (docs/valuation/v2_architecture.md) — 매일 바뀌는 할인율 재료

FRED 공개 CSV(키 불필요)에서 미 국채 10·30년, 하이일드·투자등급 스프레드, 환율을 받고,
config/valuation_v2.yaml의 월·연 단위 사전값(내재 ERP·국가위험·업종 베타)과 합쳐
knowledge/models/valuation/regime/latest.json(+ YYYYMMDD.json)에 저장한다.
체제 변화 경보: 10년물 5영업일 ±25bp, 하이일드 20영업일 ±50bp → 듀레이션·신용 노출 종목 재평가 대상.
사용: py scripts/valuation/v2/regime.py [--show]
"""
import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "radar"))
from pollers import common  # noqa: E402

OUT = ROOT / "knowledge" / "models" / "valuation" / "regime"
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv"


def cfg():
    return common.load_yaml("config/valuation_v2.yaml") or {}


def parse_fred(text):
    """[(날짜, 값)] — 결측('.' 또는 빈칸)은 건너뜀"""
    out = []
    for line in text.strip().splitlines()[1:]:
        parts = line.split(",")
        if len(parts) == 2 and parts[1] not in ("", "."):
            try:
                out.append((parts[0], float(parts[1])))
            except ValueError:
                continue
    return out


def fetch_series(sid, start):
    return parse_fred(common.http_get(FRED, {"id": sid, "cosd": start.isoformat()}, timeout=30).decode("utf-8", "replace"))


def change(series, n):
    """마지막 값 − n개 관측 전 값"""
    if len(series) <= n:
        return None
    return round(series[-1][1] - series[-1 - n][1], 4)


def build(fetch=fetch_series, today=None):
    c = cfg()
    today = today or date.today()
    start = today - timedelta(days=120)
    data, errors = {}, []
    for key, sid in (c.get("fred_series") or {}).items():
        try:
            s = fetch(sid, start)
            if s:
                data[key] = {"value": s[-1][1], "date": s[-1][0], "chg_5": change(s, 5), "chg_20": change(s, 20), "series": sid}
        except Exception as exc:
            errors.append(f"{sid}: {type(exc).__name__}")
    pri = c.get("regime_priors") or {}
    rf = data.get("ust10y", {}).get("value")
    reg = {"as_of": today.isoformat(), "rf_us": None if rf is None else rf / 100, "erp": pri.get("erp", {}).get("value"),
           "erp_as_of": pri.get("erp", {}).get("as_of"), "crp": pri.get("crp", {}), "industry": pri.get("industry", {}),
           "market": data, "errors": errors, "alerts": []}
    t10 = data.get("ust10y", {}).get("chg_5")
    if t10 is not None and abs(t10) >= 0.25:
        reg["alerts"].append(f"미 10년물 5영업일 {t10:+.2f}%p — 듀레이션 상위 종목 재평가")
    hy = data.get("hy_oas", {}).get("chg_20")
    if hy is not None and abs(hy) >= 0.50:
        reg["alerts"].append(f"하이일드 스프레드 20영업일 {hy:+.2f}%p — 신용 노출(고객 신용 포함) 종목 재평가")
    return reg


def save(reg):
    OUT.mkdir(parents=True, exist_ok=True)
    text = json.dumps(reg, ensure_ascii=False, indent=1)
    (OUT / "latest.json").write_text(text, encoding="utf-8")
    (OUT / f"{reg['as_of'].replace('-', '')}.json").write_text(text, encoding="utf-8")


def load():
    p = OUT / "latest.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def run():
    """run_hourly용 — (저장 여부, 오류)"""
    reg = build()
    if reg["rf_us"] is not None:
        save(reg)
    common.record_health("src-regime", reg["rf_us"] is not None, "; ".join(reg["errors"]) or None)
    return reg["rf_us"] is not None, reg["errors"]


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", action="store_true", help="받지 않고 저장된 값만")
    a = ap.parse_args(argv)
    reg = load() if a.show else build()
    if not a.show and reg["rf_us"] is not None:
        save(reg)
    m = reg["market"]
    print(f"[시장 체제] {reg['as_of']} 무위험(미 10년) {reg['rf_us']:.2%} · ERP {reg['erp']:.2%}({reg['erp_as_of']})")
    for k, v in m.items():
        print(f"- {k}: {v['value']} ({v['date']}, 5일 {v['chg_5']}, 20일 {v['chg_20']})")
    for a_ in reg["alerts"]:
        print("경보:", a_)
    if reg["errors"]:
        print("실패:", "; ".join(reg["errors"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
