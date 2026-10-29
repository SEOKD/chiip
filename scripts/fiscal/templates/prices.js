async () => {
  // 일봉 최근 260거래일 + 월봉 최근 120개월 CSV — Fiscal.ai 일봉에는 고가·저가가 없어 max/min(시가, 종가)로 근사한다.
  // 출력 텍스트를 파일로 저장 → py scripts/fiscal/adapter.py --ohlcv <id> <파일>
  const k = "__KEY__";
  const px = await codemode.company_stock_prices({ companyKey: k });
  const rows = (px.prices || []).filter(p => p.closePrice != null).sort((a, b) => a.date < b.date ? -1 : 1);
  const r2 = x => x == null ? "" : Math.round(x * 100) / 100;
  const daily = rows.slice(-260).map(p => {
    const o = p.openPrice == null ? p.closePrice : p.openPrice;
    return [p.date, r2(o), r2(Math.max(o, p.closePrice)), r2(Math.min(o, p.closePrice)), r2(p.closePrice), p.volume || 0].join(",");
  });
  const m = {};
  rows.forEach(p => {
    const key = p.date.slice(0, 7), o = p.openPrice == null ? p.closePrice : p.openPrice, b = m[key];
    if (!b) m[key] = { d: p.date, o, h: Math.max(o, p.closePrice), l: Math.min(o, p.closePrice), c: p.closePrice, v: p.volume || 0 };
    else { b.h = Math.max(b.h, o, p.closePrice); b.l = Math.min(b.l, o, p.closePrice); b.c = p.closePrice; b.v += p.volume || 0; }
  });
  const monthly = Object.keys(m).sort().slice(-120).map(key => { const b = m[key]; return [b.d, r2(b.o), r2(b.h), r2(b.l), r2(b.c), b.v].join(","); });
  console.log("#daily\ndate,o,h,l,c,v\n" + daily.join("\n") + "\n#monthly\ndate,o,h,l,c,v\n" + monthly.join("\n"));
}
