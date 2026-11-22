"""Proviser 회차의 이미지 재생성 차단 훅 (2026-11-22 마스터 지시 "Proviser로 Analysis Report를 점검할 때 이미지는 두 번 생성하지 않도록 하라")
pre(Bash·PowerShell): Proviser 예약 작업(chiip-proviser·chiip-report-audit-weekly) 세션이 product_images.py ensure|make를
  --no-regen(또는 CHIIP_NO_REGEN=1) 없이 부르면 거부한다. 정정은 있는 그림을 다시 쓰고, 이름표만 렌더러가 새 BOM으로 붙인다.
훅 오류는 작업을 막지 않는다.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tv_budget import task_of  # noqa: E402

PROVISER = ("chiip-proviser", "chiip-report-audit-weekly")
CALL = re.compile(r"product_images(\.py)?\s+(ensure|make)\b")


def main():
    inp = json.load(sys.stdin)
    cmd = str((inp.get("tool_input") or {}).get("command") or "")
    if not CALL.search(cmd) or "--no-regen" in cmd or "CHIIP_NO_REGEN" in cmd:
        return
    task = task_of(inp) or ""
    if not task.startswith(PROVISER):
        return
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                      "permissionDecisionReason": "Proviser 회차는 이미지를 새로 그리지 않는다 — product_images.py 명령에 --no-regen을 붙여 있는 그림만 쓴다(정정으로 BOM이 바뀌어도 이름표는 렌더러가 붙인다, 2026-11-22 마스터 지시)"}}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        main()
    except Exception:
        pass
    sys.exit(0)
