"""Apify 렌더링 대행 — robots·약관이 허용한 공개 페이지가 자바스크립트로만 그려질 때만 쓴다
(마스터 지시 2026-11-22 "Tingo, Twelvedata, Apify 모두 API Key를 넣어뒀다 … 커넥터가 막힐 경우 다른 대안으로 이를 쓰도록")

원칙: Apify는 '읽을 수 있는 페이지를 대신 그려 주는 브라우저'로만 쓴다. 약관이 자동 수집을 막은 사이트(Investegate·LSE·Yahoo 등, 2026-11-22 점검)를
  Apify로 우회하지 않는다 — 부르기 전에 robots.txt를 확인하고 config/data_sources.yaml connector_fallback.apify 원칙을 따른다.
Actor: apify/rag-web-browser(공식, URL 하나 → 본문 마크다운). run-sync-get-dataset-items, 인증은 Authorization 헤더(토큰을 주소에 넣지 않는다).
예산: 무료 월 $5 — 월 MONTHLY_RUNS회 상한(state apify_fetch). 키: D:\\local-only\\secrets\\.env APIFY_TOKEN.
사용: py radar/apify_fetch.py <url>          → 마크다운 앞부분 출력
      py radar/apify_fetch.py --status
"""
import json
import sys
import urllib.parse
import urllib.request
import urllib.robotparser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

ACTOR = "apify~rag-web-browser"
STATE = "apify_fetch"
MONTHLY_RUNS = 150
BLOCKED_HOSTS = ("investegate.co.uk", "londonstockexchange.com", "finance.yahoo.com", "finviz.com", "investing.com", "marketscreener.com", "linkedin.com", "glassdoor")


def robots_ok(url):
    p = urllib.parse.urlparse(url)
    rp = urllib.robotparser.RobotFileParser()
    try:
        rp.parse(common.http_get(f"{p.scheme}://{p.netloc}/robots.txt", timeout=20).decode("utf-8", "ignore").splitlines())
    except Exception:
        return True   # robots.txt가 없으면 허용으로 본다(다른 수집기와 같은 규칙)
    return rp.can_fetch(common.UA, url) and rp.can_fetch("ClaudeBot", url)


def _month():
    return common.now_kst().strftime("%Y-%m")


def fetch(url, token=None, post=None):
    """→ (마크다운 또는 None, 사유)"""
    host = urllib.parse.urlparse(url).netloc.lower()
    if any(h in host for h in BLOCKED_HOSTS):
        return None, "약관·robots로 막힌 사이트 — Apify로 우회하지 않는다"
    if not robots_ok(url):
        return None, "robots.txt 금지"
    st = common.load_state(STATE, {})
    if st.get("month") != _month():
        st = {"month": _month(), "runs": 0}
    if st["runs"] >= MONTHLY_RUNS:
        return None, f"이번 달 상한 {MONTHLY_RUNS}회"
    token = token or common.load_env().get("APIFY_TOKEN")
    if not token:
        return None, "APIFY_TOKEN 없음"
    body = json.dumps({"query": url, "maxResults": 1, "outputFormats": ["markdown"]}).encode()
    req = urllib.request.Request(f"https://api.apify.com/v2/acts/{ACTOR}/run-sync-get-dataset-items?timeout=120", data=body,
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    st["runs"] += 1
    common.save_state(STATE, st)
    try:
        items = json.loads((post or (lambda r: urllib.request.urlopen(r, timeout=180).read()))(req))
    except Exception as e:
        return None, f"{type(e).__name__}"
    md = next((i.get("markdown") or i.get("text") for i in items or [] if i.get("markdown") or i.get("text")), None)
    if md:
        return md, ""
    crawl = next((i.get("crawl") or {} for i in items or []), {})
    return None, f"빈 결과({crawl.get('httpStatusMessage') or crawl.get('requestStatus') or '사유 없음'})"   # 사이트가 막으면(403) 우회하지 않는다


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 2 or sys.argv[1] == "--status":
        st = common.load_state(STATE, {})
        print(f"Apify 렌더링 이번 달 {st.get('runs', 0) if st.get('month') == _month() else 0}/{MONTHLY_RUNS}회")
    else:
        md, why = fetch(sys.argv[1])
        print(md[:3000] if md else f"실패 — {why}")
