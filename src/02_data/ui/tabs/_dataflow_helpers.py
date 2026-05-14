# -*- coding: utf-8 -*-
"""
DataFlow 헬퍼 클래스 (_dataflow_helpers.py)

DataFlowTab의 파이프라인 단계별 갱신 로직을 담당하는
순수 로직 헬퍼 클래스를 제공합니다.

CHANGELOG:
    v6.0 (2026-04-28) | Copilot | dataflow_tab.py 헬퍼 분리
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PyQt5.QtWidgets import QWidget

logger = logging.getLogger(__name__)

# ============================================================
# 상수
# ============================================================
_COLLECTION_PROGRESS_MAX: int = 1000  # 프로그레스바 최대값 (수집 건수 기준)
_MONGO_DB_NAME: str = "upbit_trader"  # MongoDB 데이터베이스명


class DataFlowStepUpdater:
    """DataFlowTab 파이프라인 단계별 갱신 헬퍼.

    QWidget을 상속하지 않는 순수 로직 클래스입니다.
    각 step 메서드는 tab_widget 인자를 통해 위젯을 갱신합니다.

    사용 예::

        updater = DataFlowStepUpdater()
        updater.update_all(self, stats)
    """

    def update_all(self, tab: "QWidget", stats: dict) -> None:
        """파이프라인 단계별 상태를 모두 갱신합니다.

        Args:
            tab: 갱신할 DataFlowTab 인스턴스
            stats: {"staging": int, "candles": int, "isolated": int} 형태의 통계 dict

        Raises:
            Exception: 전체 실패 시 에러 로그 출력
        """
        try:
            if not isinstance(stats, dict):
                logger.warning("[DataFlowTab] ⚠️ stats가 dict가 아님: %s", type(stats))
                return

            staging = int(stats.get("staging", 0))
            candles = int(stats.get("candles", 0))
            isolated = int(stats.get("isolated", 0))

            logger.info(
                "[DataFlowTab] 📊 Pipeline Stats 수신: staging=%d, candles=%d, isolated=%d",
                staging, candles, isolated
            )

            self.update_step1_collection(tab, staging, candles)
            self.update_step2_validation(tab, candles, isolated)
            self.update_step3_storage(tab, staging)
            self.update_final_status(tab, candles)

            logger.info(
                "[DataFlowTab] 🎉 Pipeline 상태 갱신 완료 (staging=%d, candles=%d, isolated=%d)",
                staging, candles, isolated
            )

        except Exception as exc:
            logger.error(
                "[DataFlowTab] ❌ update_all 전체 실패: %s",
                exc, exc_info=True
            )

    def update_step1_collection(self, tab: "QWidget", staging: int, candles: int) -> None:
        """Step 1: 데이터 수집 (WebSocket/REST) 갱신.

        Args:
            tab: 갱신할 DataFlowTab 인스턴스
            staging: Staging 테이블 건수
            candles: Candles 테이블 건수
        """
        try:
            total = staging + candles

            if hasattr(tab, "label_collect_count"):
                tab.label_collect_count.setText(f"수집 건수: {total:,}")
                logger.debug("[DataFlowTab] ✅ label_collect_count: %d", total)
            else:
                logger.warning("[DataFlowTab] ⚠️ label_collect_count 위젯 없음")

            if hasattr(tab, "progress_collect"):
                pct = min(100, int(total * 100 // _COLLECTION_PROGRESS_MAX)) if total > 0 else 0
                tab.progress_collect.setValue(pct)
                logger.debug("[DataFlowTab] ✅ progress_collect: %d%%", pct)
            else:
                logger.warning("[DataFlowTab] ⚠️ progress_collect 위젯 없음")

        except Exception as exc:
            logger.error("[DataFlowTab] ❌ Step 1 갱신 실패: %s", exc)

    def update_step2_validation(self, tab: "QWidget", candles: int, isolated: int) -> None:
        """Step 2: 데이터 검증 (Pipeline) 갱신.

        Args:
            tab: 갱신할 DataFlowTab 인스턴스
            candles: 정상 Candles 건수
            isolated: 격리 건수
        """
        try:
            if hasattr(tab, "label_valid_ok"):
                tab.label_valid_ok.setText(f"[OK] 정상: {candles:,} 건")
                logger.debug("[DataFlowTab] ✅ label_valid_ok: %d", candles)
            else:
                logger.warning("[DataFlowTab] ⚠️ label_valid_ok 위젯 없음")

            if hasattr(tab, "label_valid_isolated"):
                tab.label_valid_isolated.setText(f"[격리] {isolated:,} 건 (클릭하여 상세보기)")
                tab.label_valid_isolated.setToolTip(
                    "🔍 클릭하면 격리 데이터 상세 분석 창이 열립니다\n"
                    f"현재 격리 건수: {isolated:,} 건"
                )
                logger.debug("[DataFlowTab] ✅ label_valid_isolated: %d", isolated)
            else:
                logger.warning("[DataFlowTab] ⚠️ label_valid_isolated 위젯 없음")

        except Exception as exc:
            logger.error("[DataFlowTab] ❌ Step 2 갱신 실패: %s", exc)

    def update_step3_storage(self, tab: "QWidget", staging: int) -> None:
        """Step 3: 데이터 저장 (Staging → Candles) 갱신.

        Args:
            tab: 갱신할 DataFlowTab 인스턴스
            staging: Staging 테이블 건수
        """
        try:
            if hasattr(tab, "label_step3_staging"):
                tab.label_step3_staging.setText(f"Staging: {staging:,} 건")
                logger.debug("[DataFlowTab] ✅ label_step3_staging: %d", staging)
            else:
                logger.warning("[DataFlowTab] ⚠️ label_step3_staging 위젯 없음")

            if hasattr(tab, "label_step3_gap"):
                try:
                    from ..utils import get_gap_queue_size
                    gap_count = get_gap_queue_size()
                    tab.label_step3_gap.setText(f"Gap 큐: {gap_count:,} 건")
                    logger.debug("[DataFlowTab] ✅ label_step3_gap: %d", gap_count)
                except ImportError:
                    tab.label_step3_gap.setText("Gap 큐: -- 건")
                    logger.warning("[DataFlowTab] ⚠️ get_gap_queue_size 함수 없음")
                except Exception as gap_exc:
                    tab.label_step3_gap.setText("Gap 큐: -- 건")
                    logger.debug("[DataFlowTab] Gap 큐 조회 실패: %s", gap_exc)
            else:
                logger.warning("[DataFlowTab] ⚠️ label_step3_gap 위젯 없음")

        except Exception as exc:
            logger.error("[DataFlowTab] ❌ Step 3 갱신 실패: %s", exc)

    def update_final_status(self, tab: "QWidget", candles: int) -> None:
        """최종 데이터 현황 (TimescaleDB, Redis, MongoDB) 갱신.

        Args:
            tab: 갱신할 DataFlowTab 인스턴스
            candles: Candles 테이블 건수
        """
        try:
            self._update_timescale_count(tab, candles)
            self._update_redis_count(tab)
            self._update_mongodb_count(tab)
        except Exception as exc:
            logger.error("[DataFlowTab] ❌ 최종 현황 갱신 실패: %s", exc)

    def _update_timescale_count(self, tab: "QWidget", candles: int) -> None:
        """TimescaleDB 총 건수 레이블 갱신.

        Args:
            tab: 갱신할 DataFlowTab 인스턴스
            candles: TimescaleDB에 저장된 총 건수
        """
        try:
            if hasattr(tab, "label_timescale_total"):
                tab.label_timescale_total.setText(f"TimescaleDB 총 건수: {candles:,}")
                logger.debug("[DataFlowTab] ✅ label_timescale_total: %d", candles)
            else:
                logger.warning("[DataFlowTab] ⚠️ label_timescale_total 위젯 없음")
        except Exception as exc:
            logger.error("[DataFlowTab] ❌ TimescaleDB 갱신 실패: %s", exc)

    def _update_redis_count(self, tab: "QWidget") -> None:
        """Redis 총 키 수 레이블 갱신.

        Args:
            tab: 갱신할 DataFlowTab 인스턴스
        """
        try:
            if hasattr(tab, "label_redis_count"):
                try:
                    from ..utils import get_redis_connector
                    rc = get_redis_connector()
                    if rc is not None:
                        redis_keys = rc.dbsize()
                        tab.label_redis_count.setText(f"Redis 총 건수: {redis_keys:,} 키")
                        logger.debug("[DataFlowTab] ✅ label_redis_count: %d", redis_keys)
                    else:
                        tab.label_redis_count.setText("Redis 총 건수: -- 키")
                        logger.warning("[DataFlowTab] ⚠️ Redis 커넥터 없음")
                except ImportError:
                    tab.label_redis_count.setText("Redis 총 건수: -- 키")
                    logger.warning("[DataFlowTab] ⚠️ get_redis_connector 함수 없음")
                except Exception as redis_exc:
                    tab.label_redis_count.setText("Redis 총 건수: -- 키")
                    logger.debug("[DataFlowTab] Redis dbsize 조회 실패: %s", redis_exc)
            else:
                logger.warning("[DataFlowTab] ⚠️ label_redis_count 위젯 없음")
        except Exception as exc:
            logger.error("[DataFlowTab] ❌ Redis 갱신 실패: %s", exc)

    def _update_mongodb_count(self, tab: "QWidget") -> None:
        """MongoDB 총 문서 수 레이블 갱신.

        Args:
            tab: 갱신할 DataFlowTab 인스턴스
        """
        try:
            if hasattr(tab, "label_mongodb_count"):
                try:
                    from ..utils import get_mongo_sync_client
                    client = get_mongo_sync_client()
                    if client is not None:
                        db = client.get_database(_MONGO_DB_NAME)
                        mongo_count = db.metadata.estimated_document_count()
                        tab.label_mongodb_count.setText(f"MongoDB 총 건수: {mongo_count:,} 문서")
                        logger.debug("[DataFlowTab] ✅ label_mongodb_count: %d", mongo_count)
                    else:
                        tab.label_mongodb_count.setText("MongoDB 총 건수: -- 문서")
                        logger.warning("[DataFlowTab] ⚠️ MongoDB 클라이언트 없음")
                except ImportError:
                    tab.label_mongodb_count.setText("MongoDB 총 건수: -- 문서")
                    logger.warning("[DataFlowTab] ⚠️ get_mongo_sync_client 함수 없음")
                except Exception as mongo_exc:
                    tab.label_mongodb_count.setText("MongoDB 총 건수: -- 문서")
                    logger.debug("[DataFlowTab] MongoDB count 조회 실패: %s", mongo_exc)
            else:
                logger.warning("[DataFlowTab] ⚠️ label_mongodb_count 위젯 없음")
        except Exception as exc:
            logger.error("[DataFlowTab] ❌ MongoDB 갱신 실패: %s", exc)
