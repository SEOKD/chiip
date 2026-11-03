async () => {
  // 분기 손익 시계열(마스터 지시 2026-11-03 — 거시 지표 싱크로율·매출→GP 비용 다리) — __KEY__ 를 회사 키(예 NASDAQ_TTMI)로 바꾼다.
  // 최근 20개 분기(오래된 것부터) 매출·매출원가·매출총이익·판관비·연구개발·감가상각·기타 영업비용·영업이익.
  // 출력 JSON을 파일로 저장 → py scripts/tenbagger/quarters.py --put <회사 id> <파일>
  const k = "__KEY__";
  const r = await codemode.company_financials_standardized({ statementType: "income-statement", companyKey: k, periodType: "quarterly" });
  const v = (d, m) => d.metricsValues[m] && d.metricsValues[m].value != null ? d.metricsValues[m].value : null;
  const d0 = (r && r.data) || [];
  const q = d0.slice(0, 20).reverse().map(d => ({ period: d.reportDate, rev: v(d, "income_statement_total_revenues"), cogs: v(d, "income_statement_cost_of_sales"),
    gp: v(d, "income_statement_gross_profit"), sga: v(d, "income_statement_selling_general_and_administrative_expenses"),
    rd: v(d, "income_statement_research_and_development_expenses"), da: v(d, "income_statement_depreciation_and_amortization_expenses"),
    other: v(d, "income_statement_other_operating_expenses"), op: v(d, "income_statement_operating_profit") }));
  console.log(JSON.stringify({ key: k, source: "Fiscal.ai company_financials_standardized", currency: (d0[0] && d0[0].metricsValues.income_statement_total_revenues || {}).currency || null, q }));
}
