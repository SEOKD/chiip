"""금액 단위 표기 — 마스터 지시 2026-10-29 "단위 표기를 250억$로 하지 말고 $25B 이렇게 하라. million도 M으로, trillion도 T로",
같은 날 보강 "Pulse에서는 여전히 506억$로 표기하고 있다 — $50.6B로"

money_units(text): 텔레그램 발송 직전(notify.brand)과 리포트 HTML 렌더 직후(report_html.render)에 한 번 거친다.
  한국식 단위(조·억·천만·백만·만)를 섞어 쓴 달러 금액을 달러로 환산해 $T·$B·$M·$K 중 맞는 단위로 다시 쓴다.
  124억$ → $12.4B · 506억$ → $50.6B · 5억$ → $500M · 1.2조$ → $1.2T · 1조 2,000억$ → $1.2T · 3억 4천만 달러 → $340M
  4,200만$ → $42M · 12,014.9백만$ → $12.0B · $3.4억 → $340M · 30억 불 → $3B · 100~120억$ → $10~12B · −18억$ → −$1.8B
  단위 이름표: (백만 달러) → ($M) · (십억 달러)·(10억 달러) → ($B) · M$ → $M · B$ → $B · T$ → $T
원화·엔화(억 원·억 엔·조 원)는 건드리지 않는다. 달러 표시(USD·$·달러·불)가 붙은 금액만 바꾼다.
"""
import re

_NUM = r"\d[\d,]*(?:\.\d+)?"
_USD = r"\s*(?:\$|달러|USD|불)"
UNITS = (("조", 1e12), ("억", 1e8), ("천만", 1e7), ("백만", 1e6), ("만", 1e4))
_UNIT_RE = "|".join(u for u, _ in UNITS)   # 천만·백만이 만보다 먼저
_MUL = dict(UNITS)
# 조·억·천만·백만·만을 하나 이상 이어 쓴 금액(예: 1조 2,000억, 3억 4천만, 4,200만)
_COMPOUND = "".join(rf"(?:(?P<{k}>{_NUM})\s*{u}\s*)?" for k, u in (("jo", "조"), ("eok", "억"), ("cm", "천만"), ("bm", "백만"), ("man", "만")))
_KEYS = {"jo": 1e12, "eok": 1e8, "cm": 1e7, "bm": 1e6, "man": 1e4}


def _f(x):
    return float(x.replace(",", ""))


def _fmt(v):
    """유효숫자 3개 안팎 — 12.4·147.2·1.07·25. 반올림으로 값이 바뀌면 끝자리 0을 남긴다(12,014.9백만 → 12.0)"""
    s = f"{v:,.2f}" if abs(v) < 10 else f"{v:,.1f}"
    if "." in s and abs(float(s.replace(",", "")) - v) < 1e-9 * max(1.0, abs(v)):
        s = s.rstrip("0").rstrip(".")
    return s


def usd(v):
    """달러 금액(실수) → '$12.4B' 형식(부호 없이)"""
    a = abs(v)
    for lim, suf in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if a >= lim:
            return f"${_fmt(a / lim)}{suf}"
    return f"${_fmt(a)}"


def _suffix(v):
    a = abs(v)
    return next(((lim, suf) for lim, suf in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")) if a >= lim), (1.0, ""))


def _compound_value(m):
    vals = [(_f(m.group(k)), mul) for k, mul in _KEYS.items() if m.group(k)]
    return sum(v * mul for v, mul in vals) if vals else None


def money_units(text):
    if not text or not any(k in text for k in ("억", "조", "만", "M$", "B$", "T$", "달러", "불")):
        return text
    s = text

    # ① 범위: 100~120억$ · 120억~150억$ · 4,000~5,000만$ — 앞 숫자의 단위가 없으면 뒤 단위를 쓴다
    def rng(m):
        mul = _MUL[m.group("u2")]
        a = _f(m.group("a")) * (_MUL[m.group("u1")] if m.group("u1") else mul)
        b = _f(m.group("b")) * mul
        lim, suf = _suffix(max(abs(a), abs(b)))
        return f"{m.group('sign') or ''}${_fmt(a / lim)}~{_fmt(b / lim)}{suf}"
    s = re.sub(rf"(?P<sign>[−-]?)(?P<a>{_NUM})\s*(?P<u1>{_UNIT_RE})?\s*[~–-]\s*(?P<b>{_NUM})\s*(?P<u2>{_UNIT_RE}){_USD}", rng, s)

    # ② 앞에 $가 붙은 형태: $3.4억 · $1.2조 (뒤에 원·엔이 오면 건너뜀)
    def pre(m):
        return usd(_f(m.group("n")) * _MUL[m.group("u")])
    s = re.sub(rf"\$\s*(?P<n>{_NUM})\s*(?P<u>{_UNIT_RE})(?!\s*(?:원|엔|\$|달러|불))", pre, s)

    # ③ 조·억·천만·백만·만을 이어 쓴 금액 + 달러 표시
    def comp(m):
        v = _compound_value(m)
        return m.group(0) if v is None else f"{m.group('sign') or ''}{usd(v)}"
    s = re.sub(rf"(?P<sign>[−-]?)(?=\d){_COMPOUND}{_USD}", comp, s)

    # ④ 단위 이름표
    s = re.sub(r"\(\s*백만\s*(?:달러|불)\s*\)", "($M)", s)
    s = re.sub(r"\(\s*(?:십억|10억)\s*(?:달러|불)\s*\)", "($B)", s)
    s = re.sub(r"\(\s*조\s*(?:달러|불)\s*\)", "($T)", s)
    s = re.sub(r"(?<![A-Za-z$])([MBT])\$(?![A-Za-z0-9])", r"$\1", s)
    return s
