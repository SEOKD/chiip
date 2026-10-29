"""단계적 모델 고도화 — 파라미터는 '피팅 먼저, 추가는 나중에, 한 번에 하나씩' (마스터 지시 2026-10-29 Proviser:
"억지로 파라미터를 늘릴 필요 없다. 각 시스템의 파라미터 fitting이 끝나도 최적의 결과가 잘 나오지 않는다면 파라미터를 추가하는 식으로 단계적으로")

모델(등록부 model 값)마다 지금 단계와 다음 행동을 정한다.
  0단계 데이터 확보 — 피팅할 자료(fit.data)가 없는 사전값이 남아 있다 → 자료부터(피팅도 추가도 금지)
  1단계 기존 피팅 — 자료가 있는데 아직 피팅 안 된 파라미터가 있다 → 하네스로 walk-forward 피팅·채택 관문(새 파라미터 금지)
  2단계 잔차 진단 — 기존이 모두 피팅됐는데 연결 기능 품질이 목표(config/proviser.yaml scoring.target) 미달 →
          잔차와 후보 변수의 관계를 본다(residual_signal). |t| ≥ 2이고 논문 근거(서지·작동 원리)가 있는 후보만 등록부에 1개 proposed
  3단계 유지 — 품질 목표 충족 → 파라미터를 늘리지 않는다
채택 관문: 확장 모델은 harness.nested_test(기존 vs 기존+1, 짝지은 표본 외 손실, 누적 시도 수로 본페로니 보정)와
  관측 수 규칙(표본 외 관측 ≥ obs_per_param × (파라미터 수 + 1) — Peduzzi et al. 1996 EPV 10)을 모두 통과해야 한다.
규칙 값은 knowledge/models/params/registry.yaml design 절. 출력은 knowledge/models/params/queue.yaml(작업 지시 — Model Lab 일요일 피팅이 먼저 처리).

사용: py scripts/fit/stepwise.py --status [--write]
"""
import csv
import sys
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness  # noqa: E402
import registry  # noqa: E402

QUEUE = ROOT / "knowledge" / "models" / "params" / "queue.yaml"


def design(reg):
    return {"alpha": 0.05, "obs_per_param": 10, "quality_target": 9.0, **(reg.get("design") or {})}


def trials(model, reg):
    """그 모델에서 지금까지 시도한 파라미터 수 — 변경 기록(changelog)의 서로 다른 id + 폐기(retired) 수. 다중 검정 보정에 쓴다"""
    ids = {p["id"] for p in reg.get("params") or [] if p.get("model") == model}
    tried = {r["param_id"] for r in registry_changelog() if r.get("param_id") in ids}
    tried |= {p["id"] for p in reg.get("params") or [] if p.get("model") == model and p.get("status") == "retired"}
    return max(1, len(tried))


def registry_changelog():
    if not registry.CHANGELOG.exists():
        return []
    with registry.CHANGELOG.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def latest_quality():
    """기능별 최신 Proviser 점수(docs/proviser/scores.csv)"""
    p = ROOT / "docs" / "proviser" / "scores.csv"
    out = {}
    if p.exists():
        with p.open(encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                try:
                    out[r["task"]] = float(r["score"])
                except (KeyError, ValueError):
                    pass
    return out


def model_systems():
    """등록부 model → 연결 기능 목록(config/proviser.yaml systems.*.param_models)"""
    c = yaml.safe_load((ROOT / "config" / "proviser.yaml").read_text(encoding="utf-8")) or {}
    out = {}
    for task, s in (c.get("systems") or {}).items():
        for m in s.get("param_models") or []:
            out.setdefault(m, []).append(task)
    return out


def _fitted(p):
    return p.get("status") in ("fitted", "adopted") or bool((p.get("fit") or {}).get("last_fit"))


def stage(model, reg, quality=None, msys=None):
    """(단계 번호, 이름, 다음 행동, 근거 dict)"""
    d = design(reg)
    ps = [p for p in reg.get("params") or [] if p.get("model") == model and p.get("status") != "retired"]
    fixed = [p for p in ps if p.get("fixed_by_master")]
    live = [p for p in ps if not p.get("fixed_by_master")]
    no_data = [p["id"] for p in live if not _fitted(p) and not (p.get("fit") or {}).get("data")]
    to_fit = [p["id"] for p in live if not _fitted(p) and (p.get("fit") or {}).get("data")]
    tasks = (msys or {}).get(model, [])
    q = [quality[t] for t in tasks if quality and t in quality]
    worst = min(q) if q else None
    info = {"params": len(ps), "fixed": len(fixed), "fitted": sum(1 for p in live if _fitted(p)), "no_data": no_data, "to_fit": to_fit,
            "systems": tasks, "quality": worst, "trials": trials(model, reg)}
    if to_fit:
        return 1, "기존 피팅", f"하네스로 피팅·채택 관문: {', '.join(to_fit[:5])}" + (" 외" if len(to_fit) > 5 else ""), info
    if no_data:
        return 0, "데이터 확보", f"피팅 자료 정의·수집(fit.data): {', '.join(no_data[:5])}" + (" 외" if len(no_data) > 5 else ""), info
    if worst is not None and worst < float(d["quality_target"]):
        return 2, "잔차 진단", f"품질 {worst:.1f} < {d['quality_target']} — 잔차 vs 후보 변수(|t| ≥ 2) + 논문 근거 후보 1개만 proposed", info
    return 3, "유지", "품질 목표 충족 또는 연결 기능 없음 — 파라미터를 늘리지 않는다", info


def residual_signal(residuals, feature):
    """잔차를 후보 변수에 회귀한 기울기의 t — |t| ≥ 2면 '빠진 요인' 후보(최종 판단은 nested_test)"""
    pts = [(f, r) for f, r in zip(feature, residuals) if f is not None and r is not None]
    n = len(pts)
    fit = harness.ols([f for f, _ in pts], [r for _, r in pts])
    if not fit or n < 4:
        return None
    b, a = fit
    mx = sum(f for f, _ in pts) / n
    sxx = sum((f - mx) ** 2 for f, _ in pts)
    sse = sum((r - (a + b * f)) ** 2 for f, r in pts)
    se = (sse / (n - 2) / sxx) ** 0.5 if sxx > 0 and n > 2 else None
    return round(b / se, 2) if se else None


def can_adopt_extension(model, base_losses, ext_losses, reg, n_params_after):
    """확장(기존+1) 채택 관문 — nested_test + 관측 수 규칙"""
    d = design(reg)
    n = sum(1 for b, e in zip(base_losses, ext_losses) if b is not None and e is not None)
    need = int(d["obs_per_param"]) * (n_params_after + 1)
    if n < need:
        return False, f"표본 외 관측 {n} < {d['obs_per_param']} × (파라미터 {n_params_after} + 1) = {need}", {}
    rule = reg.get("adoption") or {}
    return harness.nested_test(base_losses, ext_losses, trials(model, reg) + 1, float(d["alpha"]), float(rule.get("min_oos_improvement", 0.05)))


def status(write=False):
    reg = registry.load()
    q, msys = latest_quality(), model_systems()
    models = sorted({p.get("model") for p in reg.get("params") or [] if p.get("model")} | set(msys))
    rows = []
    for m in models:
        st, name, act, info = stage(m, reg, q, msys)
        gap = (float(design(reg)["quality_target"]) - info["quality"]) if info["quality"] is not None else 0.0
        rows.append({"model": m, "stage": st, "stage_name": name, "action": act, "systems": info["systems"], "quality": info["quality"],
                     "params": info["params"], "fitted": info["fitted"], "trials": info["trials"], "priority": round(max(0.0, gap) + (1 if st == 1 else 0), 2)})
    rows.sort(key=lambda r: (-r["priority"], r["stage"]))
    if write:
        QUEUE.write_text("# 단계적 파라미터 작업 지시 — scripts/fit/stepwise.py --status --write(Chiip proviser 매일 갱신, Model Lab 일요일 피팅이 위에서부터 처리)\n"
                         + yaml.safe_dump({"as_of": date.today().isoformat(), "orders": rows}, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return rows


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if not argv or argv[0] != "--status":
        print(__doc__)
        return 1
    for r in status("--write" in argv):
        qq = "-" if r["quality"] is None else f"{r['quality']:.1f}"
        print(f"[{r['stage']} {r['stage_name']}] {r['model']} · 파라미터 {r['params']}(피팅 {r['fitted']}) · 연결 {','.join(r['systems']) or '-'} 품질 {qq} · 우선 {r['priority']} → {r['action']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
