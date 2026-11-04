async () => {
  // 실적 반응 합리성 엔진 입력(scripts/insight/reaction.py, 마스터 지시 2026-11-04). K·PEERS·GUIDE만 바꿔 Fiscal.ai execute_code로 돌린다.
  // ① 과거 분기: company_estimates 보고 분기의 발표 전 추정(mean)과 실제(actual) → EPS·매출 서프라이즈 %, earningsDate·시각(UTC)으로 장전/장후 판정
  // ② 반응: 장전(미 동부 09:30 전) = 발표일 종가/전일 종가, 장후 = 다음 거래일 종가/발표일 종가. 시장 = IVV(Fiscal 펀드 무료 5종), β = 직전 120거래일 회귀
  // ③ 이번 분기: 가장 최근 보고 분기 + 발표 전 20일 초과 상승 + 30일 거래대금·연 변동성
  // 과거 분기 중 발표 전 추정(mean)이 없는 분기는 서프라이즈가 null — 엔진이 σ만 쓰고 ERC는 사전값으로 둔다
  // 이번 가이던스 변화(GUIDE, %)는 모델이 회사 자료에서 읽어 넣는다(연간 중간값의 컨센서스 대비 또는 직전 가이던스 대비). 모르면 null.
  const K = "NYSE_ULS", PEERS = [], GUIDE = null, SESSION = "pre";   // SESSION: 보도자료 시각으로 모델이 정한다(Fiscal earningsDate는 10-Q 제출 시각이라 장전·장후 판정에 못 쓴다) — 과거 분기도 같은 관행으로 본다
  const [est, px, ivv, ir] = await Promise.all([
    codemode.company_estimates({ companyKey: K }),
    codemode.company_ir_events({ companyKey: K }).catch(() => []),
    codemode.company_stock_prices({ companyKey: K }),
    codemode.fund_prices({ ticker: "IVV", startDate: "2024-01-01" })]);
  const close = a => Object.fromEntries((a || []).filter(x => x.closePrice != null).map(x => [x.date, x.closePrice]));
  const S = close(px.prices), M = close(ivv.prices);
  const days = Object.keys(S).filter(d => d in M).sort();
  const ret = (o, i) => o[days[i]] / o[days[i - 1]] - 1;
  const idxOnOrAfter = d => days.findIndex(x => x >= d);
  const beta = i0 => { const xs = [], ys = []; for (let i = Math.max(1, i0 - 120); i < i0; i++) { xs.push(ret(M, i)); ys.push(ret(S, i)); }
    const mx = xs.reduce((a, b) => a + b, 0) / xs.length, my = ys.reduce((a, b) => a + b, 0) / ys.length;
    let c = 0, v = 0; xs.forEach((x, j) => { c += (x - mx) * (ys[j] - my); v += (x - mx) ** 2; }); return v ? c / v : 1; };
  const eps = r => r.metricsValues.eps_adjusted || r.metricsValues.eps_gaap, rev = r => r.metricsValues.revenue;
  const surp = cell => cell && cell.actual != null && cell.mean ? (cell.actual / cell.mean - 1) * 100 : null;
  const rep = (est.data || []).filter(r => r.periodType === "Quarterly" && r.earningsDate).sort((a, b) => a.earningsDate < b.earningsDate ? -1 : 1);
  const evDate = {}; (ir || []).filter(e => e.eventType === "earnings").forEach(e => { evDate[e.fiscalYear + "Q" + e.fiscalQuarter] = e.eventDate; });   // 발표일 = IR 실적 행사일(10-Q 제출일이 아니라)
  const events = rep.map(r => {
    const d = (evDate[r.fiscalYear + "Q" + r.fiscalQuarter] || r.earningsDate).slice(0, 10), t = r.earningsTimeOfDay || "", hh = +t.slice(0, 2) || 0;
    const pre = SESSION ? SESSION === "pre" : (hh < 14 || (hh === 14 && +t.slice(3, 5) < 30));
    let i = idxOnOrAfter(d); if (i < 1) return null;
    if (!pre) i += 1; if (i >= days.length) return null;
    const b = beta(i), ar = (ret(S, i) - b * ret(M, i)) * 100;
    return { date: d, session: pre ? "pre" : "post", eps: surp(eps(r)), rev: surp(rev(r)), ar: +ar.toFixed(2), stock: +(ret(S, i) * 100).toFixed(2), market: +(ret(M, i) * 100).toFixed(2), beta: +b.toFixed(2), i };
  }).filter(Boolean);
  const now = events[events.length - 1];
  const i = now.i, d20 = Math.max(1, i - 21);
  const drift = ((S[days[i - 1]] / S[days[d20]]) - (M[days[i - 1]] / M[days[d20]])) * 100;
  const r30 = []; for (let j = Math.max(1, i - 60); j < i; j++) r30.push(ret(S, j));
  const m30 = r30.reduce((a, b) => a + b, 0) / r30.length, vol = Math.sqrt(r30.reduce((a, b) => a + (b - m30) ** 2, 0) / (r30.length - 1) * 252);
  const adv = (px.prices || []).slice(0, 30).reduce((a, x) => a + (x.closePrice || 0) * (x.volume || 0), 0) / 30;
  console.log(JSON.stringify({ ticker: K, date: now.date, session: now.session, beta: now.beta,
    surprise: { eps: now.eps == null ? null : +now.eps.toFixed(2), rev: now.rev == null ? null : +now.rev.toFixed(2), guide: GUIDE },
    reaction: { stock: now.stock, market: now.market, peers: null, extended: null }, pre_drift20: +drift.toFixed(2),
    history: events.slice(0, -1).slice(-12).map(e => ({ date: e.date, eps: e.eps == null ? null : +e.eps.toFixed(2), rev: e.rev == null ? null : +e.rev.toFixed(2), ar: e.ar })),
    adv_usd: Math.round(adv), vol_ann: +vol.toFixed(3), peers_note: PEERS.length ? "경쟁사 수익은 모델이 따로" : null }));
}
