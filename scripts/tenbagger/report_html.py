"""텐배거 일일 리포트 HTML 렌더러 (마스터 지시 2026-10-29 "Chiip ten-bagger도 텐배거 종목 리포트를 쓰고 그래프로 시각화해
체계적인 자료를 html 파일로 남겨라. 오후 11시마다 하루 하나씩")

모델(예약 작업 chiip-tenbagger-report)은 내용만 JSON으로 쓰고, 모양·차트는 이 스크립트가 늘 같은 방식으로 그린다.
문자열 안의 **굵게**·__밑줄__·==형광==만 태그로 바꾸고(부호 붙은 %는 색을 자동으로) 나머지 HTML은 모두 이스케이프한다(수집한 웹 문장이 섞여도 스크립트가 끼어들지 않게).
사용: py scripts/tenbagger/report_html.py outputs/tenbagger/reports/20261029_CBRS.json   → 같은 이름 .html

JSON 구조(필수 = *):
{ "title"*, "subtitle", "date"*, "ticker"*, "company"*, "biz"* (사업 1줄), "lead",
  "verdict": {"view"*: "치입 판단 한 줄", "confidence": "고|중|저", "insight": 7, "alpha": 6.1},
  "summary": [{"q": "질문", "a": "답(**굵게** 가능)"}],
  "tiles": [{"k": "이름", "v": "값", "sub": "설명", "tone": "red|grn|blue|"}],
  "sections": [{"h2"*: "제목", "blocks": [블록...]}],
  "sources": ["출처 1", ...] }
블록 종류: {"type":"p","text"} · {"type":"ul","items":[...]} · {"type":"hl","text"} · {"type":"h3","text"}
  · {"type":"table","headers":[...],"rows":[[...]...]}
  · {"type":"chart","chart":{"kind":"line","title","unit","log":false,"series":[{"name","color":"a|b|c|d|e","points":[["2025-03",12.3,"설명"]...]}]}}
  · {"type":"chart","chart":{"kind":"bars","title","unit","categories":[...],"series":[{"name","color","values":[...]}]}}
  · {"type":"chart","chart":{"kind":"hbars","title","unit","rows":[{"label","bars":[{"name","color","value"}]}]}}
  · {"type":"chart","chart":{"kind":"scenario","title","unit","current":112.6,"cases":[{"name":"약세","value":60,"prob":0.3,"color":"b","why":"…"}]}}
  · {"type":"chart","chart":{"kind":"candle","title","unit","bars":[["2026-10-28",600,609.4,581.8,606.9]...],
       "hlines":[{"y":643.4,"label":"38.2% 643","color":"e"}],"zones":[{"y0":599,"y1":602,"label":"지지","tone":"grn|red"}]}}  — 한국식 색(상승 빨강·하락 파랑)
  · {"type":"chart","chart":{"kind":"revision","title","unit","start","end","series":[{"name","color","points":[["2026-02-26",4.2]...]}],
       "events":[{"date","mark":"①","kind":"실적|내러티브","tag","pct":"+110%"}]}}  — 계단선 + 선 위 사건 번호, 설명은 그래프 아래(revision_view.py가 만든다)
  · bars에 "stack": true면 쌓인 막대
  · 차트에 "pin": n이면 갤러리 n번째로 고정(그림 3 = 가격 내포 기대, 5 = EPS 리비전 추이, 8 = 주가 분해 — 마스터 지시 2026-10-30), 나머지는 절 순서대로
금액 단위는 렌더 직후 radar/units.py money_units로 $25B·$M·$T 표기로 바꾼다(마스터 지시 2026-10-29).
학술 논문 표기('저자 연도')는 남기지 않는다(마스터 지시 2026-10-30) — scrub()이 괄호째 지우고 출처 목록에서 빼며, 그래도 남으면 렌더가 실패한다.
데이터 제공처 이름(재무·컨센서스·어닝콜 스크립트를 가져온 곳)도 남기지 않는다. 본문 아래 부가 설명(차트·표 note, 업사이드 기준, 읽는 법)은 그리지 않는다(같은 날 마스터 지시).
전문 용어·기관 약자는 처음 나오는 곳에 '용어(한국어 풀이)'로 적는다 — config/report_glossary.yaml, gloss().
"""
import html
import json
import math
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "radar"))
from units import chiip_name, fx_units, money_units  # noqa: E402

COLORS = {"a": "var(--a)", "b": "var(--b)", "c": "var(--c)", "d": "var(--d)", "e": "var(--e)"}
# 그래프 글자가 viewBox 밖으로 나가 잘리지 않게(마스터 지시 2026-11-08 "Analysis 리포트에 글자가 양식 밖으로 빠져 나가서 잘리지 않도록 하라")
# 브라우저가 실제 글자 폭을 잰 뒤 viewBox를 글자까지 넓힌다 — 축 숫자·끝 이름표·범례가 오른쪽·왼쪽 끝에서 잘리던 문제(2026-11-08 AXTI 리포트 23곳 실측)
FIT_JS = ("<script>(function(){"
          # 그래프 글자 최소 크기(마스터 지시 2026-11-08 모바일 QA) — viewBox 폭 ÷ 화면 폭만큼 글자를 키워 화면에서 11px 이상
          "function grow(s){var w=s.clientWidth;if(!w)return;if(!s.dataset.w0)s.dataset.w0=s.viewBox.baseVal.width;var k=s.dataset.w0/w;s.querySelectorAll('text').forEach(function(t){if(!t.dataset.f0)t.dataset.f0=parseFloat(getComputedStyle(t).fontSize);var f=+t.dataset.f0;t.style.fontSize=(f/k<11?11*k:f)+'px'});var seen=[];s.querySelectorAll('text').forEach(function(t){t.style.display='';var b=t.getBBox();if(!b.width)return;if(seen.some(function(o){var dy=Math.min(b.y+b.height,o.y+o.height)-Math.max(b.y,o.y);return b.x<o.x+o.width-0.5&&o.x<b.x+b.width-0.5&&dy>0.45*Math.min(b.height,o.height)}))t.style.display='none';else seen.push(b)})}"
          "function stack(){if(!matchMedia('(max-width:640px)').matches)return;document.querySelectorAll('.w table').forEach(function(tb){if(tb.dataset.st)return;var hs=[].map.call(tb.querySelectorAll('thead th, tr:first-child th'),function(h){return h.textContent.trim()});var rs=[].filter.call(tb.querySelectorAll('tr'),function(r){return r.querySelector('td')});if(hs.length<4||!rs.length)return;var mx=0;hs.forEach(function(_,i){var n=0;rs.forEach(function(r){var c=r.children[i];n+=c?c.textContent.length:0});mx=Math.max(mx,n/rs.length)});if(mx<30)return;tb.dataset.st=1;tb.classList.add('stk');tb.querySelectorAll('tr').forEach(function(tr){[].forEach.call(tr.children,function(c,i){if(c.tagName==='TD')c.setAttribute('data-th',hs[i]||'')})})})}stack();"
          "function fit(){document.querySelectorAll('svg[viewBox]').forEach(function(s){try{grow(s);var v=s.viewBox.baseVal,x0=v.x,y0=v.y,x1=v.x+v.width,y1=v.y+v.height;"
          "s.querySelectorAll('text').forEach(function(t){var b=t.getBBox();if(!b.width)return;x0=Math.min(x0,b.x-2);y0=Math.min(y0,b.y-2);x1=Math.max(x1,b.x+b.width+2);y1=Math.max(y1,b.y+b.height+2)});"
          "if(x0<v.x||y0<v.y||x1>v.x+v.width||y1>v.y+v.height)s.setAttribute('viewBox',[x0,y0,x1-x0,y1-y0].join(' '))}catch(e){}})}"
          "if(document.readyState!=='loading')fit();else document.addEventListener('DOMContentLoaded',fit);window.addEventListener('load',fit);"
          "if(document.fonts&&document.fonts.ready)document.fonts.ready.then(fit);"
          # 접힌 절(details)은 펼칠 때 그래프 글자를 다시 재고, 목차·주소의 #s0 같은 대상은 열어서 보여 준다(2026-11-08)
          "document.querySelectorAll('details.sec').forEach(function(d){d.addEventListener('toggle',function(){if(d.open)fit()})});"
          "function openHash(){var h=location.hash&&document.getElementById(location.hash.slice(1));var d=h&&h.querySelector('details.sec');if(d)d.open=true}"
          "window.addEventListener('hashchange',openHash);openHash();"
          "document.querySelectorAll('.toc a').forEach(function(a){a.addEventListener('click',function(){var d=document.querySelector(a.getAttribute('href')+' details.sec');if(d)d.open=true})});"
          # 캔들을 누르면(마우스·터치) 그날 종가·고가·저가·시가를 차트 위 칸에 보여 주고 그 봉을 표시한다(마스터 지시 2026-11-08)
          "document.addEventListener('click',function(e){var k=e.target.closest&&e.target.closest('.ck');if(!k)return;var sv=k.ownerSVGElement,box=sv&&sv.parentNode.querySelector('.cinfo');"
          "if(!box)return;var d=k.dataset;box.innerHTML='<b>'+d.d+'</b> 종가 <b>'+d.c+'</b> · 고가 '+d.h+' · 저가 '+d.l+' · 시가 '+d.o+' <span class=\\''+(d.up==='1'?'red':'blue')+'\\'>'+d.p+'</span>';"
          "sv.querySelectorAll('.ck.on').forEach(function(x){x.classList.remove('on')});k.classList.add('on')})})();</script>")
CSS = """.idot{width:16px;height:16px;margin:-8px 0 0 -8px;border:1.5px solid;border-radius:50%;background:var(--bg);font-size:10px;font-weight:700;line-height:13px;text-align:center;opacity:.92}
.ilab{font-size:12.5px;line-height:1.35;font-weight:500;overflow-wrap:anywhere;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}.ilist{display:none;margin:8px 0 0;padding-left:0;list-style:none;font-size:14px}.ilist li{margin:2px 0}
@media (max-width:640px){.iwrap{padding:0!important}.iwrap .ilab,.iwrap .ilines{display:none}.ilist{display:block}}
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700&display=swap');
.cinfo{font-size:13px;min-height:1.6em;margin:2px 0 4px}.ck{cursor:pointer}.ck:hover,.ck.on{fill:var(--fg);fill-opacity:.08}
:root{--bg:#fff;--fg:#1a1d23;--mut:#5d6470;--line:#e6e8ec;--card:#f6f8fb;--a:#1a1d23;--b:#d0452f;--c:#2a5bd7;--d:#1f8a5b;--e:#b07d10;--hl:#fff5d6}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#14161a;--fg:#e8eaee;--mut:#9aa1ad;--line:#2b2f36;--card:#1c1f25;--a:#f2f3f5;--b:#ff7d66;--c:#7aa2ff;--d:#4cc38a;--e:#e0b04a;--hl:#2e2a1c;color-scheme:dark}}
:root[data-theme=dark]{--bg:#14161a;--fg:#e8eaee;--mut:#9aa1ad;--line:#2b2f36;--card:#1c1f25;--a:#f2f3f5;--b:#ff7d66;--c:#7aa2ff;--d:#4cc38a;--e:#e0b04a;--hl:#2e2a1c;color-scheme:dark}
body{margin:0;background:var(--bg);color:var(--fg);font-family:-apple-system,'Apple SD Gothic Neo','Malgun Gothic',sans-serif;line-height:1.8;font-size:16px}.w{max-width:820px;margin:0 auto;padding-block:20px 48px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
h1{font-size:21px;margin:0 0 4px;line-height:1.35}h2{font-size:18px;margin:30px 0 8px;padding-top:10px;border-top:2px solid var(--fg)}h3{font-size:15.5px;margin:18px 0 6px}
.lead{color:var(--mut);font-size:13.5px;margin:0 0 12px}.card{background:var(--card);border-radius:12px;padding:12px 14px;margin:12px 0}.hl{background:var(--hl);border-radius:12px;padding:12px 14px;margin:12px 0}
.ans{display:grid;grid-template-columns:1fr;gap:8px}.ans div{background:var(--card);border-radius:10px;padding:10px 12px}.ans b.q{display:block;font-size:12.5px;color:var(--mut)}
table{border-collapse:collapse;width:100%;font-size:13px;margin:6px 0}th,td{border-bottom:1px solid var(--line);padding:6px 5px;text-align:right;vertical-align:top}th:first-child,td:first-child{text-align:left}th{color:var(--mut);font-weight:600}
.tw{overflow-x:auto}th,td{overflow-wrap:break-word;word-break:keep-all}.mut{color:var(--mut)}.sm{font-size:12.5px}.red{color:var(--b)}.blue{color:var(--c)}.grn{color:var(--d)}
/* 그래프 한 줄에 하나(마스터 지시 2026-10-30 "가로 한 줄에 두 개라 작게 보인다") */.gal{display:grid;grid-template-columns:1fr;gap:8px}.gal>div{min-width:0}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;margin:10px 0}.tile{background:var(--card);border-radius:10px;padding:10px 12px}.tile .v{font-size:20px;font-weight:700}.tile .k{font-size:12px;color:var(--mut)}
svg{display:block;width:100%;height:auto}svg text{fill:var(--mut);font-size:10.5px}.lg{font-size:12.5px;color:var(--mut)}.lg i{display:inline-block;width:10px;height:10px;border-radius:2px;margin:0 4px 0 8px;vertical-align:-1px}
ul{padding-left:20px;margin:6px 0}li{margin:3px 0}.foot{color:var(--mut);font-size:12px;margin-top:26px;overflow-wrap:anywhere}.verdict{border:2px solid var(--fg);border-radius:12px;padding:12px 14px;margin:12px 0}
section{margin-top:34px}p{margin:10px 0}details{margin:10px 0}summary{cursor:pointer;color:var(--mut);font-size:13.5px;padding:6px 0}details.sec>summary{list-style:none;color:var(--fg)}details.sec>summary::-webkit-details-marker{display:none}details.sec>summary h2{display:flex;justify-content:space-between;align-items:center;gap:8px}details.sec>summary h2::after{content:"펼치기 ▾";font-size:12.5px;font-weight:500;color:var(--mut);white-space:nowrap}details.sec[open]>summary h2::after{content:"접기 ▴"}.toc{display:flex;flex-wrap:wrap;gap:6px;margin:22px 0 4px;position:sticky;top:0;background:var(--bg);padding:8px 0;z-index:5;border-bottom:1px solid var(--line)}.toc a{font-size:12.5px;color:var(--mut);text-decoration:none;border:1px solid var(--line);border-radius:999px;padding:3px 10px}.badge{display:inline-block;font-size:12px;border:1px solid var(--line);border-radius:6px;padding:0 6px;margin-right:4px;color:var(--mut)}
.dash{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin:12px 0}.dash>div{background:var(--card);border-radius:10px;padding:9px 11px;min-width:0}.dash .k{font-size:11.5px;color:var(--mut)}.dash .v{font-size:18px;font-weight:700;line-height:1.3;overflow-wrap:anywhere}.dash .s{font-size:11.5px;color:var(--mut);line-height:1.4;margin-top:2px;overflow-wrap:anywhere}
@media (max-width:640px){.dash{grid-template-columns:repeat(2,minmax(0,1fr))}}
.phs{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px;margin:10px 0}.ph{margin:0;border:1px solid var(--line);border-radius:12px;overflow:hidden;min-width:0}.ph img{display:block;width:100%;aspect-ratio:4/3;object-fit:cover;max-width:100%}.ph figcaption{padding:8px 12px;font-size:13.5px}
.boxes{display:grid;grid-template-columns:1fr;gap:10px;margin:10px 0}.bx{border:1px solid var(--line);border-radius:12px;overflow:hidden}.bx .bt{font-weight:700;padding:9px 12px;background:var(--card);display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap}.bx .tag{font-size:12px;font-weight:600;color:var(--c)}.bx .br{display:grid;grid-template-columns:66px minmax(0,1fr);gap:8px;padding:7px 12px;border-top:1px solid var(--line);font-size:13.5px}.bx .bl{color:var(--mut);font-size:12px;padding-top:1px}
.rate-buy{color:var(--b)}.rate-sell{color:var(--c)}.rate-mid{color:var(--e)}
/* PC·모바일 글자 크기(2026-11-03 마스터 지시) — 화면 폭에 따라 커지고, 휴대폰에서도 본문 15px·보조 12px 아래로 내려가지 않는다 */
body{font-size:clamp(15px,0.85rem + 0.35vw,17.5px);line-height:1.75}.w{max-width:880px}
h1{font-size:clamp(20px,1.05rem + 1vw,28px)}h2{font-size:clamp(17px,0.95rem + 0.6vw,22px)}h3{font-size:clamp(15px,0.9rem + 0.3vw,18px)}
.lead,.dash .s,.dash .k,.ans b.q,summary,.toc a,.bx .bl{font-size:clamp(12px,0.7rem + 0.2vw,13.5px)}
table{font-size:clamp(12.5px,0.74rem + 0.22vw,14.5px)}.dash .v{font-size:clamp(16px,0.9rem + 0.5vw,20px)}.bx .br{font-size:clamp(13px,0.78rem + 0.2vw,15px)}
svg text{font-size:11px}@media (max-width:640px){svg text{font-size:15px}th,td{padding:6px 4px}}
/* 가독성(마스터 지시 2026-11-08 "폰트 크기·종류·색·밑줄을 적재적소로 — 무분별하게 말고 읽다 보면 눈에 확 들어오게")
   글꼴 = Noto Sans KR(없으면 시스템 한글), 숫자는 표·대시보드·캔들 정보에서 자릿수 맞춤(tabular-nums).
   강조는 세 단계만: ① 결론·요약 문답·핵심 박스의 굵은 글씨 = 형광 밑줄 ② 질문 이름표 = 파란 글씨 ③ 표 안 굵은 글씨 = 굵게만(밑줄 없음) */
:root{--mk:#ffe58a}@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--mk:#5a4a12}}:root[data-theme=dark]{--mk:#5a4a12}
body{font-family:'Noto Sans KR',-apple-system,'Apple SD Gothic Neo','Malgun Gothic',sans-serif;word-break:keep-all;-webkit-text-size-adjust:100%}
h1{letter-spacing:-.01em;text-wrap:balance}h2{letter-spacing:-.01em}.sub{font-size:clamp(15.5px,0.9rem + 0.3vw,18px);line-height:1.6;color:var(--fg);opacity:.86;margin:6px 0 10px}
table,.dash,.tiles,.cinfo{font-variant-numeric:tabular-nums}
.verdict{border:0;border-left:4px solid var(--fg);background:var(--card);border-radius:4px 12px 12px 4px;padding:14px 16px;line-height:1.85}
.verdict b,.ans div>b:not(.q),.hl b{background:linear-gradient(transparent 60%,var(--mk) 60%);padding:0 1px}
.ans b.q{color:var(--c);font-weight:700;margin-bottom:2px}
/* 강조 확대(마스터 지시 2026-11-12 "색과 볼드, 밑줄 등을 더") — 본문 굵게 = 진한 남색, __밑줄__ = 색 밑줄, ==형광== = 형광 칠, 부호 % = 오름 빨강·내림 파랑, 소제목 = 색 막대 */
:root{--em:#16348a;--ul:#d0452f}@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--em:#a9c1ff;--ul:#ff7d66}}:root[data-theme=dark]{--em:#a9c1ff;--ul:#ff7d66}
.w p b,.w li b,.card>b:first-child~* b,.bx .br b{color:var(--em);font-weight:700}
.w u{text-decoration:underline;text-decoration-color:var(--ul);text-decoration-thickness:2px;text-underline-offset:3px}
.w mark{background:linear-gradient(transparent 55%,var(--mk) 55%);color:inherit;padding:0 1px}
.up{color:var(--b);font-weight:600}.dn{color:var(--c);font-weight:600}
h2{border-top-color:var(--c)}h3{border-left:4px solid var(--c);padding-left:9px;line-height:1.4}
.card>b:first-child{color:var(--c)}.lead b{color:var(--fg)}
.w a{color:var(--c);text-underline-offset:3px;text-decoration-thickness:1px}.toc a{color:var(--mut)}.toc{flex-wrap:nowrap;overflow-x:auto;scrollbar-width:thin}.toc a{flex:0 0 auto}   /* 고정 목차는 PC·모바일 모두 한 줄(여러 줄이면 본문을 가린다) */
@media (max-width:640px){
  body{font-size:16px;line-height:1.72}.w{padding-block:14px 40px}
  .toc{flex-wrap:nowrap;overflow-x:auto;-webkit-overflow-scrolling:touch;scrollbar-width:none;margin:14px 0 4px;padding:6px 0}.toc::-webkit-scrollbar{display:none}.toc a{flex:0 0 auto;padding:5px 12px}
  th,td{min-width:4.6em}th:first-child,td:first-child{min-width:7em}
  .tw th:first-child,.tw td:first-child{position:sticky;left:0;background:var(--bg);z-index:1}
  details.sec>summary h2{padding:12px 0 4px}.verdict{padding:12px 13px}
  table.stk thead,table.stk tr:first-child:has(th){display:none}table.stk,table.stk tbody,table.stk tr,table.stk td{display:block;width:auto;min-width:0}
  table.stk tr{border:1px solid var(--line);border-radius:10px;padding:8px 11px;margin:0 0 8px}table.stk td{border:0;padding:3px 0;text-align:left;position:static}
  table.stk td:first-child{font-weight:700;font-size:15px}table.stk td:not(:first-child)::before{content:attr(data-th);display:block;font-size:12px;color:var(--mut)}table.stk td:empty{display:none}
}"""
DISCLAIMER = "연구 후보이지 매수 권유가 아닙니다 · 공개 자료 기반 분석이며 투자 권유가 아님 · 1차 판정, 미검증 · Chiip ten-bagger"
DISCLAIMER3 = "구매 등급·목표주가 모두 규칙이 계산한 모델 값으로, 개인의 보유 종목·자금 사정을 반영하지 않는다 · 공개 자료 기반 분석이며 투자 권유가 아님 · 1차 판정, 미검증 · Chiip ten-bagger"


_UP = re.compile(r"(?:(?<=^)|(?<=[\s(（:·,]))(\+\d[\d.,]*%(?:p)?)")
_DN = re.compile(r"(?:(?<=^)|(?<=[\s(（:·,]))([−–-]\d[\d.,]*%(?:p)?)")


def t(s):
    """이스케이프 후 **굵게**·__밑줄__·==형광==만 허용. 부호 붙은 %는 오름 빨강·내림 파랑(마스터 지시 2026-11-12 "색과 볼드, 밑줄을 더")"""
    s = html.escape(str(s if s is not None else ""))
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"__(.+?)__", r"<u>\1</u>", s)
    s = re.sub(r"==(.+?)==", r"<mark>\1</mark>", s)
    s = _UP.sub(r'<span class="up">\1</span>', s)
    return _DN.sub(r'<span class="dn">\1</span>', s)


def _legend(series):
    return '<div class="lg">' + "".join(f'<i style="background:{COLORS.get(s.get("color", "c"), "var(--c)")}"></i>{t(s["name"])}' for s in series) + "</div>"


def _fmt(v):
    if v is None:
        return "-"
    return f"{v:,.0f}" if abs(v) >= 100 else (f"{v:,.1f}" if abs(v) >= 10 else f"{v:,.2f}")


def chart_line(c):
    W, H, L, R, T, B = 700, 260, 48, 14, 14, 26
    series = c.get("series") or []
    keys = list(dict.fromkeys(p[0] for s in series for p in s.get("points") or []))   # '10/2'·'6/12'처럼 글자순과 시간순이 다른 라벨이 있어 입력 순서를 쓴다
    if len(series) > 1 and all(str(k)[:4].isdigit() for k in keys):   # 시리즈마다 날짜가 다르면 ISO 날짜만 합쳐 정렬한다
        keys = sorted(keys)
    vals = [p[1] for s in series for p in s.get("points") or [] if p[1] is not None]
    if not keys or not vals:
        return ""
    log = bool(c.get("log")) and min(vals) > 0
    lo, hi = (min(vals), max(vals))
    if log:
        lo, hi = math.log10(lo) - 0.1, math.log10(hi) + 0.1
    else:
        pad = (hi - lo) * 0.1 or abs(hi) * 0.1 or 1
        lo, hi = min(0, lo - pad) if lo >= 0 else lo - pad, hi + pad
    X = lambda k: L + (keys.index(k) / max(len(keys) - 1, 1)) * (W - L - R)
    Y = lambda v: T + (hi - (math.log10(v) if log else v)) / (hi - lo) * (H - T - B)
    g = []
    for i in range(5):
        v = lo + (hi - lo) * i / 4
        real = 10 ** v if log else v
        g.append(f'<line x1="{L}" x2="{W - R}" y1="{Y(real):.1f}" y2="{Y(real):.1f}" stroke="var(--line)"/><text x="{L - 4}" y="{Y(real) + 3:.1f}" text-anchor="end">{_fmt(real)}</text>')
    step = max(1, len(keys) // 8)
    for i, k in enumerate(keys):
        if i % step == 0 or i == len(keys) - 1:
            g.append(f'<text x="{X(k):.1f}" y="{H - 6}" text-anchor="middle">{t(k)}</text>')
    if c.get("now") in keys:   # 현재 위치 세로선(P·Q 사이클 10년 차트, 2026-11-04)
        g.append(f'<line x1="{X(c["now"]):.1f}" x2="{X(c["now"]):.1f}" y1="{T}" y2="{H - B}" stroke="var(--fg)" stroke-dasharray="4 3"/>'
                 f'<text x="{X(c["now"]) - 4:.1f}" y="{T + 10}" text-anchor="end" style="fill:var(--fg);font-weight:700">현재</text>')
    for s in series:
        col = COLORS.get(s.get("color", "c"), "var(--c)")
        pts = [p for p in s.get("points") or [] if p[1] is not None]
        g.append(f'<polyline fill="none" stroke="{col}" stroke-width="2" points="{" ".join(f"{X(p[0]):.1f},{Y(p[1]):.1f}" for p in pts)}"/>')
        for p in pts:
            note = f" · {p[2]}" if len(p) > 2 and p[2] else ""
            g.append(f'<circle cx="{X(p[0]):.1f}" cy="{Y(p[1]):.1f}" r="4" fill="{col}" stroke="var(--bg)" stroke-width="2"><title>{t(s["name"])} {t(p[0])}: {_fmt(p[1])}{t(c.get("unit", ""))}{t(note)}</title></circle>')
    return _legend(series) + f'<svg viewBox="0 0 {W} {H}">{"".join(g)}</svg>'


def chart_stack(c):
    """쌓인 막대(양수만) — 범주가 많으면 x축 이름을 솎아 낸다"""
    W, H, L, B, T = 700, 250, 48, 30, 18
    cats, series = c.get("categories") or [], c.get("series") or []
    tots = [sum((s.get("values") or [0] * len(cats))[i] or 0 for s in series) for i in range(len(cats))]
    if not cats or not any(tots):
        return ""
    hi = max(tots) * 1.1
    Y = lambda v: T + (hi - v) / hi * (H - T - B)
    gw = (W - L - 10) / len(cats)
    g = [f'<line x1="{L}" x2="{W - 10}" y1="{Y(0):.1f}" y2="{Y(0):.1f}" stroke="var(--line)"/>']
    for i in range(5):
        v = hi * i / 4
        g.append(f'<text x="{L - 4}" y="{Y(v) + 3:.1f}" text-anchor="end">{_fmt(v)}</text>')
    step = max(1, len(cats) // 10)
    for ci, cat in enumerate(cats):
        x, base = L + ci * gw + 1, 0.0
        for s in series:
            v = (s.get("values") or [None] * len(cats))[ci]
            if not v:
                continue
            col = COLORS.get(s.get("color", "c"), "var(--c)")
            g.append(f'<rect x="{x:.1f}" y="{Y(base + v):.1f}" width="{max(gw - 2, 1):.1f}" height="{max(Y(base) - Y(base + v), 0.5):.1f}" fill="{col}"><title>{t(s["name"])} {t(cat)}: {_fmt(v)}{t(c.get("unit", ""))}</title></rect>')
            base += v
        if ci % step == 0:
            g.append(f'<text x="{x + gw / 2:.1f}" y="{H - 10}" text-anchor="middle" style="font-size:9.5px">{t(cat)}</text>')
    return _legend(series) + f'<svg viewBox="0 0 {W} {H}">{"".join(g)}</svg>'


def chart_candle(c):
    """캔들(OHLC) + 수평선·구간 띠. 한국식 색 — 상승(종가 ≥ 시가) 빨강, 하락 파랑"""
    bars = [b for b in c.get("bars") or [] if len(b) >= 5 and None not in b[1:5]]
    if not bars:
        return ""
    W, H, L, R, T, B = c.get("w", 700), 300, 40 if c.get("w") else 52, 86 if c.get("w") else 96, 12, 26
    lo = min(min(b[3] for b in bars), *[h["y"] for h in c.get("hlines") or []] or [math.inf], *[z["y0"] for z in c.get("zones") or []] or [math.inf])
    hi = max(max(b[2] for b in bars), *[h["y"] for h in c.get("hlines") or []] or [-math.inf], *[z["y1"] for z in c.get("zones") or []] or [-math.inf])
    pad = (hi - lo) * 0.04 or 1
    lo, hi = lo - pad, hi + pad
    Y = lambda v: T + (hi - v) / (hi - lo) * (H - T - B)
    gw = (W - L - R) / len(bars)
    g = []
    for i in range(5):
        v = lo + (hi - lo) * i / 4
        g.append(f'<line x1="{L}" x2="{W - R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="var(--line)"/><text x="{L - 4}" y="{Y(v) + 3:.1f}" text-anchor="end">{_fmt(v)}</text>')
    for z in c.get("zones") or []:
        col = "var(--d)" if z.get("tone") == "grn" else "var(--b)"
        g.append(f'<rect x="{L}" y="{Y(z["y1"]):.1f}" width="{W - L - R}" height="{max(Y(z["y0"]) - Y(z["y1"]), 2):.1f}" fill="{col}" opacity="0.16"><title>{t(z.get("label"))} {_fmt(z["y0"])}~{_fmt(z["y1"])}</title></rect>')
    for ln in c.get("lines") or []:   # 이동평균선(마스터 지시 2026-10-31)
        col = COLORS.get(ln.get("color", "a"), "var(--a)")
        at = {str(b[0]): i for i, b in enumerate(bars)}
        pts = [(at[str(d)], v) for d, v in ln.get("points") or [] if str(d) in at and v is not None and lo <= v <= hi]
        if len(pts) > 1:
            g.append(f'<polyline fill="none" stroke="{col}" stroke-width="1.6" points="{" ".join(f"{L + i * gw + gw / 2:.1f},{Y(v):.1f}" for i, v in pts)}"/>')
    for h in c.get("hlines") or []:
        col = COLORS.get(h.get("color", "e"), "var(--e)")
        g.append(f'<line x1="{L}" x2="{W - R}" y1="{Y(h["y"]):.1f}" y2="{Y(h["y"]):.1f}" stroke="{col}" stroke-dasharray="4 3"/>'
                 f'<text x="{W - R + 4}" y="{Y(h["y"]) + 3:.1f}" style="font-size:9.5px">{t(h.get("label"))}</text>')
    step = max(1, len(bars) // 8)
    for i, (d, o, hh, ll, cl) in enumerate(b[:5] for b in bars):
        x = L + i * gw + gw / 2
        col = "var(--b)" if cl >= o else "var(--c)"
        pf = (lambda v: f"{v:,.2f}") if hi < 1000 else (lambda v: f"{v:,.0f}")   # 캔들 정보는 호가 단위 그대로
        prev = bars[i - 1][4] if i else None
        chg = f"{(cl / prev - 1) * 100:+.1f}%" if prev else ""
        g.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{Y(hh):.1f}" y2="{Y(ll):.1f}" stroke="{col}"/>'
                 f'<rect x="{x - max(gw * 0.35, 0.6):.1f}" y="{Y(max(o, cl)):.1f}" width="{max(gw * 0.7, 1.2):.1f}" height="{max(abs(Y(o) - Y(cl)), 0.8):.1f}" fill="{col}">'
                 f'<title>{t(d)} 시 {_fmt(o)} 고 {_fmt(hh)} 저 {_fmt(ll)} 종 {_fmt(cl)}</title></rect>'
                 # 누르는 칸 = 봉 폭 전체·차트 높이 전체(가는 봉도 손가락으로 누를 수 있게)
                 f'<rect class="ck" x="{x - gw / 2:.1f}" y="{T}" width="{gw:.1f}" height="{H - T - B}" fill="transparent" data-d="{t(d)}" data-o="{pf(o)}" data-h="{pf(hh)}" data-l="{pf(ll)}" data-c="{pf(cl)}" data-p="{chg}" data-up="{1 if cl >= o else 0}"/>')
        if i % step == 0:
            g.append(f'<text x="{x:.1f}" y="{H - 8}" text-anchor="middle" style="font-size:9.5px">{t(str(d)[2:])}</text>')
    legend = _legend(c["legend"]) if c.get("legend") else ""
    lb = bars[-1]
    pf = (lambda v: f"{v:,.2f}") if hi < 1000 else (lambda v: f"{v:,.0f}")
    info = f'<div class="cinfo"><b>{t(lb[0])}</b> 종가 <b>{pf(lb[4])}</b> · 고가 {pf(lb[2])} · 저가 {pf(lb[3])} · 시가 {pf(lb[1])} <span class="mut">— 캔들을 누르면 그날 값</span></div>'
    return legend + f'<div class="cwrap">{info}<svg viewBox="0 0 {W} {H}">{"".join(g)}</svg></div>'


def chart_progress(c):
    """수주·파이프라인 — 막대 길이 = 규모(제곱근 눈금), 칠한 몫 = 진척도, 금액을 모르면 짧은 점선 막대(마스터 지시 2026-11-01)"""
    rows = c.get("rows") or []
    if not rows:
        return ""
    W, L, R = 460, 8, 8
    full = W - L - R
    top = max([r["total"] for r in rows if r.get("total")] + [0]) or 1
    g, y = [], 4
    for r in rows:
        tot, pct = r.get("total"), r.get("pct")
        wid = max(full * math.sqrt(tot / top), 40) if tot else 60
        fill = wid * min(max(pct or 0, 0), 1)
        tag = "진척 미확인" if pct is None else f"진척 {pct * 100:.0f}%"
        g.append(f'<text x="{L}" y="{y + 11}" style="fill:var(--fg);font-size:12px;font-weight:600">{t(r.get("label"))}</text>')
        g.append(f'<text x="{L}" y="{y + 25}" style="font-size:10.5px">{t(r.get("size"))} · {tag} · {t(r.get("status"))}</text>')
        dash = ' stroke-dasharray="4 3"' if not tot else ""
        g.append(f'<rect x="{L}" y="{y + 31}" width="{wid:.1f}" height="12" rx="4" fill="var(--line)" stroke="var(--mut)" stroke-width="0.6"{dash}/>')
        if fill > 0:
            g.append(f'<rect x="{L}" y="{y + 31}" width="{max(fill, 3):.1f}" height="12" rx="4" fill="var(--c)"/>')
        y += 54
    return f'<svg viewBox="0 0 {W} {y}">{"".join(g)}</svg>'


PIPE_TIERS = (("확정", ("확정",), "d"), ("조건부", ("조건부",), "c"), ("협상·프레임워크", ("협상", "프레임워크"), "e"), ("MOU·파이프라인", ("MOU", "파이프라인"), "a"))


def chart_pipeline(c):
    """수주·파이프라인 확실성 사다리(마스터 지시 2026-11-08 "시각물이 직관적이지 못하다 — 직관성을 더 올려라").
    위: 금액을 아는 건의 확실성별 몫 한 줄. 아래: 확실성 단계(확정 → 조건부 → 협상·프레임워크 → MOU·파이프라인)마다 띠를 두고 건을 쌓는다.
    색 = 확실성, 막대 길이 = 금액(제곱근 눈금), 진하게 칠한 몫 = 진척도. 금액을 모르는 건은 막대 대신 '금액 비공개' 표시."""
    rows = c.get("rows") or []
    if not rows:
        return ""
    W, L = 360, 6   # 휴대폰 폭에서 글자가 줄지 않게 좁게 그린다(다른 그림보다 글이 많다)
    full = W - 2 * L
    unit = c.get("money", "")
    top = max([r["total"] for r in rows if r.get("total")] + [0]) or 1
    tiers = [(n, [r for r in rows if r.get("status") in keys], col) for n, keys, col in PIPE_TIERS]
    g, y = [], 4
    known = [(n, sum(r["total"] for r in rs if r.get("total")), col) for n, rs, col in tiers]
    tot = sum(v for _, v, _ in known)
    hidden = sum(1 for r in rows if not r.get("total"))
    if tot:
        x = L
        g.append(f'<text x="{L}" y="{y + 11}" style="fill:var(--fg);font-size:12px;font-weight:600">금액을 아는 건의 확실성 몫</text>')
        for n, v, col in known:
            if v:
                w = full * v / tot
                g.append(f'<rect x="{x:.1f}" y="{y + 17}" width="{max(w, 2):.1f}" height="14" fill="{COLORS[col]}"><title>{t(n)} {t(c.get("fmt", {}).get(n, ""))}</title></rect>')
                if w > 60:
                    g.append(f'<text x="{x + 4:.1f}" y="{y + 28}" style="fill:#fff;font-size:10.5px">{t(n)} {v / tot:.0%}</text>')
                x += w
        y += 36
    if hidden:
        g.append(f'<text x="{L}" y="{y + 10}" style="font-size:10.5px">금액 비공개 {hidden}건은 위 몫에서 빠진다</text>')
        y += 16
    for n, rs, col in tiers:
        if not rs:
            continue
        s = sum(r["total"] for r in rs if r.get("total"))
        label = f"{n} · {len(rs)}건" + (f" · {c.get('fmt', {}).get(n) or f'{s:,.1f}'}" if s else "")
        h0, at = y, len(g)   # 띠 바탕은 글 아래에 깔리도록 나중에 이 자리에 넣는다
        y += 6
        g.append(f'<text x="{L + 8}" y="{y + 12}" style="fill:{COLORS[col]};font-size:13.5px;font-weight:700">{t(label)}</text>')
        y += 18
        for r in rs:
            lines = wrap_units(r.get("label"), 24)
            for i, ln in enumerate(lines[:2]):
                g.append(f'<text x="{L + 8}" y="{y + 13 + 15 * i}" style="fill:var(--fg);font-size:13px;font-weight:600">{t(ln)}</text>')
            y += 15 * min(len(lines), 2) + 2
            if r.get("total"):
                wid = max((full - 150) * math.sqrt(r["total"] / top), 24)
                g.append(f'<rect x="{L + 8}" y="{y}" width="{wid:.1f}" height="12" rx="3" fill="{COLORS[col]}" fill-opacity="0.28"/>')
                p = r.get("pct")
                if p:
                    g.append(f'<rect x="{L + 8}" y="{y}" width="{max(wid * min(p, 1), 3):.1f}" height="12" rx="3" fill="{COLORS[col]}"/>')
                tx = L + 14 + wid
            else:
                g.append(f'<rect x="{L + 8}" y="{y}" width="74" height="12" rx="3" fill="none" stroke="{COLORS[col]}" stroke-dasharray="3 2"/>'
                         f'<text x="{L + 13}" y="{y + 9.5}" style="font-size:9.5px">금액 비공개</text>')
                tx = L + 90
            info = " · ".join(x for x in (r.get("size"), "진척 미확인" if r.get("pct") is None else f"진척 {r['pct'] * 100:.0f}%", r.get("when")) if x)
            g.append(f'<text x="{tx:.1f}" y="{y + 10}" style="font-size:11.5px">{t(info)}</text>')
            y += 22
        g.insert(len(g) - (len(g) - 0), "")
        g.insert(at, f'<rect x="{L}" y="{h0}" width="{full}" height="{y - h0}" rx="6" fill="{COLORS[col]}" fill-opacity="0.06" stroke="{COLORS[col]}" stroke-opacity="0.35" stroke-width="0.8"/>')
        y += 8
    legend = '<p class="sm mut">색 = 확실성(확정 → MOU) · 막대 길이 = 금액 · 진한 몫 = 진척도</p>'
    return legend + f'<svg viewBox="0 0 {W} {y}">{"".join(g)}</svg>'


def wrap_units(s, width):
    """한글 1칸, 영문·숫자 0.55칸으로 재서 줄을 나눈다 — SVG 글자는 스스로 줄바꿈하지 않는다"""
    lines, cur, used = [], "", 0.0
    for ch in str(s or ""):
        w = 1.0 if ord(ch) > 0x2E7F else 0.55
        if used + w > width and cur:
            lines.append(cur.strip())
            cur, used = "", 0.0
        cur += ch
        used += w
    return lines + ([cur.strip()] if cur.strip() else [])


def chart_portfolio(c):
    """제품·서비스 포트폴리오 — 무엇을 어디에 팔아 어떻게 버는지 카드로(마스터 지시 2026-11-02). 휴대폰에서 글자가 줄지 않게 폭을 좁게 잡는다. 매출 몫을 알면 막대를 그린다"""
    rows = c.get("rows") or []
    if not rows:
        return ""
    W, pad, wide, step = 340, 12, 28, 16   # 2026-11-11 마스터 지시 "제품·서비스 포트폴리오 설명란 폰트 크기를 줄여라" — 글자 작게·한 줄 더 길게
    g, y = [], 2
    for r in rows:
        top = y
        names = wrap_units(r.get("name"), wide - 4)
        y += 18
        for i, line in enumerate(names):
            g.append(f'<text x="{pad}" y="{y + i * step}" style="fill:var(--fg);font-size:12px;font-weight:700">{t(line)}</text>')
        g.append(f'<text x="{W - pad}" y="{y}" text-anchor="end" style="fill:var(--c);font-size:11.5px;font-weight:600">{t(r.get("tag"))}</text>')
        y += (len(names) - 1) * step + 6
        share = r.get("share")
        if isinstance(share, (int, float)):
            full = W - 2 * pad - 60
            g.append(f'<rect x="{pad}" y="{y}" width="{full}" height="8" rx="4" fill="var(--line)"/><rect x="{pad}" y="{y}" width="{max(full * min(share, 1), 3):.1f}" height="8" rx="4" fill="var(--c)"/>')
            g.append(f'<text x="{W - pad}" y="{y + 8}" text-anchor="end" style="font-size:11.5px">매출 {share * 100:.0f}%</text>')
            y += 14
        for label, key, color in ((None, "what", "var(--fg)"), ("쓰는 곳", "use", "var(--mut)"), ("수익", "money", "var(--mut)")):
            if not r.get(key):
                continue
            text = f"{label} · {r[key]}" if label else r[key]
            for line in wrap_units(text, wide):
                y += step
                g.append(f'<text x="{pad}" y="{y}" style="fill:{color};font-size:10.5px">{t(line)}</text>')
        y += 12
        g.insert(0, f'<rect x="1" y="{top}" width="{W - 2}" height="{y - top}" rx="10" fill="none" stroke="var(--line)"/>')
        y += 8
    return f'<svg viewBox="0 0 {W} {y}" style="width:100%;max-width:460px;height:auto">{"".join(g)}</svg>'


def chart_actest(c):
    """분기 실적 vs 컨센서스 — 패널마다 실적·컨센서스 막대를 다른 색으로(마스터 지시 2026-10-31 "매출과 EPS 같이 그려라. actual과 estimated 바는 다른 색으로")"""
    panels = [p for p in c.get("panels") or [] if p.get("categories")]
    if not panels:
        return ""
    W, PH, L, gap = 460, 170, 34, 34
    g, y0 = [], 16
    for p in panels:
        cats, act, est = p["categories"], p.get("actual") or [], p.get("est") or []
        vals = [v for v in act + est if v is not None]
        hi = max(vals + [0]) * 1.18 or 1
        Y = lambda v: y0 + (hi - v) / hi * (PH - 26)
        gw = (W - L - 10) / len(cats)
        g.append(f'<text x="{L}" y="{y0 - 5}" style="fill:var(--fg);font-size:12px;font-weight:700">{t(p.get("name"))}</text><line x1="{L}" x2="{W - 10}" y1="{Y(0):.1f}" y2="{Y(0):.1f}" stroke="var(--line)"/>')
        for i, cat in enumerate(cats):
            x = L + i * gw + gw * 0.12
            bw = gw * 0.36
            for j, (v, col) in enumerate(((act[i] if i < len(act) else None, "var(--c)"), (est[i] if i < len(est) else None, "var(--e)"))):
                if v is None:
                    continue
                xb = x + j * (bw + 2)
                g.append(f'<rect x="{xb:.1f}" y="{Y(v):.1f}" width="{bw:.1f}" height="{max(Y(0) - Y(v), 1):.1f}" rx="2" fill="{col}"><title>{t(cat)} {"실적" if j == 0 else "컨센서스"} {_fmt(v)}</title></rect>')
                if j == 0 or (i < len(act) and act[i] is None):
                    g.append(f'<text x="{xb + bw / 2:.1f}" y="{Y(v) - 3:.1f}" text-anchor="middle" style="font-size:9px">{_fmt(v)}</text>')
            g.append(f'<text x="{x + gw * 0.38:.1f}" y="{Y(0) + 12:.1f}" text-anchor="middle" style="font-size:9.5px">{t(cat)}</text>')
        y0 += PH + gap - 14
    return _legend([{"name": "실적", "color": "c"}, {"name": "컨센서스", "color": "e"}]) + f'<svg viewBox="0 0 {W} {y0 - 10}">{"".join(g)}</svg>'


def chart_revision(c):
    """계단선 + 선 위 사건 번호(마스터 지시 2026-10-30 "그래프에는 선 위에 이벤트를 숫자로만 표기하고(점선을 제외하고) 아래 부가 설명에는 숫자별 이벤트가 무엇인지 설명").
    점선·변화율·추정 변경 점은 그리지 않는다. 번호는 내년 EPS 선(리비전의 기준) 위, 가까운 사건은 위로 쌓는다"""
    series = c.get("series") or []
    vals = [p[1] for s in series for p in s.get("points") or [] if p[1] is not None]
    if not vals:
        return ""
    d0, d1 = date.fromisoformat(c["start"]), date.fromisoformat(c["end"])
    span = (d1 - d0).days or 1
    W, H, L, R, T, B = 440, 300, 34, 10, 14, 22   # 휴대폰 폭에서 글자가 읽히게 좁은 좌표계(마스터는 모바일로 본다)
    X = lambda s: L + (date.fromisoformat(str(s)[:10]) - d0).days / span * (W - L - R)
    lo, hi = min(0, min(vals)), max(vals) * 1.14 or 1
    Y = lambda v: T + (hi - v) / (hi - lo) * (H - T - B)
    g = []
    for i in range(5):
        v = lo + (hi - lo) * i / 4
        g.append(f'<line x1="{L}" x2="{W - R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="var(--line)"/><text x="{L - 4}" y="{Y(v) + 3:.1f}" text-anchor="end">{_fmt(v)}</text>')
    y, m = d0.year, d0.month
    while date(y, m, 1) <= d1:
        if date(y, m, 1) >= d0 and m % 2 == 0:
            x = X(date(y, m, 1).isoformat())
            g.append(f'<text x="{x:.1f}" y="{H - 6}" text-anchor="middle" style="font-size:9.5px">{str(y)[2:]}-{m:02d}</text>')
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    for s in series:
        col = COLORS.get(s.get("color", "c"), "var(--c)")
        pts = [p for p in s.get("points") or [] if p[1] is not None]
        path, prev = [], None
        for p in pts:
            if prev is not None:
                path.append(f"{X(p[0]):.1f},{Y(prev):.1f}")
            path.append(f"{X(p[0]):.1f},{Y(p[1]):.1f}")
            prev = p[1]
        path.append(f"{X(c['end']):.1f},{Y(prev):.1f}")
        g.append(f'<polyline fill="none" stroke="{col}" stroke-width="2.2" points="{" ".join(path)}"/>')
        g.append(f'<text x="{X(c["end"]) - 2:.1f}" y="{Y(prev) + 14:.1f}" text-anchor="end" style="fill:{col};font-size:11px;font-weight:700">{_fmt(prev)}</text>')
    top = [p for p in series[-1].get("points") or [] if p[1] is not None]

    def peak(day):
        """사건 직후 계단까지 넘는 높이 — 번호가 세로 계단에 겹치지 않게"""
        stop = (date.fromisoformat(day[:10]) + timedelta(days=14)).isoformat()
        return max([p[1] for p in top if p[0] <= day][-1:] + [p[1] for p in top if day < p[0] <= stop] or [top[0][1]])
    last_x, lift = -99.0, 0
    for e in c.get("events") or []:
        if not e.get("mark"):
            continue
        x = min(max(X(e["date"]), L + 7), W - R - 7)
        lift = lift + 13 if x - last_x < 14 else 0
        last_x = x
        g.append(f'<text x="{x:.1f}" y="{max(Y(peak(str(e["date"]))) - 6 - lift, 11):.1f}" text-anchor="middle" style="fill:var(--fg);font-size:12px;font-weight:700">{t(e["mark"])}</text>')
    return _legend(series) + f'<svg viewBox="0 0 {W} {H}">{"".join(g)}</svg>'


def chart_bars(c):
    if c.get("stack"):
        return chart_stack(c)
    W, L, T = c.get("w", 700), 48, 18
    cats, series = c.get("categories") or [], c.get("series") or []
    vals = [v for s in series for v in s.get("values") or [] if v is not None]
    if not cats or not vals:
        return ""
    nl = max(len(wrap_label(x, (W - L - 10) / len(cats) - 4)) for x in cats)   # 이름표 줄 수만큼 아래 여백(2026-11-08 겹침 방지)
    B = 18 + (nl - 1) * 11
    H = 220 + B
    lo, hi = min(0, min(vals)), max(0, max(vals)) * 1.15 or 1
    Y = lambda v: T + (hi - v) / (hi - lo) * (H - T - B)
    gw = (W - L - 10) / len(cats)
    bw = max(4, (gw - 10) / max(len(series), 1))
    g = [f'<line x1="{L}" x2="{W - 10}" y1="{Y(0):.1f}" y2="{Y(0):.1f}" stroke="var(--line)"/>']
    for i in range(5):
        v = lo + (hi - lo) * i / 4
        g.append(f'<text x="{L - 4}" y="{Y(v) + 3:.1f}" text-anchor="end">{_fmt(v)}</text>')
    for ci, cat in enumerate(cats):
        x0 = L + ci * gw + 5
        for si, s in enumerate(series):
            v = (s.get("values") or [None] * len(cats))[ci]
            if v is None:
                continue
            col = COLORS.get((s.get("colors") or [None] * len(cats))[ci] or s.get("color", "c"), "var(--c)")   # 막대마다 색(colors, 2026-11-08 가이던스·컨센서스 구분)
            y, h = (Y(v), Y(0) - Y(v)) if v >= 0 else (Y(0), Y(v) - Y(0))
            x = x0 + si * bw
            g.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw - 2:.1f}" height="{max(h, 1):.1f}" rx="2" fill="{col}"><title>{t(s["name"])} {t(cat)}: {_fmt(v)}{t(c.get("unit", ""))}</title></rect>')
            if len(series) <= 3:
                g.append(f'<text x="{x + (bw - 2) / 2:.1f}" y="{(y - 3) if v >= 0 else (y + h + 10):.1f}" text-anchor="middle" style="font-size:9.5px">{_fmt(v)}</text>')
        g.append(label_svg(cat, x0 + gw / 2 - 5, H - B + 14, gw - 4)[0])
    if c.get("trend"):   # 막대 위 추이선(멀티플 프리미엄 추이, 2026-11-06)
        for si, s in enumerate(series):
            pts = [(L + ci * gw + 5 + si * bw + (bw - 2) / 2, Y(v)) for ci, v in enumerate(s.get("values") or []) if v is not None]
            if len(pts) >= 2:
                g.append(f'<polyline points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in pts)}" fill="none" stroke="var(--b)" stroke-width="2"/>'
                         + "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="var(--b)"/>' for x, y in pts))
    return _legend(c.get("legend") or series) + f'<svg viewBox="0 0 {W} {H}">{"".join(g)}</svg>'


def _tw(text, px=12):
    """글자 폭 어림 — 한글·한자는 글자 크기만큼, 영문·숫자는 그 0.6배"""
    return sum(px if ord(ch) > 0x2E80 else px * 0.6 for ch in text)


def _wrap2(text, width):
    """최대 두 줄로 접는다. 띄어쓰기에서 먼저 끊고, 그래도 넘치면 둘째 줄 끝을 …로 줄인다(전체 이름은 마우스를 올리면 보인다)"""
    if _tw(text) <= width:
        return [text]
    words, a = text.split(" "), ""
    while words and _tw((a + " " + words[0]).strip()) <= width:
        a = (a + " " + words.pop(0)).strip()
    if not a:   # 띄어쓰기 없는 긴 이름
        k = 1
        while k < len(text) and _tw(text[:k + 1]) <= width:
            k += 1
        a, words = text[:k], [text[k:]]
    b = " ".join(words)
    while _tw(b + "…") > width and len(b) > 1:
        b = b[:-1]
    return [a, b + ("…" if b != " ".join(words) else "")]


def chart_hbars(c):
    """가로 막대 — 음수도 그린다(0 기준선 왼쪽). 항목 이름이 긴 그래프(콜 변화 항목 등)를 위해 이름 칸을 넓게(2026-10-30)"""
    rows = c.get("rows") or []
    vals = [b.get("value") or 0 for r in rows for b in r.get("bars") or []]
    if not rows or not vals:
        return ""
    W, R = c.get("w", 700), 56
    # 긴 항목 이름은 두 줄로 접고 이름 칸을 넓힌다 — 좁은 화면(PC·모바일 HTML)에서 왼쪽이 잘리던 문제(마스터 지시 2026-11-07, 코닝 마진 절)
    lines = {r["label"]: _wrap2(str(r["label"]), W * 0.42) for r in rows}
    L = min(W * 0.45, max(c.get("label_w", 180), max(_tw(x) for ls in lines.values() for x in ls) + 14))
    pct = "%" if c.get("unit") == "%" else ""   # 막대 값에 % 단위를 붙인다(마스터 지시 2026-11-01)
    hi, lo = max(max(vals), 0), min(min(vals), 0)
    span = (hi - lo) * 1.12 or 1
    base = lo * 1.12   # 음수가 있으면 왼쪽 여유를 두고 0 기준선을 오른쪽으로 민다
    X = lambda v: L + ((v - base) if lo < 0 else max(v, 0)) / span * (W - L - R)
    x0 = X(0)
    names = []
    for r in rows:
        for b in r.get("bars") or []:
            if b["name"] not in [n["name"] for n in names]:
                names.append({"name": b["name"], "color": b.get("color", "c")})
    g, y = [], 10
    for r in rows:
        bars = r.get("bars") or []
        ls = lines[r["label"]]
        mid = y + 8 * len(bars) + 4 - (len(ls) - 1) * 7
        g.append(f'<text x="{L - 8}" y="{mid}" text-anchor="end" style="fill:var(--fg);font-size:12px"><title>{t(r["label"])}</title>'
                 + "".join(f'<tspan x="{L - 8}" dy="{0 if i == 0 else 14}">{t(x)}</tspan>' for i, x in enumerate(ls)) + "</text>")
        for b in bars:
            v = b.get("value") or 0
            col = COLORS.get(b.get("color", "c"), "var(--c)")
            x1, x2 = sorted((x0, X(v)))
            g.append(f'<rect x="{x1:.1f}" y="{y}" width="{max(2, x2 - x1):.1f}" height="14" rx="3" fill="{col}"><title>{t(r["label"])} {t(b["name"])}: {_fmt(b.get("value"))}{t(c.get("unit", ""))}</title></rect>'
                     # 음수 값 글자는 0 기준선 오른쪽에 — 막대 왼쪽 끝에 두면 항목 이름과 겹친다(마스터 지시 2026-11-08, 마진 기여·비용 비중 변화)
                     + f'<text x="{(x2 if v >= 0 else x0) + 4:.1f}" y="{y + 11}">{_fmt(b.get("value"))}{pct}</text>')
            y += 17
        y += 14
    if lo < 0:
        g.append(f'<line x1="{x0:.1f}" x2="{x0:.1f}" y1="4" y2="{y - 6}" stroke="var(--mut)" stroke-dasharray="3 3"/>')
    return _legend(names) + f'<svg viewBox="0 0 {W} {y + 4}">{"".join(g)}</svg>'


def chart_scenario(c):
    cases = c.get("cases") or []
    if not cases:
        return ""
    cur = c.get("current")
    W, L, R = 700, 120, 70
    mx = max([k.get("value") or 0 for k in cases] + [cur or 0]) * 1.1 or 1
    X = lambda v: L + v / mx * (W - L - R)
    g, y = [], 10
    for k in cases:
        col = COLORS.get(k.get("color", "c"), "var(--c)")
        mult = f" ({k['value'] / cur - 1:+.0%})" if cur else ""
        prob = f" · 확률 {k['prob'] * 100:.0f}%" if k.get("prob") is not None else ""
        g.append(f'<text x="{L - 6}" y="{y + 12}" text-anchor="end" style="fill:var(--fg);font-size:12px">{t(k["name"])}</text>'
                 f'<rect x="{L}" y="{y}" width="{max(2, X(k["value"]) - L):.1f}" height="16" rx="3" fill="{col}"><title>{t(k["name"])}: {_fmt(k["value"])}{t(c.get("unit", ""))}{mult}{prob} — {t(k.get("why", ""))}</title></rect>'
                 f'<text x="{X(k["value"]) + 4:.1f}" y="{y + 12}">{_fmt(k["value"])}{mult}{prob}</text>')
        y += 26
    if cur:
        g.append(f'<line x1="{X(cur):.1f}" x2="{X(cur):.1f}" y1="4" y2="{y}" stroke="var(--fg)" stroke-dasharray="4 3"/><text x="{X(cur) + 4:.1f}" y="{y + 12}">현재 {_fmt(cur)}</text>')
        ev = sum((k.get("prob") or 0) * k["value"] for k in cases)
        if ev and abs(sum(k.get("prob") or 0 for k in cases) - 1) < 0.02:
            g.append(f'<text x="{L}" y="{y + 26}" style="fill:var(--fg)">확률 가중 {_fmt(ev)} ({ev / cur - 1:+.0%})</text>')
            y += 14
        if c.get("target"):
            g.append(f'<line x1="{X(c["target"]):.1f}" x2="{X(c["target"]):.1f}" y1="4" y2="{y - 14}" stroke="var(--d)" stroke-width="2"/><text x="{L}" y="{y + 26}" style="fill:var(--d);font-weight:700">목표주가 {_fmt(c["target"])} ({c["target"] / cur - 1:+.0%})</text>')
            y += 14
    return f'<svg viewBox="0 0 {W} {y + 18}">{"".join(g)}</svg>'


def chart_satellite(c):
    """시설 위성 영상 — 처음과 최신을 나란히(마스터 지시 2026-11-03). 영상은 렌더 때 파일에서 읽어 svg 안에 넣는다. 출처 표기는 약관이 요구한다"""
    import site_view
    W, gap, side, g, y = 480, 12, 234, [], 0
    for p in c.get("panels") or []:
        uris = [(site_view.image_uri(i["path"]), i["date"]) for i in p.get("images") or []]
        uris = [u for u in uris if u[0]]
        if not uris:
            continue
        y += 16
        g.append(f'<text x="0" y="{y}" style="fill:var(--fg);font-size:13px;font-weight:700">{t(p.get("name"))}</text>')
        y += 6
        for i, (uri, date) in enumerate(uris[:2]):
            x = i * (side + gap)
            g.append(f'<image x="{x}" y="{y}" width="{side}" height="{side}" href="{uri}"/>')
            g.append(f'<text x="{x}" y="{y + side + 14}" style="fill:var(--mut);font-size:11.5px">{t(date)}</text>')
        y += side + 30
        g.append(f'<text x="0" y="{y}" style="fill:var(--mut);font-size:10px">{t(p.get("credit"))}</text>')
        y += 12
    return f'<svg viewBox="0 0 {W} {y}">{"".join(g)}</svg>' if g else ""


def _label_w(ch, fs):
    """글자 폭 대략값 — 한글·한자 1em, 그 밖 0.58em"""
    return fs * (1.0 if ord(ch) > 0x2E80 else 0.58)


def wrap_label(text, max_w, fs=9.5, max_lines=3):
    """x축 이름표를 칸 폭에 맞춰 줄바꿈(마스터 지시 2026-11-08 "x축의 텍스트 설명이 겹쳐 보인다") — 공백·가운뎃점·괄호·슬래시에서 끊고,
    그래도 넘치면 글자 단위로 끊는다. max_lines를 넘으면 마지막 줄을 '…'로 줄이고 전체는 <title>로 남긴다"""
    import re as _re
    toks = [x for x in _re.split(r"(?<=[ ·/,)])|(?=[(])", str(text)) if x]
    lines, cur = [], ""
    width = lambda s_: sum(_label_w(ch, fs) for ch in s_)
    for tok in toks:
        if width(cur + tok) <= max_w or not cur:
            cur += tok
        else:
            lines.append(cur.strip())
            cur = tok
        while width(cur) > max_w and len(cur) > 1:   # 한 토막이 칸보다 길면 글자 단위로
            k = len(cur)
            while k > 1 and width(cur[:k]) > max_w:
                k -= 1
            lines.append(cur[:k].strip())
            cur = cur[k:]
    if cur.strip():
        lines.append(cur.strip())
    if len(lines) > max_lines:
        last = lines[max_lines - 1]
        while last and width(last + "…") > max_w:
            last = last[:-1]
        lines = lines[:max_lines - 1] + [last + "…"]
    return lines or [""]


def label_svg(text, cx, y, max_w, fs=9.5, max_lines=3):
    """여러 줄 x축 이름표 SVG — 줄 수와 함께 돌려준다"""
    lines = wrap_label(text, max_w, fs, max_lines)
    spans = "".join(f'<tspan x="{cx:.1f}" dy="{0 if i == 0 else fs * 1.15:.1f}">{t(x)}</tspan>' for i, x in enumerate(lines))
    return f'<text x="{cx:.1f}" y="{y:.1f}" text-anchor="middle" style="font-size:{fs}px"><title>{t(text)}</title>{spans}</text>', len(lines)


def chart_waterfall(c):
    """폭포 — total은 0부터 막대, cost는 앞 막대 끝에서 내려간다(2026-11-03 매출 → 매출총이익 → 영업이익)"""
    steps = c.get("steps") or []
    if not steps:
        return ""
    W, L, T = c.get("w", 700), 40, 18
    gw0 = (W - L - 10) / len(steps)
    nl = max(len(wrap_label(x.get("label", ""), gw0 - 4)) for x in steps)   # 이름표 줄 수만큼 아래 여백을 늘린다
    B = 14 + nl * 11
    H = 216 + B
    level, bars = 0.0, []
    for s in steps:
        v = s.get("value") or 0
        if s.get("kind") == "total":
            bars.append((s["label"], 0.0, v, "total"))
            level = v
        else:
            bars.append((s["label"], level, level + v, "cost"))
            level += v
    lo, hi = min(0.0, min(min(a, b) for _, a, b, _ in bars)), max(max(a, b) for _, a, b, _ in bars) * 1.1 or 1
    Y = lambda v: T + (hi - v) / (hi - lo) * (H - T - B)
    gw = (W - L - 10) / len(bars)
    g = [f'<line x1="{L}" x2="{W - 10}" y1="{Y(0):.1f}" y2="{Y(0):.1f}" stroke="var(--line)"/>']
    for i, (lab, a, b, kind) in enumerate(bars):
        x = L + i * gw + 4
        y1, y2 = sorted((Y(a), Y(b)))
        col = "var(--c)" if kind == "total" else "var(--b)"
        val = b - a
        g.append(f'<rect x="{x:.1f}" y="{y1:.1f}" width="{gw - 8:.1f}" height="{max(y2 - y1, 1):.1f}" rx="2" fill="{col}"><title>{t(lab)}: {_fmt(val)}</title></rect>')
        g.append(f'<text x="{x + (gw - 8) / 2:.1f}" y="{y1 - 3:.1f}" text-anchor="middle" style="font-size:10px">{_fmt(val)}</text>')
        g.append(label_svg(lab, x + (gw - 8) / 2, H - B + 14, gw - 4)[0])   # 칸 폭에 맞춘 줄바꿈 — 겹침 방지(2026-11-08)
    return f'<svg viewBox="0 0 {W} {H}">{"".join(g)}</svg>'


CHARTS = {"line": chart_line, "bars": chart_bars, "hbars": chart_hbars, "scenario": chart_scenario, "candle": chart_candle, "revision": chart_revision, "actest": chart_actest, "progress": chart_progress, "pipeline": chart_pipeline, "portfolio": chart_portfolio, "satellite": chart_satellite, "waterfall": chart_waterfall}


def figures(d, images=False):
    """그림 번호 순서 [(절, 블록)…] — pin이 있는 차트를 그 번호에 꽂고 나머지는 절 순서대로. HTML 갤러리·마크다운·노션이 같은 번호를 쓴다.
    format 3(2026-10-31 양식)은 report_layout이 정한 d['gallery'] 순서 그대로"""
    if d.get("format") == 3:
        return [(None, c["block"] if c.get("kind") == "image_block" else {"type": "chart", "chart": c}) for c in d.get("gallery") or []
                if CHARTS.get(c.get("kind")) or (images and c.get("kind") == "image_block")]   # 제품·분해도 사진은 HTML 한눈에 보기에만(마크다운·노션은 그림 번호에서 뺀다)
    figs = [(s, b) for s in d.get("sections") or [] for b in s.get("blocks") or [] if b.get("type") == "chart" and CHARTS.get((b.get("chart") or {}).get("kind")) and (b.get("chart") or {}).get("kind") != "progress"]
    pinned = sorted((f for f in figs if f[1]["chart"].get("pin")), key=lambda f: f[1]["chart"]["pin"])
    out = [f for f in figs if not f[1]["chart"].get("pin")]
    for f in pinned:
        out.insert(min(f[1]["chart"]["pin"] - 1, len(out)), f)
    return out


def under_lines(c):
    """그래프 아래 설명 — 부가 설명을 넣지 않는 규칙의 예외 둘뿐: 그림 5의 사건 번호(kind revision)와 몬테카를로 해석(conclusion). 마스터 지시 2026-10-30. HTML·마크다운·노션이 같은 줄을 쓴다"""
    if c.get("conclusion"):
        return c["conclusion"] if isinstance(c["conclusion"], list) else [c["conclusion"]]
    if c.get("kind") != "revision":
        return []
    out = []
    for e in c.get("events") or []:
        if e.get("mark"):
            pct = str(e.get("pct") or "")
            out.append(f"{e['mark']} {str(e.get('date'))[2:]} {e.get('tag')} · " + ("실적 창과 겹침" if pct == "겹침" else f"EPS 리비전 {pct}"))
    return out


def short_paras(text, limit=170):
    """긴 문단은 두 문장씩 나눈다 — 벽처럼 쌓인 글을 줄인다(마스터 지시 2026-11-01)"""
    text = str(text or "")
    if len(text) <= limit or text.startswith("**"):
        return [text]
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [" ".join(parts[i:i + 2]) for i in range(0, len(parts), 2)]


def block(b):
    k = b.get("type")
    if k == "p":
        return "".join(f"<p>{t(x)}</p>" for x in short_paras(b.get("text")))
    if k == "h3":
        return f"<h3>{t(b.get('text'))}</h3>"
    if k == "hl":
        return f'<div class="hl sm">{t(b.get("text"))}</div>'
    if k == "ul":
        return "<ul>" + "".join(f"<li>{t(i)}</li>" for i in b.get("items") or []) + "</ul>"
    if k == "table":
        head = "".join(f"<th>{t(h)}</th>" for h in b.get("headers") or [])
        rows = "".join("<tr>" + "".join(f"<td>{t(c)}</td>" for c in r) + "</tr>" for r in b.get("rows") or [])
        cap = f"<b>{t(b['title'])}</b>" if b.get("title") else ""
        table = f'<div class="card tw">{cap}<table><tr>{head}</tr>{rows}</table></div>'
        if len(b.get("rows") or []) > 6:   # 긴 표는 접어 둔다 — 읽는 흐름을 끊지 않게
            return f'<details><summary>{t(b.get("title") or "표")} 펼치기 ({len(b["rows"])}행)</summary>{table}</details>'
        return table
    if k == "boxes":   # 음영이 다른 설명 박스(마스터 지시 2026-10-31 "하이픈으로 풀이하지 말고 음영이 다른 설명박스 안에")
        out = []
        for x in b.get("items") or []:
            tag = f'<span class="tag">{t(x["tag"])}</span>' if x.get("tag") else ""
            rows = "".join(f'<div class="br"><div class="bl">{t(a)}</div><div>{t(v)}</div></div>' for a, v in x.get("lines") or [] if v)
            out.append(f'<div class="bx"><div class="bt"><span>{t(x.get("title"))}</span>{tag}</div>{rows}</div>')
        return '<div class="boxes">' + "".join(out) + "</div>"
    if k == "photos":   # 제품·시설 실사 사진(마스터 지시 2026-11-05, photo_view.py)
        import photo_view
        out = []
        for x in b.get("items") or []:
            ph = photo_view.load(x.get("file", ""))
            if ph:
                cap = f'<b>{t(x.get("name"))}</b>' + (f' — {t(x["caption"])}' if x.get("caption") else "")
                out.append(f'<figure class="ph"><img src="{ph["uri"]}" alt="{t(x.get("name"))}" loading="lazy"><figcaption>{cap}<div class="sm mut">{t(x.get("credit"))}</div></figcaption></figure>')
        return '<div class="phs">' + "".join(out) + "</div>" if out else ""
    if k == "image":   # AI 개념도 + Chiip 이름표(마스터 지시 2026-11-08, scripts/tenbagger/image_view.py)
        return image_html(b)
    if k == "bom":
        return bom_html(b)
    if k == "chart":
        c = b.get("chart") or {}
        fn = CHARTS.get(c.get("kind"))
        if not fn:
            return ""
        legend = "".join(f'<div class="sm mut">{t(x)}</div>' for x in under_lines(c))
        return f'<div class="card"><b>{t(c.get("title"))}</b>{fn(c)}{legend}</div>'
    return ""


def _img_uri(rel):
    import base64
    p = ROOT / rel
    if not p.exists():
        return None
    mime = {".webp": "image/webp", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}.get(p.suffix.lower(), "image/png")
    return f"data:{mime};base64," + base64.b64encode(p.read_bytes()).decode()


def _spread(ys, gap):
    """이름표 세로 위치를 겹치지 않게 벌린다(0~100%) — 위에서 아래로 최소 gap, 넘치면 아래에서 위로 밀어 올린다"""
    out = []
    for y in ys:
        out.append(max(y, (out[-1] + gap) if out else y))
    over = (out[-1] - 100) if out else 0
    if over > 0:
        out = [v - over for v in out]
        for k in range(len(out) - 2, -1, -1):
            out[k] = min(out[k], out[k + 1] - gap)
    return [max(v, 2.0) for v in out]


def image_html(b):
    """그림은 base64로 넣고, 컴포넌트 이름표는 그림 밖 좌우 여백에 두고 지시선으로 부품 위치의 작은 번호 점과 잇는다
    (마스터 지시 2026-11-08 "각 컴포넌트 위에 텍스트로 설명", 2026-11-09 "설명 문구를 넣을 때 이미지를 가리게 배치하지 마라").
    그림 위에는 번호 점만 — 휴대폰(640px 이하)은 좌우 칸 대신 그림 아래 번호 목록. 이름표는 Chiip이 붙인다(그림 안 글자 금지, ADR-017)"""
    uri = _img_uri(b.get("file", ""))
    if not uri:
        return f'<p class="sm mut">이미지 없음(파일 없음) — {t(b.get("title"))}</p>'
    L, W = 26.0, 48.0   # 왼쪽 칸 폭·그림 폭(%) — 오른쪽 칸도 26%
    cs = []
    for c in b.get("callouts") or []:
        no = int(c["no"])
        cs.append({"no": no, "x": float(c["x"]), "y": float(c["y"]) * 100, "own": c.get("own"), "label": c.get("label") or "",
                   "mark": CIRCLED[no - 1] if 0 < no <= len(CIRCLED) else str(no)})
    dots, labels, lines, items = [], [], [], []
    for side in ("l", "r"):
        grp = sorted([c for c in cs if (c["x"] < 0.5) == (side == "l")], key=lambda c: c["y"])
        for c, ly in zip(grp, _spread([c["y"] for c in grp], 11.0)):
            col = "var(--c)" if c["own"] else "var(--fg)"
            px = L + W * c["x"]
            ax = L - 0.8 if side == "l" else L + W + 0.8
            lines.append(f'<line x1="{ax:.1f}" y1="{ly:.1f}" x2="{px:.1f}" y2="{c["y"]:.1f}" stroke="{col}" stroke-width="1" vector-effect="non-scaling-stroke" opacity=".7"/>')
            pos = f"right:{100 - L + 1.2:.1f}%;text-align:right" if side == "l" else f"left:{L + W + 1.2:.1f}%"
            labels.append(f'<span class="ilab" style="position:absolute;top:{ly:.1f}%;{pos};width:{L - 2:.1f}%;transform:translateY(-50%);color:{col}">'
                          f'<b>{c["mark"]}</b> {t(c["label"])}</span>')
    for c in sorted(cs, key=lambda c: c["no"]):
        col = "var(--c)" if c["own"] else "var(--fg)"
        dots.append(f'<span class="idot" style="position:absolute;left:{c["x"] * 100:.1f}%;top:{c["y"]:.1f}%;border-color:{col};color:{col}">{c["no"]}</span>')
        items.append(f'<li><b style="color:{col}">{c["mark"]}</b> {t(c["label"])}</li>')
    legend = ""
    if b.get("legend"):
        legend = '<div class="sm">' + " · ".join(f'<b style="color:{"var(--c)" if own else "var(--fg)"}">{CIRCLED[int(no) - 1] if 0 < int(no) <= len(CIRCLED) else no}</b> {t(part)}' for no, part, own in b["legend"]) + "</div>"
    img = f'<div style="position:relative"><img src="{uri}" alt="{t(b.get("title"))}" style="width:100%;display:block">{"".join(dots)}</div>'
    if cs:
        body = (f'<div class="iwrap" style="position:relative;padding:0 {L:.0f}%">{img}'
                f'<svg class="ilines" viewBox="0 0 100 100" preserveAspectRatio="none" style="position:absolute;inset:0;width:100%;height:100%;pointer-events:none">{"".join(lines)}</svg>'
                f'{"".join(labels)}</div><ol class="ilist">{"".join(items)}</ol>')
    else:
        body = img
    # 그림 아래 범례·캡션은 뺀다(2026-11-11 마스터 지시 "밑에 부가 설명을 빼라"). AI 그림 표시(ADR-017)는 제목 줄 작은 표지로만 남긴다
    return f'<figure class="card"><b>사진 {t(b.get("photo"))}. {t(b.get("title"))}</b> <span class="sm mut">AI 생성 개념도</span>{body}</figure>'


CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮"


def bom_html(b):
    if b.get("scope") == "industry":
        head = ["번호", "부품", "하는 일", "공급사", "Chiip 감시", "점유율·비중", "출처", "확인/추정"]
    else:
        head = ["번호", "부품", "하는 일", "공급사", "이 회사 위치", "원가 비중", "출처", "확인/추정"]
    def rows(rs):
        out = []
        for r in rs:
            gray = ' style="color:var(--mut)"' if r[-1] == "추정" else ""
            own = ' style="color:var(--c);font-weight:700"' if r[4] == "이 회사" or str(r[4]).startswith("감시") else ""
            cells = "".join(f"<td{own if i == 4 else ''}>{t(c)}</td>" for i, c in enumerate(r))
            out.append(f"<tr{gray}>{cells}</tr>")
        return "".join(out)
    th = "".join(f"<th>{t(h)}</th>" for h in head)
    html = f'<div class="card tw"><b>BOM(부품 구성)</b><table><tr>{th}</tr>{rows(b.get("rows") or [])}</table></div>'
    if b.get("equip"):
        html += f'<div class="card tw"><b>공정·장비(제품에 들어가지 않고 만드는 데 쓰는 것)</b><table><tr>{th}</tr>{rows(b["equip"])}</table></div>'
    if b.get("candidates"):
        html += '<div class="sm">후보 메모(감시 목록 밖 상장사 — 자동으로 넣지 않는다): ' + t(" · ".join(b["candidates"])) + "</div>"
    if b.get("own_none"):
        html += '<div class="sm mut">이 회사 부품 없음(고객의 최종 제품)</div>'
    html += f'<div class="sm mut">BOM 기준일 {t(b.get("as_of") or "미확인")} · 출처 {t(b.get("source_note") or "표의 출처 열")} · 회색 행은 출처 없는 추정</div>'
    return html


# 내부 약어 → 풀어 쓴 말(마스터 지시 2026-10-29 "v2 기본이 뭐였더라? 암호로 해놓으면 직관적으로 못 알아보니 의미를 풀어서 표기하라")
PLAIN = [("DCF(v2, ", "DCF("), ("v2 기본 시나리오", "DCF 기본 시나리오"), ("v2 기본", "DCF 내재가치(기본)"), ("v2 강세", "DCF 내재가치(강세)"), ("v2 약세", "DCF 내재가치(약세)"),
         ("MC P50", "몬테카를로 중앙값"), ("MC 기대", "몬테카를로 기대값"), ("v2 엔진", "현금흐름 할인(DCF)"), ("v2 DCF", "DCF"),
         ("v2 결과", "DCF 결과"), ("v2의", "DCF의"), ("(v2,", "(DCF,"), ("v2 ", "DCF ")]


def plain(s):
    for a, b in PLAIN:
        s = s.replace(a, b)
    return s


# 양식에 참고 문헌을 남기지 않는다(마스터 지시 2026-10-30 "양식에 'Greenwood & Hanson 2015' 같은 참고 자료 출처를 남기지 마라") — 저자 목록은 저장소 인용에서 뽑았다
REF_NAMES = r"Bessembinder|Greenwood|Mauboussin|Damodaran|Shiller|Bhojraj|Rhodes-Kropf|Boehmer|Lakonishok|LeBaron|Osler|Asquith|Karceski|Yartseva|Rappaport|Peduzzi"
REF_JOURNAL = r"JFE|QJE|JF|RFS|JFQA|JPE|AER|FRBNY|Journal of Finance"
REF_PAREN = re.compile(rf"\s*[(（][^()（）]*(?:\b(?:{REF_NAMES})\b|(?<!\d)(?:19|20)\d\d(?!\d)[^()（）]*\b(?:{REF_JOURNAL})\b)[^()（）]*[)）]")
REF_CITE = re.compile(rf"\b(?:{REF_NAMES})\b[^.。;]{{0,40}}(?<!\d)(?:19|20)\d\d(?!\d)")   # 한글 조사가 붙어도 잡히게 \b 대신 숫자 경계


# 리포트 글에 계산 주체(엔진)를 넣지 않는다(마스터 지시 2026-11-08 "Chiip이 본인을 엔진이라고 부르는데, 굳이 주체를 넣지 마라").
# 가스엔진·엔진 블록 같은 실제 제품은 건드리지 않도록 평가 용어 앞의 '엔진'만 지운다
_SELF = [(re.compile(r"\(?(?:v2|멀티플) 엔진\)?"), ""), (re.compile(r"(?<=\(DCF\)) 엔진"), ""),
         (re.compile(r"엔진이 고른다"), "규칙으로 고른다"), (re.compile(r"엔진이 고른 "), "선정 "), (re.compile(r"엔진이 정한 "), "산정된 "),
         (re.compile(r"엔진이 (?=동종|과거|펀더멘털|규칙)"), ""), (re.compile(r"엔진[은의] (?=\d|최근|약세|기본|강세)"), ""),
         (re.compile(r"엔진 (?=목표주가|규칙 등급|선정|DCF|배수|약세|강세|기본|시나리오|해석|계산|판단|산정|등급|업사이드|멀티플|`)"), "")]


def no_self(x):
    if not isinstance(x, str) or "엔진" not in x:
        return x
    for pat, rep in _SELF:
        x = pat.sub(rep, x)
    return x


def _scrub_text(x):
    return no_self(REF_PAREN.sub("", x)) if isinstance(x, str) else x


def _walk(o, fn):
    if isinstance(o, dict):
        return {k: _walk(v, fn) for k, v in o.items()}
    if isinstance(o, list):
        return [_walk(v, fn) for v in o]
    return fn(o)


# 데이터 제공처 이름을 남기지 않는다(마스터 지시 2026-10-30 "재무 데이터와 컨센서스 데이터, 어닝콜 스크립트를 가져온 출처를 남기지 마라", "출처를 남기면 가독성이 떨어진다") — 추정치는 일반 명칭 '컨센서스'로만
VENDOR_RE = re.compile(r"Fiscal\.ai|fiscal\.ai|Zacks|zacks|easyconomics|ir_events|company_estimates")
VENDOR_SUBS = [(re.compile(r"\s*\[?\(?Data provided by Zacks Investment Research, Inc\.,?\s*\[?www\.zacksdata\.com\]?(?:\([^)]*\))?\)?\.?"), ""),
               (re.compile(r"[,·]?\s*(?:Fiscal\.ai\s*)?(?:company_)?(?:ir_events(?:_transcript)?|estimates)(?:\s*q\d-\d{4})?"), ""),
               (re.compile(r"\s*\(https?://www\.zacksdata\.com\)"), ""),
               (re.compile(r"(?:Fiscal\.ai|Fiscal)\s*(?:자체\s*)?추정|모델 추정"), "컨센서스"),
               (re.compile(r"Zacks\s*(?:컨센서스|추정)|애널리스트 추정"), "컨센서스"),
               (re.compile(r"Zacks\s*(의견|목표가)"), r"애널리스트 \1"),
               (re.compile(r"Zacks(?=\s*[$CF\d])"), "컨센서스"),
               (re.compile(r"\s*\(Fiscal\)"), ""),
               (re.compile(r"(?<![A-Za-z])Fiscal(?=\s*\$)"), "컨센서스"),
               (re.compile(r"(?:Fiscal\.ai|Zacks)\s*(?:일별 배수|재무|일봉|장기 월봉|개요|표준화)?\s*(?:기준)?\s*"), ""),
               (re.compile(r"(?<![A-Za-z])Fiscal(?![A-Za-z ]*[Yy]ear)"), "컨센서스"),
               (re.compile(r"\s*[(（]\s*[)）]"), "")]
NOT_SOURCE = re.compile(r"Fiscal|fiscal\.ai|Zacks|zacks|트랜스크립트|easyconomics|보강 적용")


def _strip_vendor(x):
    if not isinstance(x, str):
        return x
    for pat, rep in VENDOR_SUBS:
        x = pat.sub(rep, x)
    return x


def _glossary():
    return yaml.safe_load((ROOT / "config" / "report_glossary.yaml").read_text(encoding="utf-8"))


_YEAR = re.compile(r"(?<![A-Za-z0-9])(CY|FY)(20\d\d)(?![A-Za-z0-9(（])")
_URL = re.compile(r"(https?://\S+)")


_Q4 = re.compile(r"(?<![0-9A-Za-z_/.\-])20(\d\d)Q([1-4])(?![0-9A-Za-z])")
_Q2 = re.compile(r"(?<![0-9A-Za-z_/.\-])(\d\d)Q([1-4])(?![0-9A-Za-z])")


def quarter_text(x):
    """2026Q3·26Q3 → 3Q26(마스터 지시 2026-10-31). 주소는 건드리지 않는다"""
    if not isinstance(x, str) or "Q" not in x:
        return x
    return "".join(p if _URL.fullmatch(p) else _Q2.sub(r"\2Q\1", _Q4.sub(r"\2Q\1", p)) for p in _URL.split(x))


def gloss_text(s, terms, pat, seen):
    """처음 나온 용어 뒤에 (풀이). 바로 뒤에 괄호가 있으면 이미 풀이된 것으로 본다. 주소는 건드리지 않는다"""
    def one(m):
        w = m.group(0)
        if w in seen:
            return w
        after = m.string[m.end():m.end() + 2]
        if after[:1] in ("(", "（"):
            if after[1:2].isdigit() or after[1:2] in ("+", "-", "−", "$", "~"):
                return w   # '멀티플(−54%)'처럼 숫자 괄호면 다음에 나오는 곳에서 풀이한다
            seen.add(w)
            return w
        seen.add(w)
        return f"{w}({terms[w]})"

    out = []
    for part in _URL.split(s):
        out.append(part if _URL.fullmatch(part) else pat.sub(one, part))
    return "".join(out)


# 회사 설명으로 쓴 풀이 — 회사명은 뜻을 풀지 않는다(마스터 지시 2026-11-08 "기업명의 의미는 풀이하지 마라")
_NATION = "(?:미국|중국|일본|대만|한국|영국|프랑스|캐나다|독일|네덜란드|스위스)"
_COMPANY_DEF = re.compile(rf"회사(?!용)|은행|증권|운용사|연구소|공대|합작사|^{_NATION} [A-Z]|^{_NATION} \S+(?<![청국부처원회법소])$")
_KIND_DEF = re.compile(r"전문|군$|들$")   # 'GPU 임대 전문 클라우드 회사'처럼 회사 '유형' 설명은 풀이한다
_PERIOD = re.compile(r"[FC]?Q[1-4]|FY\d*")   # 회계 분기·연도 표기는 금융 용어라 풀지 않는다


def clean_def(term, text):
    """풀이를 다듬는다 — 용어 자신을 되풀이하는 괄호는 지우고(XPV: '…플랫폼(AI XPV)' → '…플랫폼'), 남은 괄호는 쉼표로 바꾼다(괄호 안 괄호 방지).
    풀이가 회사 설명이거나 지운 뒤에도 용어를 되풀이하면 None(풀이하지 않는다). 마스터 지시 2026-11-08"""
    t = re.sub(r"\s*[(（][^()（）]*[)）]", lambda m: "" if term in m.group(0) else ", " + m.group(0).strip()[1:-1], str(text)).strip(" ,")
    if not t or term in t or (_COMPANY_DEF.search(t) and not _KIND_DEF.search(t)) or _PERIOD.fullmatch(term):
        return None
    return t


def gloss(d):
    """읽는 순서대로(Chiip View → 요약 → 본문 글·표) 용어를 처음 나오는 곳에서 풀이한다. 숫자 타일·차트 글자는 건드리지 않는다"""
    glossary = _glossary()
    raw = {**glossary["terms"], **(d.get("terms") or {})}   # d['terms'] = 이 리포트의 제품명·정책명 풀이(datapack terms)
    skip = set(glossary.get("names") or {}) | set(d.get("names") or [])   # 회사명·티커는 풀지 않는다(2026-11-08)
    skip |= set(glossary.get("no_gloss") or {}) | set(glossary.get("plain_ok") or [])   # 금융 용어·흔한 약자는 datapack terms에 있어도 풀지 않는다
    terms = {k: v for k, v in ((k, clean_def(k, v)) for k, v in raw.items() if k not in skip) if v}
    names = sorted(terms, key=len, reverse=True)
    plain = {**(glossary.get("no_gloss") or {}), **(glossary.get("names") or {})}   # 마스터 지시 2026-10-31 — 이 용어는 괄호 풀이를 달지 않는다. 모델이 직접 적은 풀이도 지운다
    drop = re.compile("|".join(rf"(?<={re.escape(t)})[(（](?:{'|'.join(re.escape(w) for w in ws)})[)）]" for t, ws in plain.items())) if plain else None
    pat = re.compile(r"(?<![A-Za-z0-9/.\-])(?:" + "|".join(re.escape(x) for x in names) + r")(?![A-Za-z0-9/\-])")
    seen = set()
    twin = re.compile(r"[(（]([^()（）]+)[)）][(（]([^()（）]+)[)）]")   # '이름(관계사)(엔진·부품)'처럼 이어진 괄호는 하나로(2026-11-08)
    g = lambda x: twin.sub(r"(\1, \2)", gloss_text(drop.sub("", x) if drop else x, terms, pat, seen)) if isinstance(x, str) else x
    if d.get("verdict"):
        d["verdict"]["view"] = g(d["verdict"].get("view"))
    for s in d.get("summary") or []:
        s["a"] = g(s.get("a"))
    for sec in d.get("sections") or []:
        for b in sec.get("blocks") or []:
            k = b.get("type")
            if k in ("p", "hl", "h3"):
                b["text"] = g(b.get("text"))
            elif k == "ul":
                b["items"] = [g(i) for i in b.get("items") or []]
            elif k == "table":
                b["rows"] = [[g(c) for c in r] for r in b.get("rows") or []]
            elif k == "boxes":
                for x in b.get("items") or []:
                    x["title"] = g(x.get("title"))   # 제품명 제목도 풀이한다(마스터 지시 2026-11-01)
                    x["lines"] = [[a, g(v)] for a, v in x.get("lines") or []]
    return d


def clean_vendor(d):
    """리포트 JSON에 저장하기 전 제공처 표기를 지운다 — 차트·표 주석까지(렌더되지 않는 칸도 파일에 남지 않게)"""
    d = {**d, "sources": [x for x in d.get("sources") or [] if not NOT_SOURCE.search(str(x))]}
    return _walk(d, _strip_vendor)


def scrub(d):
    """참고 문헌·데이터 제공처·읽는 법 문단을 지우고 용어를 풀이한다. 괄호 밖에 인용이나 제공처가 남으면 ValueError — 모델이 문장을 고쳐야 한다"""
    d = {**d, "sources": [x for x in d.get("sources") or [] if not REF_CITE.search(str(x)) and not NOT_SOURCE.search(str(x))]}
    d.pop("lead", None)
    d = _walk(_walk(_walk(d, _scrub_text), _strip_vendor), quarter_text)
    for s in d.get("sections") or []:
        s["blocks"] = [b for b in s.get("blocks") or [] if not (b.get("type") in ("p", "hl") and str(b.get("text")).startswith(("**읽는 법", "리비전 출처")))]
    body = json.dumps(d, ensure_ascii=False)
    left = REF_CITE.search(body) or VENDOR_RE.search(body)
    if left:
        raise ValueError(f"남기면 안 되는 표기가 있다: {body[max(0, left.start() - 30):left.end() + 30]}")
    return gloss(d)


def upside(d):
    """Chiip View 업사이드(+%) — verdict.upside가 있으면 그것, 없으면 판단 시나리오 확률 가중값 ÷ 현재값 − 1(기간은 시나리오 제목)"""
    v = d.get("verdict") or {}
    if v.get("upside") is not None:
        return v["upside"], v.get("upside_basis") or ""
    sc = next((b["chart"] for s in d.get("sections") or [] for b in s.get("blocks") or []
               if b.get("type") == "chart" and (b.get("chart") or {}).get("kind") == "scenario"), None)
    if not sc or not sc.get("current") or not sc.get("cases"):
        return None, ""
    ew = sum(float(c.get("prob") or 0) * float(c.get("value") or 0) for c in sc["cases"])
    return ew / float(sc["current"]) - 1, f"판단 시나리오 확률 가중 · {sc.get('title', '')}"


def render3(d):
    """2026-10-31 양식 — 제목 → Chiip View → 대시보드 → 한 장 요약 → 한눈에 보기(그림 번호 없음) → 본론. 순서는 report_layout이 정한다"""
    v = d.get("verdict") or {}
    parts = [f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
             f'<title>{t(d["company"])} 텐배거 리포트</title><style>{CSS}</style></head><body><div class="w">',
             f'<h1>{t(d["title"])}</h1>' + (f'<p class="sub">{t(d["subtitle"])}</p>' if d.get("subtitle") else ""),
             f'<p class="lead">{t(d["date"])} · {t(d["company"])}({t(d["ticker"])}) · 기업: {t(d["biz"])}</p>']
    parts.append(f'<div class="verdict"><b>Chiip View</b><br>{t(v.get("view"))}</div>')
    if d.get("tiles"):
        parts.append('<div class="dash">' + "".join(
            f'<div><div class="k">{t(x.get("k"))}</div><div class="v {x.get("tone", "")}">{t(x.get("v"))}</div><div class="s">{t(x.get("sub"))}</div></div>' for x in d["tiles"]) + "</div>")
    if d.get("summary"):
        parts.append("<h2>한 장 요약</h2><div class=\"ans\">" + "".join(f'<div><b class="q">{t(s.get("q"))}</b>{t(s.get("a")).replace(chr(10), "<br>")}</div>' for s in d["summary"]) + "</div>")
    figs = figures(d, images=True)
    if figs or d.get("gallery_photos"):   # 사진도 한눈에 보기에(2026-11-07)
        parts.append("<h2>한눈에 보기</h2><div class=\"gal\">" + "".join(f"<div>{block(b)}</div>" for _, b in figs) + "".join(f"<div>{block(b)}</div>" for b in d.get("gallery_photos") or []) + "</div>")
    names = [str(s.get("h2")) for s in d.get("sections") or []]
    parts.append('<nav class="toc">' + "".join(f'<a href="#s{i}">{t(n)}</a>' for i, n in enumerate(names)) + "</nav>")
    for i, s in enumerate(d.get("sections") or []):
        # 한눈에 보기 다음 세부 설명은 절마다 접어 둔다(마스터 지시 2026-11-08) — 제목을 누르거나 위 목차를 누르면 펼쳐진다
        parts.append(f"<section id=\"s{i}\"><details class=\"sec\"><summary><h2>{t(s.get('h2'))}</h2></summary>" + "".join(block(b) for b in s.get("blocks") or []) + "</details></section>")
    src = "; ".join(t(x) for x in d.get("sources") or [])
    parts.append(f'<div class="foot">출처: {src or "미기재"}<br>{DISCLAIMER3}</div></div>{FIT_JS}</body></html>')
    return money_units(fx_units(chiip_name("".join(parts).replace("치입 판단", "Chiip View").replace("Chiip 판단", "Chiip View"))))


def render(d):
    for key in ("title", "date", "ticker", "company", "biz"):
        if not d.get(key):
            raise ValueError(f"필수 항목 없음: {key}")
    d = scrub(json.loads(plain(json.dumps(d, ensure_ascii=False))))
    if d.get("format") == 3:
        return render3(d)
    v = d.get("verdict") or {}
    parts = [f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
             f'<title>{t(d["company"])} 텐배거 리포트</title><style>{CSS}</style></head><body><div class="w">',
             f'<h1>{t(d["title"])}</h1>' + (f'<p class="sub">{t(d["subtitle"])}</p>' if d.get("subtitle") else ""),
             f'<p class="lead">{t(d["date"])} · {t(d["company"])}({t(d["ticker"])}) · 기업: {t(d["biz"])}</p>']
    if v:   # 마스터 지시 2026-10-29: 확신도 → 컨빅션(같은 고·중·저), 인사이트 → 알파(같은 10점 체계), 업사이드 +% 추가
        up, _ = upside(d)
        alpha = v.get("insight") if v.get("insight") is not None else v.get("alpha")
        badges = "".join(f'<span class="badge">{t(x)}</span>' for x in (
            f"컨빅션 {v['confidence']}" if v.get("confidence") else None,
            f"알파 {alpha}/10" if alpha is not None else None,
            f"업사이드 {up:+.0%}" if up is not None else None) if x)
        parts.append(f'<div class="verdict"><b>Chiip View</b> {badges}<br>{t(v.get("view"))}</div>')
    if d.get("summary"):
        parts.append("<h2>한 장 요약</h2><div class=\"ans\">" + "".join(
            f'<div><b class="q">{t(s.get("q"))}</b>{t(s.get("a")).replace(chr(10), "<br>")}</div>' for s in d["summary"]) + "</div>")
    if d.get("tiles"):
        parts.append('<div class="tiles">' + "".join(
            f'<div class="tile"><div class="k">{t(x.get("k"))}</div><div class="v {x.get("tone", "")}">{t(x.get("v"))}</div><div class="k">{t(x.get("sub"))}</div></div>'
            for x in d["tiles"]) + "</div>")
    # 그래프 전체를 상단에(마스터 지시 2026-10-29 "Chiip View와 한 장 요약 다음 시각물 그래프를 전부 — 시간이 없을 때 상단만 보고 파악")
    figs = figures(d)
    num = {id(b): i for i, (_, b) in enumerate(figs, 1)}
    if figs:
        parts.append("<h2>한눈에 보기 — 그래프 전체</h2><div class=\"gal\">" + "".join(
            f'<div id="fig{num[id(b)]}">' + block(b).replace("<b>", f'<b>그림 {num[id(b)]} · ', 1) + "</div>"
            for _, b in figs) + "</div>")
    for s in d.get("sections") or []:
        body = "".join(
            (f'<p class="sm mut">📊 <a href="#fig{num[id(b)]}">그림 {num[id(b)]}</a> · {t((b.get("chart") or {}).get("title"))} (위 \'한눈에 보기\')</p>'
             if id(b) in num else block(b)) for b in s.get("blocks") or [])
        parts.append(f"<h2>{t(s.get('h2'))}</h2>" + body)
    src = "; ".join(t(x) for x in d.get("sources") or [])
    parts.append(f'<div class="foot">출처: {src or "미기재"}<br>{DISCLAIMER}</div></div>{FIT_JS}</body></html>')
    out = chiip_name("".join(parts).replace("치입 판단", "Chiip View").replace("Chiip 판단", "Chiip View"))   # GitHub·텔레그램 보고 표기(마스터 지시 2026-10-29)
    return money_units(fx_units(out))   # $25B·$M·$T 표기(마스터 지시 2026-10-29), ¥·€·£ 표기(2026-10-31)


def artifact_html(d):
    """claude.ai 비공개 Artifact 판(마스터 지시 2026-10-30 "리포트 링크는 html로" — 모바일에서 그대로 보이는 보기 링크).
    게시 때 문서 뼈대가 씌워지므로 doctype·html·head·body를 빼고, 이름 같은 짧은 <title>과 옆 여백 약속 메타를 맨 위에 둔다."""
    full = render(d)
    style = re.search(r"<style>.*?</style>", full, re.S).group(0)
    body = re.search(r"<body>(.*)</body>", full, re.S).group(1)
    name = f"{d['ticker']} 텐배거 리포트 {str(d['date'])[5:].replace('-', '·')}"
    return f'<title>{html.escape(name)}</title>\n<meta name="claude:viewport-fit-sides" content="cover">\n{style}\n{body}\n'


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    src = Path(argv[0])
    d = json.loads(src.read_text(encoding="utf-8"))
    out = src.with_suffix(".html")
    out.write_text(render(d), encoding="utf-8")
    print(f"[텐배거 리포트] {out} ({out.stat().st_size // 1024}KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
