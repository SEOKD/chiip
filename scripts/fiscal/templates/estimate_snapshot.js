async () => {
  // 발표가 다가온 종목의 Fiscal.ai 추정을 매일 얼려 둔다(마스터 지시 2026-11-01). company_estimates는 지난 분기의 발표 전 추정을 남기지 않아 서프라이즈 표가 2순위로 내려간다.
  // `py scripts/fiscal/estimates.py --code`가 __KEYS__를 채운다. 출력 → 파일 → `py scripts/fiscal/estimates.py --put <파일>`
  const KEYS = __KEYS__;
  const M = ["revenue", "eps_adjusted", "eps_gaap", "ebit_adjusted", "ebitda_adjusted"];
  const rows = [], errors = [];
  const one = async k => {
    try {
      const fe = await codemode.company_estimates({ companyKey: k });
      const d = (fe.data || []).find(x => x.periodType === "Quarterly" && !(x.metricsValues.revenue && x.metricsValues.revenue.actual != null));
      if (!d) return;
      const metrics = {};
      for (const m of M) {
        const c = d.metricsValues[m];
        if (c && c.mean != null) metrics[m] = { mean: c.mean, source: c.source, basis: c.basis, asOf: c.asOf };
      }
      rows.push({ key: k, reportDate: d.reportDate, period: `${d.calendarYear}Q${d.calendarQuarter}`, currency: fe.currency || null, metrics });
    } catch (e) { errors.push(`${k}: ${String(e.message || e).slice(0, 80)}`); }
  };
  for (let i = 0; i < KEYS.length; i += 6) await Promise.all(KEYS.slice(i, i + 6).map(one));   // 동시 6개 이하
  console.log(JSON.stringify({ rows, errors }));
}
