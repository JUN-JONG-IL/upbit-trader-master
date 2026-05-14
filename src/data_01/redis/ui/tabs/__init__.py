"""
Package initializer for redis.ui.tabs

이 파일을 두는 목적:
- 상대 import를 명확하게 하여 Pylance/IDE 경고 감소
- tabs 패키지에서 제공하는 모듈들을 한곳에서 노출하여
  상위 모듈이 from .tabs import common, status_tab 형태로 안정적으로 사용 가능하게 함.
- 필요한 경우 여기서 추가 초기화(로깅 설정 등)를 할 수 있음.

사용 예:
    from .tabs import common, status_tab
"""

from importlib import import_module
from typing import List

__all__: List[str] = [
    "common",
    "connection_tab",
    "status_tab",
    "pubsub_tab",
    "gap_queue_tab",
    "l1_cache_tab",
    "cluster_tab",
    "sentinel_tab",
]

# 명시적 임포트: 존재하지 않는 모듈이 있으면 ImportError를 발생시키지 않고
# None으로 대체하여 상위에서 안전하게 검사할 수 있게 함.
# (대부분의 경우 모듈이 모두 존재하므로 정상적으로 임포트됩니다.)
def _safe_import(name: str):
    try:
        return import_module(f".{name}", package=__package__)
    except Exception:
        # 임포트 실패 시 None으로 두고 로그는 남기지 않음(상위에서 처리)
        return None

common = _safe_import("common")
connection_tab = _safe_import("connection_tab")
status_tab = _safe_import("status_tab")
pubsub_tab = _safe_import("pubsub_tab")
gap_queue_tab = _safe_import("gap_queue_tab")
l1_cache_tab = _safe_import("l1_cache_tab")
cluster_tab = _safe_import("cluster_tab")
sentinel_tab = _safe_import("sentinel_tab")