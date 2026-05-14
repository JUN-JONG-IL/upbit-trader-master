#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
WidgetFactory: 위젯 생성/배치 전담 모듈

변경점(2026-03-26 이후 보강):
- 부모 패키지를 ModuleType으로 '의도적으로' 등록할 때와, __init__.py 실행을 시도했다가 실패한 경우를
  구분하여 내부 통계에 기록합니다.
  - 의도적 등록 -> registered_module_types
  - __init__ 실행 실패 -> skipped_init_failures
- 이렇게 하면 정상적인 안전 등록(부작용 회피)이 로그에서 문제처럼 보이는 것을 방지합니다.
- 그 외 로직은 파일 기반 로드(spec_from_file_location), safe-naming 변환, dotted import 후보 시도 등을 유지합니다.
"""
from __future__ import annotations

import importlib.util
import importlib
import logging
import os
import sys
import traceback
import types
import keyword
import re
from typing import Any, Dict, Optional

try:
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QSplitter
    _HAS_QT = True
except Exception:
    Qt = None  # type: ignore[assignment]
    QSplitter = None  # type: ignore[assignment]
    _HAS_QT = False

logger = logging.getLogger(__name__)

# 중복 경고/알림을 1회만 출력하도록 간단 캐시
_SEEN_WARNINGS = set()

# 내부 로그/상��� 통계
_LOG_STATS = {
    "registered_module_types": set(),   # 의도적으로 ModuleType으로 등록된 부모 패키지명
    "skipped_init_failures": set(),     # __init__.py 실행을 시도했으나 실패한 패키지명(실패 사례)
    "placeholder_used": set(),          # placeholder 사용된 위젯명
    "successful_widgets": [],           # 성공 생성된 위젯명(목록)
    "failed_widgets": [],               # 실패한 위젯명(목록)
    "import_candidate_skips": set(),    # 건너뛴 import 후보 예시
}

# 위젯 경로 매핑 (window_main.py에서 이동)
# 경로는 src/ 디렉터리 기준 상대 경로 (src/ 접두사 제외)
_WIDGET_PATHS: Dict[str, tuple] = {
    "CoinlistWidget":          (os.path.join("03_market", "coinlist", "ui", "widget_coin_list.py"), "CoinlistWidget"),
    "ChartWidget":             (os.path.join("04_chart", "ui", "widget_chart.py"), "ChartWidget"),
    "OrderbookWidget":         (os.path.join("03_market", "orderbook", "ui", "widget_orderbook.py"), "OrderbookWidget"),
    "TradeWidget":             (os.path.join("10_trade", "orders", "ui", "widget_trade.py"), "TradeWidget"),
    "HoldingListWidget":       (os.path.join("08_portfolio", "holdings", "ui", "widget_holding_list.py"), "HoldingListWidget"),
    "ScannerFrameWidget":      (os.path.join("07_scanner", "engine", "ui", "widget_scanner_frame.py"), "ScannerFrameWidget"),
    "UserinfoWidget":          (os.path.join("08_portfolio", "userinfo", "ui", "widget_userinfo.py"), "UserinfoWidget"),
    "DetailholdinglistWidget": (os.path.join("08_portfolio", "holdings", "ui", "widget_detail_holding.py"), "DetailholdinglistWidget"),
    "SignallistWidget":        (os.path.join("10_trade", "ui", "signals", "widget_signal_list.py"), "SignallistWidget"),
    "SignalselectWidget":      (os.path.join("10_trade", "ui", "signals", "widget_signal_select.py"), "SignalselectWidget"),
    # 수정: SettingsWidget 경로를 실제 레포 파일 위치로 변경 (기존: 11_server/settings/ui/widget_settings.py)
    "SettingsWidget":          (os.path.join("11_server", "ui", "settings", "widget_server_settings.py"), "SettingsWidget"),
}


def _is_valid_identifier_segment(s: str) -> bool:
    """문자열 s가 파이썬 식별자 규칙(키워드 아님 포함)을 만족하는지 확인합니다."""
    if not s:
        return False
    if not s.isidentifier():
        return False
    if keyword.iskeyword(s):
        return False
    return True


def _safe_segment(s: str) -> str:
    """
    파일/디렉터리 세그먼트를 안전한 파이썬 식별자로 변환합니다.
    - 이미 유효하면 그대로 반환
    - 유효하지 않으면 앞에 '_'를 붙이고, 유효 아닌 문자들은 '_'로 치환합니다.
    예: '04_chart' -> '_04_chart'
    """
    if _is_valid_identifier_segment(s):
        return s
    # 치환: 알파벳/숫자/_ 외 문자는 '_'로
    safe = re.sub(r'[^0-9a-zA-Z_]', '_', s)
    if not safe:
        safe = "_p"
    # 식별자로 시작해야 하므로 숫자로 시작하면 '_' 추가
    if not (safe[0].isalpha() or safe[0] == "_"):
        safe = "_" + safe
    # 키워드 방지
    if keyword.iskeyword(safe):
        safe = "_" + safe
    return safe


class WidgetFactory:
    """위젯 생성/배치 전담 팩토리"""

    @staticmethod
    def _make_placeholder_widget_class(name: str):
        """파일/모듈이 없을 때 반환할 최소 폴백 위젯 클래스"""
        try:
            from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout
        except Exception:
            # PyQt가 아예 없을 경우 None 반환
            return None

        class _Placeholder(QWidget):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                try:
                    layout = QVBoxLayout()
                    lbl = QLabel(f"Missing widget: {name}")
                    layout.addWidget(lbl)
                    self.setLayout(layout)
                except Exception:
                    pass

        _Placeholder.__name__ = f"Placeholder_{name}"
        return _Placeholder

    @staticmethod
    def _try_import_module_candidates(rel_path: str):
        """
        파일 경로(rel_path)를 받아서 도트 네임 후보들을 생성하고 import 시도.
        - 기존의 원본 dotted 후보 외에 '안전한(safe) dotted' 후보를 추가시도합니다.
        - 세그먼트에 유효하지 않은 식별자가 포함된 원본 후보는 바로 건너뛰되,
          safe 후보는 생성하여 시도합니다.
        성공 시 모듈을 반환, 실패 시 None.
        """
        # normalize to forward slashes for predictable conversion
        norm = rel_path.replace("\\", "/")
        if norm.startswith("src/"):
            norm = norm[4:]
        base = norm.replace(".py", "").strip("/")
        original_dotted = base.replace("/", ".")
        original_segments = original_dotted.split(".") if original_dotted else []
        # safe dotted (숫자/비표준 세그먼트를 치환)
        safe_segments = [_safe_segment(s) for s in original_segments]
        safe_dotted = ".".join(safe_segments) if safe_segments else ""

        candidates = []

        # 원본 후보 (만약 모든 세그먼트가 유효하면)
        if original_segments and all(_is_valid_identifier_segment(seg) for seg in original_segments):
            candidates.append(original_dotted)
            candidates.append(f"src.{original_dotted}" if original_dotted else "src")

        # safe 후보 (항상 시도)
        if safe_dotted:
            candidates.append(safe_dotted)
            candidates.append(f"src.{safe_dotted}")

        # 순회하며 시도
        for cand in candidates:
            if not cand:
                continue
            # 최종 검증: 각 세그먼트가 유효한 파이썬 식별자인지 확인
            segments = cand.split(".")
            if not all(_is_valid_identifier_segment(seg) for seg in segments):
                _LOG_STATS["import_candidate_skips"].add(cand)
                logger.debug("[WidgetFactory] import 후보 건너뜀(식별자 아님): %s", cand)
                continue
            try:
                mod = importlib.import_module(cand)
                return mod
            except Exception as ex:
                # 실패는 debug로 남기고 다음 후보 시도
                logger.debug("[WidgetFactory] import 시도 실패: %s -> %s", cand, ex, exc_info=True)
                continue
        return None

    @staticmethod
    def _load_widget_class(rel_path: str, class_name: str) -> Optional[Any]:
        """파일/모듈 경로 기반 위젯 클래스 로드 (경로 오류 수정 + 임포트 후보 시도 + placeholder 폴백)

        주요 보강:
        - 상대 임포트 처리를 위해 '안전한' dotted 모듈 이름을 생성하고 부모 패키지를 sys.modules에 등록.
        - 패키지의 __init__.py를 자동 실행하지 않고 ModuleType으로 등록하여 부작용을 방지(안전성 우선).
        - 파일 기반 로드 후 모듈 __spec__/__loader__/__package__를 정확히 설정하여 상대 import가 동작하도록 도움.
        - 실패 시 placeholder로 폴백.
        """
        import traceback as _tb
        try:
            from pathlib import Path as _Path
            src_root = str(_Path(__file__).resolve().parents[3])

            # normalize rel_path
            _rel = rel_path.replace("\\", "/")
            if _rel.startswith("src/"):
                _rel = _rel[4:]
            rel_path_norm = _rel.replace("/", os.sep)

            abs_path = os.path.join(src_root, rel_path_norm)

            # 원래 parts(디렉터리 세그먼트)와 안전한 세그먼트 변환
            mod_name_parts = rel_path_norm.replace(os.sep, ".").replace("/", ".").replace(".py", "").split(".")
            original_parts = [p for p in mod_name_parts if p]  # 디스크 상의 세그먼트 (예: ['04_chart','ui','widget_chart'])
            safe_parts = [_safe_segment(p) for p in original_parts]  # 안전한 식별자로 변환

            # transformed dotted module name (sys.modules에 등록할 이름)
            transformed_mod_name = ".".join(safe_parts) if safe_parts else ""

            # 부모 패키지들을 sys.modules에 등록 — 실제 디렉터리 경로은 original_parts 사용
            # 변경: __init__.py의 코드를 실행하지 않고 ModuleType으로 등록 (부작용 방지)
            for i in range(1, len(original_parts)):
                pkg_name = ".".join(safe_parts[:i])
                pkg_dir = os.path.join(src_root, *original_parts[:i])
                if pkg_name not in sys.modules:
                    # 원래는 skipped_pkgs에 기록했으나, 이는 의도적 등록일 수 있으므로 'registered_module_types'로 구분
                    _LOG_STATS["registered_module_types"].add(pkg_name)
                    pkg_mod = types.ModuleType(pkg_name)
                    pkg_mod.__package__ = pkg_name
                    try:
                        pkg_mod.__path__ = [pkg_dir]  # type: ignore[attr-defined]
                    except Exception:
                        # __path__ assignment 실패 시 무시
                        pass
                    sys.modules[pkg_name] = pkg_mod

            # 1) 파일이 존재하면 파일 기반으로 로드 (transformed 모듈 이름 사용)
            if os.path.isfile(abs_path):
                try:
                    # 모듈 이름이 비어있을 수 있으므로 fallback 이름 설정
                    module_name_for_spec = transformed_mod_name or os.path.splitext(os.path.basename(abs_path))[0]
                    spec = importlib.util.spec_from_file_location(module_name_for_spec, abs_path, submodule_search_locations=[os.path.dirname(abs_path)])
                    if not spec or not spec.loader:
                        logger.debug("[WidgetFactory] spec 생성 실패: %s", abs_path)
                    else:
                        mod = importlib.util.module_from_spec(spec)
                        # set module attributes to help relative imports
                        mod.__spec__ = spec
                        mod.__loader__ = spec.loader
                        if len(safe_parts) > 1:
                            mod.__package__ = ".".join(safe_parts[:-1])
                        else:
                            mod.__package__ = ""
                        # register both transformed_mod_name and module_name_for_spec in sys.modules so imports can find it
                        sys.modules[module_name_for_spec] = mod
                        if transformed_mod_name and transformed_mod_name != module_name_for_spec:
                            sys.modules[transformed_mod_name] = mod
                        try:
                            spec.loader.exec_module(mod)  # type: ignore[union-attr]
                        except Exception as _exec_e:
                            # 만약 파일을 실행하는 과정에서 에러가 발생하면,
                            # 이것이 패키지 초기화(__init__.py) 실패와 유사한 경우라면 'skipped_init_failures'로 기록 가능.
                            logger.debug("[WidgetFactory] 파일 모듈 실행 중 예외: %s -> %s", abs_path, _exec_e, exc_info=True)
                        cls = getattr(mod, class_name, None)
                        if cls:
                            return cls
                except Exception:
                    logger.debug("[WidgetFactory] file-spec load 실패 for %s", abs_path, exc_info=True)

            # 2) 파일이 없거나 ���일 로드 실패 — dotted-module 임포트 후보 시도 (기존 방식 + safe 후보)
            try:
                mod = WidgetFactory._try_import_module_candidates(rel_path)
                if mod is not None:
                    cls = getattr(mod, class_name, None)
                    if cls:
                        return cls
            except Exception:
                logger.debug("[WidgetFactory] module-candidate import attempts failed for %s", rel_path, exc_info=True)

            # 3) 마지막 폴백: placeholder 위젯 클래스 생성 (앱이 멈추지 않도록)
            placeholder = WidgetFactory._make_placeholder_widget_class(class_name)
            if placeholder is not None:
                _LOG_STATS["placeholder_used"].add(class_name)
                return placeholder

            # 4) placeholder도 불가하면 None 반환
            logger.error("[WidgetFactory] %s 로드 불가(파일/모듈/placeholder 모두 실패): %s", class_name, abs_path)
            logger.debug("[WidgetFactory] src_root: %s", src_root)
            logger.debug("[WidgetFactory] rel_path: %s", rel_path_norm)
            return None

        except Exception as e:
            logger.error("[WidgetFactory] %s 로드 실패: %s", class_name, e)
            logger.debug("[WidgetFactory] traceback:\n%s", _tb.format_exc())
            # try to provide placeholder last-resort
            try:
                placeholder = WidgetFactory._make_placeholder_widget_class(class_name)
                if placeholder:
                    _LOG_STATS["placeholder_used"].add(class_name)
                    return placeholder
            except Exception:
                pass
            return None

    @staticmethod
    def create_all_widgets(ui_state_manager: Optional[Any]) -> Dict[str, Any]:
        """모든 위젯을 한 번에 생성 (오류 처리 강화)"""

        # 시작 로그는 debug로 (로딩 완료 시 summary만 INFO)
        logger.debug("[WidgetFactory] 위젯 클래스 로딩 시작...")
        widgets: Dict[str, Any] = {}
        success_count = 0
        fail_count = 0

        # 내부 집계 초기화
        _LOG_STATS["registered_module_types"].clear()
        _LOG_STATS["skipped_init_failures"].clear()
        _LOG_STATS["placeholder_used"].clear()
        _LOG_STATS["successful_widgets"].clear()
        _LOG_STATS["failed_widgets"].clear()
        _LOG_STATS["import_candidate_skips"].clear()

        for name, (rel_path, cls_name) in _WIDGET_PATHS.items():
            cls = WidgetFactory._load_widget_class(rel_path, cls_name)
            if cls is None:
                logger.error("[WidgetFactory] %s 로드 실패 (경로: %s)", name, rel_path)
                widgets[name] = None
                fail_count += 1
                _LOG_STATS["failed_widgets"].append(name)
                continue

            try:
                if name in ("CoinlistWidget", "ChartWidget", "OrderbookWidget"):
                    widget = cls(ui_state_manager=ui_state_manager)
                else:
                    widget = cls()
                widgets[name] = widget
                success_count += 1
                _LOG_STATS["successful_widgets"].append(name)
                # 성공 로그는 상세출력 대신 집계로 처리하여 로그 소음 감소
            except TypeError:
                # ui_state_manager 미지원 시 인자 없이 생성
                try:
                    widgets[name] = cls()
                    success_count += 1
                    _LOG_STATS["successful_widgets"].append(name)
                except Exception as e:
                    logger.error("[WidgetFactory] %s 생성 실패: %s", name, e)
                    logger.debug("[WidgetFactory] traceback:\n%s", traceback.format_exc())
                    widgets[name] = None
                    fail_count += 1
                    _LOG_STATS["failed_widgets"].append(name)
            except Exception as e:
                logger.error("[WidgetFactory] %s 생성 실패: %s", name, e)
                logger.debug("[WidgetFactory] traceback:\n%s", traceback.format_exc())
                widgets[name] = None
                fail_count += 1
                _LOG_STATS["failed_widgets"].append(name)

        total = len(_WIDGET_PATHS)

        # 요약 정보: 한 줄로 간결하게
        summary_msg = f"[WidgetFactory] 위젯 생성 완료: {success_count}/{total} 성공, {fail_count}/{total} 실패"
        # 추가 요약: 의도적 등록된 부모 패키지 수, __init__ 실패 수, placeholder 사용 위젯 목록(있을 경우)
        registered = list(_LOG_STATS["registered_module_types"])
        skipped_inits = list(_LOG_STATS["skipped_init_failures"])
        placeholder_used = list(_LOG_STATS["placeholder_used"])
        import_skips = list(_LOG_STATS["import_candidate_skips"])
        details = []
        if registered:
            details.append(f"registered_module_types={len(registered)}")
        if import_skips:
            details.append(f"import_candidate_skips={len(import_skips)}")
        if skipped_inits:
            details.append(f"skipped_init_failures={len(skipped_inits)}")
        if placeholder_used:
            details.append(f"placeholders={','.join(sorted(placeholder_used))}")
        if details:
            summary_msg += " (" + "; ".join(details) + ")"

        logger.info(summary_msg)

        # placeholder 사용이나 실패가 있으면 요약 경고/정보를 남김
        if placeholder_used:
            # 한 번의 warning으로 어떤 위젯이 placeholder인지 알려줌
            logger.warning("[WidgetFactory] placeholder 사용됨: %s", ", ".join(sorted(placeholder_used)))

        if skipped_inits:
            # 실제 실패한 __init__ 목록은 warning으로 노출 (운영자가 확인 필요)
            logger.warning("[WidgetFactory] __init__ 실행 실패(요청 검토 필요): %s", ", ".join(sorted(skipped_inits[:20])))
        else:
            # 정상적인 경우 registered 목록은 debug로만 남김
            logger.debug("[WidgetFactory] 부모 패키지 안전 등록(예시): %s", ", ".join(sorted(registered[:20])))

        return widgets

    @staticmethod
    def setup_splitter(main_window: Any, widgets: Dict[str, Any]) -> None:
        """QSplitter 설정 (차트 상단, 종목 테이블 하단)"""
        if not _HAS_QT or QSplitter is None:
            return
        try:
            logger.debug("[WidgetFactory] QSplitter 설정 중...")

            coinlist = widgets.get("CoinlistWidget")
            chart = widgets.get("ChartWidget")
            search = widgets.get("ScannerFrameWidget")

            if not coinlist:
                logger.error("[WidgetFactory] CoinlistWidget 없음 - QSplitter 건너뜀")
                return

            main_window.vertical_splitter = QSplitter(Qt.Vertical)
            layout = getattr(main_window, "verticalLayout_7", None)
            if not layout:
                logger.warning("[WidgetFactory] verticalLayout_7 없음 - 기본 배치")
                main_window.coinlist_widget = coinlist
                main_window._symbol_table = coinlist
                if chart:
                    main_window.chart_widget = chart
                    main_window._chart_widget_inst = chart
                if search:
                    main_window.search_frame_widget = search
                    main_window._search_widget_inst = search
                return

            # 기존 위젯 제거
            while layout.count():
                item = layout.takeAt(0)
                if item and item.widget():
                    item.widget().setParent(None)

            # sub_frame_top (차트/스캐너) 설정
            sub_frame_top = getattr(main_window, "sub_frame_top", None)
            sub_layout = getattr(main_window, "horizontalLayout_sub", None)
            if sub_frame_top and sub_layout:
                while sub_layout.count():
                    item = sub_layout.takeAt(0)
                    if item and item.widget():
                        item.widget().setParent(None)

                if chart:
                    sub_layout.addWidget(chart)
                    main_window.chart_widget = chart
                    main_window._chart_widget_inst = chart
                if search:
                    sub_layout.addWidget(search)
                    main_window.search_frame_widget = search
                    main_window._search_widget_inst = search

                main_window.vertical_splitter.addWidget(sub_frame_top)
            else:
                logger.warning("[WidgetFactory] sub_frame_top 없음 - 차트/스캐너 직접 배치")
                if chart:
                    main_window.vertical_splitter.addWidget(chart)
                    main_window.chart_widget = chart
                    main_window._chart_widget_inst = chart
                if search:
                    main_window.vertical_splitter.addWidget(search)
                    main_window.search_frame_widget = search
                    main_window._search_widget_inst = search

            # 종목 테이블 배치
            main_window.vertical_splitter.addWidget(coinlist)
            main_window.coinlist_widget = coinlist
            main_window._symbol_table = coinlist

            # QSplitter 스타일 설정
            main_window.vertical_splitter.setSizes([500, 500])
            main_window.vertical_splitter.setHandleWidth(8)
            main_window.vertical_splitter.setStyleSheet(
                "QSplitter::handle { background-color: #d1d5db; margin: 2px 0px; }"
                " QSplitter::handle:hover { background-color: #3b82f6; }"
                " QSplitter::handle:vertical { height: 8px; }"
            )
            layout.addWidget(main_window.vertical_splitter)
            logger.debug("[WidgetFactory] QSplitter 설정 완료")

        except Exception as e:
            logger.error("[WidgetFactory] QSplitter 설정 실패: %s", e)

    @staticmethod
    def place_remaining_widgets(main_window: Any, widgets: Dict[str, Any]) -> None:
        """나머지 위젯 배치 (호가창, 거래, 보유자산 등)"""
        placements = [
            ("verticalLayout_8",  "orderbook_widget",        "OrderbookWidget",        "_orderbook_widget_inst"),
            ("verticalLayout_11", "holding_list_widget",     "HoldingListWidget",      "_holding_widget_inst"),
            ("verticalLayout_11", "trade_widget",            "TradeWidget",            "_trade_widget_inst"),
            ("verticalLayout_13", "userinfo_widget",         "UserinfoWidget",         None),
            ("verticalLayout",    "detailholdinglist_widget","DetailholdinglistWidget", None),
            ("verticalLayout_10", "signal_list_widget",      "SignallistWidget",       None),
            ("verticalLayout_14", "signal_select_widget",    "SignalselectWidget",     None),
        ]

        placed = 0
        for layout_attr, obj_name, widget_key, inst_attr in placements:
            layout = getattr(main_window, layout_attr, None)
            widget = widgets.get(widget_key)
            if not layout or not widget:
                continue

            try:
                for i in range(layout.count()):
                    item = layout.itemAt(i)
                    w = item.widget() if item else None
                    if w and w.objectName() == obj_name:
                        layout.removeWidget(w)
                        w.deleteLater()
                        break

                layout.addWidget(widget)
                setattr(main_window, obj_name, widget)
                if inst_attr:
                    setattr(main_window, inst_attr, widget)
                placed += 1
            except Exception as e:
                logger.warning("[WidgetFactory] %s 배치 실패: %s", widget_key, e)

        logger.debug("[WidgetFactory] 나머지 위젯 배치 완료: %d/%d개", placed, len(placements))

    @staticmethod
    def connect_legacy_widgets(main_window: Any) -> None:
        """레거시 위젯 연결 (setChart, setOrder 등)"""
        logger.debug("[WidgetFactory] 레거시 위젯 연동 중...")
        connections = [
            ("coinlist_widget",     "setChart",    "chart_widget"),
            ("coinlist_widget",     "setOrder",    "orderbook_widget"),
            ("coinlist_widget",     "setOrderbook","orderbook_widget"),
            ("coinlist_widget",     "setTrade",    "trade_widget"),
            ("orderbook_widget",    "setTrade",    "trade_widget"),
            ("search_frame_widget", "setChart",    "chart_widget"),
            ("search_frame_widget", "setOrder",    "orderbook_widget"),
            ("search_frame_widget", "setTrade",    "trade_widget"),
        ]

        success_count = 0
        skip_count = 0
        total = len(connections)

        for source_attr, method_name, target_attr in connections:
            source = getattr(main_window, source_attr, None)
            target = getattr(main_window, target_attr, None)
            if not source or not target:
                skip_count += 1
                continue
            if not hasattr(source, method_name):
                skip_count += 1
                continue
            try:
                getattr(source, method_name)(target)
                success_count += 1
            except Exception as e:
                logger.warning("[WidgetFactory] %s.%s 실패: %s", source_attr, method_name, e)
                skip_count += 1

        logger.debug("[WidgetFactory] 레거시 위젯 연동 완료: %d/%d 성공, %d/%d 건너뜀",
                    success_count, total, skip_count, total)


    @staticmethod
    def apply_default_layout(main_window: Any) -> None:
        """위젯 기본 레이아웃/스타일 설정"""
        try:
            for widget, method, *args in [
                (getattr(main_window, "coinlist_widget", None), "setMinimumWidth", 350),
                (getattr(main_window, "chart_widget", None), "setMinimumSize", 600, 0),
                (getattr(main_window, "orderbook_widget", None), "setMinimumWidth", 300),
                (getattr(main_window, "trade_widget", None), "setMinimumHeight", 0),
            ]:
                if widget:
                    getattr(widget, method)(*args)
            _hl_sub = getattr(main_window, "horizontalLayout_sub", None)
            if _hl_sub is not None:
                _hl_sub.setStretch(0, 3)
                _hl_sub.setStretch(1, 1)
                _hl_sub.setSpacing(0)
                _hl_sub.setContentsMargins(0, 0, 0, 0)
            _vl7 = getattr(main_window, "verticalLayout_7", None)
            if _vl7 is not None:
                _vl7.setSpacing(0)
                _vl7.setContentsMargins(0, 0, 0, 0)
            cw = getattr(main_window, "centralwidget", None)
            if cw:
                cw.setStyleSheet("QWidget { padding: 0px; margin: 0px; }")
            mb = getattr(main_window, "menubar", None)
            if mb:
                mb.setStyleSheet("QMenuBar { padding: 0px; margin: 0px; border: none; }")
            for fa in ("frame_1", "frame_2", "frame_3", "sub_frame_top"):
                f = getattr(main_window, fa, None)
                if f:
                    try:
                        f.setStyleSheet("QFrame { padding: 0px; margin: 0px; border: none; }")
                    except Exception:
                        pass
            main_window.setStyleSheet("QMainWindow { padding: 0px; margin: 0px; }")
        except Exception as e:
            logger.warning("[WidgetFactory] apply_default_layout 예외: %s", e)


__all__ = ["WidgetFactory", "_WIDGET_PATHS"]