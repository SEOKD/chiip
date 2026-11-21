"""커넥터 장애 감지 훅 — Fiscal.ai·Easyconomics MCP가 한도·인증·서버 오류를 내면 막힘을 기록하고 대체 경로를 모델에게 알린다
(마스터 지시 2026-11-22 "TradingView, Fiscal.ai 등 커넥터가 막힐 경우 다른 대안으로 이를 쓰도록 하는 시스템을 설계하라")

post: 응답(또는 실패)에 한도·인증·서버 오류 표지가 있으면 radar/state/channel_down.json에 '<채널>: 막힘 끝 시각'(DOWN_H시간)을 남기고,
      additionalContext로 radar/market_data.FALLBACK 안내문을 붙인다. source_router·self_heal·market_data --status가 같은 기록을 읽는다.
TradingView는 tv_budget.py가 따로 맡는다(일일 예산·냉각). 훅 오류는 작업을 막지 않는다.
"""
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KST = timezone(timedelta(hours=9))
CHANNELS = (("mcp__4056a804-908b-4b7a-b720-ace3a2bcabc9__", "fiscal"), ("mcp__easyconomics__", "easyconomics"))
DOWN_H = {"fiscal": 1, "easyconomics": 6}
BAD = re.compile(r"rate.?limit|too many requests|\b429\b|quota|limit exceeded|exceeded (?:your|the)|unauthori[sz]ed|\b401\b|\b403\b|forbidden|"
                 r"\b50[0234]\b|service unavailable|bad gateway|internal server error|timed? ?out|connection (?:refused|reset)", re.I)


def fallback(ch):
    try:
        sys.path.insert(0, str(ROOT / "radar"))
        import market_data
        return market_data.FALLBACK.get(ch, "")
    except Exception:
        return ""


def main(event):
    try:
        inp = json.load(sys.stdin)
    except Exception:
        return
    tool = str(inp.get("tool_name") or "")
    ch = next((c for p, c in CHANNELS if tool.startswith(p)), None)
    if not ch:
        return
    resp = json.dumps(inp.get("tool_response") or inp.get("error") or "", ensure_ascii=False)[:4000]
    failed = event == "failure"
    if not (failed or BAD.search(resp)):
        return
    if not failed and '"error":null' in resp.replace(" ", "") and not re.search(r"rate.?limit|too many|quota|exceeded", resp, re.I):
        return   # 정상 응답 본문에 숫자 401·503 등이 섞인 경우
    now = datetime.now(KST)
    f = ROOT / "radar" / "state" / "channel_down.json"
    try:
        st = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        st = {}
    st[ch] = (now + timedelta(hours=DOWN_H[ch])).isoformat(timespec="seconds")
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    msg = (f"[커넥터 막힘] {ch} 오류(한도·인증·서버) — {DOWN_H[ch]}시간 동안 막힘으로 기록했다(radar/state/channel_down.json). "
           f"같은 호출을 되풀이하지 말고 대체 경로를 쓴다: {fallback(ch)} · 상태 확인 py radar/market_data.py --status")
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUseFailure" if failed else "PostToolUse", "additionalContext": msg}}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        main(sys.argv[1] if len(sys.argv) > 1 else "post")
    except Exception:
        pass
    sys.exit(0)
