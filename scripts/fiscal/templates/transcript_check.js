async () => {
  // 어닝콜 전문 신규 게재 확인 — `py radar/transcript_watch.py --code`가 __ITEMS__([{key, event}])를 채워 준다(마스터 지시 2026-10-30
  // "어닝 콜이 끝나도 Fiscal.ai에 스크립트가 올라오는 데 딜레이가 있다 — 새로 올라오면 정리하라"). 본문은 받지 않고 있음·화자 수·Q&A 유무만.
  // 출력 → 파일 → `py radar/transcript_watch.py --put <파일>`. 트랜스크립트는 라이선스 자료 — 요지만 자기 말로, 인용 15단어 이하.
  const ITEMS = __ITEMS__;
  const found = [], missing = [], errors = [];
  const one = async it => {
    try {
      const t = await codemode.company_ir_events_transcript({ companyKey: it.key, eventKey: it.event });
      const paras = ((t.transcript && t.transcript.paragraphs) || []).length;
      if (!paras) { missing.push(it.key + "|" + it.event); return; }
      found.push({ key: it.key, event: it.event, date: (t.event && (t.event.eventDate || t.event.date)) || null, speakers: (t.speakers || []).length,
        paragraphs: paras, qa: !!(t.sections || []).find(s => s.sectionType === "qa") });
    } catch (e) {
      const m = String(e && e.message || e);
      if (/not found|invalid event key/i.test(m)) missing.push(it.key + "|" + it.event); else errors.push(it.key + "|" + it.event + ": " + m.slice(0, 100));
    }
  };
  for (let i = 0; i < ITEMS.length; i += 6) await Promise.all(ITEMS.slice(i, i + 6).map(one));   // 동시 6개 이하
  console.log(JSON.stringify({ checked: ITEMS.length, found, missing, errors }));
}
