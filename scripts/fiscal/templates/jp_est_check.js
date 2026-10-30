async () => {
  // 일본 종목 실적 ①의 (est. …) 가능 여부(마스터 지시 2026-10-30 "일본 주식종목의 실적 지표에도 컨센서스를 (est. )로 붙여라 — Fiscal.ai에서").
  // __KEYS__ = ["XJPX_6981", …] — 일본 상장 키는 'XJPX_<코드>'(TSE_ 아님), 미국 상장 일본 기업은 NYSE_SONY처럼 미국 키.
  // 2026-10-30 확인: 감시 일본 60종목 중 Fiscal에 키가 있는 17곳도 company_estimates·Zacks·주가 모두 '아직 없음'
  // (Fiscal의 일본 재무·추정은 미국 상장 기업만 — 도요타·소니·MUFG 등). 키마다 est가 생기면 earnings_est.js에 그 키를 넣어 쓴다.
  const keys = __KEYS__, out = {};
  for (let i = 0; i < keys.length; i += 3) {
    await Promise.all(keys.slice(i, i + 3).map(async k => {
      const r = {};
      try { const e = await codemode.company_estimates({ companyKey: k }); r.fiscal = e.data.filter(d => d.periodType === "Quarterly").length; }
      catch (x) { r.fiscal = String(x.message || x).slice(0, 40); }
      try { const a = await codemode.company_analyst_estimates({ companyKey: k }); r.zacks = a.data.length; }
      catch (x) { r.zacks = String(x.message || x).slice(0, 40); }
      out[k] = r;
    }));
  }
  console.log(JSON.stringify(out));   // 숫자 = 쓸 수 있음(분기 칸 수), 글자 = 없음 사유
}
