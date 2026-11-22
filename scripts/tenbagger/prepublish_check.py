"""Analysis 리포트 발행 전 결정론 점검 — 주간 점검에서 되풀이된 오류를 코드로 잡는다
(마스터 지시 2026-11-22 "Analysis Report 초안에서 실수를 최소화하도록 시스템 전체를 점검하라").

근거: docs/proviser/reports/20261122_week.md — 28건 중 27건·96곳 정정, 같은 오류 12유형이 두 리포트 이상에서 되풀이됐다.
문장 지시(R-20261116·R-20261119·R-20261122)는 사흘 넘게 지켜지지 않았다(R-20261119-01) → 발행 단계(publish_tenbagger.prepare)에서 멈춘다.

점검(실패 = 발행 멈춤, 경고 = 회차 요약에 적는다):
  고객 줄     '최대 고객·상위 n곳'에 지역·부문·채널·기타 묶음이 들어감 / 'Customer A(Customer' 겹침
  타일        빈 값 · 손익비 −0.0/0.0 · 목표주가 자릿수($10 미만 소수) · 판단 문장 목표주가와 다름 · 현지 통화 상장사에 '$' 주가
  자리표시    판단 문장 '임시·TODO·초안'
  금액 표기   $1,000M 이상을 $M로
  동종 배수   '동종 중앙값 n배'가 리포트 안에서 두 값 이상
  수주 확정   pipeline '확정' total 합 > 공시 잔고(reported_backlog)
  불가능 값   −100%를 넘는 손실률
  차익 이름표 목표주가와 기본 시나리오가 다른데 '(목표주가·기본 시나리오)' 한 이름표
  적자 리비전 적자 기업 EPS가 더 음수로 갔는데 '상향'
  반응일      revision_events 실적 행의 session(장전·장후)이 SEC 8-K 접수 시각과 다름(미국 상장사, 네트워크 실패는 경고)
  대조 줄     _model.json에 '보강 적용·타일 대조·산식 대조·일봉 대조' 4줄(R-20261119-01)
사용: py scripts/tenbagger/prepublish_check.py outputs/tenbagger/reports/<날짜>_<티커>.json [--no-sec]
"""
import json
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GROUP = re.compile(r"미국|북미|유럽|아시아|중국|일본|한국|대만|해외|국내|내수|수출|지역|부문|사업부|채널|유통|대리점|도매|소매|민간|기타|집계|\(합\)|그 밖|잔여|미분해|상업|주거|"
                   r"Americas|EMEA|APAC|Asia|Europe|North America|International|Domestic|Segment|Channel|Distribut|Other|Rest of", re.I)
CUR_SYM = {"GBP": "£", "GBX": "£", "EUR": "€", "JPY": "¥", "KRW": "₩", "TWD": "NT$", "HKD": "HK$", "CHF": "CHF", "SEK": "SEK", "DKK": "DKK", "NOK": "NOK", "CAD": "C$"}


def _num(s):
    try:
        return float(str(s).replace(",", "").replace("−", "-"))
    except ValueError:
        return None


def _text(d):
    return json.dumps(d, ensure_ascii=False)


def check_customers(d, dp, add):
    full = _text(d.get("summary")) + _text(d.get("sections"))
    if re.search(r"Customer [A-F]\s*\(\s*Customer", full):
        add("실패", "고객 줄", "'Customer A(Customer …' 이름 겹침")
    items = (dp.get("customers") or {}).get("items") or []
    groups = [x.get("name", "") for x in items[:3] if GROUP.search(str(x.get("name", "")))]
    if groups and re.search(r"최대 고객|상위\s*\d\s*곳|상위 고객", full):
        add("실패", "고객 줄", f"'최대 고객·상위 n곳'인데 datapack customers에 묶음이 있다: {', '.join(groups[:3])} — '최대 매출 묶음'으로 쓰고 10-K·10-Q 단일 고객 공시를 따로 넣는다(R-20261122-01 ①)")


def check_tiles(d, dp, add):
    v = d.get("verdict") or {}
    tiles = d.get("tiles") or []
    for x in tiles:
        if not str(x.get("v") or "").strip():
            add("실패", "타일", f"'{x.get('k')}' 값이 비었다 — 없으면 '회사 가이던스 없음'처럼 이유를 쓴다")
        if re.search(r"손익비[^0-9−-]{0,12}[−-]?0\.0(?!\d)", str(x.get("sub")) + str(x.get("v"))):
            add("실패", "타일", f"'{x.get('k')}' 손익비 0.0 — 약세·강세가 같은 쪽이면 '해당 없음(이유)'")
    tgt = v.get("target")
    if tgt is not None:
        shown = [m for x in tiles for m in re.findall(r"목표주가\s*[^\d\s]{0,4}\s*([\d,]+(?:\.\d+)?)", str(x.get("v")) + " " + str(x.get("sub")))]
        for s in shown:
            n = _num(s)
            if n is None:
                continue
            if abs(n - tgt) > max(0.006, 0.005 * tgt):
                add("실패", "타일", f"타일 목표주가 {s} ≠ verdict.target {tgt}")
            elif tgt < 10 and "." not in s and abs(tgt - round(tgt)) > 1e-9:
                add("실패", "타일", f"$10 미만 목표주가를 정수로 잘랐다: {s} (verdict {tgt})")
        in_view = [_num(m) for m in re.findall(r"목표주가\s*[^\d\s]{0,4}\s*([\d,]+(?:\.\d+)?)", str(v.get("view") or ""))]
        if any(n is not None and abs(n - tgt) > max(0.006, 0.005 * tgt) for n in in_view):
            add("실패", "판단 문장", f"판단 문장 목표주가 {in_view} ≠ verdict.target {tgt}")
    cur = str((dp.get("profile") or {}).get("currency") or dp.get("unit") or "").upper()
    sym = next((s for k, s in CUR_SYM.items() if k in cur), None)
    price_tile = next((x for x in tiles if x.get("k") == "주가"), None)
    if sym and price_tile and str(price_tile.get("v", "")).startswith("$"):
        add("실패", "통화", f"{cur} 상장사 주가 타일이 '$' — '{sym}'로")
    if re.search(r"임시|TODO|초안|자리표시|placeholder", str(v.get("view") or ""), re.I) or not str(v.get("view") or "").strip():
        add("실패", "판단 문장", "verdict.view가 비었거나 임시 문장(R-20261110-01)")


def prose(d):
    """표·차트를 뺀 글(판단·요약·타일·문단·목록) — 표 머리가 ($M)인 열은 $M가 맞다(D-20261114-01)"""
    parts = [_text(d.get("verdict")), _text(d.get("summary")), _text(d.get("tiles"))]
    parts += [_text(b) for _, b in _blocks(d) if b.get("type") not in ("table", "chart")]
    return " ".join(parts)


def check_text(d, html, add):
    body = prose(d)
    big = re.findall(r"\$\d{1,3},\d{3}(?:\.\d+)?M\b", body)
    if big:
        add("실패", "금액 표기", f"$1,000M 이상을 $M로: {big[0]} 외 {len(big) - 1}건 — $B로")
    peers = sorted({round(_num(m), 1) for m in re.findall(r"동종\s*중앙값?\s*([\d.]+)\s*배", _text(d)) if _num(m) is not None})
    if len(peers) > 1:
        add("실패", "동종 배수", f"'동종 중앙값'이 {len(peers)}개 값: {peers} — 멀티플 선정 표 값 하나만(R-20261122-01 ⑥)")
    # 손실·하방 문맥의 −100% 초과만(실적 증감률 −131%는 맞는 값이다)
    loss = [m for m in re.findall(r"(?:손실|다운사이드|하방|낙폭|최악|약세|원금|지분가치)[^%]{0,25}?[−-](\d{3,}(?:\.\d+)?)\s*%", _text(d)) if _num(m) and _num(m) > 100]
    if loss:
        add("실패", "불가능 값", f"−100%를 넘는 손실률 {loss[:3]} — 지분가치 0에서 자른다")
    v = d.get("verdict") or {}
    base = next((c.get("value") for _, b in _blocks(d) if (b.get("chart") or {}).get("kind") == "scenario"
                 for c in (b["chart"].get("cases") or []) if re.search(r"기본|base", str(c.get("name") or c.get("label") or ""), re.I)), None)
    if base is not None and v.get("target") is not None and abs(float(base) - float(v["target"])) > 0.01 * float(v["target"]) \
            and re.search(r"\(목표주가\s*·\s*기본 시나리오\)", body):
        add("실패", "차익 이름표", f"목표주가 {v['target']} ≠ 기본 시나리오 {base}인데 '(목표주가·기본 시나리오)' 한 이름표")


def _blocks(d):
    for s in d.get("sections") or []:
        for b in s.get("blocks") or []:
            yield s, b
    for ch in d.get("gallery") or []:
        yield {}, {"type": "chart", "chart": ch}


def check_backlog(dp, add):
    p = dp.get("pipeline") or {}
    rep = _num(p.get("reported_backlog"))
    tot = [_num(x.get("total")) for x in p.get("items") or [] if x.get("status") == "확정" and _num(x.get("total")) is not None]
    if rep and tot and sum(tot) > rep * 1.02:
        add("실패", "수주 확정", f"'확정' 합 {sum(tot):.2f} > 공시 잔고 {rep} — 합계·부분집합·선수금·기준일 뒤 수주 겹침을 뺀다(R-20261122-01 ②)")


def check_eps_sign(d, dp, add):
    rows = ((dp.get("consensus") or {}).get("revisions") or {}).get("rows") or []
    full = _text(d)
    for r in rows:
        if "EPS" not in str(r.get("metric")):
            continue
        a, b = _num(r.get("from")), _num(r.get("to"))
        if a is None or b is None or a >= 0 or b >= a:
            continue
        if re.search(rf"{re.escape(str(r.get('period')))}[^.]{{0,40}}EPS[^.]{{0,40}}상향", full):
            add("실패", "적자 리비전", f"{r['period']} EPS {a} → {b}는 적자 확대 = 하향인데 '상향'(R-20261122-01 ④)")


def _sec_json(url):
    sys.path.insert(0, str(ROOT / "radar"))
    from pollers import sec_filings
    req = urllib.request.Request(url, headers={"User-Agent": sec_filings._ua()})
    return json.loads(urllib.request.urlopen(req, timeout=20).read())


def session_of(utc_iso):
    """SEC 접수 시각(UTC) → 미국 동부 장전·장중·장후"""
    t = datetime.fromisoformat(utc_iso.replace("Z", "+00:00")).astimezone(timezone.utc)
    et = t - timedelta(hours=4 if 3 <= t.month <= 10 else 5)   # 서머타임 근사(3~10월) — 경계 주는 경고로만 쓴다
    hm = et.hour * 60 + et.minute
    return ("before" if hm < 570 else "after" if hm >= 960 else "during"), et.date().isoformat()


def check_sessions(dp, add):
    tk = str(dp.get("ticker") or "").split(":")[-1].upper()
    evs = [e for e in dp.get("revision_events") or [] if e.get("kind") == "실적" and e.get("session") and e.get("date")]
    if not tk or not evs or not str(dp.get("id", "")).startswith("us-"):
        return
    try:
        cik = next(v["cik_str"] for v in _sec_json("https://www.sec.gov/files/company_tickers.json").values() if v["ticker"].upper() == tk)
        r = _sec_json(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json")["filings"]["recent"]
    except Exception as exc:
        add("경고", "반응일", f"SEC 조회 실패({type(exc).__name__}) — 8-K 접수 시각으로 session을 손으로 확인")
        return
    acc = [(r["filingDate"][i], r["acceptanceDateTime"][i]) for i, f in enumerate(r["form"]) if f.startswith("8-K") and "2.02" in (r["items"][i] or "")]
    for e in evs:
        near = [a for fd, a in acc if abs((datetime.fromisoformat(fd) - datetime.fromisoformat(e["date"])).days) <= 1]
        if not near:
            continue
        sess, day = session_of(near[0])
        if sess != e["session"] or day != e["date"]:
            add("실패", "반응일", f"{e.get('tag') or e['date']}: datapack {e['date']} {e['session']} vs 8-K 접수 {day} {sess}(ET) — 반응일이 하루 밀린다(R-20261122-01 ③)")


def check_model(src, add):
    m = src.with_name(src.stem + "_model.json")
    if not m.exists():
        add("경고", "대조 줄", f"{m.name} 없음")
        return
    t = m.read_text(encoding="utf-8")
    miss = [k for k in ("보강 적용", "타일 대조", "산식 대조", "일봉 대조") if k not in t]
    if miss:
        add("실패", "대조 줄", f"_model.json에 {', '.join(miss)} 줄 없음(R-20261119-01)")


def run(src, sec=True):
    src = Path(src)
    d = json.loads(src.read_text(encoding="utf-8"))
    html_p = src.with_suffix(".html")
    html = html_p.read_text(encoding="utf-8") if html_p.exists() else ""
    rid = next((p.name for p in (ROOT / "knowledge" / "models" / "companies").iterdir()
                if (p / "datapack.json").exists() and json.loads((p / "datapack.json").read_text(encoding="utf-8")).get("ticker") in (d.get("ticker"),)), None) \
        if not d.get("id") else d["id"]
    dp_p = ROOT / "knowledge" / "models" / "companies" / str(rid) / "datapack.json"
    dp = json.loads(dp_p.read_text(encoding="utf-8")) if rid and dp_p.exists() else {}
    out = []

    def add(st, name, detail):
        out.append({"status": st, "name": name, "detail": detail})
    for fn, args in ((check_customers, (d, dp, add)), (check_tiles, (d, dp, add)), (check_text, (d, html, add)),
                     (check_backlog, (dp, add)), (check_eps_sign, (d, dp, add)), (check_model, (src, add))) + (((check_sessions, (dp, add)),) if sec else ()):
        try:
            fn(*args)
        except Exception as exc:   # 점검기 오류는 경고로(발행을 막지 않는다)
            add("경고", fn.__name__, f"점검 오류 {type(exc).__name__}: {exc}"[:200])
    return out


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    srcs = [a for a in argv if not a.startswith("--")]
    bad = 0
    for s in srcs:
        res = run(s, sec="--no-sec" not in argv)
        fails = [x for x in res if x["status"] == "실패"]
        bad += len(fails)
        print(f"[발행 전 점검] {Path(s).name}: 실패 {len(fails)} · 경고 {len(res) - len(fails)}")
        for x in res:
            print(f"  {x['status']} · {x['name']} — {x['detail']}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
