# -*- coding: utf-8 -*-
"""
TF 안전권 진행률 패널 Mixin (tf_safe_panel.py)

[책임]
    StatusWidget 의 ``status_widget.ui`` 에 추가된 ``groupBox_tf_safe`` /
    ``widget_tf_progress_host`` 를 살아있는 위젯으로 만들기 위한 단일 책임
    Mixin. 잘 동작 중인 ``UIUpdatersMixin`` / ``SignalHandlersMixin`` 등 기존
    Mixin 의 코드는 일체 건드리지 않는다.

[제공 기능]
    - ``_init_tf_safe_panel()``  : ``TFProgressWidget`` 인스턴스를 placeholder
      에 도킹하고, 별도 15초 ``QTimer`` 를 시작한다.
    - ``_refresh_tf_safe_panel()`` : 기본 심볼(``KRW-BTC``) 의 6개 TF 에 대해
      ``MetadataManager.compute_safe_zone_pct()`` 를 비동기로 호출, 결과를
      위젯에 푸시한다. 호출은 짧은 lifecycle 의 ``QThread`` 워커에서 수행
      하므로 GUI 스레드를 블로킹하지 않는다.
    - ``_set_tf_safe_symbol(symbol)`` : 표시 대상 심볼 변경(필요 시 외부 호출).

[비파괴 보장]
    - placeholder (``widget_tf_progress_host``) 가 없으면 조용히 noop.
    - PyQt5 / MetadataManager 가 없는 환경에서도 import 만 되도록 가드.
    - 기존 타이머/이벤트 루프 변경 없음 — 내부 전용 ``QTimer`` 1개만 추가.

[성능 / 렉 방지]
    - 갱신 주기 15초 (`_TF_SAFE_REFRESH_MS`) — 메모리 룰과 일치.
    - 워커 ``isRunning()`` 가드 → 중복 실행 차단 (메모리 룰 'performance').
    - 결과 라벨은 GUI 스레드에서만 갱신 (Qt 시그널 사용).
"""
from __future__ import annotations

import logging
import os
import sys
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from PyQt5.QtCore import QObject, QThread, QTimer, pyqtSignal
    from PyQt5.QtWidgets import QVBoxLayout, QWidget
    _HAS_QT = True
except ImportError:  # pragma: no cover
    _HAS_QT = False


_TF_SAFE_REFRESH_MS = 15_000  # 15s 표준 폴링 (메모리 룰 'performance')
_DEFAULT_TFS = ["1m", "5m", "15m", "1h", "4h", "1d"]
_DEFAULT_SYMBOL = os.environ.get("STATUSWIDGET_TF_SAFE_SYMBOL", "KRW-BTC")


# ---------------------------------------------------------------------------
# 비동기 워커 — MetadataManager.compute_safe_zone_pct N회 호출
# ---------------------------------------------------------------------------

if _HAS_QT:

    class _TFSafeWorker(QThread):
        """짧은 수명의 워커 — 1회 실행 후 종료.

        기본 이벤트 루프 위에 새 ``asyncio.run`` 을 띄워 ``compute_safe_zone_pct``
        를 N개 TF 에 대해 병렬 호출(``asyncio.gather``) 한다. 결과는
        ``finished_results(dict)`` 시그널로 보낸다.
        """

        finished_results = pyqtSignal(str, dict)  # (symbol, results)

        def __init__(self, symbol: str, timeframes: List[str], parent: Optional[QObject] = None) -> None:
            super().__init__(parent)
            self._symbol = symbol
            self._tfs = list(timeframes)

        def run(self) -> None:  # noqa: D401
            """워커 본체 — 새 asyncio 루프에서 ``compute_safe_zone_pct`` 를 N개 TF에
            대해 동시 호출(``asyncio.gather``) 한 뒤 ``finished_results(symbol, dict)``
            시그널로 GUI 스레드에 결과를 전달한다.
            """
            try:
                import asyncio

                async def _gather_all() -> Dict[str, Dict[str, Any]]:
                    mgr = self._resolve_metadata_manager()
                    if mgr is None:
                        return {}
                    coros = [
                        mgr.compute_safe_zone_pct(self._symbol, tf)
                        for tf in self._tfs
                    ]
                    raw = await asyncio.gather(*coros, return_exceptions=True)
                    out: Dict[str, Dict[str, Any]] = {}
                    for tf, val in zip(self._tfs, raw):
                        if isinstance(val, dict):
                            out[tf] = val
                    return out

                try:
                    results = asyncio.run(_gather_all())
                except RuntimeError:
                    # 이미 루프가 활성화된 환경 폴백 — 새 루프를 생성
                    loop = asyncio.new_event_loop()
                    try:
                        results = loop.run_until_complete(_gather_all())
                    finally:
                        loop.close()
                self.finished_results.emit(self._symbol, results or {})
            except Exception as exc:
                logger.debug("[TFSafeWorker] 실행 실패: %s", exc)
                self.finished_results.emit(self._symbol, {})

        # ------------------------------------------------------------------
        @staticmethod
        def _resolve_metadata_manager() -> Optional[Any]:
            """프로세스 내에서 사용 가능한 ``MetadataManager`` 를 찾는다.

            ``data_01`` 패키지명이 숫자로 시작해 일반 ``import_module`` 가 불가하므로
            파일 기반 ``importlib.util`` 폴백을 사용한다 (``pipeline_loader`` 패턴).
            """
            # 1) sys.modules 에 이미 로드된 모듈이 있다면 우선 활용
            for name, mod in list(sys.modules.items()):
                if mod is None:
                    continue
                if not name.endswith("metadata_manager"):
                    continue
                factory = getattr(mod, "create_metadata_manager", None) or getattr(
                    mod, "get_metadata_manager", None
                )
                if callable(factory):
                    try:
                        return factory()
                    except Exception:
                        pass
                cls = getattr(mod, "MetadataManager", None)
                if cls is not None:
                    try:
                        return cls()
                    except Exception:
                        pass

            # 2) 파일 기반 동적 로드 (digit-prefix 패키지 호환)
            try:
                import importlib.util
                import pathlib

                here = pathlib.Path(__file__).resolve()
                # tf_safe_panel.py: src/data_01/ui/status_widget/  →  parents[3] == src/
                src_root = here.parents[3]
                mm_path = src_root / "data_01" / "mongodb" / "metadata_manager.py"
                if not mm_path.exists():
                    return None
                spec = importlib.util.spec_from_file_location(
                    "_tf_safe_metadata_manager", str(mm_path)
                )
                if spec is None or spec.loader is None:
                    return None
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                factory = getattr(mod, "create_metadata_manager", None) or getattr(
                    mod, "get_metadata_manager", None
                )
                if callable(factory):
                    try:
                        return factory()
                    except Exception:
                        pass
                cls = getattr(mod, "MetadataManager", None)
                if cls is not None:
                    try:
                        return cls()
                    except Exception:
                        pass
            except Exception as exc:
                logger.debug("[TFSafeWorker] file-based metadata 로드 실패: %s", exc)
            return None


    class TFSafePanelMixin:
        """``status_widget.ui`` 의 TF 안전권 진행률 패널 라이프사이클 Mixin."""

        # ------------------------------------------------------------------
        def _init_tf_safe_panel(self) -> None:
            """``widget_tf_progress_host`` 에 TFProgressWidget 도킹 + 타이머 시작.

            placeholder 가 존재하지 않거나 PyQt5/위젯 모듈 로드가 실패하면
            아무 것도 하지 않는다(완전 비파괴).
            """
            self._tf_safe_widget: Optional[Any] = None
            self._tf_safe_timer: Optional[QTimer] = None
            self._tf_safe_worker: Optional[_TFSafeWorker] = None
            self._tf_safe_symbol: str = _DEFAULT_SYMBOL
            self._tf_safe_tfs: List[str] = list(_DEFAULT_TFS)

            host = getattr(self, "widget_tf_progress_host", None)
            if host is None:
                logger.debug("[TFSafePanel] placeholder 없음 — 비활성")
                return

            try:
                # PyQt5 위젯도 `data_01` 디지트 프리픽스 패키지 안에 있어
                # 표준 `import` 가 안 되므로 파일 기반 동적 로드
                import importlib.util
                import pathlib

                here = pathlib.Path(__file__).resolve()
                src_root = here.parents[3]  # src/
                tfp_path = src_root / "data_01" / "ui" / "widgets" / "tf_progress_widget.py"
                if not tfp_path.exists():
                    raise FileNotFoundError(str(tfp_path))
                _key = "_tf_progress_widget"
                if _key in sys.modules:
                    tfp_mod = sys.modules[_key]
                else:
                    spec = importlib.util.spec_from_file_location(_key, str(tfp_path))
                    if spec is None or spec.loader is None:
                        raise ImportError("spec load 실패")
                    tfp_mod = importlib.util.module_from_spec(spec)
                    sys.modules[_key] = tfp_mod
                    spec.loader.exec_module(tfp_mod)
                TFProgressWidget = getattr(tfp_mod, "TFProgressWidget")
            except Exception as exc:
                logger.debug("[TFSafePanel] TFProgressWidget 로드 실패: %s", exc)
                return

            try:
                widget = TFProgressWidget(timeframes=self._tf_safe_tfs, title=None, parent=host)
                lay = host.layout()
                if lay is None:
                    lay = QVBoxLayout(host)
                    lay.setContentsMargins(0, 0, 0, 0)
                lay.addWidget(widget)
                self._tf_safe_widget = widget
            except Exception as exc:
                logger.debug("[TFSafePanel] 위젯 도킹 실패: %s", exc)
                return

            # 심볼 라벨 갱신
            self._set_tf_safe_symbol(self._tf_safe_symbol)

            # 수집 설정에서 선택된 TF 로드 → 위젯에 강조 표시 전달
            try:
                selected = self._load_selected_timeframes()
                if selected and hasattr(widget, "set_selected_timeframes"):
                    widget.set_selected_timeframes(selected)
            except Exception as exc:
                logger.debug("[TFSafePanel] 선택 TF 로드 실패: %s", exc)

            # 전용 타이머 (메인 _timer 와 분리, 15s)
            try:
                self._tf_safe_timer = QTimer(self)  # type: ignore[arg-type]
                self._tf_safe_timer.setInterval(_TF_SAFE_REFRESH_MS)
                self._tf_safe_timer.timeout.connect(self._refresh_tf_safe_panel)
                self._tf_safe_timer.start()
                # 즉시 1회 갱신
                QTimer.singleShot(500, self._refresh_tf_safe_panel)
            except Exception as exc:
                logger.debug("[TFSafePanel] 타이머 시작 실패: %s", exc)

        # ------------------------------------------------------------------
        def _set_tf_safe_symbol(self, symbol: str) -> None:
            """표시 대상 심볼 변경 (전체 TF 진행률 기준)."""
            if not symbol:
                return
            self._tf_safe_symbol = str(symbol)
            lbl = getattr(self, "label_tf_safe_symbol", None)
            if lbl is not None:
                try:
                    lbl.setText(
                        f"전체 TF 안정권 진행률 (대표심볼: {self._tf_safe_symbol})"
                    )
                except Exception:
                    pass

        # ------------------------------------------------------------------
        def _load_selected_timeframes(self) -> List[str]:
            """MongoDB ``ui_settings.collection_settings.timeframes`` 에서 사용자가
            수집 설정에 체크한 TF 리스트를 동기적으로 로드한다.

            네트워크/DB 실패 시 빈 리스트를 반환 — 호출부에서 noop 처리.
            """
            try:
                import os as _os

                from pymongo import MongoClient  # type: ignore

                mongo_uri = _os.environ.get(
                    "MONGO_URI", "mongodb://localhost:27017/upbit_trader"
                )
                client = MongoClient(
                    mongo_uri,
                    serverSelectionTimeoutMS=1500,
                    directConnection=True,
                )
                try:
                    db_name = mongo_uri.rstrip("/").rsplit("/", 1)[-1] or "upbit_trader"
                    doc = (
                        client[db_name]["ui_settings"].find_one({"user_id": "default"})
                        or {}
                    )
                    col = doc.get("collection_settings", {}) or {}
                    tfs = col.get("timeframes") or col.get("collected_timeframes")
                    if isinstance(tfs, (list, tuple)) and tfs:
                        return [str(t) for t in tfs if t]
                finally:
                    try:
                        client.close()
                    except Exception:
                        pass
            except Exception as exc:
                logger.debug("[TFSafePanel] collection_settings 로드 실패: %s", exc)
            return []

        # ------------------------------------------------------------------
        def _refresh_tf_safe_panel(self) -> None:
            """워커 isRunning 가드 + 새 워커 1회 실행."""
            if getattr(self, "_tf_safe_widget", None) is None:
                return
            worker = getattr(self, "_tf_safe_worker", None)
            if worker is not None and worker.isRunning():
                return  # 중복 실행 차단
            try:
                worker = _TFSafeWorker(
                    symbol=self._tf_safe_symbol,
                    timeframes=self._tf_safe_tfs,
                    parent=self,  # type: ignore[arg-type]
                )
                worker.finished_results.connect(self._on_tf_safe_results)
                worker.start()
                self._tf_safe_worker = worker
            except Exception as exc:
                logger.debug("[TFSafePanel] 워커 시작 실패: %s", exc)

        # ------------------------------------------------------------------
        def _on_tf_safe_results(self, symbol: str, results: Dict[str, Dict[str, Any]]) -> None:
            """워커 종료 시 결과를 위젯에 반영(GUI 스레드)."""
            widget = getattr(self, "_tf_safe_widget", None)
            if widget is None:
                return
            try:
                widget.update_from_results(results or {})
            except Exception as exc:
                logger.debug("[TFSafePanel] update_from_results 실패: %s", exc)

else:  # pragma: no cover
    class TFSafePanelMixin:  # type: ignore[no-redef]
        def _init_tf_safe_panel(self) -> None:
            return

        def _set_tf_safe_symbol(self, symbol: str) -> None:
            return

        def _refresh_tf_safe_panel(self) -> None:
            return

        def _on_tf_safe_results(self, *args, **kwargs) -> None:
            return


__all__ = ["TFSafePanelMixin"]
