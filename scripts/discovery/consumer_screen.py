"""Chiip Consumer 신규 발굴 스크린 (마스터 지시 2026-11-04 "SharkNinja 같은 소비재 성장 종목을 발굴하는 파이프라인이 잘 구현돼 있는지 점검하고 보완")

점검 결과: config/consumer.yaml 지도(손으로 고른 30개사)만 다시 재고 있어 지도 밖 종목은 들어올 길이 없었다(SharkNinja·YETI 같은 소형 가전·생활 내구재 부문도 없음).
이 스크립트가 TradingView 스크리너 결과(모델이 mcp-tv-run-screener로 받은 JSON)를 결정론으로 걸러 지도 밖 후보를 config/consumer_auto.yaml에 넣는다.
  관문  미국 거래소(OTC 제외) · 시가총액 min_mcap~max_mcap · 매출 TTM 성장 ≥ min_growth · 매출총이익률 ≥ min_gm(가격 결정력)
        · 업종이 소비재 지도 부문으로 매핑되는 것만(자동차·식품 원자재 등 제외) · 이미 지도에 있으면 건너뜀
  편입  관문 통과 후보를 성장률 순으로 max_new개까지(한 회차) · 자동 지도 상한 max_auto
  이후  scripts/discovery/consumer.py가 지도 + 자동 지도를 같은 국면·점수로 판정한다(Fiscal 펀더멘털은 --stale·--code로 채운다)
규칙 config/consumer.yaml screen. 연구 후보이지 매수 권유가 아니다.
사용: py scripts/discovery/consumer_screen.py <스크리너 JSON> [--dry]
스크리너 호출(모델): market america, filters {"sector": ["Consumer Durables","Consumer Non-Durables","Retail Trade","Consumer Services"],
  "market_cap_basic": [1e9, null], "total_revenue_yoy_growth_ttm": [12, null]}, columns [name, description, sector, industry, market_cap_basic,
  total_revenue_yoy_growth_ttm, gross_margin_ttm], sort_by total_revenue_yoy_growth_ttm, limit 200, symbol_types ["stock"]
"""
import json
import sys
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CFG = ROOT / "config" / "consumer.yaml"
AUTO = ROOT / "config" / "consumer_auto.yaml"
EXCH = {"NYSE": "NYSE", "NASDAQ": "NASDAQ", "AMEX": "AMEX"}


def cfg():
    return yaml.safe_load(CFG.read_text(encoding="utf-8"))


def auto():
    return (yaml.safe_load(AUTO.read_text(encoding="utf-8")) or {}).get("companies") or [] if AUTO.exists() else []


def segment(industry, c):
    for seg, words in c["screen"]["industry_map"].items():
        if any(w.lower() in str(industry or "").lower() for w in words):
            return seg
    return None


def screen(rows, c=None, known=None):
    c = c or cfg()
    s = c["screen"]
    known = known if known is not None else {str(x.get("code")).upper() for x in (c.get("companies") or []) + auto()}
    out = []
    for r in rows:
        ex, _, tk = str(r.get("symbol") or "").partition(":")
        if ex not in EXCH or not tk or tk.upper() in known:
            continue
        g, gm, mc = r.get("total_revenue_yoy_growth_ttm"), r.get("gross_margin_ttm"), r.get("market_cap_basic")
        if g is None or gm is None or mc is None:
            continue
        if g < s["min_growth"] * 100 or g > s["max_growth"] * 100 or gm < s["min_gm"] * 100 or not (s["min_mcap"] <= mc <= s["max_mcap"]):
            continue
        seg = segment(r.get("industry"), c)
        if not seg:
            continue
        out.append({"id": f"us-{tk.lower()}", "name": r.get("description") or tk, "market": "us", "code": tk, "fiscal": f"{EXCH[ex]}_{tk}", "segment": seg,
                    "aliases": [r.get("description") or tk], "added_by": "chiip", "since": date.today().isoformat(),
                    "why": f"스크린: 매출 TTM {g:+.0f}% · GPM {gm:.0f}% · 시총 ${mc / 1e9:.1f}B · {r.get('industry')}"})
    out.sort(key=lambda x: -float(x["why"].split("매출 TTM ")[1].split("%")[0]))
    return out


def run(path, dry=False):
    c = cfg()
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = (data.get("data") or data).get("rows") if isinstance(data, dict) else data
    cand = screen(rows or [], c)
    have = auto()
    room = max(0, c["screen"]["max_auto"] - len(have))
    new = cand[:min(c["screen"]["max_new"], room)]
    if new and not dry:
        AUTO.write_text("# Chiip Consumer 자동 지도 — scripts/discovery/consumer_screen.py가 스크린 통과 종목을 넣는다(마스터 지시 2026-11-04). 손으로 고치지 않는다.\n"
                        + yaml.safe_dump({"companies": have + new}, allow_unicode=True, sort_keys=False, width=200), encoding="utf-8")
    return {"passed": len(cand), "added": [x["code"] for x in new], "auto_total": len(have) + (len(new) if not dry else 0), "room": room}


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(run(argv[0], dry="--dry" in argv), ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
