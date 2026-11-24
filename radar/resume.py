"""긴 수집 작업의 이어받기 커서(2026-11-24 점검 D3 후속, docs/audit/20261124_pipeline_audit.md)

trade-ppi는 25분 한도에서도 끊겼다(44개 입력 × 7개국 + e-Stat 10년 표). 끊기면 처음부터 다시 돌아 영원히 끝나지 못한다.
단계(입력 하나·종목 하나·묶음 하나)를 마칠 때마다 결과를 radar/state/resume_<이름>.json에 적고, 다음 회차는 끝난 단계를 건너뛴다.
한 주기가 끝나면 finish()로 비운다. 주기 시작이 days일보다 오래됐거나 설정(key)이 바뀌면 새 주기로 다시 시작한다.

run_hourly는 시간 초과 때 progress()를 앞뒤로 비교해 진전이 있으면 RETRY_MIN 뒤에 다시 돌린다(하루 뒤가 아니라).
"""
import hashlib
import json
from datetime import date

from pollers import common

PREFIX = "resume_"


def digest(obj):
    """설정이 바뀌면 이어받지 않도록 — 짧은 해시"""
    return hashlib.sha1(json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()[:12]


class Cursor:
    def __init__(self, name, key="", days=2, today=None):
        self.name, self.today = name, today or common.now_kst().date()
        st = common.load_state(PREFIX + name)
        fresh = st.get("start") and st.get("key") == key and (self.today - date.fromisoformat(st["start"])).days < days
        self.st = st if fresh else {"start": self.today.isoformat(), "key": key, "done": {}}
        self.resumed = bool(fresh and self.st["done"])

    def done(self, step):
        return step in self.st["done"]

    def get(self, step, default=None):
        return self.st["done"].get(step, default)

    def mark(self, step, data=True):
        self.st["done"][step] = data
        self.st["at"] = common.iso(common.now_kst())
        common.save_state(PREFIX + self.name, self.st)

    def finish(self):
        common.save_state(PREFIX + self.name, {})

    def __len__(self):
        return len(self.st["done"])


def progress(name):
    """이 작업이 지금까지 마친 단계 수 — 진행 기록이 없으면 0"""
    return len((common.load_state(PREFIX + name) or {}).get("done") or {})
