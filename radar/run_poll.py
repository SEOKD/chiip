"""레이더 폴링 진입점 (BUILD_PROMPT §10.4~10.5, §21.3)

Windows 작업 스케줄러가 몇 분마다 실행한다. 모델은 부르지 않는다.
1) 기한이 된 원천만 수집 → 2) 새 항목만 inbox 저장 → 3) 규칙 P0 선알림
4) P1 묶음 발송 → 5) 새 항목이 있으면 run_triage(모델 판정) 호출

사용: py radar/run_poll.py [--force] [--no-triage] [--only src-id]
"""
import argparse
import importlib
import os
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402
import notify  # noqa: E402

LOCK = common.STATE / "run_poll.lock"


def acquire_lock():
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    if LOCK.exists():
        from datetime import datetime, timedelta
        age = common.now_kst() - datetime.fromtimestamp(LOCK.stat().st_mtime, common.KST)
        if age < timedelta(minutes=15):
            return False
    LOCK.write_text(str(os.getpid()), encoding="utf-8")
    return True


def prune_inbox(keep_days=14):
    """inbox 날짜 폴더 보관 정책: 14일 지난 폴더 삭제(원본은 재수집 가능, 카드는 radar/cards에 남음)"""
    import shutil
    cutoff = (common.now_kst().date().toordinal()) - keep_days
    for d in common.INBOX.glob("20*"):
        try:
            from datetime import datetime
            if datetime.strptime(d.name, "%Y%m%d").date().toordinal() < cutoff:
                shutil.rmtree(d)
        except ValueError:
            continue


def registry():
    return [s for s in (common.load_yaml("config/source_registry.yaml") or [])
            if s.get("enabled") and s.get("run_on") in ("local", "both") and s.get("module")]


def interval(src):
    tier = "T0" if any(str(x) == "T0" or str(x).startswith("co-") for x in src.get("scope", [])) else "T2"
    base = common.interval_for(tier)
    return max(base, int(src.get("interval_min", base)))


def run_source(src, env):
    mod = src["module"]
    if mod == "rss":
        from pollers import rss
        return rss.poll_source(src)
    module = importlib.import_module(f"pollers.{mod}")
    return module.poll(env)


def deterministic_p0(items):
    rules = (common.load_yaml("config/alert_rules.yaml") or {}).get("deterministic_p0", {})
    pats = rules.get("dart_report_patterns", [])
    excl = rules.get("dart_exclude_patterns", [])
    sent = []
    for it in items:
        if it["source_id"] != "src-dart" or it.get("tier") not in rules.get("scope_tiers", ["T0"]):
            continue
        rep = it.get("report_nm", "")
        if any(p in rep for p in pats) and not any(x in rep for x in excl):
            text = f"{rules.get('message_prefix', '[P0-규칙]')} {it['title']} {rules.get('suffix', '')}\n{it['url']}"
            notify.send(text, "P0")
            sent.append(it["item_id"])
    if sent:
        state = common.load_state("rule_p0", {"ids": []})
        state["ids"] = (state["ids"] + sent)[-500:]
        common.save_state("rule_p0", state)
    return sent


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-triage", action="store_true")
    ap.add_argument("--only")
    ap.add_argument("--baseline", action="store_true",
                    help="첫 실행용: 지금 있는 항목을 '본 것'으로만 기록하고 알림·판정하지 않음")
    args = ap.parse_args(argv)
    if not acquire_lock():
        print("다른 폴링이 실행 중 — 건너뜀")
        return 0
    try:
        env = common.load_env()
        new_total = []
        for src in registry():
            if args.only and src["id"] != args.only:
                continue
            if not args.force and not common.is_due(src["id"], interval(src)):
                continue
            try:
                items = run_source(src, env)
                new = common.save_new_items(items)
                common.record_health(src["id"], True)
                new_total.extend(new)
                print(f"{src['id']}: 수집 {len(items)}, 신규 {len(new)}")
            except RuntimeError as exc:  # 키 없음 등 설정 문제
                common.record_health(src["id"], False, exc)
                print(f"{src['id']}: 건너뜀 — {exc}")
            except Exception as exc:
                common.record_health(src["id"], False, f"{type(exc).__name__}: {exc}")
                print(f"{src['id']}: 오류 — {type(exc).__name__}: {exc}")
                traceback.print_exc(limit=1)
            finally:
                common.mark_run(src["id"])
        if args.baseline:
            import run_triage
            run_triage.mark_triaged(it["item_id"] for it in new_total)
            print(f"기준선 기록 {len(new_total)}건 — 알림·판정 없음")
            return 0
        if new_total:
            sent = deterministic_p0(new_total)
            if sent:
                print(f"규칙 P0 선알림 {len(sent)}건")
        notify.flush_p1()
        prune_inbox()
        if new_total and not args.no_triage:
            import run_triage
            run_triage.main([])
        return 0
    finally:
        LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
