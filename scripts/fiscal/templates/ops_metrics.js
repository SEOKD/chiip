async () => {
  // 운영 지표 — 수주(orders·bookings)·수주잔고·재고·영업현금흐름·CAPEX·FCF 분기 이력(마스터 지시 2026-11-14 "수주/출하 비율 × 재고", "Rule of 40").
  // 출력 → 파일 → `py scripts/tenbagger/ops_view.py --put <id> <파일>` → datapack "ops". 매출·매출원가는 datapack quarters_hist를 쓴다.
  const k = "__KEY__";
  const [b, c, s, inc] = await Promise.all([
    codemode.company_financials_standardized({ companyKey: k, periodType: "quarterly", statementType: "balance-sheet" }).catch(() => null),
    codemode.company_financials_standardized({ companyKey: k, periodType: "quarterly", statementType: "cash-flow-statement" }).catch(() => null),
    codemode.company_segments_and_kpis({ companyKey: k, periodType: "quarterly" }).catch(() => null),
    codemode.company_financials_standardized({ companyKey: k, periodType: "quarterly", statementType: "income-statement" }).catch(() => null)]);
  const val = v => (v && typeof v === "object" ? v.value : v);
  const pick = (mv, re) => { const key = Object.keys(mv || {}).find(x => re.test(x)); return key ? val(mv[key]) : null; };
  const q = {};
  const row = d => (q[d.reportDate] ||= { period: d.reportDate });
  for (const d of (inc && inc.data) || []) {   // datapack quarters_hist가 없을 때 쓰는 매출·매출원가
    const r = row(d);
    r.rev = pick(d.metricsValues, /^income_statement_(total_)?revenues?$/i);
    r.cogs = pick(d.metricsValues, /^income_statement_(total_)?cost_of_(revenues?|goods_sold|sales)/i);
  }
  for (const d of (b && b.data) || []) row(d).inventory = pick(d.metricsValues, /^balance_sheet_(total_)?inventor/i);
  for (const d of (c && c.data) || []) {
    const r = row(d);
    r.ocf = pick(d.metricsValues, /cash_from_operating_activities$/i);   // 'changes_in_other_operating_activities'를 잡지 않게
    r.capex = pick(d.metricsValues, /capital_expenditure|purchase.*property/i);
    r.fcf = pick(d.metricsValues, /free_cash_flow/i);
  }
  // KPI: 'Total Orders'·'Bookings'·'Backlog' 같은 이름 — 합계가 있으면 합계 하나만 쓴다
  const ms = ((s && s.metrics) || []).filter(m => m.metricId);
  const find = re => ms.filter(m => re.test(m.metricName)).sort((a, b2) => (/total/i.test(b2.metricName) ? 1 : 0) - (/total/i.test(a.metricName) ? 1 : 0))[0];
  const om = find(/^(total )?(orders|bookings|new orders|order intake)$|total (orders|bookings)|^orders received/i);
  const bm = find(/^(total )?(backlog|remaining performance obligations?|rpo)$|total backlog/i);
  for (const d of (s && s.data) || []) {
    const r = row(d);
    if (om) r.orders = d.metricsValues[om.metricId] ?? null;
    if (bm) r.backlog = d.metricsValues[bm.metricId] ?? null;
  }
  const rows = Object.values(q).sort((a, b2) => (a.period < b2.period ? -1 : 1)).slice(-16);
  console.log(JSON.stringify({ key: k, orders_label: om ? om.metricName : null, backlog_label: bm ? bm.metricName : null, q: rows,
    source: "Fiscal.ai company_financials_standardized(재무상태표·현금흐름표)·company_segments_and_kpis" }));
}
