# 대만 법설회·홍콩 실적 브리핑 Q&A 확보 절차 — 출처 등급·접근 판정·IR 프로필

> 마스터 지시(2026-10-30, 대만 지시문·홍콩 지시문 원문 제공). 일본 절차(`jp_ir_qa_procedure.md`)와 같은 출처 등급 A~E를 쓴다 — **가이던스·수치는 A·B로만 확정, C~E는 톤·맥락 참고.**
> 수집(결정론): 대만은 `radar/pollers/tw_disclosure.py`가 TWSE OpenAPI 重大訊息에서 '召開法人說明會' 공고를 🎙로 표시하고 `radar/state/tw_ir_profile.json`에 쌓는다. 홍콩은 아직 감시 종목이 없어 수집기 없음 — 커버리지에 들어오면 이 절차를 모델이 수행한다. 판단·대체 경로는 펄스 ⑥ IR 질의응답(모델).

## 출처 등급 (일본과 같음)
| 등급 | 대만 | 홍콩 |
|---|---|---|
| A | 簡報(中/英)·회사 逐字稿·월별 매출(每月營收) | results announcement·발표자료·회사 전사 |
| B | 회사 Q&A/問答 요지 | cninfo 投资者关系活动记录表(业绩说明会)·上证路演中心·全景网 텍스트 문답 |
| C | Seeking Alpha·GuruFocus·roic.ai·StockAnalysis 전사 | StockAnalysis·GuruFocus·Quartr·reportify.cn·Seeking Alpha |
| D | MOPS 影音·IR 웹캐스트·TWSE WebPro 녹화 자체 전사 | 웹캐스트 다시보기 자체 전사 |
| E | 經濟日報·工商時報·MoneyDJ·鉅亨網·科技新報·DIGITIMES·自由時報 재구성 | 信報·HKET·明報·阿斯達克·财新·第一财经·证券时报·Bloomberg·Reuters·SCMP 재구성 |

## 접근 판정 (2026-10-30 확인 — 바뀌면 다시 본다)
| 원천 | 판정 | 쓰는 법 |
|---|---|---|
| TWSE OpenAPI 重大訊息(t187ap04_L) | 공식 공개 API | 수집기 자동(召開法人說明會 감지) |
| MOPS 신 사이트(mops.twse.com.tw) | robots.txt 없음(404), 화면은 스크립트 기반 | 모델이 건별로 열람만(法人說明會一覽表 t100sb07_1·影音連結), 자동 반복 수집 안 함 |
| MOPS 구 사이트(mopsov.twse.com.tw) | robots 전면 금지(User-Agent *) | **쓰지 않음** |
| HKEXnews | robots.txt 응답이 HTML(규칙 확인 불가) | 모델이 건별 열람만(종목코드 검색·실적 전후 2주 공시) |
| cninfo(巨潮资讯) | robots 응답 오류(확인 불가) | 건별 열람 전 robots 재확인, 안 되면 上证路演·全景网으로 |
| 上证路演中心(roadshow.sseinfo.com) | robots 전부 허용 | 텍스트 문답 열람 |
| 全景网(rs.p5w.net) | robots 전부 허용 | 텍스트 문답 열람 |
| StockAnalysis | 허용(/e/·/p/ 제외) | 전사 목록(/quote/tpe/{코드}·/quote/hkg/{코드}/transcripts), 유료 구역 열지 않음 |
| GuruFocus | 일반 페이지 허용(/_api/·/forum/ 등 금지) | 공개 페이지만 |
| roic.ai | robots 리다이렉트(확인 못 함) | 열람 시 robots 확인 후 |
| Seeking Alpha | robots가 AI 수집기 차단 | 색인 제목만 |
| 대만·홍콩 언론 | 유료벽 우회 금지 | 공개 부분·제목, 발언자·매체·날짜 필수 |
| 영상(D) | 음성 인식 도구 미가동(TODO_MASTER 승인 대기) · YouTube 내려받기 금지 | 영상 주소·길이·언어 전환·Q&A 시작 시각만 기록 |

## 대만 — 法人說明會(법설회)
0. **Fiscal.ai 먼저**: `company_ir_events`·트랜스크립트(미국 ADR이 있으면 ADR 키로도 — 예 TSM·UMC·ASX). 있으면 기본 자료로 쓰고 1~2단계는 대조용.
1. **MOPS로 법설회 특정**: 法人說明會一覽表에서 개최일시·장소(自辦/受邀)·擇要訊息·簡報(中/英)·影音連結. 重大訊息 '召開法人說明會' 공고(수집기 🎙 항목)에서 影音 업로드 예정일·주최 증권사. **受邀(증권사 초청)는 영상이 없을 수 있다** — 주최 증권사·행사명을 적어 둔다.
2. **기업 IR 사이트(중문·영문 모두)**: 검색어 '{회사명} 法說會 逐字稿'·'{회사명} 法說會 影音'·'{영문명} investor conference transcript'·'{영문명} earnings conference call webcast'. 우선순위 transcript/逐字稿 > Q&A/問答 > webcast/影音 > presentation/簡報.
3. **영상 전사(D)**: MOPS 影音·IR 웹캐스트·TWSE WebPro 녹화 중 하나라도 있으면 — 도구 승인 전엔 주소·길이만. 대만 법설회는 중·영 혼용이 많다: 언어 전환 구간, 발표부·問答 시작 시각을 기록.
4. **제3자 전사(C)**: 중문 발언이 '[foreign language]'로 빠진 경우가 있어 영상·보도와 대조.
5. **언론 재구성(E)**: 검색어 '{회사명} 法說會'·'法說會 展望'·'法說會 Q&A'·'{회사명} 總經理 表示 {키워드}'·'{회사명} 財務長 指出'. 대만 매체는 당일 문답을 주제별로 재구성한 기사를 많이 낸다.
6. **보완**: 월별 매출(每月營收, `src-twse-monthly`)로 법설회 가이던스를 대조(대만 특유의 검증 수단) · 주주총회 議事錄·年報 경영진 메시지 · 법설회가 연 1~2회뿐이면 최근 법설회 + 월매출 추이 + 보도로 분기 판단을 대신한다.
7. **모두 실패**: 'Q&A 미확보' + 發言人 문의 메일 **초안만**(outputs/report/tw_qa/drafts/, 발송은 마스터 몫).
- **IR 프로필**: 법설회 빈도(분기/반기/연 — 수집기가 공고 수로 1차 계산, 첫해는 과소)·自辦/受邀·영상 유무·언어·전문 게재 여부·미국 ADR 여부.

## 홍콩 — 실적 브리핑
0. **종목 유형 분류**(`config/coverage.yaml hk_type`): A 미국 동시상장 · B A+H 동시상장 · C 본토 기업 H주 단독 · D 홍콩 현지 기업. 유형에 맞는 경로부터 간다.
1. **HKEXnews로 브리핑 특정**: 종목코드로 실적 발표 전후 2주 공시. 키워드 results briefing·results presentation·conference call·webcast·業績說明會·业绩说明会·網上直播. 일시·웹캐스트 URL·다시보기 기간·사전 질문 이메일·출석 경영진. results announcement·발표자료는 함께(A).
2. **유형별 Q&A 경로**:
   - A: Fiscal.ai → IR 아카이브 웹캐스트 → Seeking Alpha(제목). 중문 콜·영문 콜을 따로 하는 회사는 둘 다.
   - B: cninfo에서 A주 코드 + '投资者关系活动记录表'('业绩说明会' 체크 문서에 문답, B) · 上证路演中心·全景网·中国证券网路演中心 행사 페이지 텍스트 문답(B). **애널리스트용 별도 콜이 주 자료** — 리테일용 텍스트 문답과 구분.
   - C: 공시의 웹캐스트 플랫폼(roadshowchina.cn 등) 다시보기 → 전사(D).
   - D: IR 웹캐스트 → 전사, 또는 제3자 전사(C~D).
3. **제3자 전사(C)**: StockAnalysis·GuruFocus·Quartr·reportify.cn·Seeking Alpha.
4. **언론 재구성(E)**: 검색어 '{회사명} 業績會'·'{회사명} 业绩会 管理层'·'{회사명} 分析師會'·'{영문명} earnings call said'.
5. **보완**: 홍콩은 반기 보고가 기본 — 분기 자료가 없으면 자발적 분기 업데이트(voluntary announcement·operational update)와 투자자 행사 자료. 주주총회 문답·investor day를 같은 논점으로 연결.
6. **모두 실패**: 'Q&A 미확보' + 공시의 IR 이메일 문의 **초안만**(outputs/report/hk_qa/drafts/).
- **IR 프로필**: 종목 유형(A~D)·다른 상장 코드·브리핑 플랫폼·다시보기 기간·언어(광둥어/보통화/영어).

## 공통 기록 규칙
- 모든 인용에 원문 URL·페이지 또는 타임스탬프, 발언자 직책. 질문자 미공개면 '질문자 미공개'(추측 금지).
- 중문 원문은 보존하고 한국어 번역 병기(번역은 증거가 아님). 원문 전체를 노션·저장소에 복제하지 않는다(요지·15단어 이하 인용·링크).
- 출력: `outputs/report/tw_qa/<YYYYMMDD>_<코드>.md`·`outputs/report/hk_qa/<YYYYMMDD>_<코드>.md` — 일본과 같은 7항목(숫자·AI 수요·톤·바뀐 말·질문 초점·피한 질문·밸류 다리), 줄마다 등급.
- IR 프로필은 노션 '아시아 IR 프로필'(구 '일본 IR 프로필', `config/notion.yaml jp_ir_profile`)에 시장별 행으로 동기화.
