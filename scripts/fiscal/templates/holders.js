async () => {
  // 13F 기관 보유(지정 분기, 2쪽까지 = 최대 2,000 기관) + 내부자 거래 — 바이사이드 층·조용한 매집.
  // 13F는 분기 말 뒤 45일 안에 공개된다(지연). __YEAR__·__QUARTER__ = 최근 공개 분기(예 2026, 2). sharesChange = 직전 분기 대비.
  const k = "__KEY__", Y = __YEAR__, Q = __QUARTER__;
  const [a1, a2, ins] = await Promise.allSettled([
    codemode.company_institutional_holders({ companyKey: k, year: Y, quarter: Q, pageNumber: 1 }),
    codemode.company_institutional_holders({ companyKey: k, year: Y, quarter: Q, pageNumber: 2 }),
    codemode.company_insider_transactions({ companyKey: k })]);
  const rows = r => r.status === "fulfilled" ? ((r.value && r.value.data) || []) : [];
  const A = rows(a1).concat(rows(a2));
  const total = a1.status === "fulfilled" && a1.value.pagination ? a1.value.pagination.totalCount : A.length;
  const sum = (rs, f) => rs.reduce((s, h) => s + (h[f] || 0), 0);
  const up = A.filter(h => (h.sharesChange || 0) > 0), down = A.filter(h => (h.sharesChange || 0) < 0);
  const newPos = A.filter(h => h.sharesChange != null && h.shares && h.sharesChange === h.shares).length;
  const top = A.slice().sort((x, y) => (y.sharesChange || 0) - (x.sharesChange || 0)).slice(0, 5)
    .map(h => ({ holder: h.holderName, chg: h.sharesChange, chg_pct: h.sharesChangePercent, pct_out: h.percentOfSharesOutstanding }));
  const tx = rows(ins).slice(0, 20).map(t => ({ date: t.transactionDate, who: t.holderName, title: t.title, type: t.transactionType, ad: t.acquiredDisposed, shares: t.shares, value: t.transactionValue }));
  const open = rows(ins).filter(t => /Open Market/.test(t.transactionType || ""));
  console.log(JSON.stringify({ quarter: `${Y}Q${Q}`, holders: total, covered: A.length, shares: sum(A, "shares"), net_change: sum(A, "sharesChange"),
    increased: up.length, decreased: down.length, new_positions: newPos, top_buyers: top,
    insider_open_market: { buys: open.filter(t => t.acquiredDisposed === "acquired").length, sells: open.filter(t => t.acquiredDisposed === "disposed").length }, insider: tx,
    errors: [a1, a2, ins].filter(r => r.status === "rejected").map(r => String(r.reason && r.reason.message || r.reason).slice(0, 120)) }));
}
