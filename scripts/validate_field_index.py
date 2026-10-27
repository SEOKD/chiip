"""필드 인텔 추상 포인터 검증 — BUILD_PROMPT §3.2, §21.4

knowledge/field_intel_index.csv 가 '포인터만' 담고 있는지 검사한다.
오류가 있으면 종료 코드 1.
"""
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "knowledge" / "field_intel_index.csv"
COLUMNS = ["fi_id", "entered_at", "disclosure_class", "source_class", "reliability", "entities", "topics",
           "linked_theses", "corroboration", "embargo_until", "f1_converted_at", "publicly_confirmed_at",
           "confirm_source_id", "lead_days", "outcome"]
CLASSES = {"F1", "F2", "F3", "F4"}
RELIABILITY = re.compile(r"^[A-F][1-6]$")
CORROBORATION = {"pending", "corroborated", "contradicted"}
OUTCOMES = {"pending", "confirmed", "refuted", "unresolved"}
TOPIC_RE = re.compile(r"^[a-z0-9\-]+$")
SOURCE_CLASS_RE = re.compile(r"^[A-Z]-[a-z0-9\-]+$")


def main():
    if not INDEX.exists():
        print("field_intel_index.csv 없음")
        return 1
    errors = []
    with INDEX.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != COLUMNS:
            errors.append(f"열 이름이 규격과 다름: {reader.fieldnames}")
        rows = list(reader)
    seen = set()
    for n, row in enumerate(rows, 2):
        fid = row.get("fi_id", "")
        where = f"{n}행({fid})"
        if not re.match(r"^FI-\d{4}$", fid):
            errors.append(f"{where} fi_id 형식")
        if fid in seen:
            errors.append(f"{where} 중복 id")
        seen.add(fid)
        if row.get("disclosure_class") not in CLASSES:
            errors.append(f"{where} disclosure_class는 F1~F4")
        if not SOURCE_CLASS_RE.match(row.get("source_class", "")):
            errors.append(f"{where} source_class는 'A-fab-planning' 같은 범주만")
        if not RELIABILITY.match(row.get("reliability", "")):
            errors.append(f"{where} reliability는 A1~F6")
        for topic in filter(None, row.get("topics", "").split(";")):
            if not TOPIC_RE.match(topic):
                errors.append(f"{where} topics는 영문 소문자 태그만(원문·수치·고객 추정 금지)")
                break
        if row.get("corroboration") not in CORROBORATION:
            errors.append(f"{where} corroboration 허용값 아님")
        if row.get("outcome") not in OUTCOMES:
            errors.append(f"{where} outcome 허용값 아님")
        if row.get("disclosure_class") == "F2" and not row.get("embargo_until"):
            errors.append(f"{where} F2는 embargo_until 필수")
    for e in errors:
        print(f"[실패] {e}")
    print(f"포인터 {len(rows)}건, 오류 {len(errors)}건")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
