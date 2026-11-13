"""텐배거 리포트 'P·Q 사이클' 절 (마스터 지시 2026-11-03 "이 기업이 구조적인 Q사이클과 구조적인 P사이클 중 어떤 사이클에 직면해 있고
앞으로 몇 분기가 지나면 다른 사이클로 전환하는지 그래프로 시각화하고 P와 Q사이클의 정도를 정량화하라")

매출 = P(가격) × Q(물량). 전년 대비 로그 증가율로 나눈다: g_매출 = g_P + g_Q. 숫자는 여기서 계산하고 모델은 가격·물량 근거만 고른다.
datapack "pq":
  {"why": "이 회사 가격·물량을 무엇으로 재는가 한 줄",
   "price": {"source": "asp", "series": {"2025-09-27": 12.4, …}, "unit": "$/개"}          # 회사 공시 ASP(분기 끝 날짜 → 값)
          | {"source": "ppi", "input": "pcb", "country": "us"}                             # 제품 PPI(config/trade_ppi.yaml)를 가격 대용
   "volume": {"series": {"2025-09-27": 1.2, …}, "unit": "백만 개"}}                         # 선택 — 출하량을 공시하면 P = 매출 ÷ 물량
  가격·물량을 잴 수 없으면 {"none": "이유"}.
매출은 datapack "quarters_hist"(scripts/tenbagger/quarters.py).

정량화(IB 사이클 분석 방식):
- 국면: 최근 4분기 평균 g_P·g_Q로 P 사이클(g_P > g_Q, g_P > 0) / Q 사이클(g_Q > g_P, g_Q > 0) / 동반 하강.
- 강도(0~10): 자기 이력 대비 z값 → 5 + 2z(0~10으로 자른다). 구조성: 최근 8분기 중 같은 요인이 우세했던 비율.
- 마진 확인: P 사이클인데 GPM이 오르지 않으면 원가 전가형(가짜 P)으로 표시한다.
- 전환 시점: g_P·g_Q 8분기 전망(pq_forecast — BIC 차수 AR + 물량은 컨센서스 결합)에서 우세 요인이 처음 바뀌는 분기를 센다.
  고른 차수가 AR(2)이고 특성근이 복소수면 고유 주기 2π ÷ arccos(a1 ÷ 2√−a2)도 낸다. 모형 산출이며 가이던스가 아니다.

10년 위치·프리미엄(마스터 지시 2026-11-04 "P사이클과 Q사이클의 과거 10개 년도 차트 … 어느 시점에 있는지 … P·Q 프리미엄 −100~+100% … 전망",
상수 config/pq_cycle.yaml, 등록부 prm-pq-*):
- 레벨: P = 가격 지수 4분기 평균, Q = TTM 매출 ÷ P(계절성을 TTM으로 지운다). 추세 = 로그 레벨의 HP 필터(λ 1600) → 갭 = 로그(레벨 ÷ 추세).
- 위치: 갭 부호 × 최근 2분기 방향으로 사이클 시계(회복·확장·둔화·수축), 10년 분위.
- 기업 유형: 10년 매출 갭 분산 중 P 갭 몫(분산 분해) — 0.5 이상이면 P형, 아니면 Q형.
- 프리미엄(IB 정상화 이익 방식, mid-cycle normalization): 지금 매출총이익이 추세 수준(정상) 대비 얼마나 부풀었나를 요인별로 나눈다.
    Q 프리미엄 = (e^gQ − 1) × 물량 증분 마진 ÷ 정상 GPM,  P 프리미엄 = e^gQ × (e^gP − 1) × 가격 전가율 ÷ 정상 GPM, ±100%에서 자른다.
    정상 GPM = 10년 GPM 중앙값, 물량 증분 마진 = 전년 대비 ΔGP ÷ ΔRev 회귀 기울기(정상 GPM의 1~2배로 자른다). GP가 없으면 매출 기준.
    +면 이익이 사이클 덕에 정상보다 높다(피크 이익에 높은 멀티플을 주면 이중 계산 — IB는 정상 이익에 멀티플을 건다), −면 정상보다 낮다.
- 전망(2026-11-08 재설계, pq_forecast 맨 위): 가격 갭 AR(p)·물량은 통계 갭과 컨센서스 내포 물량의 분산 역수 결합 → 전망 연장 HP로 끝점 편향 보정
  → 4·8분기 뒤 갭·80% 범위·프리미엄, 갭이 절반이 되는 분기(반감기). 구조 단절(분리·재작성)은 datapack pq.breaks 또는 자동 감지로 그 뒤만 쓴다.
- 가격 근거가 없으면(pq 없음·none) datapack industry → 업종 PPI(FRED) 대용으로 잰다. 회사 판매가가 아니라고 표시한다.
"""
import json
import math
import sys
from pathlib import Path

import yaml

import pq_forecast as F
from pq_forecast import Z80
import sync_view as sv

UNKNOWN = "미확인"
MIN_POINTS = 8
HORIZON = 8
ROOT = Path(__file__).resolve().parents[2]
CFG = ROOT / "config" / "pq_cycle.yaml"
FRED_CACHE = ROOT / "knowledge" / "models" / "pq" / "fred.json"
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv"


def cfg():
    return yaml.safe_load(CFG.read_text(encoding="utf-8"))


def fred_monthly(sid, cache=None, fetch=True):
    """FRED 월 시계열 {YYYY-MM: 값}. 캐시에 없으면 공개 CSV를 받아 저장한다"""
    store = cache if cache is not None else (json.loads(FRED_CACHE.read_text(encoding="utf-8")) if FRED_CACHE.exists() else {})
    if sid not in store and fetch and cache is None:
        sys.path.insert(0, str(ROOT / "radar"))
        from pollers import common
        txt = common.http_get(FRED, {"id": sid}, timeout=30).decode("utf-8", "replace")
        s = {}
        for line in txt.splitlines()[1:]:
            d, _, v = line.partition(",")
            try:
                s[d[:7]] = float(v)
            except ValueError:
                pass
        if s:
            store[sid] = s
            FRED_CACHE.parent.mkdir(parents=True, exist_ok=True)
            FRED_CACHE.write_text(json.dumps(store, ensure_ascii=False), encoding="utf-8")
    return store.get(sid) or {}


def price_basis(dp, c=None):
    """(가격 근거 dict, 대용 여부, 설명) — datapack pq가 없거나 none이면 업종 PPI 대용"""
    pq = dp.get("pq") or {}
    if pq and not pq.get("none") and (pq.get("price") or pq.get("volume")):
        return pq, False, None
    c = c or cfg()
    # 회사별 가격 지수가 업종 대용보다 먼저(2026-11-11 점검) — 업종 PPI가 그 회사의 '판매 가격'이 아닐 때가 있다:
    # 메모리 회사에 미국 반도체 PPI(로직 중심, 전년비 −2%)를 쓰면 D램 가격 급등(한국 D램 PPI +418%)이 전부 물량으로 잡히고,
    # 위탁생산(EMS)에 인쇄회로기판 PPI를 쓰면 원가가 가격으로 잡혀 물량이 줄어든다는 전망이 나온다. P = 그 회사가 파는 물건의 가격이어야 한다
    e = (c.get("price_by_entity") or {}).get(dp.get("entity_id") or dp.get("id"))
    if e:
        if e.get("source") == "ppi":
            return {"price": {"source": "ppi", "input": e["input"], "country": e["country"]}}, True, e["label"]
        return {"price": {"source": "fred", "series": e["series"]}}, True, e["label"]
    m = (c.get("fred_by_industry") or {}).get(dp.get("industry"))
    if not m:
        return None, True, None
    return {"price": {"source": "fred", "series": m["series"]}}, True, m["label"]


def _quarterly(series):
    out = {}
    for d, v in (series or {}).items():
        if v:
            out[sv.qlabel(str(d))[0]] = float(v)
    return out


def price_monthly(pq, history=None, db=sv.HS_DB, fred_cache=None):
    """가격 근거가 월간 지수(PPI·FRED)면 {YYYY-MM: 값}, 아니면 None — 나우캐스트(pq_forecast ⑦)용"""
    pr = (pq or {}).get("price") or {}
    if (pq or {}).get("volume"):
        return None
    if pr.get("source") == "ppi":
        return sv.monthly({"source": "ppi", "input": pr["input"], "country": pr["country"]}, history, db)
    if pr.get("source") == "fred":
        return fred_monthly(pr["series"], fred_cache)
    return None


def levels(dp, pq=None, history=None, db=sv.HS_DB, fred_cache=None):
    """분기 라벨 → 매출·가격·GPM·GP"""
    pq = pq if pq is not None else dp["pq"]
    qs = [r for r in (dp.get("quarters_hist") or {}).get("q") or [] if r.get("rev")]
    rev, ends, gpm, gpv = {}, {}, {}, {}
    for r in qs:
        lab, ym = sv.qlabel(r["period"])
        rev[lab], ends[lab] = float(r["rev"]), ym
        gp = r.get("gp") if r.get("gp") is not None else (r["rev"] - r["cogs"] if r.get("cogs") is not None else None)
        if gp is not None:
            gpm[lab], gpv[lab] = gp / r["rev"], float(gp)
    vol = _quarterly((pq.get("volume") or {}).get("series"))
    pr = pq.get("price") or {}
    if vol:
        price = {q: rev[q] / vol[q] for q in rev if vol.get(q)}
    elif pr.get("source") == "asp":
        price = _quarterly(pr.get("series"))
    elif pr.get("source") == "ppi":
        price = sv.quarterize(sv.monthly({"source": "ppi", "input": pr["input"], "country": pr["country"]}, history, db), ends, True)
    elif pr.get("source") == "fred":
        price = sv.quarterize(fred_monthly(pr["series"], fred_cache), ends, True)
    else:
        price = {}
    return rev, price, gpm, gpv


def decompose(dp, history=None, db=sv.HS_DB, pq=None, fred_cache=None):
    rev, price, gpm, _ = levels(dp, pq, history, db, fred_cache)
    rows = []
    for q in sorted(rev):
        b = sv.shift_q(q, -4)
        if b in rev and q in price and b in price and price[b] and rev[b]:
            gr, gp_ = math.log(rev[q] / rev[b]), math.log(price[q] / price[b])
            rows.append({"q": q, "g_rev": gr, "g_p": gp_, "g_q": gr - gp_, "gpm": gpm.get(q), "gpm_prev": gpm.get(b)})
    return rows


def ar2(y):
    """(c, a1, a2) 최소제곱 — 정규방정식 3×3"""
    X = [(1.0, y[i - 1], y[i - 2]) for i in range(2, len(y))]
    Y = y[2:]
    A = [[sum(x[i] * x[j] for x in X) for j in range(3)] for i in range(3)]
    b = [sum(x[i] * t for x, t in zip(X, Y)) for i in range(3)]
    for i in range(3):   # 가우스 소거
        p = max(range(i, 3), key=lambda r: abs(A[r][i]))
        A[i], A[p], b[i], b[p] = A[p], A[i], b[p], b[i]
        if abs(A[i][i]) < 1e-12:
            return None
        for r in range(3):
            if r != i:
                f = A[r][i] / A[i][i]
                A[r] = [a - f * c for a, c in zip(A[r], A[i])]
                b[r] -= f * b[i]
    return tuple(b[i] / A[i][i] for i in range(3))


def period(a1, a2):
    if a2 >= 0 or a1 * a1 + 4 * a2 >= 0:
        return None
    x = a1 / (2 * math.sqrt(-a2))
    return 2 * math.pi / math.acos(max(-1.0, min(1.0, x)))


def project(y, coef, n=HORIZON):
    c, a1, a2 = coef
    out, h = [], list(y)
    for _ in range(n):
        v = c + a1 * h[-1] + a2 * h[-2]
        v = max(-1.5, min(1.5, v))   # 로그 증가율 폭주 방지
        out.append(v)
        h.append(v)
    return out


def regime(gp, gq):
    if gp < 0 and gq < 0:
        return "동반 하강"
    return "P 사이클" if gp >= gq else "Q 사이클"


def strength(xs):
    m = sum(xs) / len(xs)
    s = math.sqrt(sum((x - m) ** 2 for x in xs) / max(len(xs) - 1, 1)) or 1
    return max(0.0, min(10.0, 5 + 2 * (sum(xs[-4:]) / len(xs[-4:]) - m) / s))


def compute(dp, history=None, db=sv.HS_DB, pq=None, fred_cache=None):
    rows = decompose(dp, history, db, pq, fred_cache)
    if len(rows) < 4:
        return {"rows": rows, "enough": False}
    gp, gq = [r["g_p"] for r in rows], [r["g_q"] for r in rows]
    mp, mq = sum(gp[-4:]) / 4, sum(gq[-4:]) / 4
    now = regime(mp, mq)
    last8 = rows[-8:]
    dom = "P" if now == "P 사이클" else ("Q" if now == "Q 사이클" else None)
    persist = None if not dom else sum(1 for r in last8 if (r["g_p"] >= r["g_q"]) == (dom == "P")) / len(last8)
    gpm_up = None
    if rows[-1]["gpm"] is not None and rows[-1]["gpm_prev"] is not None:
        gpm_up = rows[-1]["gpm"] - rows[-1]["gpm_prev"]
    out = {"rows": rows, "enough": True, "now": now, "mp": mp, "mq": mq, "p_score": strength(gp), "q_score": strength(gq), "persist": persist, "gpm_chg": gpm_up,
           "fake_p": now == "P 사이클" and gpm_up is not None and gpm_up <= 0, "proj": None, "switch": None, "period": None}
    if len(rows) >= MIN_POINTS:
        fc = cfg().get("forecast") or {}
        # 전년 대비 증가율은 평균이 0이 아니라 절편을 둔다. 4분기 겹친 표본(⑤)·장기 평균 수축(⑥) — pq_forecast 맨 위
        kw = {"pmax": fc.get("ar_pmax", 3), "intercept": True, "max_root": fc.get("max_root", 0.95), "overlap": fc.get("overlap_q", 4), "mean_k": fc.get("mean_prior_k")}
        fp = F.ar_fit(gp, mean_prior=math.log(1 + fc["mean_prior_p"]) if "mean_prior_p" in fc else None, **kw)
        fq = F.ar_fit(gq, mean_prior=math.log(1 + fc["mean_prior_q"]) if "mean_prior_q" in fc else None, **kw)
        if fp and fq:
            rev = levels(dp, pq, history, db, fred_cache)[0]
            last, qs = rows[-1]["q"], sorted(rev)
            # ⑦ 가격 나우캐스트 — 마지막 실적 다음 분기에 이미 나온 월간 가격이 있으면 그 분기 가격 증가율은 관측값
            now_p, n_m = None, 0
            mon = price_monthly(pq or dp.get("pq"), history, db, fred_cache)
            if mon:
                # 회사 분기 끝 달 기준(52·53주 결산 포함) — 달력 분기로 잡으면 10월 결산 종목은 8~10월 대신 10~12월을 봤다(2026-11-14 점검)
                ends = {sv.qlabel(r["period"])[0]: sv.qlabel(r["period"])[1] for r in (dp.get("quarters_hist") or {}).get("q") or [] if r.get("period")}
                y_, m_ = ends.get(last) or (int(last[:4]), int(last[-1]) * 3)
                end = (y_ + (m_ + 3 - 1) // 12, (m_ + 3 - 1) % 12 + 1)
                now_p, n_m = F.nowcast_yoy(mon, end, sv.months_back)
            if now_p is not None:
                pp_, sep_ = F.ar_path(gp + [now_p], fp, HORIZON - 1)
                pp, sep = [now_p] + pp_, [fp["sigma"] * math.sqrt((3 - n_m) / 3)] + [math.sqrt(s * s + (fp["sigma"] ** 2) * (3 - n_m) / 3) for s in sep_]
            else:
                pp, sep = F.ar_path(gp, fp, HORIZON)
            qq, seq = F.ar_path(gq, fq, HORIZON)
            cons, basis = F.consensus_quarters(dp, qs[-1], rev[qs[-1]], sv.shift_q, HORIZON + 4)
            allq = {**cons, **rev}
            proj = []
            for i, (a, b) in enumerate(zip(pp, qq)):
                q, base = sv.shift_q(last, i + 1), sv.shift_q(last, i - 3)
                w = 0.0
                if q in rev and base in allq and allq[base] > 0:   # 가격 지표보다 먼저 나온 실적 분기 — 매출은 관측값, 물량 = 매출 − 가격(2026-11-14 점검: AMAT 4Q 실적을 버리고 AR로만 잡았다)
                    b, w = math.log(rev[q] / allq[base]) - a, 1.0
                    se_q_i = sep[i]
                    proj.append({"q": q, "g_p": a, "g_q": b, "w_cons": w, "se_p": sep[i], "se_q": se_q_i, "actual_rev": True})
                    continue
                if q in allq and base in allq and allq[base] > 0:
                    b, _, w = F.combine(b, seq[i], math.log(allq[q] / allq[base]) - a, math.sqrt(F.cons_se(dp, i + 1, fc) ** 2 + sep[i] ** 2))
                se_q_i = seq[i] if not w else math.sqrt(1 / (1 / max(seq[i], 1e-9) ** 2 + 1 / max(math.sqrt(F.cons_se(dp, i + 1, fc) ** 2 + sep[i] ** 2), 1e-9) ** 2))
                proj.append({"q": q, "g_p": a, "g_q": b, "w_cons": w, "se_p": sep[i], "se_q": se_q_i})
            cur = mp >= mq
            sw = next((i + 1 for i, p in enumerate(proj) if (p["g_p"] >= p["g_q"]) != cur), None)
            per = lambda f: period(f["phi"][0], f["phi"][1]) if f["p"] == 2 else None
            out.update({"proj": proj, "switch": sw, "period": {"P": per(fp), "Q": per(fq)}, "models": (F.ar_name(fp["p"]), F.ar_name(fq["p"])), "cons": basis if cons else None,
                        "nowcast": {"q": proj[0]["q"], "months": n_m} if now_p is not None else None,
                        "means": {"P": (fp["mean_raw"], fp["mean"]), "Q": (fq["mean_raw"], fq["mean"])}})
    return out


def hp(y, lam):
    """HP 필터 추세: (I + λ·D'D)τ = y, D = 2차 차분. 가우스 소거(n ≤ 60)"""
    n = len(y)
    if n < 4:
        return list(y)
    A = [[0.0] * n for _ in range(n)]
    for i in range(n):
        A[i][i] = 1.0
    for k in range(n - 2):
        d = {k: 1.0, k + 1: -2.0, k + 2: 1.0}
        for i, a in d.items():
            for j, b in d.items():
                A[i][j] += lam * a * b
    b = list(y)
    for i in range(n):
        p = max(range(i, n), key=lambda r: abs(A[r][i]))
        A[i], A[p], b[i], b[p] = A[p], A[i], b[p], b[i]
        for r in range(i + 1, n):
            f = A[r][i] / A[i][i]
            if f:
                A[r] = [a - f * c for a, c in zip(A[r], A[i])]
                b[r] -= f * b[i]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = (b[i] - sum(A[i][j] * x[j] for j in range(i + 1, n))) / A[i][i]
    return x


def clock(gap, prev):
    """사이클 시계(OECD 경기 시계 방식): 추세 위·아래 × 최근 방향"""
    up = gap >= prev
    if gap >= 0:
        return "확장" if up else "둔화"
    return "회복" if up else "수축"


def premiums(g_p, g_q, gpm_mid, m_q, c):
    cap = c["premium_cap"]
    q = (math.exp(g_q) - 1) * m_q / gpm_mid
    p = math.exp(g_q) * (math.exp(g_p) - 1) * c["p_dropthrough"] / gpm_mid
    return max(-cap, min(cap, p)), max(-cap, min(cap, q))


def _median(xs):
    s = sorted(xs)
    n = len(s)
    return None if not n else (s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2)


def breaks(dp, rev, c):
    """(마지막 단절 분기, 이유) — datapack pq.breaks [{q, why}](분리·대형 인수·재작성)가 먼저, 없으면 자동 감지:
    분기 매출 로그 변화가 연달아 반대 방향으로 ±spike_log를 넘으면(급변 뒤 되돌림) 재작성·연결 범위가 섞인 자료로 본다(X-13 가법 이상치 판정과 같은 생각)"""
    decl = [b for b in ((dp.get("pq") or {}).get("breaks") or []) if b.get("q")]
    if decl:
        b = max(decl, key=lambda x: x["q"])
        return b["q"], f"{b['q']} {b.get('why', '구조 변화')}(datapack 선언)"
    th = (c.get("forecast") or {}).get("spike_log", 0.4)
    qs = sorted(rev)
    d = [(q, math.log(rev[q] / rev[p])) for p, q in zip(qs, qs[1:]) if rev[p] > 0 and rev[q] > 0 and sv.shift_q(p, 1) == q]
    hit = [d[i + 1][0] for i in range(len(d) - 1) if abs(d[i][1]) > th and abs(d[i + 1][1]) > th and d[i][1] * d[i + 1][1] < 0]
    if not hit:
        return None, None
    return max(hit), f"{max(hit)} 전후 분기 매출 급변·되돌림(재작성·분리 자료가 섞인 것으로 보임) — 그 뒤만 쓴다"


def long_cycle(dp, pq, history=None, db=sv.HS_DB, fred_cache=None, c=None):
    """10년 P·Q 레벨 갭·위치·프리미엄·전망"""
    c = c or cfg()
    rev, price, gpm, gpv = levels(dp, pq, history, db, fred_cache)
    qs = sorted(rev)
    cut, why = breaks(dp, rev, c)
    if cut:   # 구조 단절 뒤만 쓴다 — 단절을 사이클로 읽으면 추세·갭이 모두 틀린다(CLAUDE.md '단위·기간을 맞출 수 없으면 비교 불가')
        qs = [q for q in qs if q > cut]
    pts = []
    for i in range(3, len(qs)):
        win = qs[i - 3:i + 1]
        if sv.shift_q(win[0], 3) != win[-1] or not all(q in price and price[q] for q in win):
            continue
        ttm = sum(rev[q] for q in win)
        p = sum(price[q] for q in win) / 4
        gp = sum(gpv[q] for q in win) if all(q in gpv for q in win) else None
        pts.append({"q": win[-1], "rev": ttm, "p": p, "vol": ttm / p, "gp": gp})
    pts = pts[-40:]
    if len(pts) < c["min_ttm_points"]:
        return {"enough": False, "n": len(pts), "break": why}
    lam = c["hp_lambda"]
    lp, lv = [math.log(x["p"]) for x in pts], [math.log(x["vol"]) for x in pts]
    fcast = _forecast(dp, pts, lp, lv, rev, qs, lam, c)
    # 끝점 편향 보정 — 전망 경로를 이어 붙여 필터를 다시 건다(Kaiser·Maravall 1999). 전망이 없으면 그대로
    ext_p, ext_q = lp + fcast["lp"] + fcast.get("tail_p", []), lv + fcast["lq"] + fcast.get("tail_q", [])
    tp, tv = hp(ext_p, lam), hp(ext_q, lam)
    n = len(pts)
    for x, a, b, ta, tb in zip(pts, lp, lv, tp, tv):
        x["g_p"], x["g_q"] = a - ta, b - tb
        x["trend_p"], x["trend_q"] = math.exp(ta), math.exp(tb)
    has_gp = all(x["gp"] is not None for x in pts)
    if has_gp:
        gpm_mid = _median([x["gp"] / x["rev"] for x in pts])
        dr = [(pts[i]["rev"] - pts[i - 4]["rev"], pts[i]["gp"] - pts[i - 4]["gp"]) for i in range(4, len(pts))]
        sxx = sum(a * a for a, _ in dr)
        slope = sum(a * b for a, b in dr) / sxx if sxx else gpm_mid
        m_q = max(gpm_mid * c["q_margin_floor"], min(gpm_mid * c["q_margin_cap"], 1.0, slope))
    else:
        gpm_mid, m_q, slope = 1.0, 1.0, None
    for x in pts:
        x["prem_p"], x["prem_q"] = premiums(x["g_p"], x["g_q"], gpm_mid, m_q, c)
    gp_s, gq_s = [x["g_p"] for x in pts], [x["g_q"] for x in pts]
    var = lambda s: sum((v - sum(s) / len(s)) ** 2 for v in s) / len(s)
    vp, vq = var(gp_s), var(gq_s)
    cov = sum((a - sum(gp_s) / len(gp_s)) * (b - sum(gq_s) / len(gq_s)) for a, b in zip(gp_s, gq_s)) / len(gp_s)
    p_share = (vp + cov) / (vp + vq + 2 * cov) if (vp + vq + 2 * cov) > 1e-12 else 0.5   # 매출 갭 분산 중 P 몫
    now, prev = pts[-1], pts[-3]
    pct = lambda s, v: sum(1 for t in s if t <= v) / len(s)
    out = {"enough": True, "n": len(pts), "pts": pts, "gpm_mid": gpm_mid if has_gp else None, "m_q": m_q if has_gp else None, "slope": slope, "basis": "매출총이익" if has_gp else "매출",
           "p_share": max(0.0, min(1.0, p_share)), "type": "P형" if p_share >= 0.5 else "Q형",
           "clock_p": clock(now["g_p"], prev["g_p"]), "clock_q": clock(now["g_q"], prev["g_q"]), "pct_p": pct(gp_s, now["g_p"]), "pct_q": pct(gq_s, now["g_q"]),
           "proj": None, "half": {"P": None, "Q": None}, "fc": fcast["meta"]}
    if fcast["lp"]:
        proj = []
        for i, (lpf, lqf, sp, sq, w) in enumerate(zip(fcast["lp"], fcast["lq"], fcast["se_p"], fcast["se_q"], fcast["w"])):
            a, b = lpf - tp[n + i], lqf - tv[n + i]
            pa, qa = premiums(a, b, gpm_mid, m_q, c)
            proj.append({"q": sv.shift_q(now["q"], i + 1), "g_p": a, "g_q": b, "prem_p": pa, "prem_q": qa, "se_p": sp, "se_q": sq, "w_cons": w})
        out["proj"] = proj
        for k, g0, ser in (("P", now["g_p"], [x["g_p"] for x in proj]), ("Q", now["g_q"], [x["g_q"] for x in proj])):
            if abs(g0) > 1e-3:
                out["half"][k] = next((i + 1 for i, v in enumerate(ser) if abs(v) <= abs(g0) / 2 or v * g0 < 0), None)
    return out


def _forecast(dp, pts, lp, lv, rev, qs, lam, c):
    """로그 P·Q 레벨 8분기 전망 — P는 갭 AR(p), Q는 통계 갭 AR(p)와 컨센서스 내포 물량의 분산 역수 결합(pq_forecast 맨 위)"""
    fc = c.get("forecast") or {}
    empty = {"lp": [], "lq": [], "se_p": [], "se_q": [], "w": [], "meta": None}
    tp0, tv0 = hp(lp, lam), hp(lv, lam)
    gp0, gq0 = [a - b for a, b in zip(lp, tp0)], [a - b for a, b in zip(lv, tv0)]
    kw = {"pmax": fc.get("ar_pmax", 3), "max_root": fc.get("max_root", 0.95), "overlap": fc.get("overlap_q", 4)}   # TTM도 4분기 겹친 표본(⑤)
    fp, fq = F.ar_fit(gp0, **kw), F.ar_fit(gq0, **kw)
    if not fp or not fq:
        return empty
    H = HORIZON
    gpf, sep = F.ar_path(gp0, fp, H)
    gqf, seq = F.ar_path(gq0, fq, H)
    k = fc.get("trend_slope_q", 4)   # 추세는 끝 k분기 평균 기울기로 잇는다
    sp_, sq_ = (tp0[-1] - tp0[-1 - k]) / k, (tv0[-1] - tv0[-1 - k]) / k
    lpf = [tp0[-1] + sp_ * (h + 1) + gpf[h] for h in range(H)]
    lq_stat = [tv0[-1] + sq_ * (h + 1) + gqf[h] for h in range(H)]
    last = pts[-1]["q"]   # 전망 기준 = 가격이 있는 마지막 TTM 분기. 컨센서스는 마지막 실적 분기 다음부터 잇는다(PPI가 늦으면 둘이 다르다)
    cons, basis = F.consensus_quarters(dp, qs[-1], rev[qs[-1]], sv.shift_q, H + 4)
    lq, se_q, w = [], [], []
    for h in range(H):
        win = [sv.shift_q(last, h + 1 - j) for j in range(4)]
        ttm = sum(rev.get(q) if q in rev else cons.get(q, float("nan")) for q in win) if all(q in rev or q in cons for q in win) else None
        if ttm and ttm > 0:
            lq_cons = math.log(ttm) - lpf[h]   # 매출 = P × Q → log Q = log 매출 − log P
            v, s, wc = F.combine(lq_stat[h], seq[h], lq_cons, math.sqrt(F.cons_se(dp, h + 1, fc) ** 2 + sep[h] ** 2))
        else:
            v, s, wc = lq_stat[h], seq[h], 0.0
        lq.append(v)
        se_q.append(s)
        w.append(wc)
    # 보고 구간(8분기) 뒤로 8분기를 더 잇는다 — 연장한 끝점에 다시 생기는 편향을 보고 구간 밖으로 민다.
    # P는 AR 경로, Q는 전망 끝 4분기의 분기 성장률을 그대로 잇는다(과거 추세 기울기를 이으면 고성장 뒤 감속하는 컨센서스가 추세 아래로 끌려 내려간다)
    gpf2, _ = F.ar_path(gp0, fp, 2 * H)
    tail_p = [tp0[-1] + sp_ * (h + 1) + gpf2[h] for h in range(H, 2 * H)]
    g_end = (lq[-1] - lq[-5]) / 4
    tail_q = [lq[-1] + g_end * (h + 1 - H) for h in range(H, 2 * H)]
    meta = {"p_model": F.ar_name(fp["p"]) + (" 정상성 보정" if fp["shrunk"] else ""), "q_model": F.ar_name(fq["p"]) + (" 정상성 보정" if fq["shrunk"] else ""),
            "p_root": fp["radius"], "q_root": fq["radius"], "cons": basis if cons else None, "w4": w[3] if len(w) > 3 else None, "w8": w[-1] if w else None}
    return {"lp": lpf, "lq": lq, "tail_p": tail_p, "tail_q": tail_q, "se_p": sep, "se_q": se_q, "w": w, "meta": meta}


def _pct(x):
    return UNKNOWN if x is None else f"{x * 100:+.1f}%"


def _trend(now, later):
    d = later - now
    if abs(d) < 0.03:
        return "비슷하게 유지"
    return ("확대" if abs(later) > abs(now) else "축소") if now * later > 0 else ("+로 반전" if later > 0 else "−로 반전")


def long_blocks(lc, label):
    pts = lc["pts"]
    now = pts[-1]
    pp, pq_ = now["prem_p"], now["prem_q"]
    head = (f"**10년 위치: {lc['type']} 기업(매출 갭 분산의 {lc['p_share'] * 100:.0f}%가 가격) — 가격은 추세 대비 {_pct(math.exp(now['g_p']) - 1)}({lc['clock_p']}, 10년 분위 {lc['pct_p'] * 100:.0f}%), "
            f"물량은 {_pct(math.exp(now['g_q']) - 1)}({lc['clock_q']}, 분위 {lc['pct_q'] * 100:.0f}%). P 프리미엄 {pp * 100:+.0f}%, Q 프리미엄 {pq_ * 100:+.0f}%"
            f"({lc['basis']}이 정상(추세) 수준보다 요인별로 이만큼 높거나 낮다).**")
    if lc["proj"]:
        p4, p8 = lc["proj"][3], lc["proj"][-1]
        g = lambda x: _pct(math.exp(x) - 1)
        head += (f" 전망으로 가격 갭은 4분기 뒤 {g(p4['g_p'])}·8분기 뒤 {g(p8['g_p'])}, 물량 갭은 {g(p4['g_q'])}·{g(p8['g_q'])}"
                 + (f"(물량은 컨센서스 몫 {p4['w_cons'] * 100:.0f}%를 섞었다)" if p4.get("w_cons") else "(컨센서스가 없어 통계 전망만)") + ".")
    if pp + pq_ > 0.15:
        head += " 이익이 사이클 덕에 정상보다 높다 — 지금 이익에 높은 멀티플을 함께 주면 사이클을 두 번 세는 셈이다(IB는 정상 이익에 멀티플을 건다)."
    elif pp + pq_ < -0.15:
        head += " 이익이 정상보다 낮다 — 바닥 이익 기준 멀티플은 높아 보여도 정상 이익 기준으로는 낮을 수 있다."
    B = [{"type": "hl", "text": head}]
    xs = [x["q"] for x in pts]
    proj = lc["proj"] or []
    B.append({"type": "chart", "chart": {"kind": "line", "title": "10년 P·Q 사이클 — 추세(HP 필터) 대비 갭과 8분기 전망", "unit": "%", "now": now["q"], "series": [
        {"name": "가격(P) 갭", "color": "b", "points": [[x["q"], round((math.exp(x["g_p"]) - 1) * 100, 1)] for x in pts]},
        {"name": "물량(Q) 갭", "color": "c", "points": [[x["q"], round((math.exp(x["g_q"]) - 1) * 100, 1)] for x in pts]},
        {"name": "P 전망", "color": "e", "points": [[now["q"], round((math.exp(now["g_p"]) - 1) * 100, 1)]] + [[p["q"], round((math.exp(p["g_p"]) - 1) * 100, 1)] for p in proj]},
        {"name": "Q 전망", "color": "d", "points": [[now["q"], round((math.exp(now["g_q"]) - 1) * 100, 1)]] + [[p["q"], round((math.exp(p["g_q"]) - 1) * 100, 1)] for p in proj]}]}})
    hv = lambda k: UNKNOWN if not lc["half"][k] else f"{lc['half'][k]}분기"
    f = lambda p, k: UNKNOWN if not p else f"{p[k] * 100:+.0f}%"
    rows = [["추세 대비 갭(현재)", _pct(math.exp(now["g_p"]) - 1), _pct(math.exp(now["g_q"]) - 1)],
            ["사이클 시계", lc["clock_p"], lc["clock_q"]], ["10년 분위", f"{lc['pct_p'] * 100:.0f}%", f"{lc['pct_q'] * 100:.0f}%"],
            ["프리미엄(현재)", f"{pp * 100:+.0f}%", f"{pq_ * 100:+.0f}%"],
            ["프리미엄 4분기 뒤", f(proj[3] if len(proj) > 3 else None, "prem_p"), f(proj[3] if len(proj) > 3 else None, "prem_q")],
            ["프리미엄 8분기 뒤", f(proj[-1] if proj else None, "prem_p"), f(proj[-1] if proj else None, "prem_q")],
            ["갭 반감기", hv("P"), hv("Q")]]
    band = lambda p, k: UNKNOWN if not p else f"{_pct(math.exp(p['g_' + k]) - 1)} ({_pct(math.exp(p['g_' + k] - Z80 * p['se_' + k]) - 1)}~{_pct(math.exp(p['g_' + k] + Z80 * p['se_' + k]) - 1)})"
    if proj:
        rows += [["갭 4분기 뒤(80% 범위)", band(proj[3], "p"), band(proj[3], "q")], ["갭 8분기 뒤(80% 범위)", band(proj[-1], "p"), band(proj[-1], "q")]]
    fcm = lc.get("fc") or {}
    if fcm:
        rows.append(["전망 모형", fcm["p_model"], fcm["q_model"] + (f" + 컨센서스({fcm['cons']}, 4분기 뒤 몫 {fcm['w4'] * 100:.0f}%)" if fcm.get("cons") else " (컨센서스 없음)")])
    B.append({"type": "table", "title": "10년 P·Q 사이클 위치·프리미엄", "headers": ["항목", "가격(P)", "물량(Q)"], "rows": rows})
    note = (f"방법: P = 가격 지수 4분기 평균({label}), Q = TTM 매출 ÷ P. 추세는 로그 레벨의 HP 필터(λ 1600)로 정상(mid-cycle) 수준을 잡는다. "
            f"프리미엄 = 요인별 {lc['basis']} 증분 ÷ 정상 {lc['basis']}"
            + (f"(정상 GPM {lc['gpm_mid'] * 100:.1f}% = 10년 중앙값, 물량 증분 마진 {lc['m_q'] * 100:.1f}% = 전년 대비 ΔGP÷ΔRev 회귀, 가격은 전액 이익 반영)" if lc["gpm_mid"] else "(GP 이력이 없어 매출 기준)")
            + f". 표본 {lc['n']}개 TTM 분기. 전망: 가격 갭은 BIC로 차수를 고른 자기회귀모델(정상성 보정), 물량은 통계 갭 자기회귀모델과 컨센서스 매출 ÷ 가격 전망(매출 = P × Q)을 분산 역수로 섞는다(Bates·Granger 1969). "
               "끝점 편향을 줄이려고 전망 경로를 이어 붙인 뒤 HP 필터를 다시 건다(Kaiser·Maravall 1999). 80% 범위는 예측 오차(TTM이 4분기씩 겹쳐 생기는 자기상관을 뉴이·웨스트 장기 분산으로 반영)와 애널리스트 범위에서 낸다. 모형 산출이며 가이던스가 아니다.")
    B.append({"type": "p", "text": note})
    return B


def band4(p, k):
    """4분기 뒤 투영값과 80% 범위(전년 대비)"""
    s = p.get("se_" + k)
    v = p["g_" + k]
    return _pct(v) if s is None else f"{_pct(v)} ({_pct(v - Z80 * s)}~{_pct(v + Z80 * s)})"


def mean_txt(m):
    raw, shr = m
    return UNKNOWN if raw is None else f"{_pct(math.exp(raw) - 1)} → {_pct(math.exp(shr) - 1)}"


def section(dp, history=None, db=sv.HS_DB, fred_cache=None):
    dp = dp or {}
    own = dp.get("pq")
    pq, proxy, label = price_basis(dp)
    if not pq:
        if not own:
            raise SystemExit("datapack에 pq가 없고 업종 PPI 대용(config/pq_cycle.yaml fred_by_industry)도 없다(scripts/tenbagger/pq_view.py 맨 위) — 가격·물량을 잴 수 없으면 {'none': '이유'}, 옛 리포트 정정은 --legacy")
        return None
    if proxy:
        label = f"{label} 대용 — 회사 판매가가 아니라 업종 가격"
    else:
        label = {"asp": "회사 공시 ASP", "ppi": "제품 PPI", "fred": "FRED PPI"}.get((pq.get("price") or {}).get("source"), "출하량 공시")
    c = compute(dp, history, db, pq, fred_cache)
    lc = long_cycle(dp, pq, history, db, fred_cache)
    if not c["enough"]:
        return {"h2": "P·Q 사이클", "blocks": [{"type": "hl", "text": f"**가격·물량을 나눌 표본이 부족하다(전년 대비 {len(c['rows'])}분기).** 가격 근거({label})의 이력이 쌓이면 다시 잰다."}]}
    head = f"**{c['now']} — 최근 4분기 평균 가격 기여 {_pct(c['mp'])}, 물량 기여 {_pct(c['mq'])}(전년 대비 로그 증가율).** P 강도 {c['p_score']:.1f}/10, Q 강도 {c['q_score']:.1f}/10"
    if c["persist"] is not None:
        head += f", 최근 8분기 중 {c['persist'] * 100:.0f}%가 같은 요인 우세({'구조적' if c['persist'] >= 0.75 else '순환적'})"
    head += "."
    if c["fake_p"]:
        head += f" 다만 GPM이 전년보다 {c['gpm_chg'] * 100:+.1f}%p로 오르지 않아 원가 전가형 가격 상승일 가능성이 있다."
    if c["proj"]:
        other = "Q 사이클" if c["mp"] >= c["mq"] else "P 사이클"
        head += f" 전망으로는 {f'{c['switch']}분기 뒤({c['proj'][c['switch'] - 1]['q']}) {other}로 전환' if c['switch'] else f'{HORIZON}분기 안에 전환 신호가 없다'}" + ("(물량은 컨센서스를 섞었다)." if c.get("cons") else "(통계 전망만).")
    if pq.get("why"):
        head += " " + str(pq["why"])
    rows = c["rows"]
    B = [{"type": "hl", "text": head}]
    hist_p = [[r["q"], round(r["g_p"] * 100, 1)] for r in rows]
    hist_q = [[r["q"], round(r["g_q"] * 100, 1)] for r in rows]
    series = [{"name": "가격(P) 기여", "color": "b", "points": hist_p}, {"name": "물량(Q) 기여", "color": "c", "points": hist_q}]
    if c["proj"]:
        lastp, lastq = hist_p[-1], hist_q[-1]
        series += [{"name": "P 투영", "color": "e", "points": [lastp] + [[p["q"], round(p["g_p"] * 100, 1)] for p in c["proj"]]},
                   {"name": "Q 투영", "color": "d", "points": [lastq] + [[p["q"], round(p["g_q"] * 100, 1)] for p in c["proj"]]}]
    B.append({"type": "chart", "chart": {"kind": "line", "title": "매출 증가율의 가격·물량 분해와 8분기 전망(전년 대비)", "unit": "%", "series": series}})
    B.append({"type": "chart", "chart": {"kind": "bars", "title": "분기별 매출 증가율 분해", "unit": "%", "categories": [r["q"] for r in rows[-8:]],
                                         "series": [{"name": "가격(P)", "color": "b", "values": [round(r["g_p"] * 100, 1) for r in rows[-8:]]},
                                                    {"name": "물량(Q)", "color": "c", "values": [round(r["g_q"] * 100, 1) for r in rows[-8:]]}]}})
    per = c.get("period") or {}
    B.append({"type": "table", "title": "P·Q 사이클 정량", "headers": ["항목", "가격(P)", "물량(Q)"],
              "rows": [["최근 4분기 평균 기여", _pct(c["mp"]), _pct(c["mq"])], ["강도(0~10, 자기 이력 z)", f"{c['p_score']:.1f}", f"{c['q_score']:.1f}"],
                       ["고유 주기(자기회귀모델 과거 2개 시점일 때)", UNKNOWN if not per.get("P") else f"{per['P']:.1f}분기", UNKNOWN if not per.get("Q") else f"{per['Q']:.1f}분기"],
                       ["다음 4분기 투영 평균", UNKNOWN if not c["proj"] else _pct(sum(p["g_p"] for p in c["proj"][:4]) / 4), UNKNOWN if not c["proj"] else _pct(sum(p["g_q"] for p in c["proj"][:4]) / 4)]]
              + ([["4분기 뒤 투영(80% 범위)", band4(c["proj"][3], "p"), band4(c["proj"][3], "q")],
                  ["장기 평균(표본 → 기저율 수축)", mean_txt(c["means"]["P"]), mean_txt(c["means"]["Q"])],
                  ["투영 모형", c["models"][0] + (f" · {c['nowcast']['q']} 월간 가격 {c['nowcast']['months']}개월 반영" if c.get("nowcast") else ""),
                   c["models"][1] + (f" + 컨센서스({c['cons']})" if c.get("cons") else " (컨센서스 없음)")]] if c["proj"] and len(c["proj"]) > 3 else [])})
    B.append({"type": "p", "text": f"가격 근거: {label}. PPI를 쓰면 회사 판매가가 아니라 업종 가격 대용이다. 로그 증가율이라 가격·물량 기여의 합이 매출 증가율이다. "
                                         "전망: 가격은 BIC로 차수를 고른 자기회귀모델에 이미 발표된 월간 가격을 먼저 넣고(나우캐스트), 물량은 자기회귀모델과 '컨센서스 매출 증가율 − 가격 전망'을 분산 역수로 섞는다. "
                                         "장기 평균은 표본 평균을 장기 기저율(가격 연 2%·물량 연 4%) 쪽으로 줄인다 — 고성장 구간만 담긴 표본이 그 성장을 끝없이 잇지 않게. 범위는 4분기 겹친 표본의 자기상관을 반영한다. 모형 산출이며 가이던스가 아니다."
                                         + (f" 회사 판매가로 잴 수 없는 이유: {own['none']}" if proxy and own and own.get("none") else "")})
    if lc["enough"]:
        B = long_blocks(lc, label) + B
    else:
        B.append({"type": "p", "text": (f"10년 위치·프리미엄: 구조 단절({lc['break']}) 뒤 TTM 표본이 {lc['n']}개로 {cfg()['min_ttm_points']}개에 못 미쳐 10년 비교를 하지 않는다 — 단절 전후 매출은 같은 회사 범위가 아니다."
                                             if lc.get("break") else f"10년 위치·프리미엄: TTM 표본 {lc['n']}개로 {cfg()['min_ttm_points']}개에 못 미친다 — quarters.js로 분기 {cfg()['quarters_fetch']}개를 다시 받으면 나온다.")})
    return {"h2": "P·Q 사이클", "blocks": B}
