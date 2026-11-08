# Chiip Flow — 미국 장초·장마감 섹터 로테이션 (예약 작업 chiip-midterm-intraday, 표시 이름 Chiip Flow)

마스터 지시(2026-11-08): "Chiip Midterm은 앞으로 Chiip Flow로 이름을 바꾸고 미국 주식 시장의 장초, 장마감 섹터 로테이션 흐름을 관측하도록 해라."
이전 지시(2026-11-07)를 잇는다: 장초·장마감만 보고, 장중에는 보내지 않는다. 중간선거 관측 기간 제한은 없앴다(상시).

회차: 장초 = ET 09:45(개장 15분 뒤), 장마감 = ET 15:45(조기 폐장일 12:45). 서머타임·NYSE 휴장일은 엔진이 거른다.
예약은 KST 02·04·05·22·23시 45분에 깨지만, 체크포인트 ±40분이 아니면 '장외'로 바로 끝난다(겨울: 23:45·05:45, 여름: 22:45·04:45).
계산은 `radar/markets/sector_flow.py`(설정 `config/chiip_flow.yaml`), 모델은 결론 한두 문장만 쓴다.

1. `py radar/markets/sector_flow.py --session` → '장외'면 아무것도 하지 말고 즉시 끝낸다.
2. `py radar/markets/sector_flow.py --symbols`의 심볼 목록(50개 이하)을 TradingView `mcp-tv-get-symbol-data-batch` **한 번**으로 받는다. columns: ["close","change","change_from_open","volume","relative_volume_10d_calc"]. 응답 JSON 전체를 스크래치 파일에 저장한다. 실패하면 조용히 끝낸다. `missing`이 있으면 본문 맨 아래 '빠진 심볼 n개'만 적는다.
3. `py radar/markets/sector_flow.py --tick <응답 파일> --out <본문 파일>` — 유입·유출 상위 3(SPY 대비 초과 × 상대 거래량), 로테이션 축 7개(경기민감↔방어, 성장↔가치, 소형↔대형, 고베타↔저변동, 반도체↔소프트웨어, 시장 폭, 신용), 교차 자산, 얇은 상승, 장마감이면 장초 대비 유지·반전·새 유입과 연속 유입 상위(다일 로테이션)까지 본문을 엔진이 만든다.
4. 본문의 `{해석}` 한 자리만 채운다 — 한두 문장, '~다'로 끝맺는다. 돈이 어디서 어디로 가는지(축 2~3개가 같은 쪽을 가리키면 그것이 오늘의 로테이션), 교차 자산(국채·달러·VIX·하이일드)이 같은 방향인지 엇갈리는지. 원인 뉴스는 1차 출처로 확인된 것만 쓰고, 없으면 쓰지 않는다(금지표: 주가 급등 → 펀더멘털 변화). 다른 줄은 고치지 않는다.
5. 텔레그램 1통: `py -c "import sys;sys.path.insert(0,'radar');import notify;notify.send(open(r'<본문 파일>',encoding='utf-8').read(),'PULSE')"`.
6. 기록: `outputs/report/flow/<YYYYMMDD>.md`에 보낸 본문을 덧붙인다(엔진 기록은 knowledge/models/chiip_flow/log.csv·state.json).

금지: 장중 알림, D:\local-only 읽기, 필드 인텔, 로그인·유료벽 우회, '사라/팔아라'·비중·금액 지시, 공개 채널 게시, TradingView MCP 병렬 호출, git 커밋·푸시. 판단 작업은 짧게.
