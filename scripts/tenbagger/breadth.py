"""추정치 수정 폭(revision breadth) — 마스터 선택 2026-11-14 "추정치 수정 폭"

왜: EPS 리비전 크기(평균이 몇 % 움직였나)는 애널리스트 한 명의 큰 수정에 끌려간다. 수정 폭은 '몇 명이 같은 방향으로 움직였나'를 본다 —
    IB 전략가들이 쓰는 순 수정 비율(Citi Earnings Revision Index 꼴, (상향 − 하향) / 전체)과 같은 정의.
재료: Fiscal.ai company_analyst_estimates history(Zacks) — 컨센서스가 바뀐 날마다 평균·애널리스트 수.
      개별 애널리스트 수정 건수는 주지 않으므로 '애널리스트 수가 같은 채로 평균이 움직인 날' = 수정 1건(상향·하향)으로 센다.
      애널리스트 수가 바뀐 날은 커버리지 변화(편입·제외)라 수정에서 빼고 따로 센다.
      같은 날·같은 지표는 기간(분기·올해·내년)을 묶어 1건 — 한 명이 여러 기간을 한꺼번에 고쳐도 1건이다.
한계: 같은 날 여러 명이 고치면 1건으로 합쳐진다(건수는 하한). 같은 날 상향·하향이 섞이면 많은 쪽만 남는다.
설정: config/revision_breadth.yaml (상수는 knowledge/models/params/registry.yaml prm-breadth-*).

사용: py scripts/tenbagger/breadth.py --code NYSE_LTH NASDAQ_NVDA …   # execute_code에 넣을 코드(revision_breadth.js)
      py scripts/tenbagger/breadth.py --put <출력 파일>                # knowledge/models/estimates/breadth.json에 종목별 결과
      py scripts/tenbagger/breadth.py --show <id>                       # datapack consensus.revision_breadth로 계산
Analysis 리포트는 eps_history.js 한 번으로 재료가 같이 들어온다(adapter --eps-history → consensus.revision_breadth).
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CFG = ROOT / "config" / "revision_breadth.yaml"
STORE = ROOT / "knowledge" / "models" / "estimates" / "breadth.json"
TPL = ROOT / "scripts" / "fiscal" / "templates" / "revision_breadth.js"


def cfg():
    return yaml.safe_load(CFG.read_text(encoding="utf-8"))


def _d(s):
    return date.fromisoformat(str(s)[:10])


def events(rows, today, tol):
    """[(날짜, 지표, 'up'|'down'|'cov')] — 열린 기간(기간 끝 > today)만, 같은 계열의 연속 두 값 비교"""
    series = {}
    for r in rows or []:
        metric, ptype, end, asof, mean, n = (list(r) + [None] * 6)[:6]
        if not asof or mean is None or not end or _d(end) <= today:
            continue
        series.setdefault((metric, ptype, end), []).append((_d(asof), float(mean), n))
    out = []
    for (metric, _, _), v in series.items():
        v.sort(key=lambda x: x[0])
        for (d0, m0, n0), (d1, m1, n1) in zip(v, v[1:]):
            if n0 != n1:
                out.append((d1, metric, "cov"))
                continue
            if not m0:
                continue
            ch = m1 / m0 - 1 if m0 > 0 else (m1 - m0) / abs(m0)
            if abs(ch) >= tol:
                out.append((d1, metric, "up" if ch > 0 else "down"))
    return by_day(out)


def by_day(ev):
    """같은 날·같은 지표는 1건 — 애널리스트 한 명이 올해·내년·분기를 한꺼번에 고치면 기간 수만큼 세지 않게.
    방향 = 그날 그 지표의 상향 기간 수 − 하향 기간 수의 부호(같으면 버린다). 수정이 없고 커버리지 변화만 있으면 'cov'"""
    day = {}
    for d, m, k in ev:
        c = day.setdefault((d, m), {"up": 0, "down": 0, "cov": 0})
        c[k] += 1
    out = []
    for (d, m), c in sorted(day.items()):
        if c["up"] != c["down"]:
            out.append((d, m, "up" if c["up"] > c["down"] else "down"))
        elif not c["up"] and c["cov"]:
            out.append((d, m, "cov"))
    return out


def ratio(up, down, min_events):
    return (up - down) / (up + down) if up + down >= min_events else None


def compute(rows, today=None, c=None):
    """{창: {지표: {up, down, cov, b}, '전체': {...}}}"""
    c = c or cfg()
    today = today or date.today()
    ev = events(rows, today, c["tol"])
    res = {}
    for w in c["windows"]:
        lo = today - timedelta(days=w)
        cell = {}
        for name in list(c["metrics"]) + ["전체"]:
            sel = [e for e in ev if e[0] > lo and (name == "전체" or e[1] == name)]
            up, dn, cov = (sum(1 for e in sel if e[2] == k) for k in ("up", "down", "cov"))
            cell[c["metrics"].get(name, name)] = {"up": up, "down": dn, "cov": cov, "b": ratio(up, dn, c["min_events"])}
        res[w] = cell
    return res


def verdict(b, strong):
    if b is None:
        return "표본 적음"
    return "상향 우세" if b >= strong else ("하향 우세" if b <= -strong else "엇갈림")


def _r(b):
    return "-" if b is None else f"{b:+.2f}"


def blocks(dp, today=None):
    """Analysis 리포트 '어닝콜 변화·컨센서스' 절 — 한 문단 + 표. 재료가 없으면 []"""
    rb = (dp.get("consensus") or {}).get("revision_breadth") or {}
    if not rb.get("rows"):
        return []
    c = cfg()
    today = today or (_d(rb["as_of"]) if rb.get("as_of") else date.today())
    res = compute(rb["rows"], today, c)
    w0, w1 = c["windows"][0], c["windows"][-1]
    names = [v for v in c["metrics"].values()] + ["전체"]
    shown = [n for n in names if any(res[w][n]["up"] + res[w][n]["down"] + res[w][n]["cov"] for w in c["windows"])]
    if not shown:
        return []
    rows = []
    for n in shown:
        row = [n]
        for w in c["windows"]:
            x = res[w][n]
            row += [f"{x['up']} / {x['down']}", _r(x["b"])]
        row.append(str(sum(res[w][n]["cov"] for w in c["windows"][-1:])))
        rows.append(row)
    e0, e1 = res[w0]["EPS"], res[w1]["EPS"]
    v0, v1 = verdict(e0["b"], c["strong"]), verdict(e1["b"], c["strong"])
    turn = ""
    if e0["b"] is not None and e1["b"] is not None and (e0["b"] > 0) != (e1["b"] > 0) and abs(e0["b"] - e1["b"]) >= c["strong"]:
        turn = f" 최근 {w0}일 방향이 {w1}일과 반대다 — 추정 흐름이 돌아서는 중일 수 있다(다음 실적·가이던스로 확인)."
    text = (f"**추정치 수정 폭:** 최근 {w0}일 EPS 추정은 상향 {e0['up']}건·하향 {e0['down']}건으로 **{v0}**(순 비율 {_r(e0['b'])}), "
            f"{w1}일은 상향 {e1['up']}건·하향 {e1['down']}건으로 {v1}({_r(e1['b'])})이다.{turn} "
            f"평균이 몇 % 움직였나(리비전 크기)와 달리 몇 번 같은 방향으로 고쳤나를 본다 — 수정 1건은 애널리스트 수가 그대로인 채 컨센서스가 움직인 날(지표별 하루 1건)이라 "
            f"같은 날 여러 명이 고치면 1건으로 합쳐지고, 상향 + 하향이 {c['min_events']}건 미만이면 순 비율을 쓰지 않는다.")
    head = ["지표"] + [h for w in c["windows"] for h in (f"{w}일 상향/하향", f"{w}일 순 비율")] + [f"{w1}일 커버리지 변화"]
    return [{"type": "p", "text": text},
            {"type": "table", "title": f"추정치 수정 폭 — 열린 기간(다음 분기들·올해·내년) 컨센서스 수정 건수, 최근 {w0}·{w1}일",
             "headers": head, "rows": rows,
             "note": (f"(리포트 본문엔 그리지 않는 기록용 주석) 수정 1건 = 애널리스트 수가 같은 채로 컨센서스 평균이 {c['tol'] * 100:.1f}% 이상 움직인 날(지표별, 그날 바뀐 기간들의 다수 방향). 같은 날 여러 명이 고치면 1건이라 건수는 하한이다. "
                      f"순 비율 = (상향 − 하향) / (상향 + 하향), 상향 + 하향이 {c['min_events']}건 미만이면 '-'. 커버리지 변화 = 수정 없이 애널리스트 수만 바뀐 날(수정에서 뺀다).")}]


def summary(res, c):
    e = {w: res[w]["EPS"] for w in c["windows"]}
    return {f"eps_b{w}": e[w]["b"] for w in c["windows"]} | {f"eps_up{w}": e[w]["up"] for w in c["windows"]} | {f"eps_down{w}": e[w]["down"] for w in c["windows"]}


def put(out, today=None):
    """revision_breadth.js 출력 → breadth.json {asof, rows: {키: 요약}}"""
    c = cfg()
    doc = json.loads(STORE.read_text(encoding="utf-8")) if STORE.exists() else {"rows": {}}
    for k, v in (out.get("out") or {}).items():
        t = today or (_d(v["asOf"]) if v.get("asOf") else date.today())
        res = compute(v.get("rows"), t, c)
        doc["rows"][k] = {"as_of": t.isoformat(), **summary(res, c), "all_b90": res[c["windows"][-1]]["전체"]["b"]}
    doc["asof"] = (today or date.today()).isoformat()
    doc["source"] = out.get("source")
    if out.get("errors"):
        doc["errors"] = out["errors"][-50:]
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(out.get("out") or {})


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if argv and argv[0] == "--code":
        print(TPL.read_text(encoding="utf-8").replace("__KEYS__", json.dumps(argv[1:])))
        return 0
    if len(argv) >= 2 and argv[0] == "--put":
        n = put(json.loads(Path(argv[1]).read_text(encoding="utf-8")))
        print(f"[수정 폭] {n}종목 → {STORE.relative_to(ROOT)}")
        return 0
    if len(argv) >= 2 and argv[0] == "--show":
        dp = json.loads((ROOT / "knowledge" / "models" / "companies" / argv[1] / "datapack.json").read_text(encoding="utf-8"))
        print(json.dumps(blocks(dp), ensure_ascii=False, indent=1))
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
