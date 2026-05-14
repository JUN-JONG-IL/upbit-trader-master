# -*- coding: utf-8 -*-
"""
시그널 핸들러 Mixin (signal_handlers.py)

CHANGELOG:
    v6.2 (2026-05-03) | Copilot |
        - _on_metrics_updated(): _last_candles_total 캐싱 추가
          * DB 조회 실패 시에도 마지막 성공한 candles 건수로 "처리 완료" 표시
          * DataFlow 탭 갱신 시 이미 조회한 _stats 재사용 (중복 DB 조회 제거)
          * _tab_dashboard 없이도 _tab_dataflow 블록에서 _stats 조회
    v6.1 (2026-04-28) | Copilot |
        - _on_metrics_updated(): 플로우 상태 텍스트 세분화
          * ws_qps=0 + ws_manager 있음  → "연결됨 (수신 대기)"
          * ws_qps=0 + ws_manager 없음  → "WebSocket 미연결"
          * ws_qps>0                    → "수신 N건/초"
        - staging_count 변화 시 통신 테이블에 DB 저장 행 자동 추가
        - UI 갱신 상태는 WS 여부와 무관하게 항상 현재 시각 표시
"""
from __future__ import annotations

import logging
import os
import time as _perf_time
from datetime import datetime
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

try:
    from PyQt5.QtCore import pyqtSlot
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

if TYPE_CHECKING:
    pass

if _HAS_QT:
    class SignalHandlersMixin:
        """시그널 핸들러 Mixin."""

        # ------------------------------------------------------------------
        # DB 헬스체크 시그널
        # ------------------------------------------------------------------

        @pyqtSlot(dict)
        def _on_health_updated(self, health: dict) -> None:
            """DB 헬스 체크 결과 반영.

            상단 groupBox_db_status 가 제거됨에 따라 개별 label_db_* 갱신은 생략하고,
            전체 상태 레이블(label_overall_status) 에 OK/FAIL 수를 요약 표시합니다.
            """
            _DB_ROLE_MAP = {
                "timescale":  "TimescaleDB — OHLCV 캔들·Hypertable",
                "redis":      "Redis — L1캐시·PubSub·Gap큐",
                "mongo":      "MongoDB — 메타데이터·설정·UI",
                "postgres":   "PostgreSQL — 이벤트스토어·주문원장",
                "kafka":      "Kafka — 실시간 파이프라인·이관",
                "clickhouse": "ClickHouse — 장기 OLAP·백테스팅",
                "mlflow":     "MLflow — AI/ML 실험 추적",
            }
            try:
                # 개별 label_db_* 위젯이 여전히 존재하는 경우 업데이트 (호환성 유지)
                label_map = {
                    "timescale":  "label_db_timescale",
                    "redis":      "label_db_redis",
                    "mongo":      "label_db_mongo",
                    "postgres":   "label_db_postgres",
                    "kafka":      "label_db_kafka",
                    "clickhouse": "label_db_clickhouse",
                    "mlflow":     "label_db_mlflow",
                }
                for key, label_name in label_map.items():
                    lbl = getattr(self, label_name, None)
                    if lbl is not None:
                        ok = health.get(key, False)
                        role = _DB_ROLE_MAP.get(key, key.capitalize())
                        status_text = "OK" if ok else "FAIL"
                        lbl.setText(f"[{status_text}] {role}")
                        lbl.setToolTip(
                            f"{'연결 정상' if ok else '연결 실패'} — {role}"
                        )

                # 전체 상태 요약을 label_overall_status 에 반영
                ok_count = sum(1 for v in health.values() if v)
                total = len(health)
                fail_count = total - ok_count
                lbl_overall = getattr(self, "label_overall_status", None)
                if lbl_overall is not None:
                    if fail_count == 0:
                        lbl_overall.setText(f"전체 상태: 정상 ({ok_count}/{total})")
                        lbl_overall.setStyleSheet("color: #34C759; font-weight: bold;")
                    else:
                        failed_names = [k for k, v in health.items() if not v]
                        lbl_overall.setText(f"전체 상태: 오류 {fail_count}개 — {', '.join(failed_names)}")
                        lbl_overall.setStyleSheet("color: #FF3B30; font-weight: bold;")
                    lbl_overall.setToolTip(
                        "\n".join(
                            f"{'[OK]' if health.get(k, False) else '[FAIL]'} {desc}"
                            for k, desc in _DB_ROLE_MAP.items()
                        )
                    )
            except Exception as exc:
                logger.debug("[StatusWidget] DB 상태 레이블 갱신 실패: %s", exc)

            # 안전하게 _tab_dashboard 참조 (AttributeError 방지)
            _tab_dashboard = getattr(self, "_tab_dashboard", None)
            if _tab_dashboard is not None:
                try:
                    services = [
                        (
                            "TimescaleDB",
                            f"{os.getenv('TIMESCALE_HOST', '127.0.0.1')}:" f"{os.getenv('TIMESCALE_PORT', '5432')}",
                            "asyncpg",
                            "timescale",
                        ),
                        (
                            "Redis",
                            f"{os.getenv('REDIS_HOST', '127.0.0.1')}:" f"{os.getenv('REDIS_PORT', '58530')}",
                            "redis-py",
                            "redis",
                        ),
                        (
                            "MongoDB",
                            f"{os.getenv('MONGO_HOST', '127.0.0.1')}:" f"{os.getenv('MONGO_PORT', '27017')}",
                            "motor",
                            "mongo",
                        ),
                        (
                            "PostgreSQL",
                            f"{os.getenv('POSTGRES_HOST', '127.0.0.1')}:" f"{os.getenv('POSTGRES_PORT', '5433')}",
                            "psycopg",
                            "postgres",
                        ),
                        (
                            "Kafka",
                            f"{os.getenv('KAFKA_HOST', '127.0.0.1')}:" f"{os.getenv('KAFKA_PORT', '9092')}",
                            "kafka-python",
                            "kafka",
                        ),
                        (
                            "ClickHouse",
                            f"{os.getenv('CLICKHOUSE_HOST', '127.0.0.1')}:" f"{os.getenv('CLICKHOUSE_HTTP_PORT', '8123')}",
                            "clickhouse-driver",
                            "clickhouse",
                        ),
                        (
                            "MLflow",
                            f"{os.getenv('MLFLOW_HOST', '127.0.0.1')}:" f"{os.getenv('MLFLOW_PORT', '5000')}",
                            "mlflow",
                            "mlflow",
                        ),
                    ]
                    check_fn_map = {k: (lambda ok=v: ok) for k, v in health.items()}
                    try:
                        _tab_dashboard.update_service_table(services, check_fn_map)
                    except Exception as exc:
                        logger.debug("[StatusWidget] Tab 1 서비스 테이블 갱신 실패: %s", exc)
                except Exception as exc:
                    logger.debug("[StatusWidget] Tab 1 서비스 테이블 갱신 실패: %s", exc)

            try:
                total = len(health)
                if total > 0:
                    ok_count = sum(1 for v in health.values() if v)
                    if ok_count == total:
                        overall = "정상"
                        style = "color: #34C759; font-weight: bold;"
                    elif ok_count >= total * 0.5:
                        overall = "경고"
                        style = "color: #FF9500; font-weight: bold;"
                    else:
                        overall = "실패"
                        style = "color: #FF3B30; font-weight: bold;"
                    lbl = getattr(self, "label_overall_status", None)
                    if lbl is not None:
                        lbl.setText(f"전체 상태: {overall} ({ok_count}/{total})")
                        lbl.setStyleSheet(style)
                        failed_services = [name for name, ok in health.items() if not ok]
                        if failed_services:
                            tip = "[오류] 실패 서비스:\n" + "\n".join(
                                f"  • {s}" for s in failed_services
                            )
                        else:
                            tip = "[OK] 모든 서비스 정상"
                        lbl.setToolTip(tip)
                self._last_health = dict(health)
            except Exception as exc:
                logger.debug("[StatusWidget] 전체 상태 계산 실패: %s", exc)

        # ------------------------------------------------------------------
        # 실시간 지표 시그널
        # ------------------------------------------------------------------

        @pyqtSlot(int, int, int, str)
        def _on_metrics_updated(
            self,
            ws_qps: int,
            pipeline_qps: int,
            staging_count: int,
            last_text: str,
        ) -> None:
            """실시간 지표 갱신.

            Args:
                ws_qps: WebSocket 초당 수신 건수
                pipeline_qps: Pipeline 초당 처리 건수
                staging_count: Staging 저장 건수
                last_text: 마지막 수신 텍스트
            """
            _stats: dict = {}
            _gap = 0

            # 안전하게 탭 레퍼런스 수집 (AttributeError 방지)
            _tab_dashboard = getattr(self, "_tab_dashboard", None)
            _tab_websocket = getattr(self, "_tab_websocket", None)
            _tab_dataflow = getattr(self, "_tab_dataflow", None)
            _tab_error = getattr(self, "_tab_error", None)
            _tab_gap = getattr(self, "_tab_gap", None)

            # ── 대시보드 탭 갱신 ─────────────────────────────────────
            if _tab_dashboard is not None:
                try:
                    from ..utils import get_pipeline_stats, get_gap_queue_size
                    _stats = get_pipeline_stats()
                    _gap = get_gap_queue_size()

                    # pipeline_qps 보정: MetricsUpdater 콜백이 0이면 candles 증가량으로 파생
                    if pipeline_qps == 0:
                        _candles_now = _stats.get("candles", 0)
                        _prev_candles = getattr(self, "_prev_candles_for_qps", _candles_now)
                        _interval_s = getattr(self, "_metrics_interval_s", 3)
                        delta_candles = _candles_now - _prev_candles
                        safe_interval = max(1, _interval_s)
                        derived_qps = max(0, int(delta_candles / safe_interval))
                        if derived_qps > 0:
                            pipeline_qps = derived_qps
                        self._prev_candles_for_qps = _candles_now
                    if getattr(self, "_metrics_updater", None) is not None:
                        # 다음 QPS 계산 주기를 위해 MetricsUpdater 갱신 간격(초) 캐싱
                        try:
                            self._metrics_interval_s = self._metrics_updater.get_interval_seconds()
                        except Exception:
                            pass

                    # Staging→Candles 표시를 get_pipeline_stats()의 최신값으로 갱신
                    _fresh_staging = _stats.get("staging", staging_count)
                except Exception as exc:
                    logger.debug("[StatusWidget] 파이프라인 통계 조회 실패: %s", exc)
                    _fresh_staging = staging_count

                try:
                    try:
                        _tab_dashboard.update_metrics(
                            ws_qps=ws_qps,
                            pipeline_qps=pipeline_qps,
                            staging_count=_fresh_staging,
                            last_recv=last_text,
                        )
                    except Exception as exc:
                        logger.debug("[StatusWidget] 대시보드 지표 갱신 실패: %s", exc)
                except Exception:
                    pass

                try:
                    if hasattr(_tab_dashboard, "update_pipeline_labels"):
                        try:
                            _tab_dashboard.update_pipeline_labels(
                                staging=_stats.get("staging", 0),
                                candles=_stats.get("candles", 0),
                                isolated=_stats.get("isolated", 0),
                                gap_count=_gap if isinstance(_gap, int) else 0,
                                isolated_recent=_stats.get("isolated_recent", 0),
                            )
                        except Exception as exc:
                            logger.debug("[StatusWidget] 대시보드 파이프라인 레이블 갱신 실패: %s", exc)
                    if getattr(self, "_metrics_updater", None) is not None:
                        try:
                            self._metrics_updater.set_staging_count(_stats.get("staging", 0))
                        except Exception as exc:
                            logger.debug("[StatusWidget] staging_count 갱신 실패: %s", exc)
                except Exception as exc:
                    logger.debug("[StatusWidget] 대시보드 파이프라인 레이블 갱신 실패: %s", exc)

                try:
                    from ..utils import get_cache_stats
                    _cache = get_cache_stats()
                    _now_str = datetime.now().strftime("%H:%M:%S")
                    if hasattr(_tab_dashboard, "update_cache_labels"):
                        try:
                            _tab_dashboard.update_cache_labels(
                                l1_count=_cache.get("l1_count", 0),
                                pubsub_channels=_cache.get("pubsub_channels", 0),
                                last_update=_now_str,
                            )
                        except Exception as exc:
                            logger.debug("[StatusWidget] 캐시 레이블 갱신 실패: %s", exc)
                except Exception as exc:
                    logger.debug("[StatusWidget] 캐시 레이블 갱신 실패: %s", exc)

            # ── WebSocket 탭 갱신 ─────────────────────────────────────
            if _tab_websocket is not None:
                try:
                    if hasattr(_tab_websocket, "update_metrics"):
                        _tab_websocket.update_metrics(
                            ws_qps=ws_qps,
                            total_recv=staging_count,
                            delta_ratio=0.0,
                        )
                except Exception as exc:
                    logger.debug("[StatusWidget] Tab 2 갱신 실패: %s", exc)

            # ── DataFlow 탭 갱신 ──────────────────────────────────────
            if _tab_dataflow is not None:
                try:
                    # 대시보드 탭에서 이미 조회한 _stats가 있으면 재사용, 없으면 새로 조회
                    if not _stats:
                        from ..utils import get_pipeline_stats
                        try:
                            _stats = get_pipeline_stats()
                        except Exception:
                            _stats = {}
                    if hasattr(_tab_dataflow, "update_pipeline_status"):
                        try:
                            _tab_dataflow.update_pipeline_status(_stats)
                        except Exception as exc:
                            logger.debug("[StatusWidget] Tab 3 갱신 실패: %s", exc)
                except Exception as exc:
                    logger.debug("[StatusWidget] Tab 3 갱신 실패: %s", exc)

            # ── 에러/Gap 탭 갱신 ─────────────────────────────────────
            if _tab_error is not None:
                try:
                    if hasattr(_tab_error, "refresh_errors"):
                        _tab_error.refresh_errors()
                except Exception as exc:
                    logger.debug("[StatusWidget] Tab 5 갱신 실패: %s", exc)

            if _tab_gap is not None:
                try:
                    if hasattr(_tab_gap, "refresh_gap_queue"):
                        _tab_gap.refresh_gap_queue()
                except Exception as exc:
                    logger.debug("[StatusWidget] Tab 4 갱신 실패: %s", exc)

            # ── 실시간 데이터 플로우 상태 업데이트 ───────────────────
            try:
                has_ws_manager = (
                    getattr(self, "_ws_manager_ref", None) is not None
                )

                # 마지막 성공한 candles 건수 캐싱 — DB 조회 실패 시에도 "처리 완료" 유지
                _raw_candles = _stats.get("candles", 0) if isinstance(_stats, dict) else 0
                if _raw_candles > 0:
                    self._last_candles_total = _raw_candles
                _candles_total = _raw_candles or getattr(self, "_last_candles_total", 0)

                # WebSocket 상태
                if ws_qps > 0:
                    ws_status = f"수신 {ws_qps}건/초"
                elif has_ws_manager:
                    ws_status = "연결됨 (수신 대기)"
                else:
                    ws_status = "WebSocket 미연결"

                # Pipeline 상태
                if pipeline_qps > 0:
                    pipeline_status = f"처리 {pipeline_qps}건/초"
                elif staging_count > 0:
                    pipeline_status = f"처리 대기 (staging {staging_count}건)"
                elif _candles_total > 0:
                    pipeline_status = f"처리 완료 (누적 {_candles_total:,}건)"
                else:
                    pipeline_status = "파이프라인 대기"

                # DB 저장 상태
                if staging_count > 0:
                    db_status = f"저장 {staging_count}건"
                elif _candles_total > 0:
                    db_status = f"저장 완료 (누적 {_candles_total:,}건)"
                else:
                    db_status = "DB 저장 대기"

                # UI 갱신 — 항상 현재 시각 표시
                ui_status = f"갱신 {datetime.now().strftime('%H:%M:%S')}"

                self.update_flow_status("websocket", ws_status)
                self.update_flow_status("pipeline", pipeline_status)
                self.update_flow_status("db", db_status)
                self.update_flow_status("ui", ui_status)

            except Exception as exc:
                logger.debug("[StatusWidget] 플로우 레이블 갱신 실패: %s", exc)

            # ── 통신 테이블: staging 변화 시 DB 저장 행 추가 ─────────
            try:
                prev_staging = getattr(self, "_prev_staging_count", 0)
                if staging_count > 0 and staging_count != prev_staging:
                    delta = staging_count - prev_staging
                    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    if delta > 0:
                        self.add_comm_row(
                            now_str,
                            "DB저장",
                            "staging",
                            f"누적 {staging_count}건 (+{delta}건)",
                            "-",
                        )
                self._prev_staging_count = staging_count
            except Exception as exc:
                logger.debug("[StatusWidget] 통신 테이블 DB 행 추가 실패: %s", exc)

        # ------------------------------------------------------------------
        # WebSocket 시작 알림
        # ------------------------------------------------------------------

        @pyqtSlot(int, int)
        def _on_websocket_started(self, started: int, total: int) -> None:
            """WebSocket 시작 알림.

            Args:
                started: 시작된 WebSocket 수
                total: 전체 WebSocket 수
            """
            logger.info("[StatusWidget] WebSocket 시작: %d/%d 심볼", started, total)
            try:
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.add_comm_row(
                    now_str, "WS시작", f"{started}/{total}", f"WebSocket {started}개 시작", "-"
                )
                self.update_flow_status("websocket", f"시작됨 ({started}/{total} 심볼)")
            except Exception as exc:
                logger.debug("[StatusWidget] WebSocket 시작 알림 표시 실패: %s", exc)

        # ------------------------------------------------------------------
        # WebSocket 메시지 수신 콜백
        # ------------------------------------------------------------------

        @pyqtSlot(str, str, str, str)
        def _ws_callback_slot(
            self, time_str: str, kind: str, symbol: str, data: str
        ) -> None:
            """WebSocket 메시지 수신 시 UI 갱신 (메인 스레드).

            통신 테이블 행 삽입은 200ms 간격으로 쓰로틀링하여 고빈도 메시지 시 UI 렉을 방지합니다.
            MetricsUpdater 카운트는 쓰로틀링 없이 매 메시지마다 기록합니다.

            Args:
                time_str: 수신 시각 문자열
                kind: 메시지 종류
                symbol: 심볼 코드
                data: 메시지 데이터
            """
            try:
                if getattr(self, "_metrics_updater", None) is not None:
                    try:
                        self._metrics_updater.record_ws_event(symbol)
                    except Exception:
                        pass
                self.update_flow_status("websocket", f"수신 중... ({symbol})")
                # 200ms 쓰로틀: 마지막 테이블 삽입 후 200ms 이상 경과한 경우에만 행 추가
                now_ms = _perf_time.perf_counter() * 1000
                last_ws_row_ms = getattr(self, "_last_ws_row_ms", 0.0)
                if now_ms - last_ws_row_ms >= 200.0:
                    self._last_ws_row_ms = now_ms
                    self.add_comm_row(time_str, kind, symbol, data, "-")
            except Exception as exc:
                logger.debug("[StatusWidget] WebSocket 콜백 슬롯 실패: %s", exc)

        # ------------------------------------------------------------------
        # Pipeline 처리 완료 콜백
        # ------------------------------------------------------------------

        @pyqtSlot(str, str)
        def _pipeline_callback_slot(self, time_str: str, symbol: str) -> None:
            """Pipeline 처리 완료 시 UI 갱신 (메인 스레드).

            통신 테이블 행 삽입은 300ms 간격으로 쓰로틀링합니다.

            Args:
                time_str: 처리 완료 시각 문자열
                symbol: 처리된 심볼 코드
            """
            try:
                self.update_flow_status("pipeline", f"처리 중... ({symbol})")
                now_ms = _perf_time.perf_counter() * 1000
                last_pl_row_ms = getattr(self, "_last_pl_row_ms", 0.0)
                if now_ms - last_pl_row_ms >= 300.0:
                    self._last_pl_row_ms = now_ms
                    self.add_comm_row(time_str, "Pipeline", symbol, "처리 완료", "-")
            except Exception as exc:
                logger.debug("[StatusWidget] Pipeline 콜백 슬롯 실패: %s", exc)

        # ------------------------------------------------------------------
        # 새로고침 버튼 핸들러
        # ------------------------------------------------------------------

        def _on_refresh_clicked(self) -> None:
            """새로고침 버튼 클릭 처리."""
            try:
                if getattr(self, "_health_checker", None) is not None:
                    try:
                        self._health_checker.run_check()
                    except Exception:
                        pass
                # ws_manager 재탐색 시도
                if getattr(self, "_ws_manager_ref", None) is None:
                    ws_manager = self._find_ws_manager_in_modules()
                    if ws_manager is not None:
                        self._ws_manager_ref = ws_manager
                        logger.info("[StatusWidget] ✅ 새로고침 시 WebSocket Manager 발견")
            except Exception as exc:
                logger.debug("[StatusWidget] 새로고침 처리 실패: %s", exc)

else:
    class SignalHandlersMixin:  # type: ignore[no-redef]
        """PyQt5 미설치 시 사용하는 더미 SignalHandlersMixin."""

        def _on_health_updated(self, health: dict) -> None:
            pass

        def _on_metrics_updated(
            self, ws_qps: int, pipeline_qps: int, staging_count: int, last_text: str
        ) -> None:
            pass

        def _on_websocket_started(self, started: int, total: int) -> None:
            pass

        def _ws_callback_slot(
            self, time_str: str, kind: str, symbol: str, data: str
        ) -> None:
            pass

        def _pipeline_callback_slot(self, time_str: str, symbol: str) -> None:
            pass

        def _on_refresh_clicked(self) -> None:
            pass