"""펄스 결정론 문턱 (ADR-013 H2, 마스터 승인 2026-10-31) — 새 자료가 있을 때만 모델을 띄운다

Windows 작업 chiip-pulse-trigger가 5분마다 부른다. 관문은 상태를 바꾸지 않고 들여다보기만 하고(peek),
실제 소비는 모델 회차의 0단계 `py radar/pulse.py`가 한다. 그래서 모델이 실패해도 자료를 잃지 않고 다음 회차가 다시 잡는다.
사용: py radar/pulse_trigger.py            # 문턱 1회
      py radar/pulse_trigger.py --peek     # 판정만 출력(모델 안 띄움)
"""
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402
import notify  # noqa: E402
import pulse  # noqa: E402
import run_ledger  # noqa: E402

STATE = "pulse_trigger"
CFG = common.ROOT / "config" / "harness.yaml"
HEADLESS = ("[헤드리스 회차] 환경은 이미 잡혀 있다. 아래 지시의 $env: 설정을 붙이지 말고, 명령은 `py ...`나 `python ...` 하나만 단독으로 쓴다"
            "(cd·세미콜론·파이프·리디렉션으로 잇지 않는다). 복합 명령은 권한에서 거부된다.\n\n")


def cfg():
    return yaml.safe_load(CFG.read_text(encoding="utf-8"))["pulse_trigger"]


def prompt(c):
    """예약 작업 지시문을 그대로 쓴다 — 없으면 저장소 지시서로"""
    p = Path.home() / ".claude" / "scheduled-tasks" / c["skill"] / "SKILL.md"
    if p.exists():
        text = p.read_text(encoding="utf-8")
        return HEADLESS + (text.split("---", 2)[2].strip() if text.startswith("---") else text)
    return HEADLESS + f"docs/tasks/{c['skill']}.md의 '## 지시문' 절을 읽고 그대로 수행한다."


def command(c, exe, text):
    cmd = [exe, "-p", text, "--output-format", "json", "--permission-mode", "dontAsk", "--permission-prompts", "none",
           "--max-budget-usd", str(c["max_budget_usd"]), "--allowedTools", ",".join(c["allowed_tools"])]
    if c.get("disallowed_tools"):
        cmd += ["--disallowedTools", ",".join(c["disallowed_tools"])]
    if c.get("model"):
        cmd += ["--model", c["model"]]
    return cmd


def gate_mark():
    """모델이 0단계 관문을 실제로 돌리면 바뀌는 값"""
    return common.load_state(pulse.STATE, {}).get("watermark")


def denial(d):
    """거부된 호출 — 도구와 명령 앞부분. 허용 목록을 고칠 근거다"""
    return f"{d.get('tool_name', '?')}: {str((d.get('tool_input') or {}).get('command', ''))[:80]}"


def launch(c):
    """모델 회차 1회. (성공 여부, 장부 필드)"""
    exe = shutil.which("claude")
    if not exe:
        return False, {"error": "claude CLI 없음"}
    start = time.time()
    before = gate_mark()
    try:
        proc = subprocess.run(command(c, exe, prompt(c)), cwd=common.ROOT, capture_output=True, text=True, encoding="utf-8", stdin=subprocess.DEVNULL,
                              env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=c["timeout_min"] * 60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        return False, {"error": "시간 초과", "seconds": round(time.time() - start)}
    out = json.loads(proc.stdout) if proc.stdout.strip().startswith("{") else {}
    ran = gate_mark() != before   # 종료 코드만으로는 모른다 — 권한 거부로 아무 일도 안 하고 정상 종료한 회차가 있었다
    ok = proc.returncode == 0 and not out.get("is_error") and ran
    usage = out.get("usage") or {}
    denied = [denial(d) for d in out.get("permission_denials") or []]
    return ok, {"seconds": round(time.time() - start), "cost_usd": out.get("total_cost_usd"), "turns": out.get("num_turns"), "ran": ran, "denied": denied[:8],
                "models": sorted(out.get("modelUsage") or {}),
                "input_tokens": usage.get("input_tokens"), "output_tokens": usage.get("output_tokens"),
                "error": None if ok else f"종료 코드 {proc.returncode}" + ("" if ran else " · 관문 미실행")}


def alert(text):
    notify.send(f"[Chiip Pulse 문턱] {text}", "SYSTEM")


def main(argv):
    common.stay_awake()
    if sys.stdout:   # 작업 스케줄러의 pyw에는 표준 출력이 없다
        sys.stdout.reconfigure(encoding="utf-8")
    c, st = cfg(), common.load_state(STATE, {})
    if not c.get("enabled"):
        return 0
    now = common.now_kst()
    st["heartbeat"] = common.iso(now)
    material, msg = pulse.run(peek=True)
    print(msg)
    if "--peek" in argv:
        return 0
    if not material:
        run_ledger.record("gate", "chiip-pulse", outcome="종료", via="trigger")
        common.save_state(STATE, st)
        return 0
    day = now.strftime("%Y%m%d")
    count = st.get("count", {}).get(day, 0)
    if count >= c["daily_model_cap"]:
        if st.get("cap_alert") != day:
            st["cap_alert"] = day
            alert(f"오늘 모델 회차 상한 {c['daily_model_cap']}회에 닿아 멈췄습니다. 수집은 계속되고 자료는 다음 날 회차가 잡습니다.")
        common.save_state(STATE, st)
        return 0
    st["count"] = {day: count + 1}
    common.save_state(STATE, st)   # 모델이 도는 동안에도 맥박이 남게 먼저 저장한다
    ok, fields = launch(c)
    run_ledger.record("model", "chiip-pulse", ok=ok, **fields)
    st = common.load_state(STATE, {})
    st["heartbeat"] = common.iso(common.now_kst())
    st["fails"] = 0 if ok else st.get("fails", 0) + 1
    if st["fails"] == c["fail_alert_after"]:
        alert(f"모델 회차가 {st['fails']}번 연속 실패했습니다({fields.get('error')}). 자료는 남아 있어 다음 회차가 다시 시도합니다.")
    common.save_state(STATE, st)
    return 0 if ok else 1


def run():
    """run_hourly용 — 문턱이 멈췄으면 모델 없이 알린다"""
    c, st = cfg(), common.load_state(STATE, {})
    if not c.get("enabled"):
        return 0, []
    last = st.get("heartbeat") or ""
    now = common.now_kst()
    stale = not last or datetime.fromisoformat(last) < now - timedelta(minutes=c["heartbeat_stale_min"])
    if stale and st.get("stale_alert", "-") != last:
        st["stale_alert"] = last
        common.save_state(STATE, st)
        alert(f"문턱이 {last[11:16] + ' 이후' if last else '한 번도'} 돌지 않았습니다. Windows 작업 chiip-pulse-trigger를 확인해야 합니다.")
    return 0, []


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
