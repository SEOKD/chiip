"""어닝콜 원천 단계 — Fiscal.ai → TradingView → 텔레그램 Fundeasyearnings (마스터 지시 2026-11-21
"Analysis에서 종목 어닝콜을 참조할 때 Fiscal.ai에 없다면 TradingView 또는 텔레그램 채널 https://t.me/Fundeasyearnings을 참조할 수 있는 구조")

순서와 이유
  ① Fiscal.ai `company_ir_events` → `company_ir_events_transcript` — 회사 전문(1순위, ADR-014).
  ② TradingView `mcp-tv-get-documents`(Quartr 제공, 분류 call_transcript) → `mcp-tv-get-document-view`(transcript·summary) — 전문 또는 Q&A 요약.
     radar/jp_tv_docs.py가 일본 종목에 쓰던 경로를 전 종목으로 넓힌다. 호출 상한: 한 메시지에 호출 하나(2026-11-02 사고).
  ③ 텔레그램 공개 채널 Fundeasyearnings — '📊 <티커> 실적발표 (YYYY년 N분기)' 글에 실적 요약과 Q1~Qn 질문·답변 요약이 붙는다(긴 글은 다음 글로 이어진다).
     2차 요약이다 — Q&A가 있으면 call.script kind 'Q&A 정리', 실적 요약뿐이면 콜 원천으로 치지 않는다. 숫자는 회사 1차 자료와 대조한다.
     수집: radar/pollers/tg_channels.py가 쌓은 radar/inbox/tg_channels/Fundeasyearnings.jsonl(약 열흘치) → 없으면 공개 미리보기 검색
     https://t.me/s/Fundeasyearnings?q=<티커>(로그인 없음, t.me robots.txt 없음 2026-11-21 확인).
① ②는 MCP라 결정론 스크립트가 부르지 못한다(ADR-012) — 이 스크립트는 단계표와 호출 인자를 내고, 모델이 호출해 결과를 `--tv-put`·`--put`으로 넣는다. ③은 여기서 바로 찾는다.
결과는 datapack call.script = {"kind": "전문|녹취 요약|Q&A 정리", "source": URL 또는 원천 이름, "date": "YYYY-MM-DD", "via": "fiscal|tradingview|telegram|company|notion"}.
한국 종목 관문(v2_to_report.kr_call_gap, 2026-11-15)은 이 칸만 본다 — 어느 단계에서 왔든 같다.

사용: py scripts/tenbagger/call_source.py <id>                 # 단계표(JSON): Fiscal 코드 본문·TradingView 심볼·텔레그램 찾은 글
      py scripts/tenbagger/call_source.py <id> --search        # 텔레그램을 웹 검색까지
      py scripts/tenbagger/call_source.py --tv-put <id> <파일> # get_documents 출력 → 가장 최근 콜 문서(전문·요약 id)
      py scripts/tenbagger/call_source.py --put <id> <via> <kind> <YYYY-MM-DD> <source>
"""
import csv
import html
import json
import re
import sys
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "radar"))
CHANNEL = "Fundeasyearnings"
INBOX = ROOT / "radar" / "inbox" / "tg_channels"
KINDS = ("전문", "녹취 요약", "Q&A 정리")
VIAS = ("fiscal", "tradingview", "telegram", "company", "notion")
HEAD = re.compile(r"^📊\s*([A-Z0-9][A-Z0-9.\-]*)\s*실적발표\s*\((\d{4})년\s*(\d)분기\)")
CONT = re.compile(r"^(Q\d+\s*:|- 질문|- 답변|⚠)")
QA = re.compile(r"(^|\n)Q\d+\s*:", re.M)


def _dp(eid):
    p = ROOT / "knowledge" / "models" / "companies" / eid / "datapack.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def tv_symbol(eid, ticker=None):
    p = ROOT / "config" / "tradingview_symbols.csv"
    if p.exists():
        with p.open(encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                if r.get("entity_id") == eid:
                    return r["tv_symbol"]
    return None


def _ticker(eid, dp=None):
    dp = dp if dp is not None else _dp(eid)
    t = str(dp.get("ticker") or "")
    return t.split(".")[0].upper() if t else (eid.split("-", 1)[-1].upper() if eid.startswith("us-") else "")


def threads(posts):
    """채널 글 → [{ticker, year, q, at, url, text, has_qa}] — 머리 글 뒤 이어지는 Q·질문·답변 글을 붙인다(글 번호 순)"""
    out, cur = [], None
    for p in sorted(posts, key=lambda x: x.get("id") or 0):
        t = (p.get("text") or "").strip()
        m = HEAD.match(t)
        if m:
            cur = {"ticker": m.group(1), "year": int(m.group(2)), "q": int(m.group(3)), "at": p.get("at"), "url": p.get("url"), "text": t, "ids": [p.get("id")]}
            out.append(cur)
        elif cur and CONT.match(t) and (p.get("id") or 0) - cur["ids"][-1] <= 3:
            cur["text"] += "\n" + t
            cur["ids"].append(p.get("id"))
        else:
            cur = None
    for x in out:
        x["has_qa"] = bool(QA.search(x["text"]))
    return out


def _local_posts():
    p = INBOX / f"{CHANNEL}.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def _search_posts(ticker, get=None):
    """공개 미리보기 검색 t.me/s/<채널>?q=<티커> — 로그인 없음"""
    from pollers import tg_channels
    get = get or tg_channels.fetch
    page = get(f"https://t.me/s/{CHANNEL}?q={urllib.parse.quote(ticker)}")
    return tg_channels.parse(page, seen=datetime.now().isoformat(timespec="minutes"))


def tg_find(ticker, posts=None, search=False, get=None):
    """그 티커의 실적 글(최신 순). Q&A가 있는 것만 콜 원천 후보"""
    if not ticker:
        return []
    want = lambda x: x["ticker"].split(".")[0].replace("-", "") == ticker.replace("-", "").replace(".", "")
    hits = [x for x in threads(posts if posts is not None else _local_posts()) if want(x)]
    if not hits and search:
        try:
            hits = [x for x in threads(_search_posts(ticker, get)) if want(x)]
        except Exception as e:   # 네트워크 실패는 '못 찾음'으로 — 리포트를 멈추지 않는다
            return [{"error": f"검색 실패: {type(e).__name__}"}]
    return sorted(hits, key=lambda x: x.get("at") or "", reverse=True)


FISCAL_CODE = """async () => {{
  // 어닝콜 원천 ①(call_source.py) — 최근 실적 이벤트와 전문
  // company_ir_events = 최근 이벤트 먼저인 행 배열, 전문은 resourceType 'transcript'(resourceId = eventKey 'q3-2026')
  const ev = await codemode.company_ir_events({{ companyKey: "{key}" }}).catch(e => ({{ err: String(e) }}));
  const rows = Array.isArray(ev) ? ev : [];
  const last = rows.find(r => r.eventType === "earnings");
  const tr = rows.find(r => r.resourceType === "transcript");
  let t = null;
  if (tr) t = await codemode.company_ir_events_transcript({{ companyKey: "{key}", eventKey: tr.resourceId }}).catch(x => ({{ err: String(x) }}));
  console.log(JSON.stringify({{ key: "{key}", err: ev.err || null,
    latest_event: last ? {{ fy: last.fiscalYear, q: last.fiscalQuarter, date: last.eventDate }} : null,
    transcript: tr ? {{ eventKey: tr.resourceId, date: tr.eventDate, url: tr.url, fresh: !!(last && tr.fiscalYear === last.fiscalYear && tr.fiscalQuarter === last.fiscalQuarter),
                       chars: t && t.transcript ? t.transcript.text.length : 0, qa: !!(t && (t.sections || []).some(s => s.sectionType === "qa")), err: t && t.err }} : null }}));
  // fresh=false(전문이 최근 실적보다 옛 분기)이거나 transcript=null이면 ② TradingView로
}}"""


def fiscal_key(eid):
    try:
        import yaml
        d = yaml.safe_load((ROOT / "config" / "fiscal_keys.yaml").read_text(encoding="utf-8")) or {}
        return ((d.get("keys") or {}).get(eid) or {}).get("key")
    except Exception:
        return None


def tv_blocked(now=None):
    """TradingView 한도 대기 중이면 풀리는 시각(문자열), 아니면 None — .claude/hooks/tv_budget.py가 쓰는 상태 파일"""
    p = ROOT / "radar" / "state" / "tv_budget.json"
    try:
        bu = json.loads(p.read_text(encoding="utf-8")).get("blocked_until")
    except (OSError, ValueError):
        return None
    if not bu:
        return None
    from datetime import timezone, timedelta as _td
    now = now or datetime.now(timezone(_td(hours=9)))
    return bu if datetime.fromisoformat(bu) > now else None


def plan(eid, search=False):
    dp = _dp(eid)
    tk = _ticker(eid, dp)
    key = fiscal_key(eid)
    tg = tg_find(tk, search=search)
    best = next((x for x in tg if x.get("has_qa")), None)
    steps = [
        {"order": 1, "source": "fiscal", "ready": bool(key), "key": key,
         "do": "mcp__4056a804-908b-4b7a-b720-ace3a2bcabc9__execute_code 에 code 본문" if key else "Fiscal 키 없음 — 건너뛰고 ②",
         "code": FISCAL_CODE.format(key=key) if key else None},
        {"order": 2, "source": "tradingview", "symbol": tv_symbol(eid), "ready": bool(tv_symbol(eid)) and not tv_blocked(),
         "do": (f"TradingView 한도 대기(~{tv_blocked()}) — 건너뛰고 ③" if tv_blocked() else
                "mcp-tv-get-documents(symbol, category transcripts, limit 3) → 결과 파일 → call_source.py --tv-put <id> <파일> → 고른 문서를 mcp-tv-get-document-view(transcript, 없으면 summary). 한 메시지에 호출 하나")},
        {"order": 3, "source": "telegram", "channel": CHANNEL, "ready": bool(best),
         "found": [{k: x.get(k) for k in ("ticker", "year", "q", "at", "url", "has_qa")} for x in tg[:3]],
         "do": ("찾은 글의 Q&A를 자기 말로 요약해 datapack call에 — 2차 요약이므로 숫자는 1차 자료와 대조" if best else
                ("채널에 그 티커 글이 없다" + ("" if search else " — --search로 웹 검색까지")))}]
    return {"id": eid, "ticker": tk, "current": ((dp.get("call") or {}).get("script")) or None, "steps": steps,
            "put": "py scripts/tenbagger/call_source.py --put <id> <fiscal|tradingview|telegram|company|notion> <전문|녹취 요약|Q&A 정리> <YYYY-MM-DD> <URL·원천>"}


def tv_pick(data, since_days=120, now=None):
    """get_documents 출력 → 가장 최근 콜 문서 {title, kind, reported, transcript, summary}. 없으면 None"""
    now = now or datetime.now()
    start = (now - timedelta(days=since_days)).timestamp()
    docs = [d for d in (data or {}).get("items") or [] if (d.get("category") or {}).get("id") == "call_transcript" and (d.get("reported") or 0) >= start]
    if not docs:
        return None
    d = max(docs, key=lambda x: x.get("reported") or 0)
    v = {x["type"]: x["id"] for x in d.get("views") or []}
    return {"title": d.get("title"), "kind": "전문" if v.get("transcript") else "Q&A 정리" if "Q&A" in str(d.get("title")) else "녹취 요약",
            "date": datetime.fromtimestamp(d.get("reported") or 0).date().isoformat(), "transcript": v.get("transcript"), "summary": v.get("summary")}


def put(eid, via, kind, date, source):
    if via not in VIAS or kind not in KINDS or not re.match(r"\d{4}-\d{2}-\d{2}$", date) or not source:
        raise SystemExit(f"--put <id> <{'|'.join(VIAS)}> <{'|'.join(KINDS)}> <YYYY-MM-DD> <source>")
    p = ROOT / "knowledge" / "models" / "companies" / eid / "datapack.json"
    dp = json.loads(p.read_text(encoding="utf-8"))
    dp.setdefault("call", {})["script"] = {"kind": kind, "source": source, "date": date, "via": via}
    p.write_text(json.dumps(dp, ensure_ascii=False, indent=1), encoding="utf-8")
    return dp["call"]["script"]


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if argv[:1] == ["--put"] and len(argv) >= 6:
        print(json.dumps(put(argv[1], argv[2], argv[3], argv[4], " ".join(argv[5:])), ensure_ascii=False))
        return 0
    if argv[:1] == ["--tv-put"] and len(argv) >= 3:
        print(json.dumps(tv_pick(json.loads(Path(argv[2]).read_text(encoding="utf-8"))), ensure_ascii=False))
        return 0
    if argv and not argv[0].startswith("--"):
        print(json.dumps(plan(argv[0], search="--search" in argv), ensure_ascii=False, indent=1))
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
