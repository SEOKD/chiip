async () => {
  // 종목 뉴스(최근 14일) 또는 전 종목 톱뉴스(최근 7일) 중 중요도 1~2만 — __KEY__ 가 빈 문자열이면 top_news.
  // 판단 재료일 뿐 사실이 아니다: sourceUrl·공시로 확인한다(뉴스 헤드라인 → 사실 금지).
  const k = "__KEY__";
  const r = k ? await codemode.company_news({ companyKey: k }) : await codemode.top_news({});
  const arr = Array.isArray(r) ? r : (r.data || r.articles || []);
  const out = arr.filter(a => (a.importance == null ? 5 : a.importance) <= 2).slice(0, 15)
    .map(a => ({ date: a.date, type: a.eventType, imp: a.importance, title: a.title, summary: (a.summary || "").slice(0, 300), url: a.sourceUrl, company: a.companyKey || k || null }));
  console.log(JSON.stringify(out));
}
