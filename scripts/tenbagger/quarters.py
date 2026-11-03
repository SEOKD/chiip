"""분기 손익 시계열을 datapack "quarters_hist"에 넣는다 (마스터 지시 2026-11-03). 모델 없음

본보기 scripts/fiscal/templates/quarters.js 출력(Fiscal.ai 원 단위)을 그대로 저장한다. 거시 지표 싱크로율(sync_view)과 매출→GP 비용 다리(cost_bridge_view)가 쓴다.
사용: py scripts/tenbagger/quarters.py --put <회사 id> <파일>
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def put(cid, path):
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    q = [r for r in doc.get("q") or [] if r.get("period") and r.get("rev")]
    if len(q) < 8:
        raise SystemExit(f"분기가 {len(q)}개뿐이다 — 8개 이상 필요")
    f = ROOT / "knowledge" / "models" / "companies" / cid / "datapack.json"
    dp = json.loads(f.read_text(encoding="utf-8"))
    dp["quarters_hist"] = {"source": doc.get("source"), "key": doc.get("key"), "currency": doc.get("currency"), "q": q}
    f.write_text(json.dumps(dp, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(q)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) == 4 and sys.argv[1] == "--put":
        print(f"분기 {put(sys.argv[2], sys.argv[3])}개 저장")
    else:
        raise SystemExit(__doc__)
