"""파라미터 등록부 (BUILD_PROMPT §21.14, ADR-010 §3) — knowledge/models/params/registry.yaml

등록부는 '어떤 상수가 어디서 왔고, 어떻게 피팅됐고, 표본 밖에서 얼마나 맞았나'의 장부다.
실행 중 코드는 지금처럼 config 파일의 값을 읽는다(binding). 등록부는 그 값의 출처·상태를 붙잡고,
--check로 등록부 값과 config 값이 어긋나지 않았는지 확인한다.
채택(adopt)은 표본 외 개선 기준(harness.adoption_decision)을 통과해야 하고, 큰 변경은 마스터 승인 표시가 필요하다.
config 수정은 이 스크립트가 하지 않는다 — 출력된 수정 내용을 스킬(model-lab)이 Edit로 반영한 뒤 --check.

사용: py scripts/fit/registry.py --check | --list | --bootstrap
"""
import argparse
import csv
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DIR = ROOT / "knowledge" / "models" / "params"
REGISTRY = DIR / "registry.yaml"
CHANGELOG = DIR / "changelog.csv"
CHANGE_COLS = ["date", "param_id", "old", "new", "status", "oos_prior", "oos_fit", "n_oos", "approved_by", "proposal", "note"]
STATUSES = ("prior", "proposed", "fitted", "adopted", "retired")


def load_yaml(rel_or_path):
    p = rel_or_path if isinstance(rel_or_path, Path) else ROOT / rel_or_path
    if not p.exists():
        return None
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def load():
    return load_yaml(REGISTRY) or {"params": []}


def resolve(binding):
    """'config/valuation.yaml#params.discount_rate.US' → 값 (없으면 KeyError)"""
    path, _, keys = binding.partition("#")
    node = load_yaml(path)
    for k in keys.split("."):
        if isinstance(node, list):  # universe 같은 목록은 id로 찾는다
            node = next(x for x in node if x.get("id") == k)
        else:
            node = node[k]
    return node


def check(reg=None):
    """[(id, 등록부 값, config 값)] — 어긋난 것만"""
    out = []
    for p in (reg or load())["params"]:
        if not p.get("binding") or p.get("status") == "retired":
            continue
        try:
            cur = resolve(p["binding"])
        except (KeyError, StopIteration, TypeError):
            cur = "(binding 없음)"
        if cur != p.get("value"):
            out.append((p["id"], p.get("value"), cur))
    return out


def record_change(row):
    new = not CHANGELOG.exists()
    with CHANGELOG.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CHANGE_COLS)
        if new:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in CHANGE_COLS})


def needs_approval(old, new, reg=None):
    rule = (reg or load()).get("adoption", {})
    try:
        rel = abs(float(new) - float(old)) / max(abs(float(old)), 1e-9)
    except (TypeError, ValueError):
        return True
    return rel >= float(rule.get("approval_rel_change", 0.2))


# ---------- 최초 생성: 지금 코드·설정에 박힌 상수를 옮긴다 ----------
def _p(pid, model, binding, value, unit, basis, fit=None):
    return {"id": pid, "model": model, "binding": binding, "value": value, "unit": unit, "status": "prior",
            "prior": {"value": value, "basis": basis, "source": None},
            "fit": fit or {"method": None, "target": None, "data": None, "last_fit": None, "oos_metric": None}}


def bootstrap():
    val = load_yaml("config/valuation.yaml")
    foc = load_yaml("config/focus.yaml")
    ps = []
    for reg, v in val["params"]["discount_rate"].items():
        ps.append(_p(f"prm-val-disc-{reg.lower()}", "valuation.reverse_dcf", f"config/valuation.yaml#params.discount_rate.{reg}",
                     v, "비율", "초안 가정(마스터 확인 전). 사전값 후보: 무위험금리 + 베타×다모다란 내재 ERP + 국가위험 프리미엄",
                     {"method": "CAPM 재구성(무위험금리·ERP·국가위험 공개 자료)", "target": "자기자본비용", "data": None,
                      "last_fit": None, "oos_metric": None}))
    ps.append(_p("prm-val-horizon", "valuation.reverse_dcf", "config/valuation.yaml#params.horizon_years",
                 val["params"]["horizon_years"], "년", "IB 관행(5년 명시 예측 + 터미널)"))
    for sub, s in val["subsectors"].items():
        ps.append(_p(f"prm-val-tpe-{sub}", "valuation.reverse_dcf", f"config/valuation.yaml#subsectors.{sub}.terminal_pe",
                     s["terminal_pe"], "배", f"{s['label']} 장기 P/E 초안(공개 IB 관행 종합, framework.md §4)",
                     {"method": "섹터 장기 평균 P/E(사이클 전체 구간) + 축소 추정", "target": "N년 뒤 정상 P/E",
                      "data": "가격·EPS 이력 10년+(데이터 결정 후)", "last_fit": None, "oos_metric": None}))
    for comp, w in foc["weights"].items():
        ps.append(_p(f"prm-focus-w-{comp}", "focus.score", f"config/focus.yaml#weights.{comp}", w, "가중치",
                     "균등 가중(근거 없음 — 피팅 대상)",
                     {"method": "다음 30일 |수익률|·언급량 예측력 회귀(합=1 제약, 사전값 쪽 축소)", "target": "추적 가치 실현도",
                      "data": "scores/*.csv 30일+ × 가격", "last_fit": None, "oos_metric": None}))
    ps.append(_p("prm-focus-threshold", "focus.score", "config/focus.yaml#threshold", foc["threshold"], "점",
                 "마스터 지시(5.0 이상) — 피팅하지 않는다(마스터 결정 값)"))
    ps[-1]["status"] = "adopted"
    ps[-1]["fixed_by_master"] = True
    return {
        "note": "파라미터 등록부 — scripts/fit/registry.py. 값을 바꾸면 binding 위치의 config도 같이 바꾸고 changelog.csv에 남긴다.",
        "adoption": {"min_oos_improvement": 0.05, "min_oos_n": 30, "approval_rel_change": 0.2, "shrink_k": 20,
                     "rule": "표본 외 손실이 사전값 대비 5% 이상 줄고 표본 외 관측 30개 이상일 때만 채택. 상대 변화 20% 이상은 마스터 승인"},
        "params": ps,
    }


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--bootstrap", action="store_true", help="등록부가 없을 때만 생성")
    a = ap.parse_args(argv)
    if a.bootstrap:
        if REGISTRY.exists():
            print("등록부가 이미 있다 — 덮어쓰지 않음")
            return 1
        DIR.mkdir(parents=True, exist_ok=True)
        REGISTRY.write_text(yaml.safe_dump(bootstrap(), allow_unicode=True, sort_keys=False, width=200), encoding="utf-8")
        print(f"생성: {REGISTRY.relative_to(ROOT)} ({len(load()['params'])}개)")
    if a.list:
        for p in load()["params"]:
            print(f"{p['id']:28} {p['status']:9} {p.get('value')!s:>8} {p.get('unit', '')}  ← {p.get('binding') or '-'}")
    if a.check or not (a.list or a.bootstrap):
        bad = check()
        print("[등록부 점검] " + ("일치" if not bad else f"어긋남 {len(bad)}건"))
        for pid, reg_v, cur in bad:
            print(f"- {pid}: 등록부 {reg_v} ≠ config {cur}")
        return 1 if bad else 0
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
