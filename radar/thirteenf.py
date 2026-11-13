"""13F 시즌 → Pulse 종목별 매입·매도 기관 수 순위 (마스터 지시 2026-11-08 "13F가 공시되면 Pulse를 통해 종목별 매입 및 매도 기관 수 상위순으로 정리하도록 구조를 설계하라")

구조(설정 config/thirteenf.yaml):
  ① 시계 — 13F-HR 마감 = 분기 말 + 45일(주말이면 다음 영업일). 마감 기준 세 번(잠정 D−2·주 D+1·확정 D+7) 모은다.
  ② 관문 — Pulse(radar/pulse.py)가 status()를 부른다. 그 회차의 차례가 왔고 아직 안 모았거나 안 보냈으면 회차를 연다.
  ③' 수집(universe: market, 2026-11-14 마스터 지시 — 미국 시장 전체): radar/thirteenf_market.py가 SEC 13F 정보표 원문을 전수로 받아 센다(결정론,
     run_hourly). 제출분의 send_coverage 이상을 받은 뒤 Pulse가 market_message를 보낸다. 아래 ③은 universe: fiscal_us(예전 방식)일 때만.
  ③ 수집(모델 — Fiscal.ai MCP는 스크립트가 직접 못 부른다) — `--plan`이 감시 미국 종목을 묶음으로 나눠 execute_code 본문을 준다
     (scripts/fiscal/templates/holders_batch.js). 출력 파일을 `--put`으로 넣는다. 기관 이름은 저장하지 않고 수만 센다.
  ④ 순위 — `--rank`가 매입(보유를 늘린) 기관 수 상위·매도(줄인) 기관 수 상위를 낸다. 순매입 기관 = 늘린 − 줄인, 보유 기관 대비 몫도 붙인다.
  ⑤ 전달 — `--message`가 Pulse 양식 글을 만든다. 모델이 텔레그램으로 보내고 `--sent`로 표시한다(같은 차례를 두 번 보내지 않는다).
한계: 1쪽(보유 규모 상위 최대 1,000 기관) 기준이다. 13F는 분기 말 기준·최대 45일 지연이라 선행 신호가 아니라 지난 분기 수급 확인이다(금지표: 기관 매입 → 주가 상승 아님).
상태 radar/state/thirteenf.json, 집계 knowledge/models/inst13f/<분기>.json.
사용: py radar/thirteenf.py --status · --plan · --put <파일> · --rank · --message · --sent
"""
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config" / "thirteenf.yaml"
KEYS = ROOT / "config" / "fiscal_keys.yaml"
TEMPLATE = ROOT / "scripts" / "fiscal" / "templates" / "holders_batch.js"
STATE = ROOT / "radar" / "state" / "thirteenf.json"
OUT = ROOT / "knowledge" / "models" / "inst13f"
KST = timezone(timedelta(hours=9))
US = ("NASDAQ_", "NYSE_", "AMEX_")


def cfg():
    return yaml.safe_load(CFG.read_text(encoding="utf-8"))


def _load(p, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _save(p, d):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def deadline(year, q):
    """분기(1~4)의 13F 마감일 — 분기 말 + 45일, 주말이면 다음 월요일(연방 공휴일은 따로 보지 않는다)"""
    end = {1: date(year, 3, 31), 2: date(year, 6, 30), 3: date(year, 9, 30), 4: date(year, 12, 31)}[q]
    d = end + timedelta(days=45)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def season(today, c=None):
    """오늘 기준 다룰 분기와 차례 — (year, q, 마감일, [(차례 이름, 날짜)]). 가장 최근 마감 창(D−2 ~ D+7+30일)에 든 분기"""
    c = c or cfg()
    cands = []
    for y in (today.year - 1, today.year):
        for q in (1, 2, 3, 4):
            dl = deadline(y, q)
            rounds = [(r["name"], dl + timedelta(days=r["offset"])) for r in c["rounds"]]
            if rounds[0][1] <= today <= dl + timedelta(days=40):
                cands.append((y, q, dl, rounds))
    return max(cands, key=lambda x: x[2]) if cands else None


def universe(c=None):
    keys = (yaml.safe_load(KEYS.read_text(encoding="utf-8")) or {}).get("keys") or {}
    return sorted({(v or {}).get("key") for v in keys.values() if str((v or {}).get("key") or "").startswith(US)})


def status(now=None):
    """Pulse 관문 — 지금 차례가 왔는데 아직 다 모으지 않았거나(collect) 순위를 안 보냈으면(send) 회차를 연다"""
    now = now or datetime.now(KST)
    s = season(now.date())
    if not s:
        return {"due": False}
    y, q, dl, rounds = s
    cur = [n for n, d in rounds if d <= now.date()]
    if not cur:
        return {"due": False}
    rnd = cur[-1]
    st = _load(STATE, {})
    key = f"{y}Q{q}:{rnd}"
    if (cfg().get("universe") or "") == "market":   # 시장 전체(2026-11-14) — 수집은 결정론(thirteenf_market, run_hourly). 거의 다 모였을 때만 보낸다
        if key in st.get("sent", []):
            return {"due": False}
        prog = (_load(ROOT / "radar" / "state" / "thirteenf_market.json", {}).get("progress") or {}).get(f"{y}Q{q}") or {}
        cov = prog.get("cached", 0) / prog["filers"] if prog.get("filers") else 0.0
        if cov < float(cfg().get("send_coverage", 0.95)):
            return {"due": False, "quarter": f"{y}Q{q}", "round": rnd, "coverage": round(cov, 3)}
        return {"due": True, "phase": "send", "quarter": f"{y}Q{q}", "round": rnd, "deadline": dl.isoformat(), "coverage": round(cov, 3)}
    done = st.get("done", {}).get(key, [])
    left = [k for k in universe() if k not in done]
    if left:
        return {"due": True, "phase": "collect", "quarter": f"{y}Q{q}", "round": rnd, "deadline": dl.isoformat(), "left": len(left)}
    if key not in st.get("sent", []):
        return {"due": True, "phase": "send", "quarter": f"{y}Q{q}", "round": rnd, "deadline": dl.isoformat()}
    return {"due": False}


def offered(now=None):
    pass   # 차례 기록은 --put·--sent가 남긴다(회차를 열어도 일을 마치기 전에는 다시 연다)


def plan(now=None, c=None):
    """남은 종목을 묶음으로 나눈 execute_code 본문 목록"""
    c = c or cfg()
    s = status(now)
    if not s.get("due") or s["phase"] != "collect":
        return s, []
    y, q = int(s["quarter"][:4]), int(s["quarter"][-1])
    st = _load(STATE, {})
    done = st.get("done", {}).get(f"{s['quarter']}:{s['round']}", [])
    left = [k for k in universe() if k not in done]
    body = TEMPLATE.read_text(encoding="utf-8")
    n = c["batch"]
    return s, [body.replace("__KEYS__", json.dumps(left[i:i + n])).replace("__YEAR__", str(y)).replace("__QUARTER__", str(q)) for i in range(0, len(left), n)]


def put(path, now=None):
    """holders_batch.js 출력 → 분기 집계 파일, 차례 완료 표시"""
    text = Path(path).read_text(encoding="utf-8")
    rows = json.loads(text[text.index("["):text.rindex("]") + 1])
    s = status(now)
    if not s.get("quarter"):
        raise SystemExit("지금은 13F 시즌 창이 아니다")
    agg = _load(OUT / f"{s['quarter']}.json", {"quarter": s["quarter"], "rows": {}})
    st = _load(STATE, {})
    key = f"{s['quarter']}:{s['round']}"
    done = set(st.setdefault("done", {}).get(key, []))
    ok = 0
    for r in rows:
        if r.get("quarter") != s["quarter"] or not r.get("key"):
            continue
        done.add(r["key"])   # 실패도 이번 차례에서는 다시 부르지 않는다(다음 차례에 다시)
        if r.get("error"):
            continue
        agg["rows"][r["key"]] = {**{k: r.get(k) for k in ("holders", "covered", "increased", "decreased", "new_positions", "sold_out", "net_shares")}, "round": s["round"],
                                 "at": (now or datetime.now(KST)).isoformat(timespec="minutes")}
        ok += 1
    st["done"][key] = sorted(done)
    _save(OUT / f"{s['quarter']}.json", agg)
    _save(STATE, st)
    return ok


def rank(quarter, c=None):
    c = c or cfg()
    agg = _load(OUT / f"{quarter}.json", {"rows": {}})
    rows = [{"key": k, "ticker": k.split("_", 1)[1], **v} for k, v in agg["rows"].items() if (v.get("holders") or 0) >= c["min_holders"]]
    for r in rows:
        r["net"] = (r.get("increased") or 0) - (r.get("decreased") or 0)
        r["base"] = r.get("covered") or r.get("holders") or 0
    top = c["top"]
    return {"buy": sorted(rows, key=lambda r: -(r.get("increased") or 0))[:top], "sell": sorted(rows, key=lambda r: -(r.get("decreased") or 0))[:top],
            "net_buy": sorted(rows, key=lambda r: -r["net"])[:top], "n": len(rows)}


def market_message(s, c=None, res=None):
    """시장 전체 순위 글(2026-11-14 마스터 지시) — 종목 = 티커(없으면 발행사 이름)"""
    c = c or cfg()
    if res is None:
        import thirteenf_market as M
        res = M.rank(int(s["quarter"][:4]), int(s["quarter"][-1]), c["top"], c["min_holders"])
    if not res.get("buy"):
        return None
    nm = lambda x: f"{x['ticker']}({x['name'][:28]})" if x.get("ticker") else x["name"][:36]
    line = lambda i, x, k: (f"{i}. {nm(x)} {x[k]:,}곳 (보유 {x['holders']:,}곳 · 신규 {x['new']:,}·전량 매도 {x['sold_out']:,} · "
                            f"순{'매입' if x['net'] >= 0 else '매도'} {abs(x['net']):,}곳)" + (" · 분할 보정" if x.get("split") else ""))
    st = res["stat"]
    out = [f"[Chiip Pulse · 13F {res['quarter']} 기관 수급 — 미국 시장 전체 · {s.get('round', '')} 집계]", "",
           f"매입(보유를 늘린) 기관 수 상위 {len(res['buy'])}"] + [line(i, x, "increased") for i, x in enumerate(res["buy"], 1)]
    out += ["", f"매도(보유를 줄인) 기관 수 상위 {len(res['sell'])}"] + [line(i, x, "decreased") for i, x in enumerate(res["sell"], 1)]
    out += ["", f"13F-HR 제출 기관 {st['filers']:,}곳(직전 분기도 제출해 증감을 셀 수 있는 {st['both']:,}곳) · 보유 기관 {c['min_holders']}곳 이상 {res['n']:,}종목 · "
            f"ETF·펀드 제외 · SEC 정보표 원문 기준(옵션 제외). 13F는 {res['quarter']} 분기 말 보유라 최대 45일 지난 수급이다 — 앞으로의 매매가 아니다."]
    return "\n".join(out)


def message(now=None, c=None):
    s = status(now)
    q = s.get("quarter")
    if not q:
        return None
    if ((c or cfg()).get("universe") or "") == "market":
        return market_message(s, c)
    r = rank(q, c)
    if not r["n"]:
        return None
    line = lambda i, x, k: f"{i}. {x['ticker']} {x[k]:,}곳 (보유 {x['base']:,}곳 중 {x[k] / x['base']:.0%} · 순{'매입' if x['net'] >= 0 else '매도'} {abs(x['net']):,}곳)"
    out = [f"[Chiip Pulse · 13F {q} 기관 수급 — {s.get('round', '')} 집계]", "",
           f"매입(보유를 늘린) 기관 수 상위 {len(r['buy'])}"] + [line(i, x, "increased") for i, x in enumerate(r["buy"], 1)]
    out += ["", f"매도(보유를 줄인) 기관 수 상위 {len(r['sell'])}"] + [line(i, x, "decreased") for i, x in enumerate(r["sell"], 1)]
    out += ["", f"감시 미국 {r['n']}종목, 종목마다 보유 규모 상위 최대 1,000 기관 기준. 13F는 {q} 분기 말 보유라 최대 45일 지난 수급이다 — 앞으로의 매매가 아니다."]
    return "\n".join(out)


def sent(now=None):
    s = status(now)
    st = _load(STATE, {})
    st.setdefault("sent", []).append(f"{s.get('quarter')}:{s.get('round')}")
    _save(STATE, st)


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if "--plan" in argv:
        s, bodies = plan()
        print(json.dumps(s, ensure_ascii=False))
        for i, b in enumerate(bodies, 1):
            print(f"----- 묶음 {i}/{len(bodies)} (execute_code 본문) -----")
            print(b)
        return 0
    if "--put" in argv:
        print(f"[13F] {put(argv[argv.index('--put') + 1])}종목 저장 · {json.dumps(status(), ensure_ascii=False)}")
        return 0
    if "--rank" in argv:
        s = status()
        print(json.dumps(rank(s["quarter"]) if s.get("quarter") else s, ensure_ascii=False, indent=1))
        return 0
    if "--message" in argv:
        print(message() or "[13F] 보낼 순위 없음")
        return 0
    if "--sent" in argv:
        sent()
        print("[13F] 발송 표시")
        return 0
    today = date.today()
    s = season(today)
    nxt = min(d for y in (today.year, today.year + 1) for q in (1, 2, 3, 4) if (d := deadline(y, q)) >= today)
    print(json.dumps({**status(), "next_deadline": nxt.isoformat(),
                      "season": None if not s else {"quarter": f"{s[0]}Q{s[1]}", "rounds": [(n, d.isoformat()) for n, d in s[3]]}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
