async () => {
  // 펀드 레터 — 이 종목을 다룬 펀드의 관계(롱·숏·신규·추가·축소·청산)·논조·확신도·비중·논지·변이 관점·촉매·위험(최신 기간 먼저).
  // 펀드 의견은 사실이 아니라 '기대의 증거'. 원문 인용(sourceQuote)은 15단어 이하로만 옮긴다.
  const k = "__KEY__";
  const r = await codemode.company_fund_letters({ companyKey: k });
  const th = (r.theses || []).slice(0, 12).map(t => ({
    fund: t.fund && t.fund.fundName, investor: t.investor && t.investor.investorName, period: t.letter && t.letter.reportPeriod, letter: t.letter && t.letter.title,
    relationship: t.relationship, stance: t.stance, conviction: t.conviction, size: t.positionSizePercent, horizon: t.timeHorizon,
    thesis: (t.thesisSummary || "").slice(0, 400), variant: (t.variantPerception || "").slice(0, 200), catalysts: (t.catalystSummary || "").slice(0, 200), risks: (t.riskSummary || "").slice(0, 200) }));
  console.log(JSON.stringify({ stats: r.stats, theses: th }));
}
