async () => {
  // 컨센서스 = Fiscal.ai 자체 추정(company_estimates — 가이던스·모델·Agentic Consensus) 1순위(마스터 지시 2026-10-30 "Fiscal.ai 컨센서스 데이터를 1순위로")
  // → 데이터 묶음 consensus(연·분기)는 `fiscal`부터. Zacks(`zacks`)는 Fiscal 칸이 빈 기간·지표만 채우고 대조용으로 남긴다.
  // Fiscal에 없는 것만 Zacks: 5년 리비전 이력(consensus.revisions)·애널리스트 수·분산·목표가·의견. Zacks 수치를 보여 줄 때마다 attribution 표기 의무.
  const k = "__KEY__";
  const [z, rat, fe] = await Promise.all([
    codemode.company_analyst_estimates({ companyKey: k, history: true }).catch(() => ({ data: [], history: [] })),
    codemode.company_analyst_ratings({ companyKey: k }),
    codemode.company_estimates({ companyKey: k })]);
  const mv = (d, m) => { const v = (d.metricsValues || {})[m]; return v ? { mean: v.mean, high: v.high, low: v.low, sd: v.stdDev, n: v.numEstimates, asOf: v.asOf } : null; };
  const fc = (d, m) => { const v = d.metricsValues[m]; return v && v.mean != null ? { mean: v.mean, high: v.high, low: v.low, src: v.source, basis: v.basis, conf: v.confidenceTier, asOf: v.asOf, actual: v.actual } : null; };
  const fiscal = (fe.data || []).filter(d => !d.earningsDate).map(d => ({ period: d.reportDate, type: d.periodType, rev: fc(d, "revenue"),
    eps: fc(d, fe.primaryEpsBasis === "gaap" ? "eps_gaap" : "eps_adjusted"), ebit: fc(d, "ebit_adjusted"), ebitda: fc(d, "ebitda_adjusted"),
    gross_profit: fc(d, "gross_profit"), ocf: fc(d, "operating_cash_flow"), capex: fc(d, "capex"), fcf: fc(d, "free_cash_flow") }));
  const zacks = (z.data || []).map(d => ({ period: d.reportDate, type: d.periodType, rev: mv(d, "analyst_revenue"), eps: mv(d, "analyst_eps"), ebit: mv(d, "analyst_ebit"), ebitda: mv(d, "analyst_ebitda") }));
  // history는 지표별 평면 행(metricId·reportDate·mean·numEstimates·asOf) — 매출·EPS만, 앞으로 올 기간과 최근 4개 기간, 최신 asOf 먼저
  const cut = new Date(Date.now() - 400 * 864e5).toISOString().slice(0, 10);
  const hist = (z.history || []).filter(h => (h.metricId === "analyst_eps" || h.metricId === "analyst_revenue") && h.reportDate >= cut)
    .sort((a, b) => String(b.asOf || "") < String(a.asOf || "") ? -1 : 1).slice(0, 300)
    .map(h => ({ metric: h.metricId === "analyst_eps" ? "EPS" : "매출", period: h.reportDate, type: h.periodType, mean: h.mean, n: h.numEstimates, asOf: h.asOf }));
  const guidance = (fe.data || []).filter(d => d.metricsValues.revenue && d.metricsValues.revenue.provenance && d.metricsValues.revenue.provenance.guidance)
    .slice(-4).map(d => ({ period: d.reportDate, type: d.periodType, rev: d.metricsValues.revenue.mean, low: d.metricsValues.revenue.low, high: d.metricsValues.revenue.high, guidance: d.metricsValues.revenue.provenance.guidance }));
  console.log(JSON.stringify({ primary: "fiscal", fiscal, zacks, history: hist, ratings: rat, guidance, eps_basis: fe.primaryEpsBasis,
    attribution: "Data provided by Zacks Investment Research, Inc., www.zacksdata.com (https://www.zacksdata.com)" }));
}
