"""주장(claim) 파일 검증 — BUILD_PROMPT §5.2, docs/schema.md

사용법:
    py scripts/validate_claims.py                 # knowledge/claims/ 전체
    py scripts/validate_claims.py 파일1 파일2      # 지정 파일만
오류가 하나라도 있으면 종료 코드 1.
"""
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("pyyaml이 없습니다. 먼저 실행: py -m pip install -r requirements.txt")
    sys.exit(2)

ROOT = Path(__file__).resolve().parent.parent
CLAIMS_DIR = ROOT / "knowledge" / "claims"

ENUMS = {
    "claim_type": {"확정사실", "가이던스", "추정", "채널체크", "자체추론", "필드인텔"},
    "speaker_type": {"기업", "정부", "표준기관", "연구자", "IB", "언론", "사용자취재", "AI"},
    "novelty": {"신규", "수정", "추가검증", "반복", "재해석", "미확정"},
    "supply_relation": {"확정공급", "과거공급", "인증·평가", "후보", "분석상추정", "미확인", "해당없음"},
    "confidence": {"높음", "중간", "낮음"},
}
SUBJECT_ROLES = {"설계", "IP", "제조", "조립", "검사", "판매", "운영", "구매"}
STATUS_ENUMS = {
    "manufacturing": {"개발", "파일럿", "장비설치", "공정안정화", "생산확대", "출하"},
    "customer": {"샘플", "평가", "인증완료", "디자인윈", "계약", "고객제품적용"},
    "business": {"투자계획", "승인·자금", "건설", "가동", "매출인식", "현금회수"},
}
FINANCIAL_LINKS = {"물량", "함량", "가격", "점유율", "제조비용", "시점", "해당없음"}
REQUIRED = ["id", "created", "subject", "statement", "claim_type", "speaker_type", "novelty",
            "evidence", "public_corroborated", "confidence", "falsifier", "next_check", "user_confirmed"]
ID_RE = re.compile(r"^C-\d{8}-\d{3}$")
SOURCE_RE = re.compile(r"^S-\d{8}-\d{3}$")
FIELD_REF_RE = re.compile(r"^(FI-[A-Za-z0-9-]+|S-\d{8}-\d{3})$")


def blank(value):
    return value is None or (isinstance(value, str) and not value.strip())


def check(path):
    errors = []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:  # YAML 문법 오류
        return [f"YAML 읽기 실패: {exc}"]
    if not isinstance(data, dict):
        return ["최상위가 key: value 형식이 아님"]

    for key in REQUIRED:
        if key not in data or (key not in ("public_corroborated", "user_confirmed") and blank(data.get(key))):
            errors.append(f"필수 항목 누락: {key}")

    cid = str(data.get("id", ""))
    if cid and not ID_RE.match(cid):
        errors.append(f"id 형식 오류(C-YYYYMMDD-NNN): {cid}")
    if cid and path.stem != cid:
        errors.append(f"파일 이름({path.stem})과 id({cid})가 다름")

    for key, allowed in ENUMS.items():
        value = data.get(key)
        if value is not None and value not in allowed:
            errors.append(f"{key} 허용값 아님: {value}")

    subject = data.get("subject") or {}
    if not isinstance(subject, dict) or blank(subject.get("company")):
        errors.append("subject.company 누락")
    elif subject.get("role") not in (None, *SUBJECT_ROLES):
        errors.append(f"subject.role 허용값 아님: {subject.get('role')}")

    status = data.get("status") or {}
    if isinstance(status, dict):
        for axis, allowed in STATUS_ENUMS.items():
            value = status.get(axis)
            if value is not None and value not in allowed:
                errors.append(f"status.{axis} 허용값 아님: {value}")

    for link in data.get("financial_link") or []:
        if link not in FINANCIAL_LINKS:
            errors.append(f"financial_link 허용값 아님: {link}")

    evidence = data.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        errors.append("evidence가 비어 있음(출처 없는 주장은 저장 금지)")
    else:
        for i, ev in enumerate(evidence, 1):
            if not isinstance(ev, dict):
                errors.append(f"evidence[{i}] 형식 오류")
                continue
            for key in ("source_id", "locator", "gist_ko"):
                if blank(ev.get(key)):
                    errors.append(f"evidence[{i}].{key} 누락")
            if ev.get("source_id") and not SOURCE_RE.match(str(ev["source_id"])):
                errors.append(f"evidence[{i}].source_id 형식 오류: {ev['source_id']}")

    ref = data.get("field_intel_ref")
    if data.get("claim_type") == "필드인텔" and blank(ref):
        errors.append("필드인텔 주장은 field_intel_ref 필요(F1 출처 S-… 또는 추상 id FI-…)")
    if not blank(ref) and not FIELD_REF_RE.match(str(ref)):
        errors.append("field_intel_ref는 S-… 또는 FI-… 형식만 허용(원문·인명 금지)")

    for key in ("public_corroborated", "user_confirmed"):
        if key in data and not isinstance(data[key], bool):
            errors.append(f"{key}는 true/false")
    return errors


def main(argv):
    if argv:
        files = [Path(a) for a in argv if a.endswith((".yaml", ".yml"))]
    else:
        files = sorted(CLAIMS_DIR.rglob("*.yaml")) if CLAIMS_DIR.exists() else []
    failed = 0
    seen = {}
    for path in files:
        errs = check(path)
        cid = path.stem
        if cid in seen:
            errs.append(f"중복 id: {seen[cid]}")
        seen[cid] = path
        if errs:
            failed += 1
            print(f"[실패] {path}")
            for e in errs:
                print(f"   - {e}")
    print(f"검사 {len(files)}건, 실패 {failed}건")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
