"""SPAC 피인수 기업 테마 판정 2단계 (마스터 지시 2026-11-04 "2단계 진행", 설계 knowledge/methods/spac_discovery_design.md 2절) — 모델 없음

spac_watch.py가 남긴 단계 전환(transitions.csv) 중 확정 계약 이후(S2~S5)인 스팩마다 한 번, 그 거래 서류(EDGAR 폴더의 EX-99.1 보도자료 → 본문 순)
첫 부분을 읽어 피인수 기업 이름(추정)과 테마를 정한다. 어휘·문턱은 config/spac.yaml. 결과 knowledge/models/spac/themes.csv.
테마가 맞은 전환만 Pulse '🧩 SPAC' 원본으로 넘어간다(radar/pulse.py fetch_spac). 테마 판정은 단서이지 사실이 아니다.
사용: py radar/pollers/spac_theme.py [--limit 40] [--reset]
SEC 접속 규칙: 프로젝트 User-Agent(sec_filings._ua), 요청 사이 0.15초.
"""
import csv
import json
import re
import sys
import time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from pollers import common, sec_filings   # noqa: E402
else:
    from . import common, sec_filings

DIR = common.ROOT / "knowledge" / "models" / "spac"
THEMES = DIR / "themes.csv"
COLS = ["cik", "spac", "target", "theme", "hits", "terms", "doc", "at"]
TARGET_RE = re.compile(r"business combination(?: agreement)?[^.]{0,200}?\b(?:with|and)\s+((?:[A-Z][\w&.\-]*\s?){1,6}(?:Inc\.?|Corp\.?|Corporation|Ltd\.?|Limited|LLC|Holdings|Technologies|Systems|N\.V\.|plc|AG|S\.A\.))")


def cfg():
    return common.load_yaml("config/spac.yaml")


def get(url):
    return common.http_get(url, headers={"User-Agent": sec_filings._ua()}, timeout=40)


def docs(folder, c):
    """거래 서류 폴더에서 읽을 htm 목록 — EX-99.1 보도자료 우선"""
    d = json.loads(get(folder.rstrip("/") + "/index.json"))
    items = [i for i in d.get("directory", {}).get("item", []) if i["name"].lower().endswith((".htm", ".html")) and "index" not in i["name"].lower()]
    pri = sorted(items, key=lambda i: (0 if re.search(r"ex-?99", i["name"], re.I) else 1, -int(i.get("size") or 0)))
    return [folder.rstrip("/") + "/" + i["name"] for i in pri[:c["max_docs"]]]


def classify_text(text, c):
    best, out = None, {}
    for th, words in c["themes"].items():
        n, terms = 0, []
        for w in words:
            k = len(re.findall(w, text, re.I))
            if k:
                n += k
                terms.append(re.sub(r"\\b|\(\?:[^)]*\)\??", "", w))
        out[th] = (n, terms)
        ok = n >= c["min_hits"] and (len(terms) >= c.get("min_terms", 1) or n >= (c.get("single_term") or {}).get(th, 10 ** 9))
        if ok and (best is None or n > out[best][0]):
            best = th
    m = TARGET_RE.search(text)
    return best, (out[best] if best else (0, [])), (m.group(1).strip() if m else "")


def classify(folder, c=None):
    c = c or cfg()
    text, used = "", ""
    for u in docs(folder, c):
        raw = get(u).decode("utf-8", "replace")
        text += " " + re.sub(r"\s+", " ", common.strip_tags(raw))[: c["max_chars"]]
        used = used or u
        time.sleep(0.15)
    th, (n, terms), target = classify_text(text, c)
    return {"theme": th or "", "hits": n, "terms": "|".join(terms[:6]), "target": target, "doc": used}


def load():
    if not THEMES.exists():
        return {}
    with THEMES.open(encoding="utf-8", newline="") as f:
        return {r["cik"]: r for r in csv.DictReader(f)}


def run(limit=40, reset=False):
    c = cfg()
    have = {} if reset else load()   # reset: 어휘를 바꾼 뒤 전부 다시 판정
    trans = DIR / "transitions.csv"
    if not trans.exists():
        return {"classified": 0}
    with trans.open(encoding="utf-8", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["to"] in c["alert_stages"]]
    todo, seen = [], set()
    for r in sorted(rows, key=lambda r: r["filed"], reverse=True):   # 최근 전환부터
        if r["cik"] in have or r["cik"] in seen:
            continue
        seen.add(r["cik"])
        todo.append(r)
    n, errors = 0, []
    for r in todo[:limit]:
        try:
            res = classify(r["url"], c)
        except Exception as e:
            errors.append(f"{r['cik']}: {type(e).__name__}")
            continue
        have[r["cik"]] = {"cik": r["cik"], "spac": r["name"], **res, "at": common.iso(common.now_kst())}
        n += 1
    DIR.mkdir(parents=True, exist_ok=True)
    with THEMES.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, COLS)
        w.writeheader()
        w.writerows(sorted(have.values(), key=lambda x: (x["theme"] == "", x["spac"])))
    common.record_health("src-spac-theme", not errors or n > 0, "; ".join(errors[:3]) or None)
    return {"classified": n, "left": max(0, len(todo) - limit), "matched": sum(1 for x in have.values() if x["theme"]), "errors": len(errors)}


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(run(int(argv[argv.index("--limit") + 1]) if "--limit" in argv else 40, reset="--reset" in argv), ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
