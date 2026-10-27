"""채점 스크립트 공통 — CSV/YAML 읽기, 기간 필터"""
import csv
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read_csv(rel):
    p = ROOT / rel
    if not p.exists():
        return []
    with p.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def parse_date(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s[:19]).date() if "T" in s else date.fromisoformat(s[:10])
    except ValueError:
        return None


def since(days):
    return date.today() - timedelta(days=days)


def pct(a, b):
    return f"{(100 * a / b):.0f}%" if b else "-"