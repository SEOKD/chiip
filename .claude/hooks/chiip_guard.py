"""치입 가드레일 훅 (BUILD_PROMPT §9) — Write/Edit 직전(pre)·직후(post)

pre  (PreToolUse, exit 2 = 차단):
  claim-guard      knowledge/claims/*.yaml → validate_claims 규칙 통과해야 저장
  public-guard     outputs/invest|public → 비공개 근거(F2~F4 포인터·public_corroborated:false 주장·local-only) 인용 차단
  embargo-guard    outputs/** → 해제 전 엠바고(F2) 포인터·엠바고 표시 차단
  local-path-guard 저장소 안 모든 파일 → 비밀키 패턴·금칙어·.env 파일 차단
post (PostToolUse):
  unit-guard       knowledge/models|outputs → check_units 경고를 Claude에게 보여줌(exit 2, 차단 아님)
"""
import csv
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2]).resolve()
sys.path.insert(0, str(ROOT / "scripts"))
KST = timezone(timedelta(hours=9))


def block(msg):
    print(f"[치입 가드] {msg}", file=sys.stderr)
    sys.exit(2)


def rel(path):
    try:
        return Path(path).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return None


def new_content(tool, ti):
    """Write면 content, Edit면 현재 파일에 치환을 적용한 결과"""
    if tool == "Write":
        return ti.get("content", "")
    p = Path(ti.get("file_path", ""))
    old = p.read_text(encoding="utf-8") if p.exists() else ""
    if ti.get("replace_all"):
        return old.replace(ti.get("old_string", ""), ti.get("new_string", ""))
    return old.replace(ti.get("old_string", ""), ti.get("new_string", ""), 1)


def field_index():
    f = ROOT / "knowledge" / "field_intel_index.csv"
    if not f.exists():
        return {}
    with f.open(encoding="utf-8", newline="") as fh:
        return {r["fi_id"]: r for r in csv.DictReader(fh)}


def private_claims():
    out = set()
    try:
        import yaml
    except ImportError:
        return out
    for f in (ROOT / "knowledge" / "claims").rglob("*.yaml"):
        try:
            d = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        if d.get("public_corroborated") is False:
            out.add(str(d.get("id")))
    return out


def pre(tool, ti):
    path = ti.get("file_path", "")
    r = rel(path)
    if r is None:
        return  # 저장소 밖(예: D:\local-only)은 여기서 다루지 않음
    text = new_content(tool, ti)

    # local-path-guard
    if Path(r).name.lower().endswith(".env") or Path(r).name.lower() == ".env":
        block(".env 파일은 저장소에 만들 수 없습니다. 키는 D:\\local-only\\secrets\\.env 에만.")
    import scan_sealed
    terms = scan_sealed.load_denylist()
    low = text.lower()
    if any(t in low for t in terms):
        block("금칙어(취재원 보호 목록)가 포함되어 저장을 막았습니다. 해당 표현을 지우거나 추상 포인터로 바꾸세요.")
    for kind, pat in scan_sealed.SECRET_PATTERNS:
        if r != "scripts/scan_sealed.py" and pat.search(text):
            block(f"비밀키로 보이는 값({kind})이 있어 저장을 막았습니다.")

    # claim-guard
    if r.startswith("knowledge/claims/") and r.endswith((".yaml", ".yml")):
        import tempfile
        import validate_claims
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d) / Path(r).name
            tmp.write_text(text, encoding="utf-8")
            errs = validate_claims.check(tmp)
        if errs:
            block("주장 검증 실패 — " + " / ".join(errs[:8]))

    # embargo-guard / public-guard
    if r.startswith("outputs/"):
        if re.search(r"\[EMBARGO|엠바고 원문", text, re.I):
            block("엠바고 표시가 있는 내용은 출력에 쓸 수 없습니다.")
        idx = field_index()
        now = datetime.now(KST)
        for fid in set(re.findall(r"FI-\d{4}", text)):
            row = idx.get(fid)
            if not row:
                continue
            if row["disclosure_class"] == "F2" and row.get("embargo_until"):
                try:
                    until = datetime.fromisoformat(row["embargo_until"])
                    if until.tzinfo is None:
                        until = until.replace(tzinfo=KST)
                    if now < until:
                        block(f"{fid}는 엠바고 해제 전({row['embargo_until']})입니다.")
                except ValueError:
                    block(f"{fid}의 엠바고 해제 시각 형식을 확인할 수 없어 막았습니다.")
            if (r.startswith("outputs/invest/") or r.startswith("outputs/public/")) \
                    and row["disclosure_class"] in ("F2", "F3", "F4") and not row.get("f1_converted_at"):
                block(f"{fid}({row['disclosure_class']})는 invest·public 모드에서 쓸 수 없습니다(F1 전환 전).")
        if r.startswith("outputs/invest/") or r.startswith("outputs/public/"):
            if re.search(r"local-only|sealed\\|sealed/|licensed\\|licensed/", text, re.I):
                block("invest·public 출력은 local-only 자료를 참조할 수 없습니다.")
            bad = sorted(set(re.findall(r"C-\d{8}-\d{3}", text)) & private_claims())
            if bad:
                block("공개 확인 안 된 주장(public_corroborated: false) 인용: " + ", ".join(bad[:5]))
            if r.startswith("outputs/invest/") and "투자 권유가 아님" not in text:
                block("invest 출력 하단에 '공개 자료 기반 분석이며 투자 권유가 아님' 문구가 필요합니다.")


def post(tool, ti):
    r = rel(ti.get("file_path", ""))
    if not r or not (r.startswith("knowledge/models/") or r.startswith("outputs/")):
        return
    import io
    import contextlib
    import check_units
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        check_units.main([str(ROOT / r)])
    warns = [l for l in buf.getvalue().splitlines() if l.startswith("[경고]")]
    if warns:
        print("[치입 단위 경고 — 차단 아님, 확인 후 필요하면 수정]\n" + "\n".join(warns[:10]), file=sys.stderr)
        sys.exit(2)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "pre"
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    tool = event.get("tool_name", "")
    ti = event.get("tool_input", {}) or {}
    if tool not in ("Write", "Edit", "MultiEdit"):
        return 0
    if tool == "MultiEdit":
        # 여러 치환은 Write처럼 최종 내용을 근사하기 어려우므로 new_string만 비밀·금칙어 검사
        ti = {"file_path": ti.get("file_path"), "content": "\n".join(e.get("new_string", "") for e in ti.get("edits", []))}
        tool = "Write"
    (pre if mode == "pre" else post)(tool, ti)
    return 0


if __name__ == "__main__":
    sys.exit(main())
