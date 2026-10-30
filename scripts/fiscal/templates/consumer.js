async () => {
  // 소비재·IP 국면 판정 재료(Chiip Consumer, 마스터 지시 2026-10-30) — __KEY__ 를 회사 키(config/consumer.yaml fiscal, 예 NYSE_ELF)로 바꾼다.
  // 분기 매출·매출총이익·재고 최근 12개 분기(오래된 것부터) + 시가총액·EV/매출·애널리스트 수.
  // 출력 JSON을 파일로 저장 → py scripts/discovery/consumer.py --put <id> <파일>
  const k = "__KEY__";
  const s = r => r.status === "fulfilled" ? r.value : null;
  const [is, bs, rat, mc, evs] = (await Promise.allSettled([
    codemode.company_financials_standardized({ statementType: "income-statement", companyKey: k, periodType: "quarterly" }),
    codemode.company_financials_standardized({ statementType: "balance-sheet", companyKey: k, periodType: "quarterly" }),
    codemode.company_analyst_ratings({ companyKey: k }),
    codemode.company_daily_ratios({ companyKey: k, ratioId: "calculated_market_cap" }),
    codemode.company_daily_ratios({ companyKey: k, ratioId: "ratio_ev_to_sales" })])).map(s);
  const v = (d, m) => d && d.metricsValues[m] && d.metricsValues[m].value != null ? d.metricsValues[m].value : null;
  const inv = {};
  ((bs && bs.data) || []).forEach(d => { inv[d.reportDate] = v(d, "balance_sheet_inventories"); });
  const q = ((is && is.data) || []).slice(0, 12).reverse().map(d => ({ period: d.reportDate, revenue: v(d, "income_statement_total_revenues"),
    gross_profit: v(d, "income_statement_gross_profit"), inventory: inv[d.reportDate] != null ? inv[d.reportDate] : null, earnings_date: d.earningsDate || null }));
  const first = a => (a && a.length) ? a[0].ratio : null;   // 일별 배수는 최신이 앞
  console.log(JSON.stringify({ key: k, source: "Fiscal.ai company_financials_standardized", currency: (is && is.data && is.data[0] && is.data[0].metricsValues.income_statement_total_revenues || {}).currency || null,
    q, mcap: first(mc), ev_sales: first(evs), n_analysts: rat && rat.rating ? rat.rating.numAnalysts : null }));
}
