"""Weekly Review 'Nebius GPU 렌털료 추이' 고정 블록 (마스터 지시 2026-11-13 "Weekly Review에 네비우스 GPU 렌탈료 추이도 넣도록 해라")

숫자는 모두 여기서 계산한다(모델은 읽기 한 줄 d["gpu_read"]만, 없어도 된다). 원천 knowledge/models/gpu_rental.csv(radar/gpu_rental.py, 6시간마다).
  Nebius GPU별 온디맨드·선점형 시작가($/GPU·시) — 기준일 값, 전주(7일 전 이전 마지막 값) 대비, 추적 시작 대비. 바뀌지 않았으면 '변화 없음'.
  비교 줄: CoreWeave 온디맨드·스팟, Lambda 온디맨드(8x, 11-16 새 가격표 시행 전후 구분), Silicon Data 지수(인용), Nebius 온디맨드 ÷ 지수 괴리.
  값이 없거나 단위를 맞출 수 없으면 '비교 불가'(NVL72 랙 '문의' 등). 추이 그림은 주간 종가(주의 마지막 값) — 2주가 안 되면 일별 점과 '추적 n일치'.
"""
import csv
import html
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CSV = ROOT / "knowledge" / "models" / "gpu_rental.csv"
GPUS = ["H100", "H200", "B200", "B300", "GB200", "GB300", "L40S", "RTX PRO 6000"]
NA = "비교 불가"


def _rows(path=CSV):
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return [r for r in csv.DictReader(f) if r.get("date")]


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _series(rows, provider, gpu, pick):
    """{날짜: 값} — 같은 날 여러 행이면 pick(행) 이 참인 것 중 가장 낮은 값(L40S는 CPU 구성이 둘)"""
    out = {}
    for r in rows:
        if r["provider"] == provider and r["gpu"] == gpu and pick(r):
            v = _num(r["usd_per_gpu_hr"])
            if v is not None:
                out[r["date"]] = min(v, out.get(r["date"], v))
    return out


def _at(s, day):
    ks = [k for k in sorted(s) if k <= day]
    return (ks[-1], s[ks[-1]]) if ks else (None, None)


def _chg(now, then):
    if now is None or then is None:
        return None
    return 0.0 if abs(now - then) < 1e-9 else (now / then - 1) * 100


def build(as_of, rows=None):
    rows = rows if rows is not None else _rows()
    day = str(as_of)[:10]
    prev_day = (date.fromisoformat(day) - timedelta(days=7)).isoformat()
    od = lambda r: r["term"].startswith("온디맨드")
    pre = lambda r: r["term"].startswith("선점형")
    out = []
    for g in GPUS:
        s_od, s_pre = _series(rows, "Nebius", g, od), _series(rows, "Nebius", g, pre)
        d_now, now = _at(s_od, day)
        _, wk = _at(s_od, prev_day)
        first = s_od[min(s_od)] if s_od else None
        _, pnow = _at(s_pre, day)
        _, cw = _at(_series(rows, "CoreWeave", g, od), day)
        _, cws = _at(_series(rows, "CoreWeave", g, lambda r: r["term"] == "스팟"), day)
        lam_new = _series(rows, "Lambda", g, lambda r: od(r) and "8x" in r["config"] and "시행" in r["term"])
        lam_old = _series(rows, "Lambda", g, lambda r: od(r) and "8x" in r["config"] and "시행" not in r["term"])
        _, lo = _at(lam_old, day)
        _, ln = _at(lam_new, day)
        _, idx = _at(_series(rows, "Silicon Data 지수", g, lambda r: True), day)
        out.append({"gpu": g, "od": now, "pre": pnow, "wk": _chg(now, wk), "since": _chg(now, first), "start": min(s_od) if s_od else None,
                    "cw": cw, "cw_spot": cws, "lambda": lo, "lambda_new": ln, "index": idx, "gap": _chg(now, idx),
                    "trend": _weekly(s_od, day)})
    pres = [r["pre"] for r in out if r["pre"] is not None]
    pre_bad = len(pres) >= 4 and len(set(pres)) * 2 <= len(pres)   # 서로 다른 GPU가 같은 '시작가' — 가격표 공통 문구를 읽은 것으로 보인다(2026-11-13: H100~RTX PRO 6000 모두 $0.79·$0.99)
    if pre_bad:
        for r in out:
            r["pre"] = None
    days = sorted({r["date"] for r in rows if r["provider"] == "Nebius" and r["date"] <= day})
    return {"as_of": day, "rows": out, "days": len(days), "start": days[0] if days else None, "pre_bad": pre_bad,
            "changed": [r["gpu"] for r in out if r["wk"] not in (None, 0.0)]}


def _weekly(s, day):
    """주간 종가(ISO 주의 마지막 값). 2주가 안 되면 일별 값 그대로"""
    pts = sorted((k, v) for k, v in s.items() if k <= day)
    wk = {}
    for k, v in pts:
        y, w, _ = date.fromisoformat(k).isocalendar()
        wk[(y, w)] = (k, v)
    return list(wk.values()) if len(wk) >= 2 else pts


def _usd(v):
    return f"${v:.2f}" if v is not None else NA


def _pc(v, none="-"):
    if v is None:
        return none
    return "변화 없음" if v == 0 else f"{v:+.1f}%"


def _lam(r):
    if r["lambda"] is None and r["lambda_new"] is None:
        return NA
    return " → ".join(x for x in (_usd(r["lambda"]) if r["lambda"] is not None else "", f"{_usd(r['lambda_new'])}(11-16 시행)" if r["lambda_new"] is not None else "") if x)


def _head(b):
    ch = "바뀐 GPU " + ", ".join(b["changed"]) if b["changed"] else "이번 주 Nebius 정가 변화 없음"
    return f"{ch} · 추적 {b['start']}부터 {b['days']}일치" + (" — 첫 회는 추세가 아니라 기준선" if b["days"] < 8 else "")


def md_lines(d, rows=None):
    b = build(d.get("gpu_as_of") or d["as_of"], rows)
    if not b["days"]:   # 추적(2026-11-10) 전 주차는 절을 넣지 않는다
        return []
    L = ["", "## Nebius GPU 렌털료 추이", "", _head(b), ""]
    if d.get("gpu_read"):
        L += [d["gpu_read"], ""]
    L += ["| GPU | Nebius 온디맨드 | 선점형 시작가 | 전주 대비 | 추적 시작 대비 | CoreWeave 온디맨드·스팟 | Lambda 온디맨드 | Silicon Data 지수 | Nebius ÷ 지수 |",
          "|---|---|---|---|---|---|---|---|---|"]
    for r in b["rows"]:
        L.append(f"| {r['gpu']} | {_usd(r['od'])} | {_usd(r['pre'])} | {_pc(r['wk'], '기록 전')} | {_pc(r['since'])} | {_usd(r['cw'])} · {_usd(r['cw_spot'])} | {_lam(r)} | {_usd(r['index'])} | {_pc(r['gap']) if r['gap'] not in (None, 0.0) else ('-' if r['gap'] is None else '같음')} |")
    L += ["", "단위 $/GPU·시. 랙 단위(NVL72)·'문의'는 비교 불가. L40S는 CPU 구성 중 낮은 값. Silicon Data는 공개 지수 카드 인용. Nebius ÷ 지수 = 정가가 시장 지수보다 몇 % 비싼가."
          + (" 선점형 시작가는 GPU마다 같은 값으로 읽혀 수집 점검 전까지 비교 불가로 둔다." if b["pre_bad"] else "")]
    return L


def _spark(pts, w=96, h=22):
    vs = [v for _, v in pts]
    if len(vs) < 2:
        return ""
    lo, hi = min(vs), max(vs)
    span = (hi - lo) or 1
    xy = " ".join(f"{i * (w - 4) / (len(vs) - 1) + 2:.1f},{h - 3 - (v - lo) / span * (h - 6) if hi != lo else h / 2:.1f}" for i, v in enumerate(vs))
    return f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="추이"><polyline points="{xy}" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>'


def html_section(d, rows=None):
    b = build(d.get("gpu_as_of") or d["as_of"], rows)
    if not b["days"]:
        return ""
    e = html.escape
    tr = "".join(f"<tr><td>{e(r['gpu'])}</td><td>{_usd(r['od'])}</td><td>{_usd(r['pre'])}</td><td>{_pc(r['wk'], '기록 전')}</td><td>{_pc(r['since'])}</td>"
                 f"<td>{_usd(r['cw'])} · {_usd(r['cw_spot'])}</td><td>{e(_lam(r))}</td><td>{_usd(r['index'])}</td>"
                 f"<td>{_pc(r['gap']) if r['gap'] not in (None, 0.0) else ('-' if r['gap'] is None else '같음')}</td><td>{_spark(r['trend'])}</td></tr>" for r in b["rows"])
    read = f"<p>{e(d['gpu_read'])}</p>" if d.get("gpu_read") else ""
    return (f'<section><h2>Nebius GPU 렌털료 추이</h2><p class="k">{e(_head(b))}</p>{read}<div class="tw"><table><tr><th>GPU</th><th>Nebius 온디맨드</th><th>선점형 시작가</th>'
            f'<th>전주 대비</th><th>추적 시작 대비</th><th>CoreWeave 온디맨드·스팟</th><th>Lambda 온디맨드</th><th>Silicon Data 지수</th><th>Nebius ÷ 지수</th><th>추이</th></tr>{tr}</table></div>'
            f'<p class="note">단위 $/GPU·시. 랙 단위(NVL72)·문의는 비교 불가. L40S는 CPU 구성 중 낮은 값. 추이는 주간 종가, 2주 전에는 일별 값. Silicon Data는 공개 지수 카드 인용.'
            + (" 선점형 시작가는 GPU마다 같은 값으로 읽혀 수집 점검 전까지 비교 불가로 둔다." if b["pre_bad"] else "") + '</p></section>')
