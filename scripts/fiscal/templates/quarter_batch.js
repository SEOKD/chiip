async () => {
  // 분기 결산 산업 리포트 일괄 수집(radar/industry_quarter.py --plan이 __KEYS__를 채운다, ADR-018).
  // 종목마다: 분기 손익(최근 6) · 재고(재무상태표) · CAPEX(현금흐름) · 다음 분기·다음 회계연도 컨센서스. 본문은 남기지 않고 숫자만.
  const KEYS = __KEYS__;
  const out = [];
  const val = (d, m) => d && d.metricsValues && d.metricsValues[m] && d.metricsValues[m].value != null ? d.metricsValues[m].value : null;
  const one = async kk => {
    const cands = Array.isArray(kk) ? kk : [kk];   // 키를 모르는 미국 종목은 [NASDAQ_x, NYSE_x]를 차례로
    let k = cands[0];
    try {
      for (const c of cands) { try { const p = await codemode.company_profile({ companyKey: c }); if (p) { k = c; break; } } catch (e) {} }
      const [is, bs, cf, es] = await Promise.all([
        codemode.company_financials_standardized({ statementType: "income-statement", companyKey: k, periodType: "quarterly" }),
        codemode.company_financials_standardized({ statementType: "balance-sheet", companyKey: k, periodType: "quarterly" }).catch(() => null),
        codemode.company_financials_standardized({ statementType: "cash-flow-statement", companyKey: k, periodType: "quarterly" }).catch(() => null),
        codemode.company_estimates({ companyKey: k }).catch(() => null)]);
      const q = ((is && is.data) || []).slice(0, 6).map(d => ({ period: d.reportDate, rev: val(d, "income_statement_total_revenues"), gp: val(d, "income_statement_gross_profit"),
        cogs: val(d, "income_statement_cost_of_sales"), op: val(d, "income_statement_operating_profit") }));
      const inv = ((bs && bs.data) || []).slice(0, 6).map(d => ({ period: d.reportDate, inventory: val(d, "balance_sheet_inventories") ?? val(d, "balance_sheet_inventory") }));
      const capex = ((cf && cf.data) || []).slice(0, 6).map(d => ({ period: d.reportDate, capex: val(d, "cash_flow_statement_purchases_of_property_plant_and_equipment") ?? val(d, "cash_flow_statement_capital_expenditure") }));
      const e = ((es && es.data) || []);
      const nextQ = e.find(x => x.periodType === "Quarterly" && !(x.metricsValues.revenue && x.metricsValues.revenue.actual != null));
      const nextY = e.find(x => x.periodType === "Annual" && !(x.metricsValues.revenue && x.metricsValues.revenue.actual != null));
      const mean = x => x && x.metricsValues.revenue ? x.metricsValues.revenue.mean : null;
      out.push({ key: k, asked: kk, currency: ((is && is.data && is.data[0] && is.data[0].metricsValues.income_statement_total_revenues) || {}).currency || null, q, inv, capex,
        next_q: nextQ ? { period: nextQ.periodEndDate || nextQ.fiscalPeriod || null, rev: mean(nextQ) } : null,
        next_fy: nextY ? { period: nextY.periodEndDate || nextY.fiscalPeriod || null, rev: mean(nextY) } : null });
    } catch (err) {
      out.push({ key: k, asked: kk, error: String(err && err.message || err).slice(0, 120) });
    }
  };
  for (const k of KEYS) await one(k);   // 종목당 4호출을 동시에 — 동시 6개 이하를 지키려고 종목은 하나씩
  console.log(JSON.stringify(out));
}
