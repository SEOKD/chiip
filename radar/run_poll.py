"""레이더 폴링 진입점 (BUILD_PROMPT §10.4~10.5, §21.3)

Windows 작업 스케줄러가 몇 분마다 실행한다. 모델은 부르지 않는다.
1) 기한이 된 원천만 수집 → 2) 새 항목만 inbox 저장 → 3) 규칙 P0 선알림
4) P1 묶음 발송 → 5) 새 항목이 있으면 run_triage(모델 판정) 호출

사용: py radar/run_poll.py [--force] [--no-triage] [--only src-id]
"""
import argparse
import importlib
import json
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
    """원천이 interval_min을 정했으면 그대로 쓴다. 2026-10-29 점검: 9개 매체 뉴스(src-news7-focus)·감시 종목 SEC 공시(src-sec-filings)가
    15분으로 설정돼 있었는데 티어 기본값(T2 60분)이 max()로 덮어 1시간마다만 돌았다 — MRVL·Lumentum 등 보도 지연의 한 원인"""
    if src.get("interval_min"):
        return int(src["interval_min"])
    tier = "T0" if any(str(x) == "T0" or str(x).startswith("co-") for x in src.get("scope", [])) else "T2"
    return common.interval_for(tier)


def run_source(src, env):
    mod = src["module"]
    if mod == "rss":
        from pollers import rss
        return rss.poll_source(src)
    module = importlib.import_module(f"pollers.{mod}")
    return getattr(module, src.get("entry", "poll"))(env)  # 한 모듈에 원천이 여럿이면 entry로 함수 지정


def fast_lane(items):
    """규칙 빠른 길(2026-10-29 '즉시 포착' 점검): 보유 종목 큰 사건·숏 리포트·AI 밸류체인 대형 거래 등 radar/promote.py 규칙에
    걸리는 새 항목은 모델 판정(haiku, 묶음 순차·일일 상한)을 기다리지 않고 수집 직후 보낸다. 모델이 실패하거나 상한에 걸려도
    규칙 건은 나간다. 같은 사건 반복·잡음·오래된 자료는 판정 단계와 같은 관문으로 거른다. 보낸 id는 run_triage가 다시 보내지 않는다"""
    import promote
    from pollers import gate
    sent, go_list = [], []
    for it in items:
        try:
            if not gate.is_fresh(it, "alert") or promote.noise(it) or not notify.telegram_allowed(it)[0]:
                continue
            why = promote.check(it)
            if not why:
                continue
            lvl = promote.level_for(it, why)
            if promote.duplicate_of(it):
                continue
            go, _, _ = promote.event_gate(it, lvl)
            if go:
                go_list.append((it, lvl, why))
        except Exception as exc:   # 빠른 길이 실패해도 수집·판정은 계속
            print(f"빠른 길 오류 {it.get('item_id')}: {type(exc).__name__}: {exc}")
    extra = enrich([it for it, _, _ in go_list]) if go_list else {}
    for it, lvl, why in go_list:
        try:
            e = extra.get(it["item_id"]) or {}
            if e.get("profile"):
                notify.remember_profile(it.get("entities_matched"), e["profile"], "빠른 길 모델")
            ref = notify.remember_alert(it, lvl, why, None, None)
            notify.send(notify.format_item(lvl, it, points=e.get("points"), profile=e.get("profile")), lvl, ref=ref, html_mode=True)
            sent.append(it["item_id"])
        except Exception as exc:
            print(f"빠른 길 발송 오류 {it.get('item_id')}: {type(exc).__name__}: {exc}")
    if sent:
        st = common.load_state("rule_fast", {"ids": []})
        st["ids"] = (st["ids"] + sent)[-1000:]
        common.save_state("rule_fast", st)
    return sent


FAST_SCHEMA = {"type": "object", "properties": {"results": {"type": "array", "items": {"type": "object", "properties": {
    "item_id": {"type": "string"}, "points": {"type": "array", "items": {"type": "string"}},
    "profile": {"type": "array", "items": {"type": "string"}}}, "required": ["item_id"]}}}, "required": ["results"]}
FAST_PROMPT = (
    "radar/state/fast_batch.json의 뉴스 항목마다 한국어로 두 가지를 쓴다(마스터 지시 2026-10-29 실시간 알림 양식). "
    "① points: 핵심 내용 최대 3줄(각 60자 안팎) — 무엇이 일어났나·숫자(단위 그대로, 금액은 $50.6B·$420M 표기)·왜 중요한가. "
    "제목·요약(snippet)에 있는 사실만 쓰고, 헤드라인을 사실로 단정하지 말고 주체를 붙인다(예: '로이터 보도'). 쓸 사실이 1~2개면 1~2줄만. "
    "② profile: 주인공 기업(entities_matched 첫 종목) 설명 3줄 — 비즈니스 모델 / 성장 동력 / 시장의 내러티브. "
    "known_line·narrative가 있으면 그것과 맞게 쓴다. 확실히 아는 사실만, 모르면 빈 배열. 매수·매도 표현 금지. 결과는 구조화 출력만.")


def enrich(items):
    """빠른 길 건의 핵심 3줄·회사 설명 3줄 — 소형 모델(haiku) 1회(규칙 건이 있을 때만, 일일 호출 상한 공유).
    실패·상한이면 {} — 알림은 저장된 회사 설명·기사 요약문 문장으로 나간다(발송을 막지 않는다)"""
    import run_triage
    try:
        cap = ((common.load_yaml("config/alert_rules.yaml") or {}).get("caps") or {}).get("daily_model_calls", 200)
        if not run_triage.claude_exe() or run_triage.calls_today() >= cap:
            return {}
        batch = [{"item_id": it["item_id"], "title": it.get("title"), "snippet": it.get("snippet"), "url": it.get("url"),
                  "source_id": it.get("source_id"), "published_at": it.get("published_at"), "entities_matched": it.get("entities_matched"),
                  "known_line": notify.company_line(it.get("entities_matched")),
                  "narrative": next((s for s in map(notify._narrative_summary, it.get("entities_matched") or []) if s), None)} for it in items]
        f = common.STATE / "fast_batch.json"
        f.write_text(json.dumps(batch, ensure_ascii=False, indent=1), encoding="utf-8")
        out = run_triage.run_claude(FAST_PROMPT, "haiku", FAST_SCHEMA, timeout=180)
        return {r["item_id"]: r for r in (out.get("structured_output") or {}).get("results", []) if r.get("item_id")}
    except Exception as exc:
        print(f"빠른 길 요약 실패: {type(exc).__name__}: {exc}")
        common.record_health("fast-enrich", False, exc)
        return {}


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
    common.stay_awake()
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
        try:  # 텔레그램 '⭐ 노션 기록' 버튼·답장 메모 처리 → 노션 인텔 아카이브(§21.13)
            import telegram_inbox
            telegram_inbox.run()
        except Exception as exc:
            common.record_health("telegram-inbox", False, f"{type(exc).__name__}: {exc}")
        try:  # 노션 실시간 감시(마스터 지시 2026-10-28) — NOTION_TOKEN 있을 때만, 처리는 별도 작업자 프로세스
            import notion_watch
            notion_watch.run()
        except Exception as exc:
            common.record_health("src-notion-watch", False, f"{type(exc).__name__}: {exc}")
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
            fast = fast_lane(new_total)
            if fast:
                print(f"규칙 빠른 길 발송 {len(fast)}건")
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
