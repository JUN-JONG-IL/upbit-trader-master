# -*- coding: utf-8 -*-
"""Tab 8: 수집 설정 UI 탭 (요약 뷰 + AutoBackfill 상태/제어)

상세 설정은 비모달 팝업(CollectionSettingsDialog)으로 분리되었습니다.
이 탭은 현재 설정의 요약과 AutoBackfill 상태를 함께 표시하며,
실제 위젯 로직은 다이얼로그에 위임합니다.

AutoBackfill 상태 표시:
  대기 / 점검 / 탐지 / 실행 / 완료 / 실패
  마지막 실행 시각, 처리건수, 잔여 Gap, 다음 재시도 예정
  수동 실행 1회 / 자동 모드 ON·OFF 제어 버튼

MongoDB 저장 필드 (ui_settings.auto_backfill):
  auto_enabled      - 자동 백필 활성화 여부 (bool)
  interval_seconds  - 자동 실행 주기 (int, 기본 300초)
"""
from __future__ import annotations
import logging
import os
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional, Any

logger = logging.getLogger(__name__)

try:
    from PyQt5 import uic
    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QWidget
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

# BackfillStartResult → 한국어 상태 문자열 매핑
_RESULT_KO: dict = {
    "STARTED": "실행 시작",
    "ALREADY_RUNNING": "실행 중",
    "SYMBOLS_NOT_READY_WAITING": "심볼 대기 중",
    "SYMBOLS_NOT_READY_WAITER_RUNNING": "심볼 대기 중(스레드)",
    "SYMBOLS_NOT_READY_WAITER_ALREADY_WAITING": "심볼 대기 중(중복방지)",
    "WAITER_START_FAILED": "대기 스레드 시작 실패",
    "THREAD_START_FAILED": "스레드 시작 실패",
    "COOLDOWN_ACTIVE": "쿨다운 중",
    "NOT_INITIALIZED": "초기화 전",
}

# AutoBackfillManager 내부 상태 → 요약 문자열
def _running_state_text(mgr: Any) -> str:
    """AutoBackfillManager 에서 현재 동작 상태를 요약 텍스트로 반환."""
    try:
        if getattr(mgr, "_running", False):
            return "탐지/실행 중"
        if getattr(mgr, "_waiting", False):
            return "심볼 대기 중"
        result = getattr(mgr, "last_start_result", None)
        if result is None:
            return "초기화 전"
        code = getattr(result, "value", str(result))
        return _RESULT_KO.get(code, code)
    except Exception:
        return "상태 조회 오류"


if _HAS_QT:
    class CollectionTab(QWidget):
        """Tab 8: 수집 설정 UI — 요약 뷰 + AutoBackfill 상태/제어 + 비모달 팝업 연동"""

        def __init__(self, parent=None, mongo_client=None):
            super().__init__(parent)
            ui_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "collection_tab.ui")
            try:
                uic.loadUi(ui_path, self)
            except Exception as exc:
                logger.warning("[CollectionTab] UI 파일 로드 실패: %s", exc)

            self._mongo_client = mongo_client
            self._auto_controller: Optional[Any] = None  # AutoController 인스턴스 (외부 주입 또는 자체 생성)

            # 갱신 타이머 (3초)
            self._timer = QTimer(self)
            self._timer.setInterval(3000)
            self._timer.timeout.connect(self._update_ui)

            # 상세 설정 다이얼로그 인스턴스 (지연 생성)
            self._detail_dialog = None

            # 백필/스케줄러 설정 다이얼로그 인스턴스 (지연 생성)
            self._bf_settings_dialog = None

            # 버튼 연결 — 상세 설정
            if hasattr(self, "btn_open_detail"):
                self.btn_open_detail.clicked.connect(self._open_detail_dialog)

            # 버튼 연결 — 백필/스케줄러 설정
            if hasattr(self, "btn_open_bf_settings"):
                self.btn_open_bf_settings.clicked.connect(self._open_bf_settings_dialog)

            # 탭의 프리셋 버튼 → 다이얼로그에 위임 (라이트/밸런스/헤비/기본값복원)
            if hasattr(self, "btn_preset_light"):
                self.btn_preset_light.clicked.connect(self._on_preset_light)
            if hasattr(self, "btn_preset_balance"):
                self.btn_preset_balance.clicked.connect(self._on_preset_balance)
            if hasattr(self, "btn_preset_heavy"):
                self.btn_preset_heavy.clicked.connect(self._on_preset_heavy)
            if hasattr(self, "btn_preset_default"):
                self.btn_preset_default.clicked.connect(self._on_preset_default)

            # AutoBackfill 제어 버튼
            if hasattr(self, "btn_bf_run_once"):
                self.btn_bf_run_once.clicked.connect(self._on_btn_bf_run_once)
            if hasattr(self, "btn_bf_toggle_auto"):
                self.btn_bf_toggle_auto.toggled.connect(self._on_btn_bf_toggle_auto)

            # AutoController 자체 생성 (외부에서 set_auto_controller()를 호출하지 않아도 동작)
            self._try_init_auto_controller()

            # 앱 시작 시 MongoDB에서 저장된 설정 로드
            self._load_settings_from_mongo()
            if self._auto_controller is not None:
                self._restore_backfill_settings_to_ctrl(self._auto_controller)

        # ------------------------------------------------------------------
        # AutoController 자체 초기화 (외부 주입 전 대비)
        # ------------------------------------------------------------------

        def _try_init_auto_controller(self) -> None:
            """외부 주입 없이도 AutoController를 스스로 생성합니다.

            set_auto_controller()가 나중에 호출되면 그 인스턴스로 교체됩니다.
            """
            if self._auto_controller is not None:
                return

            _ctrl_candidates = (
                "14_orchestrator.auto_controller",
                "src.14_orchestrator.auto_controller",
            )
            for _cpath in _ctrl_candidates:
                try:
                    import importlib as _il
                    _cm = _il.import_module(_cpath)
                    AutoController = getattr(_cm, "AutoController")
                    ctrl = AutoController(parent=self)
                    self._wire_auto_controller(ctrl)
                    logger.info("[CollectionTab] AutoController 자체 생성 완료 (%s)", _cpath)
                    return
                except (ImportError, AttributeError) as exc:
                    logger.debug("[CollectionTab] AutoController 생성 시도 실패 (%s): %s", _cpath, exc)
                except Exception as exc:
                    # Qt 초기화 오류 등 예상 외 실패 포함
                    logger.warning("[CollectionTab] AutoController 초기화 예외 (%s): %s", _cpath, exc)
                    return  # 더 이상 시도하지 않음

            logger.warning("[CollectionTab] AutoController 자체 생성 실패 — 수동 실행만 폴백 동작")

        def _wire_auto_controller(self, ctrl) -> None:
            """AutoController 인스턴스를 연결합니다."""
            self._auto_controller = ctrl
            try:
                ctrl.status_updated.connect(self._on_backfill_status_updated)
            except (AttributeError, RuntimeError) as exc:
                logger.debug("[CollectionTab] AutoController 시그널 연결 실패: %s", exc)

        # ------------------------------------------------------------------
        # AutoController 주입
        # ------------------------------------------------------------------

        def set_auto_controller(self, ctrl) -> None:
            """AutoController(PyQt5 QObject) 인스턴스 주입.

            ctrl.status_updated 시그널(dict)을 AutoBackfill 상태 레이블에 연결합니다.
            MongoDB에 저장된 auto_backfill 설정을 ctrl에 복원합니다.
            외부에서 주입된 컨트롤러는 자체 생성된 컨트롤러를 대체합니다.
            """
            if ctrl is None:
                return
            # 기존 자체 생성 컨트롤러의 시그널 연결 해제
            if self._auto_controller is not None and self._auto_controller is not ctrl:
                try:
                    self._auto_controller.status_updated.disconnect(self._on_backfill_status_updated)
                except Exception:
                    pass
            self._wire_auto_controller(ctrl)
            # MongoDB에 저장된 자동 모드 복원
            self._restore_backfill_settings_to_ctrl(ctrl)
            # 백필/스케줄러 설정 다이얼로그에도 컨트롤러 전파 (이미 생성된 경우)
            if self._bf_settings_dialog is not None and hasattr(self._bf_settings_dialog, "set_auto_controller"):
                self._bf_settings_dialog.set_auto_controller(ctrl)

        def _restore_backfill_settings_to_ctrl(self, ctrl) -> None:
            """MongoDB auto_backfill 설정을 AutoController에 복원."""
            if self._mongo_client is None:
                return
            try:
                db = self._mongo_client["upbit_trader"]
                doc = db.ui_settings.find_one({"user_id": "default"})
                if not doc:
                    return
                bf_settings = doc.get("auto_backfill", {})
                if not bf_settings:
                    return
                auto_enabled = bool(bf_settings.get("auto_enabled", False))
                interval_seconds = int(bf_settings.get("interval_seconds", 300))
                if auto_enabled:
                    ctrl.start_background_detection(interval_seconds)
                    self._set_auto_btn_state(True)
                    logger.info("[CollectionTab] auto_backfill 자동 모드 복원: interval=%ss", interval_seconds)
            except Exception as exc:
                logger.debug("[CollectionTab] auto_backfill 설정 복원 실패: %s", exc)

        def _save_backfill_settings_to_mongo(self, auto_enabled: bool, interval_seconds: int = 300) -> None:
            """auto_backfill 설정을 MongoDB에 비동기 저장."""
            if self._mongo_client is None:
                return

            def _save() -> None:
                try:
                    db = self._mongo_client["upbit_trader"]
                    db.ui_settings.update_one(
                        {"user_id": "default"},
                        {
                            "$set": {
                                "auto_backfill.auto_enabled": auto_enabled,
                                "auto_backfill.interval_seconds": interval_seconds,
                                "auto_backfill.updated_at": datetime.now(timezone.utc),
                            }
                        },
                        upsert=True,
                    )
                    logger.debug("[CollectionTab] auto_backfill 설정 MongoDB 저장 완료")
                except Exception as exc:
                    logger.debug("[CollectionTab] auto_backfill MongoDB 저장 실패: %s", exc)

            threading.Thread(target=_save, daemon=True).start()

        # ------------------------------------------------------------------
        # AutoBackfill 상태 슬롯
        # ------------------------------------------------------------------

        def _on_backfill_status_updated(self, status: dict) -> None:
            """AutoController.status_updated 시그널 수신 → 라벨 갱신."""
            try:
                automatic = bool(status.get("automatic", False))
                # queue_length는 하위 호환용으로 유지 (pending_count 없을 때 폴백)
                queue_len = int(status.get("queue_length", 0))
                processed_count = int(status.get("processed_count", 0))
                pending_count = int(status.get("pending_count", queue_len))
                failed_count = int(status.get("failed_count", 0))
                execution_state = str(status.get("execution_state", ""))
                last_run_ok = bool(status.get("last_run_ok", False))
                last_run_time = str(status.get("last_run_time", ""))
                interval_seconds = int(status.get("interval_seconds", 300))
                last_error_reason = str(status.get("last_error_reason", ""))

                # 실행 상태 → 표시 문자열 매핑
                _EXEC_STATE_KO = {
                    "idle": "대기",
                    "detecting": "갭 탐지 중",
                    "processing": "백필 처리 중",
                    "completed": "완료",
                    "error": "오류",
                }

                # 상태 문자열 조합
                if self._auto_controller is not None:
                    mgr = getattr(self._auto_controller, "_mgr", None)
                    state_text = _running_state_text(mgr) if mgr is not None else "--"
                else:
                    state_text = "--"

                # execution_state가 있으면 더 구체적인 상태 표시
                if execution_state and execution_state != "idle":
                    exec_ko = _EXEC_STATE_KO.get(execution_state, execution_state)
                    display_state = f"{state_text} ({exec_ko})" if state_text not in ("--", "초기화 전") else exec_ko
                else:
                    display_state = state_text

                if hasattr(self, "label_bf_status"):
                    self.label_bf_status.setText(display_state)
                    color = {
                        "탐지/실행 중": "#2196F3",
                        "심볼 대기 중": "#FF9800",
                        "쿨다운 중": "#9E9E9E",
                        "실행 시작": "#4CAF50",
                        "초기화 전": "#9E9E9E",
                    }.get(state_text, "#F44336" if "실패" in state_text or "오류" in state_text else "#333333")
                    self.label_bf_status.setStyleSheet(f"color: {color}; font-weight: bold;")

                if hasattr(self, "label_bf_last_run"):
                    if last_run_time:
                        try:
                            # ISO 포맷 → 짧은 형식
                            dt = datetime.fromisoformat(last_run_time)
                            ts = dt.strftime("%m-%d %H:%M:%S")
                        except Exception:
                            ts = last_run_time[:19]
                        ok_str = "성공" if last_run_ok else "실패"
                        self.label_bf_last_run.setText(f"마지막 실행: {ts} [{ok_str}]")
                    else:
                        self.label_bf_last_run.setText("마지막 실행: --")

                if hasattr(self, "label_bf_processed"):
                    # 처리 건수: 실제로 DB에 반영된(백필 완료된) Gap 수
                    ok_str = "성공" if last_run_ok else ("미실행" if not last_run_time else "실패")
                    fail_str = f", 실패 {failed_count}" if failed_count > 0 else ""
                    self.label_bf_processed.setText(
                        f"처리 건수: {processed_count}{fail_str} (마지막: {ok_str})"
                    )

                if hasattr(self, "label_bf_gap_remaining"):
                    # 잔여 Gap 큐: 아직 백필되지 않은 pending Gap 수
                    self.label_bf_gap_remaining.setText(f"잔여 Gap 큐: {pending_count}건")

                if hasattr(self, "label_bf_next_retry"):
                    if automatic:
                        self.label_bf_next_retry.setText(f"다음 실행: {interval_seconds}초 주기")
                    else:
                        self.label_bf_next_retry.setText("다음 실행: 수동 모드")

                if hasattr(self, "label_bf_last_result"):
                    if self._auto_controller is not None:
                        mgr = getattr(self._auto_controller, "_mgr", None)
                        if mgr is not None:
                            result = getattr(mgr, "last_start_result", None)
                            if result is not None:
                                code = getattr(result, "value", str(result))
                                desc = getattr(result, "description", "")
                                ko = _RESULT_KO.get(code, code)
                                self.label_bf_last_result.setText(f"결과: {ko}")
                                self.label_bf_last_result.setToolTip(desc)
                            # 오류 사유 표시 (status에서 우선, mgr 폴백)
                            err_reason = last_error_reason or getattr(mgr, "last_error_reason", "")
                            self._update_error_label(err_reason)

                # 자동 모드 버튼 동기화 (시그널 루프 방지)
                self._set_auto_btn_state(automatic)

                # 스케줄러 상태 레이블 갱신
                self._refresh_scheduler_status_label()

            except Exception as exc:
                logger.debug("[CollectionTab] AutoBackfill 상태 갱신 실패: %s", exc)

        def _refresh_backfill_status_direct(self) -> None:
            """AutoBackfillManager 상태를 직접 조회하여 UI를 갱신합니다.

            self._auto_controller._mgr → static 모듈 → get_auto_backfill_manager() 순서로 탐색합니다.
            NOT_INITIALIZED 표시 시 구체 사유를 툴팁에 기록합니다.
            """
            # 1) AutoController._mgr 우선
            mgr = None
            if self._auto_controller is not None:
                mgr = getattr(self._auto_controller, "_mgr", None)
            # 2) module_finder 폴백
            if mgr is None:
                try:
                    from ..utils.module_finder import get_auto_backfill_manager
                    mgr = get_auto_backfill_manager()
                except Exception:
                    pass

            if mgr is None:
                # 원인: AutoBackfillManager 가 아직 생성되지 않음
                _reason = "AutoBackfillManager 인스턴스 없음 (초기화 전)"
                if hasattr(self, "label_bf_status"):
                    self.label_bf_status.setText("초기화 전")
                    self.label_bf_status.setStyleSheet("color: #9E9E9E; font-weight: bold;")
                    self.label_bf_status.setToolTip(_reason)
                if hasattr(self, "label_bf_last_result"):
                    self.label_bf_last_result.setText("결과: NOT_INITIALIZED")
                    self.label_bf_last_result.setToolTip(_reason)
                self._update_error_label("")
                return

            try:
                state_text = _running_state_text(mgr)
                if hasattr(self, "label_bf_status"):
                    color = {
                        "탐지/실행 중": "#2196F3",
                        "심볼 대기 중": "#FF9800",
                        "쿨다운 중": "#9E9E9E",
                        "실행 시작": "#4CAF50",
                        "초기화 전": "#9E9E9E",
                    }.get(state_text, "#F44336" if "실패" in state_text else "#333333")
                    self.label_bf_status.setText(state_text)
                    self.label_bf_status.setStyleSheet(f"color: {color}; font-weight: bold;")

                result = getattr(mgr, "last_start_result", None)
                if result is not None:
                    code = getattr(result, "value", str(result))
                    ko = _RESULT_KO.get(code, code)
                    desc = getattr(result, "description", "")
                    # NOT_INITIALIZED 시 구체 사유 추가 표시
                    if code == "NOT_INITIALIZED":
                        desc = (
                            "run_once() / start_periodic() 가 한 번도 호출되지 않은 초기 상태입니다. "
                            "수동 실행 버튼을 클릭하거나 자동 모드를 ON으로 전환하세요."
                        )
                    if hasattr(self, "label_bf_last_result"):
                        self.label_bf_last_result.setText(f"결과: {ko}")
                        self.label_bf_last_result.setToolTip(desc)

                # 오류 사유 표시
                self._update_error_label(getattr(mgr, "last_error_reason", ""))

                # 처리 건수 및 잔여 Gap 큐 갱신 (직접 mgr 속성 읽기)
                processed_count = int(getattr(mgr, "_processed_count", 0))
                failed_count = int(getattr(mgr, "_failed_count", 0))
                pending_count = int(getattr(mgr, "_pending_count", 0))
                if hasattr(self, "label_bf_processed"):
                    last_ok = getattr(mgr, "last_run_ok", None)
                    ok_str = "" if last_ok is None else ("성공" if last_ok else "실패")
                    fail_str = f", 실패 {failed_count}" if failed_count > 0 else ""
                    self.label_bf_processed.setText(
                        f"처리 건수: {processed_count}{fail_str}"
                        + (f" (마지막: {ok_str})" if ok_str else "")
                    )
                if hasattr(self, "label_bf_gap_remaining"):
                    self.label_bf_gap_remaining.setText(f"잔여 Gap 큐: {pending_count}건")

                # 마지막 실행 시각 갱신
                last_run = getattr(mgr, "last_run_time", None)
                if last_run is not None and hasattr(self, "label_bf_last_run"):
                    try:
                        if isinstance(last_run, datetime):
                            ts = last_run.strftime("%m-%d %H:%M:%S")
                        else:
                            ts = str(last_run)[:19]
                        last_ok = getattr(mgr, "last_run_ok", None)
                        ok_str = "" if last_ok is None else (" [성공]" if last_ok else " [실패]")
                        self.label_bf_last_run.setText(f"마지막 실행: {ts}{ok_str}")
                    except Exception:
                        pass
            except Exception as exc:
                logger.debug("[CollectionTab] 직접 상태 조회 실패: %s", exc)

            # 스케줄러 상태 레이블 갱신 (직접 조회 후 항상 동기화)
            self._refresh_scheduler_status_label()

        def _update_error_label(self, error_reason: str) -> None:
            """label_bf_last_error 레이블을 오류 사유 문자열로 갱신합니다."""
            lbl = getattr(self, "label_bf_last_error", None)
            if lbl is None:
                return
            if error_reason:
                # 오류 분류 (간단)
                r = error_reason.lower()
                if any(k in r for k in ("not_initialized", "초기화", "설정 누락", "config")):
                    category = "설정 누락"
                elif any(k in r for k in ("db", "database", "connection", "연결", "timescale", "mongo")):
                    category = "DB 연결 실패"
                elif any(k in r for k in ("symbol", "심볼", "종목", "empty", "비어")):
                    category = "심볼 비어있음"
                elif any(k in r for k in ("thread", "worker", "스레드", "워커", "start failed")):
                    category = "워커 시작 실패"
                else:
                    category = "예외"
                lbl.setText(f"오류 사유 [{category}]: {error_reason}")
                lbl.setStyleSheet("color: #D32F2F;")
                lbl.setToolTip(
                    f"분류: {category}\n원인: {error_reason}\n\n"
                    "해결 방법:\n"
                    "  설정 누락 → '백필/스케줄러 실행 설정' 저장 후 자동 실행 ON\n"
                    "  DB 연결 실패 → DB 서비스 상태 확인\n"
                    "  심볼 비어있음 → 스캐너/AI-ML 탭에서 심볼 선택\n"
                    "  워커 시작 실패 → 앱 재시작"
                )
            else:
                lbl.setText("오류 사유: 없음")
                lbl.setStyleSheet("color: #757575;")
                lbl.setToolTip("")

        def _set_auto_btn_state(self, is_auto: bool) -> None:
            """자동 모드 버튼 상태 동기화 (toggled 시그널 루프 방지)."""
            btn = getattr(self, "btn_bf_toggle_auto", None)
            if btn is None:
                return
            try:
                btn.blockSignals(True)
                btn.setChecked(is_auto)
                if is_auto:
                    btn.setText("자동 모드: ON")
                    btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
                else:
                    btn.setText("자동 모드: OFF")
                    btn.setStyleSheet("font-weight: bold;")
            finally:
                btn.blockSignals(False)

        # ------------------------------------------------------------------
        # AutoBackfill 버튼 핸들러
        # ------------------------------------------------------------------

        def _on_btn_bf_run_once(self) -> None:
            """수동 1회 실행 버튼 — 실행 직후 상태를 즉시 갱신합니다."""
            # 실행 전 상태 표시
            if hasattr(self, "label_bf_status"):
                self.label_bf_status.setText("실행 요청 중...")
                self.label_bf_status.setStyleSheet("color: #FF9800; font-weight: bold;")

            # AutoController가 없으면 자체 생성 시도
            if self._auto_controller is None:
                self._try_init_auto_controller()

            if self._auto_controller is not None:
                try:
                    self._auto_controller.run_once()  # 내부에서 force=True 사용
                    logger.info("[CollectionTab] AutoBackfill 수동 실행 1회 요청")
                except Exception as exc:
                    logger.error("[CollectionTab] AutoBackfill 수동 실행 실패: %s", exc)
            else:
                # AutoController 생성에도 실패한 경우 AutoBackfillManager 직접 호출
                try:
                    from ..utils.module_finder import get_auto_backfill_manager
                    mgr = get_auto_backfill_manager()
                    if mgr is not None:
                        result = mgr.run_once_nonblocking(force=True)
                        logger.info("[CollectionTab] AutoBackfill 수동 실행 (직접, force=True) result=%s", result)
                    else:
                        logger.warning("[CollectionTab] AutoBackfillManager 를 찾을 수 없음 — 수동 실행 불가")
                        if hasattr(self, "label_bf_status"):
                            self.label_bf_status.setText("초기화 실패 — 로그 확인")
                            self.label_bf_status.setStyleSheet("color: #F44336; font-weight: bold;")
                        return
                except Exception as exc:
                    logger.error("[CollectionTab] AutoBackfill 수동 실행(직접) 실패: %s", exc)

            # 500ms 후 상태 즉시 갱신 (스레드 시작 시간 확보)
            QTimer.singleShot(500, self._refresh_backfill_status_direct)
            # 2초 후 한 번 더 갱신 (실행 완료 여부 확인)
            QTimer.singleShot(2000, self._refresh_backfill_status_direct)

        def _on_btn_bf_toggle_auto(self, checked: bool) -> None:
            """자동 모드 ON/OFF 토글."""
            self._set_auto_btn_state(checked)
            # 백필/스케줄러 설정 다이얼로그에서 주기(초)를 가져오거나 기본값 300초 사용
            interval = 300
            bf_dlg = self._bf_settings_dialog
            if bf_dlg is not None and hasattr(bf_dlg, "get_interval_seconds"):
                try:
                    interval = bf_dlg.get_interval_seconds()
                except Exception:
                    pass

            # AutoController가 없으면 자체 생성 시도
            if self._auto_controller is None:
                self._try_init_auto_controller()

            if self._auto_controller is not None:
                try:
                    if checked:
                        # start_background_detection 내부에서 즉시 kick-off + 주기 시작
                        self._auto_controller.start_background_detection(interval)
                    else:
                        self._auto_controller.stop_background_detection()
                except Exception as exc:
                    logger.error("[CollectionTab] 자동 모드 전환 실패: %s", exc)
            self._save_backfill_settings_to_mongo(checked, interval)

        # ------------------------------------------------------------------
        # 다이얼로그 관련
        # ------------------------------------------------------------------

        def _get_or_create_dialog(self):
            """상세 설정 다이얼로그를 반환합니다 (없으면 생성)."""
            if self._detail_dialog is None:
                try:
                    from ..dialogs.collection_settings_dialog import CollectionSettingsDialog
                    self._detail_dialog = CollectionSettingsDialog(self)
                    self._detail_dialog.settings_changed.connect(self._on_detail_settings_changed)
                except Exception as exc:
                    logger.error("[CollectionTab] 다이얼로그 생성 실패: %s", exc)
            return self._detail_dialog

        def _open_detail_dialog(self) -> None:
            """상세 설정 다이얼로그 열기 (비모달)."""
            dlg = self._get_or_create_dialog()
            if dlg is None:
                return
            if dlg.isVisible():
                dlg.activateWindow()
                return
            dlg.show()

        # ------------------------------------------------------------------
        # 백필/스케줄러 설정 다이얼로그
        # ------------------------------------------------------------------

        def _get_or_create_bf_settings_dialog(self):
            """백필/스케줄러 설정 다이얼로그를 반환합니다 (없으면 생성)."""
            if self._bf_settings_dialog is None:
                try:
                    from ..dialogs.backfill_scheduler_settings_dialog import (
                        BackfillSchedulerSettingsDialog,
                    )
                    self._bf_settings_dialog = BackfillSchedulerSettingsDialog(
                        parent=self,
                        mongo_client=self._mongo_client,
                        auto_controller=self._auto_controller,
                    )
                    self._bf_settings_dialog.settings_saved.connect(
                        self._on_bf_settings_saved
                    )
                except Exception as exc:
                    logger.error("[CollectionTab] 백필/스케줄러 설정 다이얼로그 생성 실패: %s", exc)
            return self._bf_settings_dialog

        def _open_bf_settings_dialog(self) -> None:
            """백필/스케줄러 설정 다이얼로그 열기 (비모달)."""
            dlg = self._get_or_create_bf_settings_dialog()
            if dlg is None:
                return
            # AutoController 최신 인스턴스 동기화
            if self._auto_controller is not None and hasattr(dlg, "set_auto_controller"):
                dlg.set_auto_controller(self._auto_controller)
            if dlg.isVisible():
                dlg.activateWindow()
                return
            dlg.show()

        def _on_bf_settings_saved(self, settings: dict) -> None:
            """백필/스케줄러 설정 저장 시 상태 레이블 즉시 갱신."""
            self._refresh_backfill_status_direct()
            self._refresh_scheduler_status_label(settings)

        def _refresh_scheduler_status_label(self, settings: Optional[dict] = None) -> None:
            """스케줄러 상태 레이블(label_scheduler_status)을 갱신합니다."""
            lbl = getattr(self, "label_scheduler_status", None)
            if lbl is None:
                return
            try:
                if self._auto_controller is not None:
                    status = self._auto_controller.get_status()
                    automatic = bool(status.get("automatic", False))
                    interval_sec = int(status.get("interval_seconds", 300))
                    if automatic:
                        lbl.setText(f"활성 ({interval_sec // 60}분 주기)")
                        lbl.setStyleSheet("color: #4CAF50; font-weight: bold;")
                    else:
                        lbl.setText("비활성 (수동)")
                        lbl.setStyleSheet("color: #9E9E9E; font-weight: bold;")
                else:
                    lbl.setText("비활성")
                    lbl.setStyleSheet("color: #9E9E9E; font-weight: bold;")
            except Exception as exc:
                logger.debug("[CollectionTab] 스케줄러 상태 갱신 실패: %s", exc)

        def _on_preset_light(self) -> None:
            """🟢 라이트 프리셋 — 다이얼로그에 위임."""
            dlg = self._get_or_create_dialog()
            if dlg is not None and hasattr(dlg, "apply_preset_light"):
                dlg.apply_preset_light()

        def _on_preset_balance(self) -> None:
            """🔵 밸런스 프리셋 — 다이얼로그에 위임."""
            dlg = self._get_or_create_dialog()
            if dlg is not None and hasattr(dlg, "apply_preset_balance"):
                dlg.apply_preset_balance()

        def _on_preset_heavy(self) -> None:
            """🔴 헤비 프리셋 — 다이얼로그에 위임."""
            dlg = self._get_or_create_dialog()
            if dlg is not None and hasattr(dlg, "apply_preset_heavy"):
                dlg.apply_preset_heavy()

        def _on_preset_default(self) -> None:
            """🔄 기본값 복원 — 다이얼로그에 위임."""
            dlg = self._get_or_create_dialog()
            if dlg is not None and hasattr(dlg, "apply_preset_default"):
                dlg.apply_preset_default()

        def _on_detail_settings_changed(self, settings: dict) -> None:
            """다이얼로그 설정 변경 시 요약 레이블 갱신."""
            col = settings.get("collection_settings", {})
            tfs = col.get("timeframes", [])
            tf_str = ", ".join(tfs) if tfs else "없음"
            try:
                if hasattr(self, "label_summary_timeframes"):
                    self.label_summary_timeframes.setText(f"활성 타임프레임: {tf_str}")
                if hasattr(self, "label_summary_backfill"):
                    self.label_summary_backfill.setText("복원 기준: 타임프레임별 최대 캔들 수(자동 환산 안내)")
            except Exception as exc:
                logger.debug("[CollectionTab] 요약 레이블 갱신 실패: %s", exc)

        # ------------------------------------------------------------------
        # MongoDB 설정 로드
        # ------------------------------------------------------------------

        def _load_settings_from_mongo(self) -> None:
            """앱 시작 시 MongoDB에서 저장된 설정을 로드합니다."""
            if self._mongo_client is None:
                logger.debug("[CollectionTab] MongoDB 클라이언트 없음 — 기본값 사용")
                return
            try:
                db = self._mongo_client["upbit_trader"]
                doc = db.ui_settings.find_one({"user_id": "default"})
                if not doc:
                    logger.info("[CollectionTab] 저장된 설정 없음 — 기본값 사용")
                    return
                settings = doc.get("collection_settings", {})
                if settings:
                    self.restore_settings({"collection_settings": settings})
                    logger.info("[CollectionTab] MongoDB에서 수집 설정 로드 완료")
            except Exception as exc:
                logger.error("[CollectionTab] 설정 로드 실패: %s — 기본값 사용", exc)

        # ------------------------------------------------------------------
        # 공개 API (status_widget.py 등 외부에서 호출)
        # ------------------------------------------------------------------

        def set_controller(self, ctrl) -> None:
            """CollectionSettings 컨트롤러 주입 (하위 호환 유지)"""
            pass

        def set_settings_manager(self, manager) -> None:
            """UISettingsManager 주입 → 다이얼로그에 전달"""
            dlg = self._get_or_create_dialog()
            if dlg is not None and hasattr(dlg, "set_settings_manager"):
                dlg.set_settings_manager(manager)

        def restore_settings(self, settings: dict) -> None:
            """MongoDB에서 로드한 설정을 다이얼로그에 복원하고 요약 레이블도 갱신합니다."""
            dlg = self._get_or_create_dialog()
            if dlg is not None and hasattr(dlg, "restore_settings"):
                dlg.restore_settings(settings)
            col = settings.get("collection_settings", {})
            tfs = col.get("timeframes", [])
            if tfs:
                self._on_detail_settings_changed(settings)

        def collect_current_settings(self) -> dict:
            """현재 설정을 다이얼로그에서 수집합니다."""
            dlg = self._get_or_create_dialog()
            if dlg is not None and hasattr(dlg, "collect_current_settings"):
                return dlg.collect_current_settings()
            return {}

        def on_settings_changed(self) -> None:
            """설정 변경 알림 (하위 호환 유지)"""
            pass

        def start_updates(self, interval_ms: int = 3000) -> None:
            self._timer.setInterval(max(3000, int(interval_ms)))
            self._timer.start()

        def stop_updates(self) -> None:
            self._timer.stop()

        def _update_ui(self) -> None:
            """수집 설정 탭 — 현재 수집 상태 + 설정값·제한값 요약 갱신"""
            try:
                from ..utils.candle_queries import query_table_counts
                counts = query_table_counts()
                if hasattr(self, "label_summary_candles"):
                    self.label_summary_candles.setText(
                        f"[TimescaleDB] Candles: {counts.get('candles', 0):,}건"
                    )
                if hasattr(self, "label_summary_staging"):
                    self.label_summary_staging.setText(
                        f"[TimescaleDB] Staging: {counts.get('staging', 0):,}건"
                    )
                if hasattr(self, "label_summary_isolated"):
                    self.label_summary_isolated.setText(
                        f"[격리] TimescaleDB Isolated: {counts.get('isolated', 0):,}건"
                    )
                if hasattr(self, "label_summary_last_save"):
                    lst = counts.get("last_save_time")
                    if lst:
                        from datetime import datetime
                        ts = lst.strftime("%m-%d %H:%M:%S") if isinstance(lst, datetime) else str(lst)
                    else:
                        ts = "--"
                    self.label_summary_last_save.setText(f"최종 저장: {ts}")
            except Exception as exc:
                logger.debug("[CollectionTab] UI 갱신 실패: %s", exc)

            try:
                from ..utils.config_loader import get_ws_max_subscribe, get_symbol_query_limit
                from ..utils.constants import MAX_SUBSCRIBE_LIMIT, MAX_CANDLE_LIMIT
                ws_max = get_ws_max_subscribe()
                if hasattr(self, "label_summary_timeframes"):
                    tfs = self.get_selected_timeframes()
                    tf_str = ", ".join(tfs) if tfs else "없음"
                    self.label_summary_timeframes.setText(
                        f"활성 타임프레임: {tf_str} | WS 구독: {ws_max:,} / {MAX_SUBSCRIBE_LIMIT:,}"
                    )
            except Exception as exc:
                logger.debug("[CollectionTab] 설정값 표시 실패: %s", exc)

            # AutoBackfill 상태 주기적 갱신 (AutoController 유무 무관)
            self._refresh_backfill_status_direct()

            # ── TF 진행률 위젯 강조 동기화 (느슨한 결합, 비파괴) ──
            # status_widget 이 화면에 있고 TFProgressWidget 도킹된 경우,
            # 현재 수집 설정 TF 를 즉시 강조 표시한다. 위젯이 없으면 조용히 noop.
            try:
                self._sync_tf_safe_selection()
            except Exception as exc:
                logger.debug("[CollectionTab] TF 강조 동기화 실패: %s", exc)

        def _sync_tf_safe_selection(self) -> None:
            """현재 선택 TF 를 StatusWidget 의 TFProgressWidget 에 전파.

            StatusWidget 인스턴스를 부모/탑레벨/형제에서 best-effort 로 찾고,
            ``_tf_safe_widget.set_selected_timeframes()`` 를 호출. 어떤 조건이든
            실패하면 조용히 noop.
            """
            try:
                tfs = self.get_selected_timeframes() or []
            except Exception:
                tfs = []
            if not tfs:
                return
            # 후보: 부모 체인 → 최상위 윈도우 → 그 child 위젯
            candidate = None
            try:
                w = self
                # 최상위 부모로 이동
                while True:
                    parent = w.parent() if hasattr(w, "parent") else None
                    if parent is None:
                        break
                    w = parent
                # w 가 StatusWidgetMixin 적용된 메인 윈도우라면 _tf_safe_widget 보유
                if hasattr(w, "_tf_safe_widget"):
                    candidate = w
                else:
                    # 메인 윈도우의 자손 위젯 중 _tf_safe_widget 보유 위젯 검색
                    try:
                        children = w.findChildren(QWidget)
                    except Exception:
                        children = []
                    for c in children:
                        if hasattr(c, "_tf_safe_widget"):
                            candidate = c
                            break
            except Exception:
                candidate = None
            if candidate is None:
                return
            try:
                tf_widget = getattr(candidate, "_tf_safe_widget", None)
                if tf_widget is not None and hasattr(tf_widget, "set_selected_timeframes"):
                    tf_widget.set_selected_timeframes(tfs)
            except Exception as exc:
                logger.debug("[CollectionTab] _tf_safe_widget 호출 실패: %s", exc)

        def get_selected_timeframes(self) -> list:
            dlg = self._get_or_create_dialog()
            if dlg is not None and hasattr(dlg, "get_selected_timeframes"):
                return dlg.get_selected_timeframes()
            return ["1m", "5m", "1h"]

        def get_lookback_days(self) -> int:
            dlg = self._get_or_create_dialog()
            if dlg is not None and hasattr(dlg, "get_lookback_days"):
                return dlg.get_lookback_days()
            return 3

        def update_disk_usage(self, ts_gb: float, redis_mb: float, ch_gb: float) -> None:
            dlg = self._get_or_create_dialog()
            if dlg is not None and hasattr(dlg, "update_disk_usage"):
                dlg.update_disk_usage(ts_gb, redis_mb, ch_gb)

else:
    class CollectionTab:  # type: ignore[no-redef]
        """PyQt5 미설치 시 사용하는 더미 클래스"""
        def __init__(self, parent=None, mongo_client=None):
            pass
        def set_auto_controller(self, ctrl) -> None:
            pass
        def start_updates(self, interval_ms: int = 3000) -> None:
            pass
        def stop_updates(self) -> None:
            pass
        def set_controller(self, ctrl) -> None:
            pass
        def set_settings_manager(self, manager) -> None:
            pass
        def restore_settings(self, settings: dict) -> None:
            pass
        def collect_current_settings(self) -> dict:
            return {}
        def on_settings_changed(self) -> None:
            pass
        def get_selected_timeframes(self) -> list:
            return ["1m", "5m", "1h"]
        def get_lookback_days(self) -> int:
            return 3
        def update_disk_usage(self, *args, **kwargs) -> None:
            pass
