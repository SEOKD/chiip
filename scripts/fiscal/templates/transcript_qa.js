async () => {
  // 어닝콜 Q&A 구간의 애널리스트 질문만(소속·첫 300자) — 셀사이드 내러티브의 초점·직전 콜 대비 질문 변화.
  // __EVENT__ = q3-2026 형식(연간 실적은 q4). 트랜스크립트는 라이선스 자료: 요지만 자기 말로, 인용 15단어 이하.
  const k = "__KEY__", ev = "__EVENT__";
  let t;
  try { t = await codemode.company_ir_events_transcript({ companyKey: k, eventKey: ev }); }
  catch (e) { console.log(JSON.stringify({ event: ev, error: String(e && e.message || e).slice(0, 160) })); return; }   // 콜 당일은 아직 없을 수 있다 — 다음 회차에
  const who = Object.fromEntries((t.speakers || []).map(s => [s.speaker, s]));
  const qa = (t.sections || []).find(s => s.sectionType === "qa");
  const inQa = p => !qa || p.start == null || (p.start >= (qa.start || 0) && (qa.end == null || p.start <= qa.end));
  const paras = ((t.transcript && t.transcript.paragraphs) || []).filter(inQa);
  const questions = paras.filter(p => (who[p.speaker] || {}).speakerType === "analyst")
    .map(p => ({ name: (who[p.speaker] || {}).name, firm: (who[p.speaker] || {}).company, q: p.text.slice(0, 300) }));
  console.log(JSON.stringify({ event: t.event, speakers: (t.speakers || []).length, qa_found: !!qa, questions: questions.slice(0, 30) }));
}
