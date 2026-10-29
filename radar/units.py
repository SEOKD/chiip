"""금액 단위 표기 — 마스터 지시 2026-10-29 "단위 표기를 250억$로 하지 말고 $25B 이렇게 하라. million도 M으로, trillion도 T로"

money_units(text): 텔레그램 발송 직전(notify.brand)과 리포트 HTML 렌더 직후(report_html.render)에 한 번 거친다.
  124억$ → $12.4B · 1,472억$ → $147.2B · 5억$ → $500M · 1.2조$ → $1.2T · 34.2백만 달러 → $34.2M · 100~120억$ → $10~12B · −18억$ → −$1.8B
  단위 이름표: (백만 달러) → ($M) · (십억 달러)·(10억 달러) → ($B) · M$ → $M · B$ → $B · T$ → $T
원화·엔화(억 원·억 엔·조 원)는 건드리지 않는다.
"""
import re

_NUM = r"\d[\d,]*(?:\.\d+)?"
_USD = r"\s*(?:\$|달러|USD)"


def _f(x):
    return float(x.replace(",", ""))


def _fmt(v):
    """유효숫자 3개 안팎 — 12.4·147.2·1.07·25"""
    s = f"{v:,.2f}" if abs(v) < 10 else f"{v:,.1f}"
    return s.rstrip("0").rstrip(".") if "." in s else s


def _eok(v):
    """억 달러 값 → ($ 단위 문자열 본문, 접미사)"""
    if abs(v) >= 10000:
        return _fmt(v / 10000), "T"
    if abs(v) >= 10:
        return _fmt(v / 10), "B"
    return _fmt(v * 100), "M"


def money_units(text):
    if not text or not any(k in text for k in ("억", "조", "백만", "M$", "B$", "T$", "달러")):
        return text
    s = text
    # 범위: 100~120억$ / 1.2~1.5조$
    def rng(m, unit):
        a, b = _f(m.group(2)), _f(m.group(3))
        sign = m.group(1) or ""
        if unit == "조":
            return f"{sign}${_fmt(a)}~{_fmt(b)}T"
        (na, sa), (nb, sb) = _eok(a), _eok(b)
        return f"{sign}${na}{sa if sa != sb else ''}~{nb}{sb}"
    s = re.sub(rf"([−-]?)({_NUM})\s*[~–-]\s*({_NUM})\s*조{_USD}", lambda m: rng(m, "조"), s)
    s = re.sub(rf"([−-]?)({_NUM})\s*억?\s*[~–-]\s*({_NUM})\s*억{_USD}", lambda m: rng(m, "억"), s)
    # 조 + 억 혼합: 1조 2,000억$
    s = re.sub(rf"([−-]?)({_NUM})\s*조\s*({_NUM})\s*억{_USD}",
               lambda m: f"{m.group(1)}${_fmt(_f(m.group(2)) + _f(m.group(3)) / 10000)}T", s)
    s = re.sub(rf"([−-]?)({_NUM})\s*조{_USD}", lambda m: f"{m.group(1)}${_fmt(_f(m.group(2)))}T", s)
    s = re.sub(rf"([−-]?)({_NUM})\s*억{_USD}", lambda m: "{}${}{}".format(m.group(1), *_eok(_f(m.group(2)))), s)
    s = re.sub(rf"([−-]?)({_NUM})\s*백만{_USD}", lambda m: f"{m.group(1)}${_fmt(_f(m.group(2)))}M", s)
    # 단위 이름표
    s = re.sub(r"\(\s*백만\s*달러\s*\)", "($M)", s)
    s = re.sub(r"\(\s*(?:십억|10억)\s*달러\s*\)", "($B)", s)
    s = re.sub(r"\(\s*조\s*달러\s*\)", "($T)", s)
    s = re.sub(r"(?<![A-Za-z$])([MBT])\$(?![A-Za-z0-9])", r"$\1", s)
    return s
