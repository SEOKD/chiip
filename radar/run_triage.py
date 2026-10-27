"""신규 레이더 항목 → 모델 판정 (BUILD_PROMPT §10.5)

- 관련성 없는 항목(기업·키워드 매칭 0)은 모델 없이 P3 보관.
- 나머지는 헤드리스 Claude Code(`claude -p "/radar-triage …"`, 소형 모델)로 일괄 판정.
- P0: 즉시 알림 + impact-card(상위 모델) / P1: 1시간 묶음 / P2: 브리프 대기열 / P3: 보관
- claude CLI가 없거나 로그인 전이면 전부 브리프 대기열(미판정)로 보내고 헬스에 기록.

사용: py radar/run_triage.py [--dry-run]
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402
import notify  # noqa: E402

BATCH = common.STATE / "triage_batch.json"
BRIEF_QUEUE = common.STATE / "brief_queue.jsonl"
BATCH_SIZE = 25
SCHEMA = {
    "type": "object",
    "properties": {"results": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "item_id": {"type": "string"},
            "level": {"type": "string", "enum": ["P0", "P1", "P2", "P3"]},
            "event_type": {"type": "string"},
            "what": {"type": "string"},
            "impact": {"type": "string"},
            "reason": {"type": "string"},
            "card_path": {"type": "string"}},
        "required": ["item_id", "level", "reason"]}}},
    "required": ["results"]}


def pending_items():
    done = set(common.load_state("triaged", {"ids": []})["ids"])
    out = []
    for f in sorted(common.INBOX.rglob("*.json")):
        it = json.loads(f.read_text(encoding="utf-8"))
        if it["item_id"] not in done:
            out.append(it)
    return out


def mark_triaged(ids):
    s = common.load_state("triaged", {"ids": []})
    s["ids"] = (s["ids"] + list(ids))[-30000:]
    common.save_state("triaged", s)


def to_brief(item, level, note=""):
    BRIEF_QUEUE.parent.mkdir(parents=True, exist_ok=True)
    with BRIEF_QUEUE.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"level": level, "item_id": item["item_id"], "title": item["title"], "url": item["url"],
                            "entities": item.get("entities_matched", []), "note": note,
                            "at": common.iso(common.now_kst())}, ensure_ascii=False) + "\n")


def calls_today(add=0):
    s = common.load_state("model_calls")
    day = common.now_kst().strftime("%Y-%m-%d")
    s[day] = s.get(day, 0) + add
    common.save_state("model_calls", {day: s[day]})
    return s[day]


def claude_exe():
    return shutil.which("claude")


def run_claude(prompt, model, schema=None, timeout=900):
    cmd = [claude_exe(), "-p", prompt, "--model", model, "--output-format", "json",
           "--allowedTools", "Read,Glob,Grep,Write,Edit,Bash(py scripts/*)",
           "--permission-mode", "dontAsk", "--permission-prompts", "none"]
    if schema:
        cmd += ["--json-schema", json.dumps(schema, ensure_ascii=False)]
    proc = subprocess.run(cmd, cwd=common.ROOT, capture_output=True, text=True, encoding="utf-8", timeout=timeout)
    calls_today(1)
    out = json.loads(proc.stdout) if proc.stdout.strip().startswith("{") else {}
    if proc.returncode != 0 or out.get("is_error"):
        raise RuntimeError(f"claude 실패({proc.returncode}): {str(out.get('result', proc.stderr))[:200]}")
    return out


def deep_analysis(result, item):
    """P0: impact-card 완성(상위 모델). 실패해도 알림은 이미 나감."""
    caps = (common.load_yaml("config/alert_rules.yaml") or {}).get("caps", {})
    s = common.load_state("p0_deep")
    day = common.now_kst().strftime("%Y-%m-%d")
    if s.get(day, 0) >= caps.get("daily_p0_deep_analysis", 10):
        return
    try:
        run_claude(f"/impact-card {result.get('card_path') or item['item_id']}", "sonnet", timeout=1500)
        s = {day: s.get(day, 0) + 1}
        common.save_state("p0_deep", s)
    except Exception as exc:
        common.record_health("impact-card", False, exc)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    items = pending_items()
    if not items:
        print("판정할 항목 없음")
        return 0
    relevant, archived = [], []
    for it in items:
        (relevant if it.get("entities_matched") or it.get("keywords_matched") else archived).append(it)
    mark_triaged(it["item_id"] for it in archived)
    print(f"신규 {len(items)} (관련 {len(relevant)}, 무관 보관 {len(archived)})")
    if not relevant or args.dry_run:
        return 0

    caps = (common.load_yaml("config/alert_rules.yaml") or {}).get("caps", {})
    rule_sent = set(common.load_state("rule_p0", {"ids": []})["ids"])
    exe = claude_exe()
    for i in range(0, len(relevant), BATCH_SIZE):
        batch = relevant[i:i + BATCH_SIZE]
        if not exe or calls_today() >= caps.get("daily_model_calls", 200):
            why = "claude CLI 없음" if not exe else "일일 모델 호출 상한"
            for it in batch:
                to_brief(it, "미판정", why)
            mark_triaged(it["item_id"] for it in batch)
            common.record_health("triage", False, why)
            continue
        BATCH.write_text(json.dumps(batch, ensure_ascii=False, indent=1), encoding="utf-8")
        try:
            out = run_claude(f"/radar-triage {BATCH.relative_to(common.ROOT).as_posix()}", "haiku", SCHEMA)
            results = (out.get("structured_output") or {}).get("results", [])
            common.record_health("triage", True)
        except Exception as exc:
            common.record_health("triage", False, exc)
            for it in batch:
                to_brief(it, "미판정", "판정 실패")
            mark_triaged(it["item_id"] for it in batch)
            continue
        by_id = {it["item_id"]: it for it in batch}
        for r in results:
            it = by_id.get(r["item_id"])
            if not it:
                continue
            lvl = r["level"]
            card = Path(r.get("card_path") or "").stem or None
            msg = notify.format_item(lvl, it, r.get("what"), r.get("impact"), card)
            if lvl == "P0":
                notify.send(("(규칙 선알림 후속) " if it["item_id"] in rule_sent else "") + msg, "P0")
                deep_analysis(r, it)
            elif lvl == "P1":
                notify.queue_p1(msg)
            elif lvl == "P2":
                to_brief(it, "P2", r.get("reason", ""))
        mark_triaged(by_id.keys())
    return 0


if __name__ == "__main__":
    sys.exit(main())
