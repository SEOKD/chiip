async () => {
  // 월가 컨센서스(Zacks: 평균·최고·최저·표준편차·애널리스트 수, 5년 변경 이력)·목표가·의견 + Fiscal.ai 자체 추정(가이던스 출처)
  // → 데이터 묶음 consensus(연·분기)·consensus.revisions(같은 분기끼리)·guidance. Zacks 수치를 보여 줄 때마다 attribution 표기 의무.
  const k = "__KEY__";
  const [z, rat, fe] = await Promise.all([
    codemode.company_analyst_estimates({ companyKey: k, history: true }),
    codemode.company_analyst_ratings({ companyKey: k }),
    codemode.company_estimates({ companyKey: k })]);
  const mv = (d, m) => { const v = (d.metricsValues || {})[m]; return v ? { mean: v.mean, high: v.high, low: v.low, sd: v.stdDev, n: v.numEstimates, asOf: v.asOf } : null; };
  const zacks = (z.data || []).map(d => ({ period: d.reportDate, type: d.periodType, rev: mv(d, "analyst_revenue"), eps: mv(d, "analyst_eps"), ebit: mv(d, "analyst_ebit"), ebitda: mv(d, "analyst_ebitda") }));
  // history는 지표별 평면 행(metricId·reportDate·mean·numEstimates·asOf) — 매출·EPS만, 앞으로 올 기간과 최근 4개 기간, 최신 asOf 먼저
  const cut = new Date(Date.now() - 400 * 864e5).toISOString().slice(0, 10);
  const hist = (z.history || []).filter(h => (h.metricId === "analyst_eps" || h.metricId === "analyst_revenue") && h.reportDate >= cut)
    .sort((a, b) => String(b.asOf || "") < String(a.asOf || "") ? -1 : 1).slice(0, 300)
    .map(h => ({ metric: h.metricId === "analyst_eps" ? "EPS" : "매출", period: h.reportDate, type: h.periodType, mean: h.mean, n: h.numEstimates, asOf: h.asOf }));
  const guidance = (fe.data || []).filter(d => d.metricsValues.revenue && d.metricsValues.revenue.provenance && d.metricsValues.revenue.provenance.guidance)
    .slice(-4).map(d => ({ period: d.reportDate, type: d.periodType, rev: d.metricsValues.revenue.mean, low: d.metricsValues.revenue.low, high: d.metricsValues.revenue.high, guidance: d.metricsValues.revenue.provenance.guidance }));
  console.log(JSON.stringify({ zacks, history: hist, ratings: rat, guidance, eps_basis: fe.primaryEpsBasis,
    attribution: "Data provided by Zacks Investment Research, Inc., www.zacksdata.com (https://www.zacksdata.com)" }));
}
