async () => {
  // EPS 추정 변경 이력(Zacks) — 텐배거 리포트 그림 5(지난 12개월 EPS 리비전 추이)·그림 8(최근 4개 분기 주가 분해)의 재료(마스터 지시 2026-10-30).
  // 출력 → 파일 저장 → py scripts/fiscal/adapter.py --eps-history <id> <파일> → datapack consensus.eps_history. Zacks 수치라 표기 의무.
  const k = "__KEY__";
  const z = await codemode.company_analyst_estimates({ companyKey: k, history: true });
  const cut = new Date(Date.now() - 500 * 864e5).toISOString().slice(0, 10);   // 지난해 진행 중이던 회계연도까지
  const rows = (z.history || []).filter(h => h.metricId === "analyst_eps" && h.reportDate >= cut)
    .map(h => [h.periodType === "Annual" ? "A" : "Q", h.reportDate, h.asOf, h.mean, h.numEstimates]);
  console.log(JSON.stringify({ basis: z.epsBasis, updatedAt: z.updatedAt, rows,
    source: "Fiscal.ai company_analyst_estimates history(Zacks). Data provided by Zacks Investment Research, Inc., www.zacksdata.com" }));
}
