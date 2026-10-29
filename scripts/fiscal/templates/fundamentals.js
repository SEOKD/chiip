async () => {
  // 펀더멘털 한 줄(구간·조용한 상승·알파 재료) — __KEY__ 를 회사 키(예 NYSE_PWR)로 바꾼다.
  // 출력 JSON을 파일로 저장 → py scripts/fiscal/adapter.py --fund <id> <파일>
  const k = "__KEY__";
  const s = r => r.status === "fulfilled" ? r.value : null;
  const [prof, px, est, rat, mc, evs] = (await Promise.allSettled([
    codemode.company_profile({ companyKey: k }), codemode.company_stock_prices({ companyKey: k }),
    codemode.company_estimates({ companyKey: k }), codemode.company_analyst_ratings({ companyKey: k }),
    codemode.company_daily_ratios({ companyKey: k, ratioId: "calculated_market_cap" }),
    codemode.company_daily_ratios({ companyKey: k, ratioId: "ratio_ev_to_sales" })])).map(s);
  let bars = ((px && px.prices) || []).filter(p => p.closePrice != null).sort((a, b) => a.date < b.date ? -1 : 1);
  const med = a => { const s = a.slice().sort((x, y) => x - y); return s.length ? s[Math.floor(s.length / 2)] : 0; };
  if (bars.length > 21 && (bars[bars.length - 1].volume || 0) < 0.01 * med(bars.slice(-21, -1).map(p => p.volume || 0))) bars = bars.slice(0, -1);   // 미확정 마지막 봉 제외
  const closes = bars.map(p => p.closePrice);
  const avg = n => closes.length >= n ? closes.slice(-n).reduce((a, b) => a + b, 0) / n : null;
  const last = closes.length ? closes[closes.length - 1] : null, y = closes.slice(-252);
  const q = ((est && est.data) || []).filter(d => d.periodType === "Quarterly").sort((a, b) => a.reportDate < b.reportDate ? -1 : 1);
  const done = q.filter(d => d.metricsValues.revenue && d.metricsValues.revenue.actual != null);
  const sum = (rows, m) => rows.length === 4 && rows.every(r => r.metricsValues[m] && r.metricsValues[m].actual != null) ? rows.reduce((a, r) => a + r.metricsValues[m].actual, 0) : null;
  const ttm = sum(done.slice(-4), "revenue"), prev = sum(done.slice(-8, -4), "revenue"), ebit = sum(done.slice(-4), "ebit");
  const epsKey = (est && est.primaryEpsBasis) === "gaap" ? "eps_gaap" : "eps_adjusted";
  const surprises = done.slice(-4).reverse().map(d => {
    const e = d.metricsValues[epsKey];
    return e && e.mean && e.actual != null ? Math.round(((e.actual - e.mean) / Math.abs(e.mean)) * 1000) / 10 : null;
  });
  const fwd = q.filter(d => !(d.metricsValues.revenue && d.metricsValues.revenue.actual != null)).slice(0, 4);
  const epsF = fwd.length === 4 && fwd.every(d => d.metricsValues[epsKey] && d.metricsValues[epsKey].mean != null) ? fwd.reduce((a, d) => a + d.metricsValues[epsKey].mean, 0) : null;
  const first = a => (a && a.length) ? a[0].ratio : null;   // 일별 배수는 최신이 앞
  console.log(JSON.stringify({
    key: k, as_of: bars.length ? bars[bars.length - 1].date : null, currency: prof && (prof.tradingCurrency || prof.reportingCurrency),
    mcap: first(mc), ev_sales: first(evs), rev_ttm: ttm, rev_growth: ttm && prev ? ttm / prev - 1 : null, op_margin: ttm && ebit != null ? ebit / ttm : null,
    n_analysts: rat && rat.rating ? rat.rating.numAnalysts : null, price: last, ma50: avg(50), ma200: avg(200),
    high_52w: y.length ? Math.max(...y) : null, low_52w: y.length ? Math.min(...y) : null,
    eps_fwd: epsF, eps_ttm: sum(done.slice(-4), epsKey), surprises,
    target_mean: rat && rat.priceTarget ? rat.priceTarget.mean : null, sector: prof && prof.sector, industry: prof && prof.industry,
    terminalUrl: prof && prof.terminalUrl, zacks: "Data provided by Zacks Investment Research, Inc., www.zacksdata.com"
  }));
}
