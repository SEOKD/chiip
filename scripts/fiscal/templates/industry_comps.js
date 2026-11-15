async () => {
  // 산업 리포트 비교 기업(comps) 재료 — Fiscal.ai 쪽(2026-11-15 마스터 지시: TradingView와 균형 있게 — 같은 종목을 mcp-tv-get-symbol-data-batch로도 받아 대조한다).
  // __KEYS__ = ["NASDAQ_NVDA", "TPE_3443", …] (config/fiscal_keys.yaml 또는 company_profile로 확인한 키). 한 번에 6곳 이하로 나눠 돌린다(동시 6호출 제한).
  // 종목마다: 시가총액·EV/매출·Fwd P/E·Fwd EV/EBITDA(Fiscal 자체 Forward → Street Forward) · 최근 4분기(TTM) 매출과 1년 전 대비 성장 ·
  // 다음 4개 분기 매출·EPS 추정 · 세그먼트 이름(겸업 노출도 판단용). 출력 → 파일로 저장해 datapack logic.comps에 옮기고 source에 'Fiscal.ai·TradingView'를 함께 적는다.
  // Fiscal.ai에 없는 종목(응답 오류)은 fiscal: "미수록"으로 남긴다.
  const KEYS = __KEYS__;
  const R = ["calculated_market_cap", "ratio_ev_to_sales", "ratio_forward_price_to_earnings", "ratio_street_forward_price_to_earnings",
             "ratio_forward_ev_to_ebitda", "ratio_street_forward_ev_to_ebitda"].join(",");
  const r2 = x => (typeof x === "number" ? Math.round(x * 100) / 100 : null);
  const one = async k => {
    try {
      const [rat, is, es, seg] = await Promise.all([
        codemode.company_ratios({ companyKey: k, periodType: "latest", ratioId: R }),
        codemode.company_financials_standardized({ statementType: "income-statement", companyKey: k, periodType: "quarterly" }),
        codemode.company_estimates({ companyKey: k }).catch(() => null),
        codemode.company_segments_and_kpis({ companyKey: k, periodType: "quarterly" }).catch(() => null)]);
      const m = (((rat && rat.data) || []).slice(-1)[0] || {}).metricValues || {};
      const v = d => d && d.metricsValues && d.metricsValues.income_statement_total_revenues ? d.metricsValues.income_statement_total_revenues.value : null;
      const q = (is && is.data) || [];
      const sum = a => (a.length === 4 && a.every(x => x != null) ? a.reduce((s, x) => s + x, 0) : null);
      const ttm = sum(q.slice(0, 4).map(v)), prev = sum(q.slice(4, 8).map(v));
      const fq = ((es && es.data) || []).filter(d => d.periodType === "Quarterly" && !(d.metricsValues.revenue && d.metricsValues.revenue.actual != null))
        .sort((a, b) => (a.reportDate < b.reportDate ? -1 : 1)).slice(0, 4);
      const epsK = es && es.primaryEpsBasis === "gaap" ? "eps_gaap" : "eps_adjusted";
      const nsum = id => (fq.length === 4 && fq.every(d => d.metricsValues[id] && d.metricsValues[id].mean != null) ? fq.reduce((s, d) => s + d.metricsValues[id].mean, 0) : null);
      const segs = seg ? seg.metrics.filter(x => x.metricType === "Segment").map(x => x.metricName).slice(0, 8) : [];
      return { key: k, currency: q[0] && q[0].metricsValues.income_statement_total_revenues ? q[0].metricsValues.income_statement_total_revenues.currency : null,
               mcap: m.calculated_market_cap || null, ev_sales: r2(m.ratio_ev_to_sales),
               pe_fwd: r2(m.ratio_forward_price_to_earnings || m.ratio_street_forward_price_to_earnings),
               ev_ebitda_fwd: r2(m.ratio_forward_ev_to_ebitda || m.ratio_street_forward_ev_to_ebitda),
               rev_ttm: ttm, rev_growth: ttm && prev ? r2(ttm / prev - 1) : null, last_q: q[0] ? q[0].reportDate : null,
               rev_ntm: nsum("revenue"), eps_ntm: r2(nsum(epsK)), eps_basis: epsK, segments: segs };
    } catch (e) {
      return { key: k, fiscal: "미수록", error: String(e && e.message || e).slice(0, 120) };
    }
  };
  const out = [];
  for (let i = 0; i < KEYS.length; i += 3) out.push(...(await Promise.all(KEYS.slice(i, i + 3).map(one))));
  console.log(JSON.stringify({ retrieved: new Date().toISOString(), rows: out,
    note: "Street Forward 배수·추정은 Zacks — 데이터 묶음에 'Data provided by Zacks Investment Research, Inc., www.zacksdata.com'" }));
}
