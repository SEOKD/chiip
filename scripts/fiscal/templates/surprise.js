async () => {
  // 최근 4개 분기 실적 vs 발표 직전 컨센서스 — 텐배거 리포트 datapack `consensus.surprise`(마스터 지시 2026-10-30 "GAAP 말고 컨센서스가 있는
  // Non-GAAP(adj.) 값으로, 분기별 서프라이즈는 최근 4개 분기 시계열로").
  // 실적: Fiscal company_estimates의 filed actual — EPS는 eps_adjusted(회사가 조정 EPS를 내지 않으면 GAAP, basis로 표시), 조정 EBIT·EBITDA는 회사가 낼 때만.
  // 추정: 1순위 Fiscal이 발표 전에 얼려 둔 추정(asOf < 발표일, 분기 guidance_calculated 제외), 2순위 Zacks history의 발표일 전 마지막 값(같은 기준).
  // __KEY__ = NASDAQ_SNDK 형식. 출력 rows를 datapack consensus.surprise에 그대로 넣는다. zacks_used면 Zacks 표기.
  const k = "__KEY__";
  const [fe, z] = await Promise.all([
    codemode.company_estimates({ companyKey: k }),
    codemode.company_analyst_estimates({ companyKey: k, history: true }).catch(() => ({ history: [] }))]);
  const done = fe.data.filter(d => d.periodType === "Quarterly" && d.metricsValues.revenue && d.metricsValues.revenue.actual != null).slice(-4);
  const zh = z.history || [];
  const zack = (rd, ed, metric) => {
    const rows = zh.filter(h => h.metricId === metric && h.periodType === "Quarterly" && String(h.reportDate).slice(0, 7) === String(rd).slice(0, 7) && h.asOf && (!ed || String(h.asOf) < ed));
    const r = rows.sort((a, b) => String(a.asOf) < String(b.asOf) ? -1 : 1).slice(-1)[0];
    return r ? { est: r.mean, src: "zacks", asOf: r.asOf, n: r.numEstimates } : null;
  };
  const fis = (d, key, ed) => { const c = d.metricsValues[key]; return c && c.mean != null && c.asOf && (!ed || String(c.asOf).slice(0, 10) < ed) && c.source !== "guidance_calculated" ? { est: c.mean, src: "fiscal:" + c.source, asOf: c.asOf } : null; };
  const lines = [["매출", "revenue", "analyst_revenue", 1e6, "M$"], ["EPS", "eps_adjusted", "analyst_eps", 1, "$"], ["조정 EBIT", "ebit_adjusted", "analyst_ebit", 1e6, "M$"], ["조정 EBITDA", "ebitda_adjusted", "analyst_ebitda", 1e6, "M$"]];
  const rows = [];
  for (const d of done) {
    const ed = d.earningsDate ? String(d.earningsDate).slice(0, 10) : null;
    const period = `${d.calendarYear}Q${d.calendarQuarter}`;
    for (const [name, key, zk, div, unit] of lines) {
      const c = d.metricsValues[key];
      if (!c || c.actual == null) continue;
      if (key !== "revenue" && key !== "eps_adjusted" && c.basis !== "adjusted") continue;   // 조정 EBIT·EBITDA는 회사가 낼 때만
      const e = fis(d, key, ed) || zack(d.reportDate, ed, zk);
      rows.push({ period, metric: name, unit, actual: Math.round(c.actual / div * 1000) / 1000, est: e ? Math.round(e.est / div * 1000) / 1000 : null,
        est_src: e ? e.src : null, est_asof: e ? e.asOf : null, basis: c.basis || null, earnings_date: ed });
    }
  }
  const zacks_used = rows.some(r => r.est_src === "zacks");
  console.log(JSON.stringify({ key: k, primaryEpsBasis: fe.primaryEpsBasis, rows, zacks_used,
    attribution: zacks_used ? "Data provided by Zacks Investment Research, Inc., www.zacksdata.com" : null }));
}
