# -*- coding: utf-8 -*-
"""DataViewFilterMixin — 저장 데이터 조회 탭 상단 필터 로직 분리 (SRP)

자산군 / 거래소 / 심볼 콤보 + 한글·영문·초성 검색 지원.
DataViewTab 에서 상속하여 사용합니다.

필요 속성 (DataViewTab 에서 제공):
  _combo_asset        — 자산군 QComboBox
  _combo_exch         — 거래소 QComboBox
  _combo_sym          — 심볼 QComboBox (editable)
  _edit_search_filter — 검색 QLineEdit
  _lbl_search_result  — 검색 결과 수 QLabel
  _conn_params        — DB 연결 파라미터
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------
_ASSET_CLASSES: List[str] = ["전체", "암호화폐", "국내주식", "해외주식", "파생상품/선물"]

_EXCHANGE_MAP: Dict[str, List[str]] = {
    "전체":          ["전체"],
    "암호화폐":      ["전체", "업비트", "빗썸", "바이낸스"],
    "국내주식":      ["전체", "KRX/코스피", "코스닥"],
    "해외주식":      ["전체", "NYSE", "NASDAQ"],
    "파생상품/선물": ["전체", "CME", "CBOE"],
}

_DEFAULT_SYMBOLS: List[str] = [
    "KRW-BTC", "KRW-ETH", "KRW-XRP", "KRW-SOL", "KRW-ADA",
    "KRW-DOGE", "KRW-DOT", "KRW-AVAX", "KRW-LINK", "KRW-MATIC",
    "KRW-ATOM", "KRW-LTC", "KRW-BCH", "KRW-ETC", "KRW-TRX",
    "KRW-UNI", "KRW-NEAR", "KRW-FTM", "KRW-SAND", "KRW-SHIB",
    "KRW-APT", "KRW-ARB", "KRW-OP", "KRW-SUI", "KRW-HBAR",
]

# ---------------------------------------------------------------------------
# 심볼 로드 경로 헬퍼
# ---------------------------------------------------------------------------

def _symbol_search_dir() -> str:
    """symbol_search.py 가 위치한 ui/utils 경로를 반환합니다."""
    return str(Path(__file__).resolve().parents[3] / "ui" / "utils")


try:
    from PyQt5.QtCore import QThread, pyqtSignal
    _HAS_QT = True
except ImportError:
    _HAS_QT = False


if _HAS_QT:
    class _SymbolLoadWorker(QThread):
        """TimescaleDB candles 테이블에서 심볼 목록을 비동기로 조회합니다.

        Signals:
            finished(list): 심볼 문자열 목록
            error(str): 오류 메시지
        """

        finished = pyqtSignal(list)
        error    = pyqtSignal(str)

        def __init__(self, conn_params: dict, parent=None) -> None:
            super().__init__(parent)
            self._conn_params = conn_params or {}

        def run(self) -> None:
            try:
                import psycopg2
                try:
                    from db_worker import build_connect_kwargs
                except ImportError:
                    try:
                        from .db_worker import build_connect_kwargs  # type: ignore[no-redef]
                    except ImportError:
                        raise ImportError("db_worker 를 찾을 수 없습니다.")
                kwargs = build_connect_kwargs(self._conn_params, connect_timeout=3)
                conn = psycopg2.connect(**kwargs)
                try:
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT DISTINCT symbol FROM candles"
                            " ORDER BY symbol LIMIT 10000"
                        )
                        rows = cur.fetchall()
                    symbols = [r[0] for r in rows if r and r[0]]
                    self.finished.emit(symbols if symbols else list(_DEFAULT_SYMBOLS))
                finally:
                    conn.close()
            except Exception as exc:
                logger.debug("[SymbolLoadWorker] 심볼 로드 실패 (기본값 사용): %s", exc)
                self.error.emit(str(exc))

    # -----------------------------------------------------------------------

    class DataViewFilterMixin:
        """상단 필터 바 (자산군/거래소/심볼/검색) 로직 Mixin.

        SRP 준수: 필터 UI 초기화·시그널 처리만 담당합니다.
        DB 쿼리 로직은 DataViewTab 에 위임합니다.
        """

        # ------------------------------------------------------------------
        # 초기화
        # ------------------------------------------------------------------

        def _init_filter(self) -> None:
            """필터 상태를 초기화합니다. __init__ 이후 _build_ui() 전에 호출합니다."""
            self._all_symbols: List[str] = list(_DEFAULT_SYMBOLS)
            self._all_symbol_stats: list = []
            self._name_map: Optional[dict] = None
            self._name_en_map: Optional[dict] = None
            self._symbol_worker: Optional[_SymbolLoadWorker] = None

        def _populate_filter_combos(self) -> None:
            """자산군/거래소 콤보를 초기값으로 채웁니다."""
            combo_asset = getattr(self, "_combo_asset", None)
            if combo_asset is not None:
                combo_asset.clear()
                combo_asset.addItems(_ASSET_CLASSES)

            # 거래소 콤보는 자산군 변경 핸들러가 초기화
            self._on_asset_filter_changed()

        def _start_symbol_load(self) -> None:
            """candles 테이블에서 심볼 목록을 비동기로 로드합니다.

            로드 성공 시 _all_symbols 및 콤보를 업데이트합니다.
            실패 시 _DEFAULT_SYMBOLS 를 유지합니다.
            """
            if self._symbol_worker and self._symbol_worker.isRunning():
                return
            conn_params = getattr(self, "_conn_params", {})
            self._symbol_worker = _SymbolLoadWorker(conn_params)
            self._symbol_worker.finished.connect(self._on_symbols_loaded)
            self._symbol_worker.error.connect(self._on_symbols_error)
            self._symbol_worker.start()

        def _on_symbols_loaded(self, symbols: list) -> None:
            """심볼 비동기 로드 완료 처리."""
            self._all_symbols = symbols or list(_DEFAULT_SYMBOLS)
            self._refresh_symbol_combo(self._all_symbols)
            logger.debug("[DataViewFilterMixin] 심볼 %d 개 로드 완료", len(self._all_symbols))

        def _on_symbols_error(self, msg: str) -> None:
            """심볼 로드 실패 시 기본 심볼 유지."""
            logger.debug("[DataViewFilterMixin] 심볼 로드 실패 (기본값 사용): %s", msg)
            if not self._all_symbols:
                self._all_symbols = list(_DEFAULT_SYMBOLS)
                self._refresh_symbol_combo(self._all_symbols)

        # ------------------------------------------------------------------
        # 자산군 / 거래소 변경
        # ------------------------------------------------------------------

        def _on_asset_filter_changed(self, _index: int = 0) -> None:
            """자산군 변경 시 거래소 콤보를 동기화합니다."""
            combo_asset = getattr(self, "_combo_asset", None)
            combo_exch  = getattr(self, "_combo_exch",  None)
            if combo_exch is None:
                return
            asset     = combo_asset.currentText() if combo_asset else "전체"
            exchanges = _EXCHANGE_MAP.get(asset, ["전체"])
            combo_exch.blockSignals(True)
            combo_exch.clear()
            combo_exch.addItems(exchanges)
            combo_exch.blockSignals(False)
            self._filter_symbols_by_asset_exchange()

        def _on_exchange_filter_changed(self, _index: int = 0) -> None:
            """거래소 변경 시 심볼 콤보를 필터링합니다."""
            self._filter_symbols_by_asset_exchange()

        def _filter_symbols_by_asset_exchange(self) -> None:
            """자산군·거래소 기준으로 심볼 콤보를 필터링합니다."""
            combo_asset = getattr(self, "_combo_asset", None)
            combo_exch  = getattr(self, "_combo_exch",  None)
            asset    = combo_asset.currentText() if combo_asset else "전체"
            exchange = combo_exch.currentText()  if combo_exch  else "전체"

            all_symbols = self._all_symbols or list(_DEFAULT_SYMBOLS)
            all_stats   = self._all_symbol_stats or []

            if all_stats:
                # 통계 메타 사용 (정확)
                filtered = [
                    s["symbol"] for s in all_stats
                    if (asset    == "전체" or s.get("asset_class") == asset)
                    and (exchange == "전체" or s.get("exchange")    == exchange)
                ] or [s["symbol"] for s in all_stats]
            else:
                # 접두어 기반 대략 필터
                _KRW_EXCH = {"업비트", "빗썸"}
                if exchange in _KRW_EXCH:
                    filtered = [s for s in all_symbols if s.startswith("KRW-")]
                elif exchange == "바이낸스":
                    filtered = [s for s in all_symbols if not s.startswith("KRW-")
                                and s[:1].isalpha()]
                elif exchange in ("KRX/코스피", "코스닥"):
                    filtered = [s for s in all_symbols
                                if s.isdigit() or (len(s) >= 6 and s[:6].isdigit())]
                elif exchange in ("NYSE", "NASDAQ"):
                    filtered = [s for s in all_symbols
                                if not s.startswith("KRW-") and not s.isdigit()
                                and "=" not in s]
                elif exchange in ("CME", "CBOE"):
                    filtered = [s for s in all_symbols if "=" in s]
                else:
                    filtered = list(all_symbols)

            self._refresh_symbol_combo(filtered)

        # ------------------------------------------------------------------
        # 검색 (한글/초성/영문)
        # ------------------------------------------------------------------

        def _on_search_filter(self, text: str) -> None:
            """검색어로 심볼 콤보를 필터링합니다 (한글/초성/영문/영문명 모두 지원)."""
            all_symbols = self._all_symbols or list(_DEFAULT_SYMBOLS)
            raw = text.strip()
            if not raw:
                self._refresh_symbol_combo(all_symbols)
                self._update_filter_result_label(0, show=False)
                return

            try:
                # symbol_search.py 의 고급 필터 사용
                _udir = _symbol_search_dir()
                if _udir not in sys.path:
                    sys.path.insert(0, _udir)
                from symbol_search import filter_symbols, build_name_map, build_name_en_map  # type: ignore[import]

                if self._name_map is None:
                    self._name_map = build_name_map()
                if self._name_en_map is None:
                    self._name_en_map = build_name_en_map()

                filtered = filter_symbols(raw, all_symbols, self._name_map, self._name_en_map)
            except Exception as exc:
                logger.warning("[DataViewFilterMixin] 고급 검색 실패 (폴백 사용): %s", exc)
                q = raw.lower()
                fb: dict = self._name_map or {}
                filtered = [
                    s for s in all_symbols
                    if q in s.lower() or q in fb.get(s, "").lower()
                ]

            self._refresh_symbol_combo(filtered)
            self._update_filter_result_label(len(filtered), show=True)

        def _update_filter_result_label(self, count: int, show: bool) -> None:
            """검색 결과 수 레이블을 갱신합니다."""
            lbl = getattr(self, "_lbl_search_result", None)
            if lbl is None:
                return
            lbl.setText(f"{count}개 매칭" if show else "")

        # ------------------------------------------------------------------
        # 심볼 콤보 헬퍼
        # ------------------------------------------------------------------

        def _refresh_symbol_combo(self, symbols: List[str]) -> None:
            """심볼 콤보 내용을 교체하고 이전 선택값을 유지합니다."""
            combo = getattr(self, "_combo_sym", None)
            if combo is None:
                return
            current = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(symbols)
            idx = combo.findText(current)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            combo.blockSignals(False)

        def _get_selected_symbol(self) -> str:
            """필터 콤보에서 현재 선택된 심볼을 반환합니다."""
            combo = getattr(self, "_combo_sym", None)
            if combo is None:
                return ""
            return combo.currentText().strip()

else:
    class _SymbolLoadWorker:  # type: ignore[no-redef]
        def __init__(self, *a, **kw): pass

    class DataViewFilterMixin:  # type: ignore[no-redef]
        """PyQt5 미설치 시 더미 Mixin."""
        def _init_filter(self) -> None: pass
        def _populate_filter_combos(self) -> None: pass
        def _start_symbol_load(self) -> None: pass
        def _on_asset_filter_changed(self, _i: int = 0) -> None: pass
        def _on_exchange_filter_changed(self, _i: int = 0) -> None: pass
        def _on_search_filter(self, text: str) -> None: pass
        def _get_selected_symbol(self) -> str: return ""
        def _refresh_symbol_combo(self, symbols: list) -> None: pass
        def _update_filter_result_label(self, count: int, show: bool) -> None: pass
