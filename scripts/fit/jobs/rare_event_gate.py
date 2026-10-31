"""MLP-20261030-02 검증 — 희귀 사건 브리어 비교에서 채택 관문이 틀린 모델을 통과시키는 비율(계산 검증, 피팅 아님).
진실: 모든 관측의 사건 확률 p. 기존 모델 = p(보정됨), 확장 모델 = ratio × p(과소 예측 — 진실보다 나쁨). 통과는 전부 오채택.
사용: py scripts/fit/jobs/rare_event_gate.py [--reps 20000]
"""
import argparse
import pathlib
import random
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import harness

RULE = {"min_oos_n": 30, "min_oos_improvement": 0.05}


def run(p, n, ratio, reps, rng, gates=(10, 25)):
    a = b = zero = 0
    gated = {m: 0 for m in gates}
    for _ in range(reps):
        ys = [1 if rng.random() < p else 0 for _ in range(n)]
        base = [(p - y) ** 2 for y in ys]
        ext = [(ratio * p - y) ** 2 for y in ys]
        ok_test = harness.nested_test(base, ext, trials=1, alpha=0.05, min_gain=0.05)[0]
        ok_rule = harness.adoption_decision(sum(base) / n, sum(ext) / n, n, RULE)[0]
        events = sum(ys)
        a += ok_test
        b += ok_rule
        zero += events == 0
        for m in gates:
            gated[m] += ok_test and events >= m
    return a / reps, b / reps, zero / reps, {m: v / reps for m, v in gated.items()}


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=20000)
    a = ap.parse_args(argv)
    rng = random.Random(20261030)
    print("ratio,p,n,기대사건,nested_test,adoption_decision,사건0회,사건10+관문,사건25+관문")
    for ratio in (0.5, 0.8):
        for p in (0.01, 0.02, 0.05):
            for n in (30, 60, 120, 250, 500, 1000):
                t, r, z, g = run(p, n, ratio, a.reps, rng)
                print(f"{ratio},{p},{n},{n * p:.1f},{t:.3f},{r:.3f},{z:.3f},{g[10]:.3f},{g[25]:.3f}")


if __name__ == "__main__":
    main(sys.argv[1:])
