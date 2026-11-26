"""Chiip Breadth — S&P 500·NASDAQ 100 시장 폭(market breadth) 경보 (마스터 지시 2026-11-26 "경보형으로 구축")

시장 폭 = 지수가 아니라 구성종목 몇 %가 오르고 있나. 지수만 오르고 종목은 빠지는 '좁은 상승'을 먼저 보여 준다.
지표(구성종목 중 비율, %): 52주 신고가·신저가(종가가 직전 251거래일 최고·최저 이상·이하), 20·50·200일 이동평균선 위,
  고점 대비 -30% 밑, 고점 대비 -10% 안, 상승·하락 종목 → 20일 등락비율(20일 상승 합 ÷ 하락 합 × 100).
원천: Fiscal.ai — 구성종목 = ETF 보유 내역(IVV·QQQ, fund_holdings), 일봉 = company_stock_prices. 계산은 Fiscal.ai 실행 환경 안에서 끝내고
  날짜별 비율만 받는다(종목별 주가를 모델 문맥에 싣지 않는다 — 토큰). 지수 선은 FRED(SP500·NASDAQ100).
  결정론 스크립트는 MCP를 못 부르므로 market_regime 섹터와 같은 흐름: --code → execute_code → 결과를 파일로 → --put.
  한계: 현재 구성종목으로 과거를 계산한다(생존 편향) — 그림 각주에 밝힌다.
경보(config/breadth.yaml): 문턱을 '새로 넘은 날'에만 보낸다. 넘지 않은 날은 계산만 하고 보내지 않는다.
저장: radar/inbox/breadth/<spx|ndx>.csv(git 제외). 그림·풀이는 개인 봇으로만.
사용: py radar/breadth.py --code spx [일수]     # execute_code 본문(일수 기본 5, 첫 백필은 130)
      py radar/breadth.py --put spx <파일>       # 실행 결과(JSON 한 줄) 반영 → 경보 판정 출력
      py radar/breadth.py --status              # Pulse 관문 — 갱신 필요(due)·경보 여부
      py radar/breadth.py --chart spx           # 그림
      py radar/breadth.py --send spx "<풀이>"    # 경보가 있을 때만 그림 1장 + 풀이
"""
import csv
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

CFG = "config/breadth.yaml"
OUT = common.ROOT / "radar" / "inbox" / "breadth"
STATE = "breadth"
COLS = ["nh", "nl", "a20", "a50", "a200", "adv", "dec", "dd30", "near10", "cov"]
INK, MUT, GRID = (0.05, 0.05, 0.05), (0.4, 0.4, 0.4), (0.9, 0.91, 0.93)
RED, BLUE, GREEN, ORANGE, PURPLE = (0.78, 0.33, 0.36), (0.33, 0.47, 0.72), (0.18, 0.55, 0.45), (0.80, 0.52, 0.20), (0.55, 0.40, 0.70)

# 출력에 '500'·'503' 같은 수가 단독으로 나오면 커넥터 감시 훅이 서버 오류로 오인한다 — 모든 값은 비율(소수 한 자리)로만 낸다
CODE = """async () => {
const ETF="%(etf)s", D=%(days)d, L=D+260;
const h=await codemode.fund_holdings({ticker:ETF,pageSize:700});
const ks=[...new Set(h.data.filter(x=>x.assetCategory==="equity"&&x.security&&x.security.companyKey).map(x=>x.security.companyKey))];
const agg={}; let used=0;
const run=async k=>{try{const p=await codemode.company_stock_prices({companyKey:k});
 const r=(p.prices||[]).slice(0,L).reverse(); if(r.length<30)return; used++;
 const c=r.map(x=>x.closePrice), n=c.length, ps=[0]; for(const v of c)ps.push(ps[ps.length-1]+v);
 for(let i=Math.max(1,n-D);i<n;i++){const a=agg[r[i].date]||(agg[r[i].date]=[0,0,0,0,0,0,0,0,0,0]); a[0]++;
  const lo=Math.max(0,i-251); let mx=-1e18,mn=1e18; for(let j=lo;j<i;j++){if(c[j]>mx)mx=c[j]; if(c[j]<mn)mn=c[j];}
  if(i-lo>=200){if(c[i]>=mx)a[1]++; if(c[i]<=mn)a[2]++;}
  [20,50,200].forEach((w,q)=>{if(i+1>=w&&c[i]>(ps[i+1]-ps[i+1-w])/w)a[3+q]++;});
  if(c[i]>c[i-1])a[6]++; else if(c[i]<c[i-1])a[7]++;
  const hi=Math.max(mx,c[i]); if(c[i]<=0.7*hi)a[8]++; if(c[i]>=0.9*hi)a[9]++;}}catch(e){}};
for(let i=0;i<ks.length;i+=6)await Promise.all(ks.slice(i,i+6).map(run));
const f=v=>Math.round(v*10)/10;
console.log(JSON.stringify({etf:ETF,cover:f(100*used/ks.length),rows:Object.keys(agg).sort().filter(d=>agg[d][0]>=0.8*used).map(d=>{const a=agg[d];return [d,...a.slice(1).map(v=>f(100*v/a[0])),f(100*a[0]/used)];})}));
}"""


def cfg():
    return common.load_yaml(CFG)


def code(idx, days=5):
    return CODE % {"etf": cfg()["indices"][idx]["etf"], "days": int(days)}


def path(idx):
    return OUT / f"{idx}.csv"


def read(idx):
    p = path(idx)
    if not p.exists():
        return []
    with p.open(encoding="utf-8", newline="") as f:
        return [{"date": r["date"], **{k: float(r[k]) for k in COLS if r.get(k) not in ("", None)}} for r in csv.DictReader(f)]


def put(idx, payload):
    """실행 결과 JSON → 이력에 합친다(같은 날짜는 새 값). 반환: 합친 뒤 행 수"""
    d = json.loads(payload) if isinstance(payload, str) else payload
    best = {r["date"]: r for r in read(idx)}
    for row in d["rows"]:
        best[row[0]] = {"date": row[0], **dict(zip(COLS, row[1:]))}
    OUT.mkdir(parents=True, exist_ok=True)
    with path(idx).open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, ["date"] + COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(best.values(), key=lambda r: r["date"]))
    st = common.load_state(STATE, {})
    st.setdefault(idx, {})["cover"] = d.get("cover")
    common.save_state(STATE, st)
    return len(best)


def ad20(rows):
    """20일 등락비율 — 날짜별 [(date, 값)]"""
    out = []
    for i in range(19, len(rows)):
        a = sum(r["adv"] for r in rows[i - 19:i + 1])
        b = sum(r["dec"] for r in rows[i - 19:i + 1])
        out.append((rows[i]["date"], round(100 * a / b, 1) if b else None))
    return out


def index_series(idx, since):
    import market_regime
    return [(d, v) for d, v in market_regime.fetch_series(cfg()["indices"][idx]["fred"], since)]


def _raw(rows, index, a):
    """마지막 날 문턱을 새로 넘은 것 — {종류: 문장}"""
    t, y = rows[-1], rows[-2]
    out = {}
    if (y["a200"] - a["ma200_cross"]) * (t["a200"] - a["ma200_cross"]) < 0:
        out["ma200"] = f"200일선 위 종목 {y['a200']:.0f}% → {t['a200']:.0f}% — {a['ma200_cross']}% {'상향' if t['a200'] > y['a200'] else '하향'} 돌파"
    ad = ad20(rows)
    if len(ad) >= 2 and ad[-1][1] is not None and ad[-2][1] is not None:
        if ad[-1][1] < a["ad20_low"] <= ad[-2][1]:
            out["ad_low"] = f"20일 등락비율 {ad[-1][1]:.0f} — {a['ad20_low']} 아래 진입(하락 종목 우위)"
        if ad[-1][1] > a["ad20_high"] >= ad[-2][1]:
            out["ad_high"] = f"20일 등락비율 {ad[-1][1]:.0f} — {a['ad20_high']} 위 진입(과열)"
    if t["nl"] >= a["new_low_pct"] > y["nl"]:
        out["nl"] = f"52주 신저가 종목 {t['nl']:.1f}% — {a['new_low_pct']}% 넘음"
    if len(rows) >= 6 and t["dd30"] - rows[-6]["dd30"] >= a["dd30_jump_pp"] and not (len(rows) >= 7 and y["dd30"] - rows[-7]["dd30"] >= a["dd30_jump_pp"]):
        out["dd30"] = f"고점 대비 -30% 밑 종목 5일 새 {rows[-6]['dd30']:.0f}% → {t['dd30']:.0f}%"
    if index:
        def near(day):
            px = [v for d, v in index if d <= day][-252:]
            return bool(px) and px[-1] >= max(px) * (1 - a["diverge_index_gap"] / 100)
        if near(t["date"]) and t["a200"] < a["diverge_ma200_max"] and not (near(y["date"]) and y["a200"] < a["diverge_ma200_max"]):
            out["diverge"] = f"지수는 52주 고점 {a['diverge_index_gap']:.0f}% 안인데 200일선 위 종목 {t['a200']:.0f}% — 좁은 상승"
    return out


def alerts(idx, rows=None, index=None):
    """마지막 날 새로 넘은 문턱 — [문장]. 같은 종류가 직전 cooldown 거래일 안에 울렸으면 다시 울리지 않는다(경보 남발 방지)"""
    a = cfg()["alerts"]
    rows = rows if rows is not None else read(idx)
    if len(rows) < 25:
        return []
    now = _raw(rows, index, a)
    cd = a.get("cooldown_days", 10)
    for k in range(1, cd + 1):
        if len(rows) - k < 25 or not now:
            break
        for key in _raw(rows[:-k], index, a):
            now.pop(key, None)
    return list(now.values())


def last_us_session(now=None):
    """한국 시각 기준 마지막으로 마감한 미국 정규장 날짜(주말만 거른다 — 휴장일은 Fiscal 결과에 그날 행이 없어 자연히 걸러진다)"""
    now = now or common.now_kst()
    d = (now - timedelta(hours=7)).date() - timedelta(days=1)   # 한국 07시 전이면 전전날까지
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def status(now=None):
    """Pulse 관문 — {idx: {due, code}}. 마지막 마감일 행이 없으면 due(백필이 안 됐으면 130일 코드)"""
    out, last = {}, last_us_session(now).isoformat()
    st = common.load_state(STATE, {})
    for idx in cfg()["indices"]:
        rows = read(idx)
        have = rows[-1]["date"] if rows else ""
        tried = (st.get(idx) or {}).get("tried") == last
        due = have < last and not tried
        out[idx] = {"due": due, "have": have, "want": last, "code_cmd": f"py radar/breadth.py --code {idx} {5 if len(rows) >= 100 else cfg()['days_chart'] + 30}"}
    return out


def mark_tried(idx, now=None):
    """오늘 회차에 이미 실행했다(휴장·자료 지연이어도 같은 날 다시 부르지 않는다)"""
    st = common.load_state(STATE, {})
    st.setdefault(idx, {})["tried"] = last_us_session(now).isoformat()
    common.save_state(STATE, st)


# ---------- 그림 ----------
def _axes(page, box, lo, hi, ticks, fmt, right=False, x=None):
    from memory_spot import _txt
    x0, y0, x1, y1 = box
    page.draw_rect(box, color=None, fill=(0.975, 0.978, 0.985))
    Y = lambda v: y1 - (y1 - y0) * (v - lo) / ((hi - lo) or 1)   # noqa: E731
    for v in ticks:
        page.draw_line((x0, Y(v)), (x1, Y(v)), color=GRID, width=0.5)
        _txt(page, ((x1 + 4) if right else (x0 - 4), Y(v) + 3), fmt(v), 7, MUT, right=not right)
    return Y


def chart(idx, today=None, p=None):
    import pymupdf
    from memory_spot import _txt
    c = cfg()
    name = c["indices"][idx]["name"]
    rows_all = read(idx)
    rows = rows_all[-c["days_chart"]:]
    if len(rows) < 25:
        raise SystemExit("이력 부족 — 백필 먼저(--code <idx> 160 → --put)")
    d0, d1 = date.fromisoformat(rows[0]["date"]), date.fromisoformat(rows[-1]["date"])
    try:
        idxs = [(date.fromisoformat(d), v) for d, v in index_series(idx, d0 - timedelta(days=400))]
    except Exception:
        idxs = []
    adm = dict(ad20(rows_all))
    doc = pymupdf.open()
    page = doc.new_page(width=760, height=760)
    page.draw_rect(page.rect, color=None, fill=(1, 1, 1))
    _txt(page, (40, 30), "MARKET BREADTH MONITOR", 7.5, MUT)
    _txt(page, (40, 50), f"시장 폭 추이 — {name}", 15, INK)
    _txt(page, (720, 30), f"{d1.isoformat()} 기준", 8, MUT, right=True)
    st = common.load_state(STATE, {})
    _txt(page, (720, 46), f"최근 약 2분기 · 구성종목 커버 {(st.get(idx) or {}).get('cover') or '미확인'}%", 7.5, MUT, right=True)
    L, R = 70, 690
    n = len(rows)
    X = lambda i: L + (R - L) * (i + 0.5) / n   # noqa: E731
    dates = [date.fromisoformat(r["date"]) for r in rows]

    def xlabels(y):
        last = None
        for i, d in enumerate(dates):
            if d.month != last and d.day <= 7:
                _txt(page, (X(i) - 10, y + 11), f"{d.year % 100}.{d.month:02d}", 7, MUT)
                last = d.month

    def line(pts, Y, color, w=1.2):
        pts = [pymupdf.Point(X(i), Y(v)) for i, v in pts if v is not None]
        if len(pts) > 1:
            page.draw_polyline(pts, color=color, width=w)

    def legend(y, items):
        x = (L + R) / 2 - 60 * len(items) / 2
        for lab, col in items:
            page.draw_rect((x, y - 6, x + 9, y), color=None, fill=col)
            _txt(page, (x + 12, y), lab, 7, MUT)
            x += 75

    # 01 신고가·신저가 — 막대(비율), 지수 선(오른쪽 축)
    _txt(page, (40, 80), "01  52주 신고가·신저가 (구성종목 중 %)", 9, INK)
    top = max(max(r["nh"] for r in rows), max(r["nl"] for r in rows), 5) * 1.1
    b = (L, 90, R, 230)
    Y = _axes(page, b, -top, top, [-top / 2, 0, top / 2], lambda v: f"{v:.0f}")
    bw = (R - L) / n * 0.7
    for i, r in enumerate(rows):
        page.draw_rect((X(i) - bw / 2, Y(r["nh"]), X(i) + bw / 2, Y(0)), color=None, fill=RED)
        page.draw_rect((X(i) - bw / 2, Y(0), X(i) + bw / 2, Y(-r["nl"])), color=None, fill=BLUE)
    sel = [(dates.index(d), v) for d, v in idxs if d in dates]
    if sel:
        lo, hi = min(v for _, v in sel), max(v for _, v in sel)
        pad = (hi - lo) * 0.1 or 1
        YI = _axes(page, (R, 90, R, 230), lo - pad, hi + pad, [lo, (lo + hi) / 2, hi], lambda v: f"{v:,.0f}", right=True)
        line(sel, YI, INK, 1.3)
    legend(245, [("신고가", RED), ("신저가", BLUE), (name, INK)])
    # 02 하락 심도·고점 근처
    _txt(page, (40, 275), "02  고점 대비 -30% 밑 · 고점 -10% 안 비율", 9, INK)
    Y = _axes(page, (L, 285, R, 395), 0, 100, [0, 25, 50, 75, 100], lambda v: f"{v:.0f}%")
    line([(i, r["dd30"]) for i, r in enumerate(rows)], Y, RED)
    line([(i, r["near10"]) for i, r in enumerate(rows)], Y, BLUE)
    _txt(page, (R + 4, Y(rows[-1]["near10"]) + 3), f"{rows[-1]['near10']:.1f}%", 7.5, BLUE)
    _txt(page, (R + 4, Y(rows[-1]["dd30"]) + 3), f"{rows[-1]['dd30']:.1f}%", 7.5, RED)
    legend(410, [("-30% 밑", RED), ("고점 -10% 안", BLUE)])
    # 03 이동평균선 위
    _txt(page, (40, 440), "03  이동평균선 위 종목 비율", 9, INK)
    Y = _axes(page, (L, 450, R, 560), 0, 100, [0, 20, 50, 80, 100], lambda v: f"{v:.0f}%")
    for k, col in (("a20", GREEN), ("a50", ORANGE), ("a200", PURPLE)):
        line([(i, r[k]) for i, r in enumerate(rows)], Y, col)
    _txt(page, (R + 4, Y(rows[-1]["a200"]) + 3), f"{rows[-1]['a200']:.0f}%", 7.5, PURPLE)
    legend(575, [("20일선", GREEN), ("50일선", ORANGE), ("200일선", PURPLE)])
    # 04 20일 등락비율
    _txt(page, (40, 605), "04  등락비율 (20일)", 9, INK)
    vals = [adm.get(r["date"]) for r in rows]
    hi = max([v for v in vals if v] + [150])
    Y = _axes(page, (L, 615, R, 705), 0, hi, [0, 50, 100, 150], lambda v: f"{v:.0f}")
    page.draw_line((L, Y(100)), (R, Y(100)), color=MUT, width=0.5, dashes="[2] 0")
    line(list(enumerate(vals)), Y, INK)
    xlabels(705)
    _txt(page, (40, 740), f"대상: {name} 구성종목(ETF {c['indices'][idx]['etf']} 보유 내역, 현재 명단으로 과거 계산 — 생존 편향). 신고가·신저가 = 종가가 직전 251거래일 최고·최저 이상·이하. "
         "자료: Fiscal.ai·FRED", 6.5, MUT)
    OUT.mkdir(parents=True, exist_ok=True)
    p = Path(p or OUT / f"{idx}_{d1.strftime('%Y%m%d')}.png")
    page.get_pixmap(dpi=150).save(str(p))
    return p


def summary(idx):
    rows = read(idx)
    if not rows:
        return {}
    t = rows[-1]
    ad = ad20(rows)
    return {"date": t["date"], "nh": t["nh"], "nl": t["nl"], "a20": t["a20"], "a50": t["a50"], "a200": t["a200"], "dd30": t["dd30"], "near10": t["near10"],
            "ad20": ad[-1][1] if ad else None}


def caption(idx, al, read_=""):
    s = summary(idx)
    name = cfg()["indices"][idx]["name"]
    lines = [f"[Chiip Breadth] {name} 시장 폭 경보 — {s.get('date')}"] + [f"· {a}" for a in al]
    lines.append(f"200일선 위 {s['a200']:.0f}% · 20일 등락비율 {s['ad20'] or 0:.0f} · 신고가 {s['nh']:.1f}% / 신저가 {s['nl']:.1f}%")
    if read_.strip():
        lines += ["", read_.strip()]
    return "\n".join(lines)


def send(idx, read_=""):
    import notify
    try:
        index = index_series(idx, date.today() - timedelta(days=400))
    except Exception:
        index = None
    al = alerts(idx, index=index)
    if not al:
        print("경보 없음 — 보내지 않는다")
        return False
    return notify.send_photo(chart(idx), caption(idx, al, read_)[:1000], "P1")


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if argv[:1] == ["--code"]:
        print(code(argv[1], int(argv[2]) if len(argv) > 2 else 5))
    elif argv[:1] == ["--put"]:
        n = put(argv[1], Path(argv[2]).read_text(encoding="utf-8").strip())
        mark_tried(argv[1])
        try:
            index = index_series(argv[1], date.today() - timedelta(days=400))
        except Exception:
            index = None
        al = alerts(argv[1], index=index)
        print(json.dumps({"rows": n, "last": summary(argv[1]), "alerts": al}, ensure_ascii=False))
    elif argv[:1] == ["--status"]:
        print(json.dumps(status(), ensure_ascii=False))
    elif argv[:1] == ["--chart"]:
        print(chart(argv[1]))
    elif argv[:1] == ["--send"]:
        print("[Breadth] 발송" if send(argv[1], " ".join(argv[2:])) else "[Breadth] 보내지 않음")
    else:
        print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
