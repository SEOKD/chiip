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
# 회차 시간 예산(2026-11-09 Pulse 시의성 점검): Windows 작업(chiip-radar)은 30분 한도에 강제 종료된다. 앞쪽 원천이 느리면(9개 매체 뉴스 13분)
# 뒤쪽 원천이 굶었다 — 일본 IR 질의응답이 매번 남은 시간을 다 써 11/5부터 11개 원천(일·한·대만 IR, 원자력, 방위, X 인용…)이 3.5일 멈췄다.
# 그래서 ① 밀린 비율(경과 ÷ 주기) 큰 원천부터 ② 원천마다 별도 프로세스 + 시간 한도(멈춰도 그 원천만 끊긴다) ③ 예산을 넘기면 새 원천을 시작하지 않는다.
BUDGET_MIN = 22
SOURCE_TIMEOUT_MIN = 8


def overdue(src):
    """경과 ÷ 주기 — 한 번도 안 돈 원천은 가장 먼저"""
    last = common.load_state("last_run").get(src["id"])
    if not last:
        return 1e9
    from datetime import datetime
    return (common.now_kst() - datetime.fromisoformat(last)).total_seconds() / 60 / max(interval(src), 1)


def run_child(src, timeout_s):
    """원천 하나를 별도 프로세스로 — 새 항목 목록(JSON) 또는 None(시간 초과·실패). 수집·저장·건강 기록은 자식이 한다"""
    import subprocess
    try:
        r = subprocess.run([sys.executable, str(Path(__file__)), "--child", src["id"]], capture_output=True, timeout=timeout_s, env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        common.record_health(src["id"], False, f"시간 초과 {timeout_s / 60:.0f}분 — 다음 회차에 다시(run_poll 원천별 한도)")
        common.mark_run(src["id"])
        print(f"{src['id']}: 시간 초과({timeout_s / 60:.0f}분)")
        return None
    out = r.stdout.decode("utf-8", "replace").strip().splitlines()
    for line in out[:-1]:
        print(line)
    try:
        return json.loads(out[-1]) if out else []
    except ValueError:
        print(f"{src['id']}: 자식 출력 해석 실패 — {r.stderr.decode('utf-8', 'replace')[-200:]}")
        return []


def child(sid):
    """--child: 원천 하나만 수집·저장·건강 기록하고 새 항목을 마지막 줄 JSON으로 낸다(잠금·판정 없음)"""
    env = common.load_env()
    src = next(x for x in registry() if x["id"] == sid)
    new = []
    try:
        items = run_source(src, env)
        new = common.save_new_items(items)
        common.record_health(sid, True)
        print(f"{sid}: 수집 {len(items)}, 신규 {len(new)}")
    except RuntimeError as exc:
        common.record_health(sid, False, exc)
        print(f"{sid}: 건너뜀 — {exc}")
    except Exception as exc:
        common.record_health(sid, False, f"{type(exc).__name__}: {exc}")
        print(f"{sid}: 오류 — {type(exc).__name__}: {exc}")
    finally:
        common.mark_run(sid)
    print(json.dumps(new, ensure_ascii=True, default=str))


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


def fast_interval(when=None):
    """빠른 원천(보도자료 와이어·EDGAR 최신 목록) 간격 — 미국 발표가 몰리는 창은 2분, 그 밖 5분(config/alert_rules.yaml fast_feeds)"""
    when = when or common.now_kst()
    cfg = (common.load_yaml("config/alert_rules.yaml") or {}).get("fast_feeds", {})
    hhmm = when.strftime("%H:%M")
    for a, b in cfg.get("hot_windows", []):
        if (a <= hhmm < b) if a < b else (hhmm >= a or hhmm < b):
            return cfg.get("hot_min", 2)
    return cfg.get("base_min", 5)


def fast_feeds():
    """보도자료(30분 배치에서 이관)·EDGAR 최신 목록을 먼저 본다(마스터 지시 2026-11-04 시의성 개선 ②③).
    EDGAR에 감시 종목 서류가 뜨면 그 회차에 sec_filings를 바로 돌린다(hot)"""
    new, hot, every = [], set(), fast_interval()
    if common.is_due("src-press-wire", every):
        try:
            from pollers import press_wire
            print("src-press-wire", press_wire.run())
        except Exception as exc:
            common.record_health("src-press-wire", False, f"{type(exc).__name__}: {exc}")
        finally:
            common.mark_run("src-press-wire")
    if common.is_due("src-edgar-current", every):
        try:
            from pollers import edgar_current
            if edgar_current.run():
                hot.add("src-sec-filings")
                print("src-edgar-current: 감시 종목 새 서류 → sec_filings 즉시")
        except Exception as exc:
            common.record_health("src-edgar-current", False, f"{type(exc).__name__}: {exc}")
        finally:
            common.mark_run("src-edgar-current")
    return new, hot


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
    import origin
    import promote
    from pollers import gate
    sent, go_list, notes = [], [], []
    for it in items:
        try:
            if not gate.is_fresh(it, "alert"):
                notes.append((it, "오래됨"))
                continue
            if promote.noise(it):
                notes.append((it, "잡음 제목"))
                continue
            ok, why_media = notify.telegram_allowed(it)
            if not ok:
                notes.append((it, why_media or "매체 제한"))
                continue
            why = promote.check(it, record=False)   # 서명은 보낼 때만(promote.check 설명)
            if not why:
                notes.append((it, "규칙 없음"))
                continue
            lvl = promote.level_for(it, why)
            it = origin.apply(it)   # 재인용 기사는 원보도로(2026-11-02 마스터 지시)
            dup = promote.duplicate_of(it)
            if dup:
                notes.append((it, f"이미 보낸 사건: {str(dup)[:40]}"))
                continue
            go, _, reason = promote.event_gate(it, lvl)
            if go:
                promote.commit(it)
                go_list.append((it, lvl, why))
                notes.append((it, f"발송 대상 {lvl}: {why}"))
            else:
                notes.append((it, f"사건 관문: {reason}"))
        except Exception as exc:   # 빠른 길이 실패해도 수집·판정은 계속
            notes.append((it, f"오류 {type(exc).__name__}: {exc}"))
            print(f"빠른 길 오류 {it.get('item_id')}: {type(exc).__name__}: {exc}")
    fast_log(notes)
    extra = enrich([it for it, _, _ in go_list]) if go_list else {}
    for it, lvl, why in go_list:
        try:
            e = extra.get(it["item_id"]) or {}
            if e.get("profile"):
                notify.remember_profile(it.get("entities_matched"), e["profile"], "빠른 길 모델")
            ref = notify.remember_alert(it, lvl, why, None, None)
            notify.send(notify.format_item(lvl, it, points=e.get("points"), profile=e.get("profile"), synergy=e.get("synergy")), lvl, ref=ref, html_mode=True)
            sent.append(it["item_id"])
        except Exception as exc:
            print(f"빠른 길 발송 오류 {it.get('item_id')}: {type(exc).__name__}: {exc}")
    if sent:
        st = common.load_state("rule_fast", {"ids": []})
        st["ids"] = (st["ids"] + sent)[-1000:]
        common.save_state("rule_fast", st)
    return sent


FAST_SEEN = "fast_lane"
SWEEP_H = 6


def fast_log(notes):
    """빠른 길 판정 사유(radar/state/fast_lane.log) + 본 id 기록(안전망 sweep이 다시 넣지 않게) — 2026-11-04 SK하이닉스 Reuters 단독 4시간 지연 점검:
    04:26 사본이 판정에 닿은 흔적이 없어 원인을 못 가렸다. 다음 누락은 이 기록으로 가린다"""
    if not notes:
        return
    now = common.iso(common.now_kst())
    try:
        with (common.STATE / "fast_lane.log").open("a", encoding="utf-8") as f:
            for it, why in notes:
                f.write(f"{now}\t{it.get('item_id')}\t{why}\t{str(it.get('title', ''))[:80]}\n")
    except OSError:
        pass
    st = common.load_state(FAST_SEEN, {"ids": []})
    st["ids"] = (st["ids"] + [it.get("item_id") for it, _ in notes if it.get("item_id")])[-5000:]
    common.save_state(FAST_SEEN, st)


def fast_sweep(exclude=(), hours=SWEEP_H):
    """안전망: 최근 hours 안에 inbox에 저장됐는데 빠른 길 판정 기록이 없는 항목(수집 회차가 판정 전에 멈췄거나 다른 수집기가 넣은 것)을 다시 넣는다.
    처음 켤 때는 지금 있는 항목을 기준선으로만 기록한다(과거 항목을 한꺼번에 보내지 않게)"""
    from datetime import datetime, timedelta
    first = not (common.STATE / f"{FAST_SEEN}.json").exists()
    st = common.load_state(FAST_SEEN, {"ids": []})
    now = common.now_kst()
    cut = now - timedelta(hours=hours)
    found = []
    for day in {now.strftime("%Y%m%d"), (now - timedelta(days=1)).strftime("%Y%m%d")}:
        d = common.INBOX / day
        if not d.is_dir():
            continue
        for f in d.glob("*.json"):
            try:
                it = json.loads(f.read_text(encoding="utf-8"))
                at = datetime.fromisoformat(it.get("saved_at") or it.get("detected_at"))
            except (OSError, ValueError, TypeError, AttributeError):
                continue
            if at >= cut and it.get("item_id"):
                found.append(it)
    if first:
        common.save_state(FAST_SEEN, {"ids": [it["item_id"] for it in found][-5000:]})
        return []
    seen = set(st.get("ids") or []) | set(exclude)
    return [it for it in found if it["item_id"] not in seen]


FAST_SCHEMA = {"type": "object", "properties": {"results": {"type": "array", "items": {"type": "object", "properties": {
    "item_id": {"type": "string"}, "points": {"type": "array", "items": {"type": "string"}},
    "profile": {"type": "array", "items": {"type": "string"}}, "synergy": {"type": "string"}}, "required": ["item_id"]}}}, "required": ["results"]}
FAST_PROMPT = (
    "radar/state/fast_batch.json의 뉴스 항목마다 한국어로 쓴다(마스터 지시 2026-10-29 실시간 알림 양식). "
    "① points: 핵심 내용 최대 3줄(각 60자 안팎) — 무엇이 일어났나·숫자(단위 그대로, 금액은 $50.6B·$420M 표기)·왜 중요한가. "
    "제목·요약(snippet)에 있는 사실만 쓰고, 헤드라인을 사실로 단정하지 말고 주체를 붙인다(예: '로이터 보도'). relay가 있으면 주체는 전달 매체가 아니라 원보도 매체(relay.outlet)다. 쓸 사실이 1~2개면 1~2줄만. "
    "② profile: 주인공 기업(entities_matched 첫 종목) 설명 3줄 — 비즈니스 모델 / 성장 동력 / 시장의 내러티브. "
    "각 줄 45자 안팎(휴대폰 한 줄), '모델:'·'성장:'·'내러티브:' 같은 머리말 없이 내용만(마스터 지시 2026-10-30). "
    "known_line·narrative가 있으면 그것과 맞게 쓴다. 확실히 아는 사실만, 모르면 빈 배열. "
    "③ synergy: M&A(인수·합병·사업부 매각) 기사일 때만 한 줄(70자 안팎) — 인수기업과 피인수기업의 비즈니스 모델·제품 포트폴리오를 놓고 무엇이 이어지나(교차판매·제품 공백 메우기·기술 내재화·고객·원가). "
    "기사에 없는 판단이므로 끝에 '(추정)'을 붙인다. 피인수기업 사업을 모르면 '피인수기업 사업 미확인'이라고 쓴다. M&A가 아니면 비운다. 매수·매도 표현 금지. 결과는 구조화 출력만.")


def enrich(items):
    """빠른 길 건의 핵심 3줄·회사 설명 3줄 — 소형 모델(haiku) 1회(규칙 건이 있을 때만, 일일 호출 상한 공유).
    실패·상한이면 {} — 알림은 저장된 회사 설명·기사 요약문 문장으로 나간다(발송을 막지 않는다)"""
    import run_triage
    try:
        cap = ((common.load_yaml("config/alert_rules.yaml") or {}).get("caps") or {}).get("daily_model_calls", 200)
        if not run_triage.claude_exe() or run_triage.calls_today() >= cap:
            return {}
        batch = [{"item_id": it["item_id"], "title": it.get("title"), "snippet": it.get("snippet"), "url": it.get("url"), "relay": it.get("relay"),
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


def start_tg_keeper():
    """공개 텔레그램 채널을 4분마다 읽는 보조 스레드 — 느린 수집기가 20분 넘게 돌아도 끊기지 않게(2026-11-01 점수 점검)"""
    import threading
    import time
    from pollers import tg_channels as tg

    def loop():
        while True:
            try:
                tg.poll_if_stale()
            except Exception as exc:
                common.record_health(tg.SOURCE_ID, False, f"{type(exc).__name__}: {exc}")
            time.sleep(240)
    threading.Thread(target=loop, daemon=True).start()


def main(argv=None):
    common.stay_awake()
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-triage", action="store_true")
    ap.add_argument("--only")
    ap.add_argument("--child")   # 원천 하나만(부모 run_poll이 별도 프로세스로 부른다)
    ap.add_argument("--baseline", action="store_true",
                    help="첫 실행용: 지금 있는 항목을 '본 것'으로만 기록하고 알림·판정하지 않음")
    args = ap.parse_args(argv)
    if args.child:
        child(args.child)
        return 0
    if not acquire_lock():
        print("다른 폴링이 실행 중 — 건너뜀")
        return 0
    start_tg_keeper()
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
        new_total, hot = [], set()
        if not args.only:
            new_total, hot = fast_feeds()
        import time
        t0 = time.time()
        due = [x for x in registry() if (not args.only or x["id"] == args.only)
               and (args.force or x["id"] in hot or common.is_due(x["id"], interval(x)))]
        due.sort(key=lambda x: (x["id"] not in hot, -overdue(x)))   # 급한 원천(hot) → 가장 밀린 원천 순
        for i, src in enumerate(due):
            left = BUDGET_MIN * 60 - (time.time() - t0)
            if left < 60:
                print(f"회차 시간 예산 {BUDGET_MIN}분 소진 — 남은 {len(due) - i}개는 다음 회차(가장 밀린 순으로 먼저)")
                break
            new = run_child(src, min(float(src.get("timeout_min") or SOURCE_TIMEOUT_MIN) * 60, left))   # 원천별 한도(등록부 timeout_min — 9개 매체 뉴스는 혼자 8.3분)
            if new:
                new_total.extend(new)
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
        late = fast_sweep(exclude={it["item_id"] for it in new_total})
        if late:   # 판정에 닿지 못한 최근 항목(2026-11-04 안전망)
            fast = fast_lane(late)
            print(f"빠른 길 안전망 {len(late)}건 재판정 · 발송 {len(fast)}건")
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
