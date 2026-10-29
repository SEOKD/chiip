"""마스터 노션 Stocks 색인 — 텐배거 리포트 우선순위 (마스터 지시 2026-10-30 "내 노션 Stocks의 티커 중 최신(현 시점 ±7일) 어닝콜 스크립트와
컨센서스를 입력해 놓은 종목부터 분석하라. IB 리포트 내용이 있으면 참조하라. 이 구조를 텐배거 리포트 엔진에 넣어라")

흐름: 모델(예약 작업 chiip-notion-watch 매시간 · chiip-tenbagger-report 회차 시작)이 노션 커넥터로 Stocks 아래 페이지를 읽어
  본문을 radar/inbox/notion_stocks/<page_id>.md(git 제외)에 저장 → 이 스크립트가 규칙으로 판별(--classify) → 색인에 기록(--upsert).
  판별은 코드, 읽기만 모델. pick_report.py가 색인을 읽어 '노션 Stocks' 단계로 먼저 고른다.
제목 규칙: '회사명 티커'(예: 콴타서비스 PWR) 또는 '회사명(티커)'. 티커 = 영문 대문자 1~6자(.·- 허용) 또는 숫자 4~6자리(한·일·대만). 티커 없는 페이지(테마)는 건너뛴다.
판별 규칙(본문):
  어닝콜 스크립트 — 'Operator'·'Question-and-Answer'·'Prepared Remarks'·'Q&A'·'어닝콜'·'컨퍼런스콜'·'질의응답' 중 2개 이상 또는 발언자 줄(CEO·CFO·Analyst) 3개 이상
  컨센서스 — '컨센서스'·'Consensus'·'est.'·'예상치'·'추정치' + 매출·EPS·영업이익 지표 이름
  IB 내용 — 증권사 이름(Goldman·Morgan Stanley·JPMorgan·BofA·Citi·UBS·Barclays·Jefferies·Bernstein·Evercore·Mizuho 등) 또는 '목표가'·'Price Target'·'투자의견'
  콜 날짜 — 콜 표지어 근처의 날짜(YYYY-MM-DD·YYYY.MM.DD·YYYY/MM/DD·'October 29, 2026'·'2026년 10월 29일') 중 가장 최근 것, 없으면 페이지 편집일(date_basis '편집일')
색인 knowledge/models/notion/stocks_index.json: {"updated", "pages": [{page_id,title,company,ticker,call_date,date_basis,has_transcript,has_consensus,has_ib,last_edited,checked_at}]}
사용: py scripts/tenbagger/notion_stocks.py --classify <본문 파일> --page-id <id> --title "<제목>" --edited <YYYY-MM-DD>   → 판별 JSON + 색인 기록
      py scripts/tenbagger/notion_stocks.py --list   → 색인과 오늘 ±7일 대상
IB 내용은 라이선스 자료로 다룬다 — 리포트에는 자기 말 요지만, 문장 복제·목표가를 결론처럼 쓰기 금지.
"""
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "knowledge" / "models" / "notion" / "stocks_index.json"
WINDOW_DAYS = 7
TICKER_RE = re.compile(r"(?:\(|\s|^)([A-Z][A-Z0-9.\-]{0,5}|\d{4,6})\)?\s*$")
CALL_MARKS = ("operator", "question-and-answer", "prepared remarks", "q&a", "어닝콜", "컨퍼런스콜", "실적 발표 콜", "질의응답", "earnings call")
SPEAKER_RE = re.compile(r"(?mi)^\s*\**\s*(?:[A-Z][\w.\- ]{1,40}\s*[—–-]\s*)?(?:CEO|CFO|COO|President|Chief|Analyst|애널리스트|대표|최고재무책임자)\b")
CONS_RE = re.compile(r"컨센서스|consensus|\best\.|예상치|추정치", re.I)
METRIC_RE = re.compile(r"매출|EPS|영업이익|revenue|sales|operating income|EBITDA|가이던스|guidance", re.I)
IB_RE = re.compile(r"Goldman|Morgan Stanley|JP ?Morgan|J\.P\. Morgan|BofA|Bank of America|Citi|UBS|Barclays|Jefferies|Bernstein|Evercore|Mizuho|"
                   r"Wells Fargo|Deutsche|Nomura|Macquarie|Cowen|Needham|Piper|Raymond James|KeyBanc|Truist|목표가|목표주가|price target|투자의견", re.I)
MONTHS = {m: i for i, m in enumerate(("january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"), 1)}
DATE_RES = [
    (re.compile(r"(20\d\d)[-./](\d{1,2})[-./](\d{1,2})"), lambda m: (int(m[1]), int(m[2]), int(m[3]))),
    (re.compile(r"(20\d\d)년\s*(\d{1,2})월\s*(\d{1,2})일"), lambda m: (int(m[1]), int(m[2]), int(m[3]))),
    (re.compile(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(20\d\d)", re.I),
     lambda m: (int(m[3]), MONTHS[m[1].lower()], int(m[2]))),
]


def parse_title(title):
    """'콴타서비스 PWR' → ('콴타서비스', 'PWR'), 티커가 없으면 (제목, None)"""
    t = (title or "").strip()
    m = TICKER_RE.search(t)
    if not m or re.fullmatch(r"20[0-3]\d", m.group(1)):   # 'OCP 2026' 같은 연도는 티커가 아니다(테마 페이지)
        return t, None
    company = t[: m.start()].strip(" (·-") or t
    return company, m.group(1)


def _dates(text):
    out = []
    for rx, fn in DATE_RES:
        for m in rx.finditer(text):
            try:
                y, mo, d = fn(m)
                out.append((m.start(), date(y, mo, d)))
            except (ValueError, KeyError):
                continue
    return out


def classify(text, edited=None, today=None):
    today = today or date.today()
    low = (text or "").lower()
    marks = sum(1 for k in CALL_MARKS if k in low)
    speakers = len(SPEAKER_RE.findall(text or ""))
    has_transcript = marks >= 2 or speakers >= 3
    has_consensus = bool(CONS_RE.search(text or "")) and bool(METRIC_RE.search(text or ""))
    has_ib = bool(IB_RE.search(text or ""))
    call_date, basis = None, None
    if has_transcript:
        pos = [i for k in CALL_MARKS for i in [low.find(k)] if i >= 0]
        cands = [(abs(p - min(pos)), d) for p, d in _dates(text or "")] if pos else []
        near = [d for dist, d in cands if dist <= 3000 and d <= today + timedelta(days=WINDOW_DAYS)]
        if near:
            call_date, basis = max(near), "본문 날짜"
        elif edited:
            call_date, basis = date.fromisoformat(str(edited)[:10]), "편집일"
    return {"has_transcript": has_transcript, "has_consensus": has_consensus, "has_ib": has_ib,
            "call_date": call_date.isoformat() if call_date else None, "date_basis": basis, "call_marks": marks, "speakers": speakers}


def load():
    return json.loads(INDEX.read_text(encoding="utf-8")) if INDEX.exists() else {"updated": None, "pages": []}


def upsert(entry):
    d = load()
    d["pages"] = [p for p in d["pages"] if p.get("page_id") != entry["page_id"]] + [entry]
    d["updated"] = datetime.now().astimezone().isoformat(timespec="seconds")
    INDEX.parent.mkdir(parents=True, exist_ok=True)
    INDEX.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def eligible(today=None, idx=None):
    """오늘 ±7일 안의 콜 스크립트 + 컨센서스가 있는 Stocks 종목 — 콜 날짜가 오늘에 가까운 순, 같으면 최근 편집 순"""
    today = today or date.today()
    out = []
    for p in (idx or load()).get("pages") or []:
        if not (p.get("ticker") and p.get("has_transcript") and p.get("has_consensus") and p.get("call_date")):
            continue
        cd = date.fromisoformat(p["call_date"])
        if abs((cd - today).days) <= WINDOW_DAYS:
            out.append(p)
    return sorted(out, key=lambda p: (abs((date.fromisoformat(p["call_date"]) - today).days), str(p.get("last_edited") or "")), reverse=False)


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if argv and argv[0] == "--classify":
        a = dict(zip(argv[2::2], argv[3::2]))
        text = Path(argv[1]).read_text(encoding="utf-8")
        company, ticker = parse_title(a.get("--title", ""))
        res = classify(text, a.get("--edited"))
        entry = {"page_id": a.get("--page-id"), "title": a.get("--title"), "company": company, "ticker": ticker, **res,
                 "last_edited": a.get("--edited"), "checked_at": date.today().isoformat()}
        if ticker and entry["page_id"]:
            upsert(entry)
        print(json.dumps(entry, ensure_ascii=False))
        return 0
    if argv and argv[0] == "--list":
        d = load()
        print(f"[노션 Stocks 색인] {len(d['pages'])}쪽 · 갱신 {d.get('updated')}")
        for p in eligible(idx=d):
            print(f"  ±7일 대상: {p['company']}({p['ticker']}) 콜 {p['call_date']}({p.get('date_basis')}) · 컨센서스 {p['has_consensus']} · IB {p['has_ib']}")
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
