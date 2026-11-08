"""Vertex AI 클라이언트 — 로그인 만료 없는 자동 수집(마스터 지시 2026-11-08 "Vertex AI API 키를 넣었다. 이제 로그인 만료 없이 자동으로 수집하는 체계가 가동되도록")

1순위: D:\\local-only\\secrets\\.env의 VERTEX_API_KEY(Agent Platform API 전용, 서비스 계정 chiip-vertex에 묶인 키) — 사람 승인 없이 계속 동작한다.
2순위: gcloud 로그인(ADC, project·location) — 키가 없을 때만. 로그인은 보안키 재인증으로 풀릴 수 있다.
요금은 두 경로 모두 같은 Google Cloud 결제 계정(무료 크레딧 먼저). 키는 common.load_env()로만 읽고 출력·로그·파일·커밋하지 않는다.
쓰는 곳: product_images.vertex_generate(그림 생성)·image_qa.review(자동 검수)·bom_discover.discover(부품 찾기, Google 검색 그라운딩).
"""
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _key():
    sys.path.insert(0, str(ROOT / "radar"))
    from pollers import common
    return common.load_env().get("VERTEX_API_KEY")


def mode():
    return "api_key" if _key() else "adc"


def client(cfg=None):
    from google import genai
    warnings.filterwarnings("ignore", message=".*quota project.*")
    k = _key()
    if k:
        return genai.Client(vertexai=True, api_key=k)
    v = (cfg or {}).get("vertex") or {}
    return genai.Client(vertexai=True, project=v["project"], location=v.get("location", "global"))
