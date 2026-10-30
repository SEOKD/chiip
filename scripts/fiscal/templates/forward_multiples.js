async () => {
  // Fwd 1Y 멀티플 묶음 — 텐배거 리포트 멀티플 절의 재료(마스터 지시 2026-10-30 "Fwd 1Y P/E나 Fwd 1Y EV/EBITDA 등 이익 지표로. Fwd 1Y 멀티플은 Fiscal.ai에서 우선적으로").
  // 순서: Fiscal 자체 Forward 배수(ratio_forward_*, 분모 = 다음 4개 분기 추정) → 없으면 Street Forward(ratio_street_forward_*).
  // 과거 레인지는 일별 Forward 배수가 없어 월말 가격 ÷ 그 시점 다음 4개 분기 추정 합으로 계산한다(추정 변경 이력).
  // 출력 → 파일 저장 → py scripts/fiscal/adapter.py --forward-multiples <id> <파일> → datapack multiples_now·forward·peers·history.
  // Street 값·추정 이력은 Zacks 수치 — 데이터 묶음에 표기 의무("Data provided by Zacks Investment Research, Inc., www.zacksdata.com"). 리포트 본문에는 제공처를 쓰지 않는다.
  const k = "__KEY__";
  const peers = __PEERS__;   // ["NASDAQ_ICHR", …] 동종사 회사 키
  const OWN = { pe: "ratio_forward_price_to_earnings", ev_ebitda: "ratio_forward_ev_to_ebitda" };
  const STREET = { pe: "ratio_street_forward_price_to_earnings", ev_ebitda: "ratio_street_forward_ev_to_ebitda" };
  const pos = v => (typeof v === "number" && v > 0 ? Math.round(v * 100) / 100 : null);
  const latest = async key => {
    const r = await codemode.company_ratios({ companyKey: key, periodType: "latest", ratioId: [...Object.values(OWN), ...Object.values(STREET)].join(",") }).catch(() => null);
    const v = ((r && r.data) || []).slice(-1)[0];
    const m = (v && v.metricValues) || {};
    const pick = f => (pos(m[OWN[f]]) != null ? [pos(m[OWN[f]]), "fiscal"] : pos(m[STREET[f]]) != null ? [pos(m[STREET[f]]), "street"] : [null, null]);
    const [pe, peSrc] = pick("pe");
    const [ev, evSrc] = pick("ev_ebitda");
    return { pe_fwd: pe, ev_ebitda_fwd: ev, src: { pe_fwd: peSrc, ev_ebitda_fwd: evSrc } };
  };
  const target = await latest(k);

  // 다음 4개 분기 추정 — 주요 지표 판별 재료(가이던스를 내는 지표, 감가상각 비중)와 펀더멘털 내재 멀티플의 선행 이익률·성장
  const ntmOf = async key => {
    const fe = await codemode.company_estimates({ companyKey: key }).catch(() => ({ data: [] }));
    const qs = (fe.data || []).filter(r => r.periodType === "Quarterly").sort((a, b) => (a.reportDate < b.reportDate ? -1 : 1));
    const next4 = qs.filter(r => (r.metricsValues.revenue || {}).actual == null).slice(0, 4);
    const sum = id => { const v = next4.map(r => (r.metricsValues[id] || {}).mean); return next4.length === 4 && v.every(x => x != null) ? v.reduce((a, b) => a + b, 0) : null; };
    const guided = id => next4.some(r => /^guidance/.test((r.metricsValues[id] || {}).source || ""));
    const epsId = fe.primaryEpsBasis === "adjusted" ? "eps_adjusted" : "eps_gaap";
    const ebitda = sum("ebitda_adjusted") != null ? sum("ebitda_adjusted") : sum("ebitda");
    const ebit = sum("ebit_adjusted") != null ? sum("ebit_adjusted") : sum("ebit");
    const last4 = qs.filter(r => (r.metricsValues.revenue || {}).actual != null).slice(-4).map(r => r.metricsValues.revenue.actual);
    return { qs, ntm: { eps: sum(epsId), ebitda, ebit, revenue: sum("revenue"), rev_ttm: last4.length === 4 ? last4.reduce((a, b) => a + b, 0) : null },
             guided: { eps: guided(epsId), ebitda: guided("ebitda_adjusted") || guided("ebitda") } };
  };
  const { qs, ntm, guided } = await ntmOf(k);

  // 과거 레인지 — 월말 Fwd 1Y P/E·EV/EBITDA
  const z = await codemode.company_analyst_estimates({ companyKey: k, history: true });
  const hist = id => {
    const m = {};
    (z.history || []).filter(h => h.metricId === id && h.periodType === "Quarterly" && h.mean != null).forEach(h => { (m[h.reportDate] = m[h.reportDate] || []).push([h.asOf || "", h.mean]); });
    Object.values(m).forEach(a => a.sort((x, y) => (x[0] < y[0] ? -1 : 1)));
    return m;
  };
  const he = hist("analyst_eps");
  const hb = hist("analyst_ebitda");
  const ntmAt = (h, d) => {
    const ends = Object.keys(h).filter(e => e > d).sort().slice(0, 4);
    if (ends.length < 4) return null;
    let s = 0;
    for (const e of ends) {
      const known = h[e].filter(r => r[0] <= d).slice(-1)[0];
      if (!known) return null;
      s += known[1];
    }
    return s;
  };
  const px = await codemode.company_stock_prices({ companyKey: k });
  const rows = (px.prices || []).filter(p => p.closePrice != null).sort((a, b) => (a.date < b.date ? -1 : 1));
  const mc = await codemode.company_daily_ratios({ ratioId: "calculated_market_cap", companyKey: k }).catch(() => []);
  const mcAt = {};
  mc.forEach(r => { mcAt[r.date] = r.ratio; });
  const nd = qs.map(r => [r.reportDate, (r.metricsValues.net_debt || {}).actual]).filter(r => r[1] != null);
  const ndAt = d => { const c = new Date(new Date(d) - 45 * 864e5).toISOString().slice(0, 10); const x = nd.filter(r => r[0] <= c).slice(-1)[0]; return x ? x[1] : null; };
  const monthEnds = [];
  rows.forEach((r, i) => { if (i === rows.length - 1 || rows[i + 1].date.slice(0, 7) !== r.date.slice(0, 7)) monthEnds.push(r); });
  const history = [];
  monthEnds.slice(-37, -1).forEach(r => {
    const eps = ntmAt(he, r.date);
    const eb = ntmAt(hb, r.date);
    const m = mcAt[r.date];
    const net = ndAt(r.date);
    const row = { date: r.date, pe_fwd: eps > 0 ? Math.round(r.closePrice / eps * 100) / 100 : null,
                  ev_ebitda_fwd: eb > 0 && m != null && net != null ? Math.round((m + net) / eb * 100) / 100 : null };
    if (row.pe_fwd != null || row.ev_ebitda_fwd != null) history.push(row);
  });

  const peerRows = {};
  for (const p of peers) peerRows[p] = { ...(await latest(p)), ntm: (await ntmOf(p)).ntm };
  console.log(JSON.stringify({ key: k, as_of: (rows[rows.length - 1] || {}).date, target, ntm, guided,
    peers: peerRows, history, source: "Fiscal.ai Forward 배수(다음 4개 분기 추정) → Street Forward. 과거 = 월말 가격 ÷ 그 시점 다음 4개 분기 추정(company_analyst_estimates history). Data provided by Zacks Investment Research, Inc., www.zacksdata.com" }));
}
