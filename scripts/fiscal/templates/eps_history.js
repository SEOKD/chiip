async () => {
  // EPS 추정 변경 이력(Zacks) — 텐배거 리포트 그림 5(지난 12개월 EPS 리비전 추이)·그림 8(최근 4개 분기 주가 분해)의 재료(마스터 지시 2026-10-30).
  // 출력 → 파일 저장 → py scripts/fiscal/adapter.py --eps-history <id> <파일> → datapack consensus.eps_history. Zacks 수치라 표기 의무.
  const k = "__KEY__";
  const z = await codemode.company_analyst_estimates({ companyKey: k, history: true });
  const cut = new Date(Date.now() - 500 * 864e5).toISOString().slice(0, 10);   // 지난해 진행 중이던 회계연도까지
  const rows = (z.history || []).filter(h => h.metricId === "analyst_eps" && h.reportDate >= cut)
    .map(h => [h.periodType === "Annual" ? "A" : "Q", h.reportDate, h.asOf, h.mean, h.numEstimates]);
  // 추정치 수정 폭 재료(2026-11-14) — 열린 기간, 4개 지표, 최근 100일 + 그 앞 마지막 값. scripts/tenbagger/breadth.py가 계산
  const today = new Date().toISOString().slice(0, 10), c100 = new Date(Date.now() - 100 * 864e5).toISOString().slice(0, 10);
  const M = ["analyst_eps", "analyst_revenue", "analyst_ebitda", "analyst_ebit"], base = {}, recent = [];
  for (const x of (z.history || []).filter(x => M.includes(x.metricId) && x.reportDate && x.reportDate > today)) {
    const s = `${x.metricId}|${x.periodType}|${x.reportDate}`;
    if (!x.asOf || x.asOf < c100) base[s] = x; else recent.push(x);
  }
  const breadth_rows = [...Object.values(base), ...recent].map(x => [x.metricId, x.periodType === "Annual" ? "A" : "Q", x.reportDate, x.asOf, x.mean, x.numEstimates]);
  console.log(JSON.stringify({ basis: z.epsBasis, updatedAt: z.updatedAt, rows, breadth_rows, asOf: today,
    source: "Fiscal.ai company_analyst_estimates history(Zacks). Data provided by Zacks Investment Research, Inc., www.zacksdata.com" }));
}
