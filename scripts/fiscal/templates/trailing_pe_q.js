async () => {
  // 분기말 후행 P/E(최근 4개 분기) — 대상·동종 같은 잣대(2026-11-19 BELFB: Fiscal.ai에 Zacks 컨센서스가 없어 대상 Fwd 1Y 이력이 비고
  // 멀티플 프리미엄이 현재값 1개만 나왔다). forward_multiples.js의 대상 history가 비면 이것을 돌린다.
  // 값 = Fiscal.ai company_ratios(periodType ltm) ratio_price_to_earnings — 분기말 가격 ÷ 최근 4개 분기 GAAP EPS. 음수·없음은 버린다.
  // 출력 → 파일 저장 → py scripts/fiscal/adapter.py --trailing-pe <id> <파일> → datapack history.pe_ttm · peers[].hist_q[].pe_ttm
  const k = "NASDAQ_BELFB";
  const peers = ["NASDAQ_VICR", "NASDAQ_AEIS", "NASDAQ_LFUS", "NYSE_APH", "NYSE_TEL"];   // datapack peers[].key
  const q = async key => {
    const r = await codemode.company_ratios({ companyKey: key, periodType: "ltm", ratioId: "ratio_price_to_earnings" }).catch(() => ({ data: [] }));
    return (r.data || []).map(x => ({ date: x.reportDate, pe_ttm: (x.metricValues || {}).ratio_price_to_earnings }))
      .filter(x => x.date && typeof x.pe_ttm === "number" && x.pe_ttm > 0)
      .sort((a, b) => (a.date < b.date ? -1 : 1)).slice(-4)
      .map(x => ({ date: x.date, pe_ttm: Math.round(x.pe_ttm * 100) / 100 }));
  };
  const out = { key: k, target: await q(k), peers: {} };
  for (const p of peers) out.peers[p] = await q(p);
  out.source = "Fiscal.ai company_ratios LTM ratio_price_to_earnings(분기말 가격 ÷ 최근 4개 분기 GAAP EPS)";
  console.log(JSON.stringify(out));
}
