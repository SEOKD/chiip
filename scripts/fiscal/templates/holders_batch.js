async () => {
  // 13F 시즌 일괄 집계(radar/thirteenf.py --plan이 __KEYS__·__YEAR__·__QUARTER__를 채운다, 마스터 지시 2026-11-08).
  // 종목마다 지정 분기 기관 보유 1쪽(최대 1,000 기관 — 보유 규모 상위)에서 직전 분기 대비 늘린·줄인·새로 산·전량 판 기관 수만 센다. 이름·본문은 남기지 않는다.
  const keys = __KEYS__, Y = __YEAR__, Q = __QUARTER__;
  const out = [];
  for (const k of keys) {
    try {
      const r = await codemode.company_institutional_holders({ companyKey: k, year: Y, quarter: Q, pageNumber: 1 });
      const A = (r && r.data) || [];
      const total = r && r.pagination ? r.pagination.totalCount : A.length;
      const chg = h => h.sharesChange || 0;
      out.push({ key: k, quarter: `${Y}Q${Q}`, holders: total, covered: A.length,
        increased: A.filter(h => chg(h) > 0).length, decreased: A.filter(h => chg(h) < 0).length,
        new_positions: A.filter(h => h.sharesChange != null && h.shares && h.sharesChange === h.shares).length,
        sold_out: A.filter(h => h.shares === 0 && chg(h) < 0).length,
        net_shares: A.reduce((s, h) => s + chg(h), 0) });
    } catch (e) {
      out.push({ key: k, quarter: `${Y}Q${Q}`, error: String(e && e.message || e).slice(0, 120) });
    }
  }
  console.log(JSON.stringify(out));
}
