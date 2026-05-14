#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
[Purpose]
4단계 - 정합성/검증 (validate_candle_advanced)

�� 파일은 기존 CandleValidator 구현을 보존하면서 다음을 추가/개선합니다:
- stager.py 등에서 기대하는 함수형 인터페이스 `validate_candle_advanced(candle_dict)` 제공
- dict 입력을 CandleData로 안전히 파싱하는 유틸 제공
- numpy/scipy 미설치 환경에서 동작 가능한 대체 로직 포함
- 로깅, 예외 처리 강화, 임계값을 환경변수로 설정 가능
- 모듈 수준 __all__ 정의
"""
from __future__ import annotations

import asyncio
import os
import logging
from typing import List, Dict, Any, Optional, Tuple, Union
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

# 조건부 임포트 (optional)
try:
    import numpy as np  # type: ignore
    NUMPY_AVAILABLE = True
except Exception:
    np = None  # type: ignore
    NUMPY_AVAILABLE = False

try:
    from scipy import stats  # type: ignore
    SCIPY_AVAILABLE = True
except Exception:
    stats = None  # type: ignore
    SCIPY_AVAILABLE = False

LOG = logging.getLogger("data.validator")
LOG.setLevel(os.getenv("VALIDATOR_LOG_LEVEL", "INFO"))

# 환경 변수로 임계값 조정 가능
DEFAULT_ZSCORE_THRESHOLD = float(os.getenv("VALIDATOR_ZSCORE", "3.0"))


# ============================================================
# 데이터 클래스
# ============================================================
@dataclass
class ValidationResult:
    """검증 결과"""
    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CandleData:
    """캔들 데이터 (검증용)"""
    symbol: str
    timeframe: str
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    seq: Optional[int] = None

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CandleData":
        """
        안전한 변환: 다양한 Upbit 필드 이름 지원
        기대 입력 예: dict with keys (time, open/opening_price, high/high_price, low/low_price,
        close/trade_price, volume/candle_acc_trade_volume, symbol, timeframe, seq/timestamp)
        """
        # time parsing: if it's already datetime, keep; otherwise attempt fromisoformat
        t = d.get("time") or d.get("candle_date_time_utc") or d.get("candle_date_time_kst")
        if isinstance(t, str):
            # Accept ISO-like strings
            try:
                # replace Z with +00:00 for fromisoformat stability
                t = datetime.fromisoformat(t.replace("Z", "+00:00"))
            except Exception:
                # last resort: now
                t = datetime.now(timezone.utc)
        if t is None:
            t = datetime.now(timezone.utc)

        def _f(*keys, default=0.0):
            for k in keys:
                if k in d and d[k] is not None:
                    try:
                        return float(d[k])
                    except Exception:
                        try:
                            return float(str(d[k]).replace(",", ""))
                        except Exception:
                            return default
            return default

        open_p = _f("open", "opening_price")
        high_p = _f("high", "high_price")
        low_p = _f("low", "low_price")
        close_p = _f("close", "trade_price", "trade_price")
        volume = _f("volume", "candle_acc_trade_volume", "candle_acc_trade_volume_24h")
        seq = d.get("seq") or d.get("timestamp") or d.get("id")
        try:
            seq = int(seq) if seq is not None else None
        except Exception:
            seq = None

        symbol = d.get("symbol") or d.get("market") or "UNKNOWN"
        timeframe = d.get("timeframe") or d.get("unit") or "1m"

        return cls(
            symbol=str(symbol),
            timeframe=str(timeframe),
            time=t,
            open=open_p,
            high=high_p,
            low=low_p,
            close=close_p,
            volume=volume,
            seq=seq,
        )


# ============================================================
# CandleValidator 클래스 (개선판)
# ============================================================
class CandleValidator:
    """캔들 데이터 검증기 (4단계)"""

    def __init__(self, zscore_threshold: float = DEFAULT_ZSCORE_THRESHOLD):
        self.zscore_threshold = float(zscore_threshold)
        self.stats = {"validated": 0, "passed": 0, "failed": 0, "warnings": 0}

    # --------------------------------------------------------
    # 기본 검증 (OHLC 논리)
    # --------------------------------------------------------
    def validate_ohlc(self, candle: CandleData) -> ValidationResult:
        errors: List[str] = []
        warnings: List[str] = []

        # Null/NaN guard
        try:
            o, h, l, c, v = float(candle.open), float(candle.high), float(candle.low), float(candle.close), float(
                candle.volume
            )
        except Exception as e:
            LOG.debug("parse error in validate_ohlc: %s", e)
            return ValidationResult(valid=False, errors=[f"parse_error:{e}"], warnings=[])

        if h < l:
            errors.append(f"high ({h}) < low ({l})")
        if h < o:
            errors.append(f"high ({h}) < open ({o})")
        if h < c:
            errors.append(f"high ({h}) < close ({c})")
        if l > o:
            errors.append(f"low ({l}) > open ({o})")
        if l > c:
            errors.append(f"low ({l}) > close ({c})")
        if v < 0:
            errors.append(f"volume ({v}) < 0")
        if v == 0:
            warnings.append("volume is zero")
        if o <= 0 or h <= 0 or l <= 0 or c <= 0:
            errors.append("price values must be positive")

        vr = ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            metadata={"symbol": candle.symbol, "time": candle.time, "ohlc": (o, h, l, c)},
        )
        return vr

    # --------------------------------------------------------
    # AI 이상치 감지 (Z-Score) - numpy/scipy 있으면 사용
    # --------------------------------------------------------
    def detect_outliers(self, candles: List[CandleData]) -> Dict[int, ValidationResult]:
        outliers: Dict[int, ValidationResult] = {}

        if not candles:
            return outliers

        closes = []
        vols = []
        for c in candles:
            try:
                closes.append(float(c.close))
                vols.append(float(c.volume))
            except Exception:
                closes.append(0.0)
                vols.append(0.0)

        try:
            if NUMPY_AVAILABLE and SCIPY_AVAILABLE:
                # use scipy.stats.zscore for robustness
                close_z = stats.zscore(np.array(closes), nan_policy="omit")
                vol_z = stats.zscore(np.array(vols), nan_policy="omit")
                # ensure same length lists
                for idx, (cz, vz) in enumerate(zip(close_z, vol_z)):
                    warn: List[str] = []
                    if abs(cz) > self.zscore_threshold:
                        warn.append(f"close_zscore:{float(cz):.2f}")
                    if abs(vz) > self.zscore_threshold:
                        warn.append(f"volume_zscore:{float(vz):.2f}")
                    if warn:
                        outliers[idx] = ValidationResult(valid=True, errors=[], warnings=warn, metadata={"index": idx})
            else:
                # Fallback: simple std-based zscore without scipy
                if len(closes) >= 2:
                    mean_c = sum(closes) / len(closes)
                    mean_v = sum(vols) / len(vols)
                    std_c = (sum((x - mean_c) ** 2 for x in closes) / len(closes)) ** 0.5
                    std_v = (sum((x - mean_v) ** 2 for x in vols) / len(vols)) ** 0.5
                    for idx, (x, y) in enumerate(zip(closes, vols)):
                        cz = (x - mean_c) / (std_c or 1.0)
                        vz = (y - mean_v) / (std_v or 1.0)
                        warn: List[str] = []
                        if abs(cz) > self.zscore_threshold:
                            warn.append(f"close_zscore:{float(cz):.2f}")
                        if abs(vz) > self.zscore_threshold:
                            warn.append(f"volume_zscore:{float(vz):.2f}")
                        if warn:
                            outliers[idx] = ValidationResult(valid=True, errors=[], warnings=warn, metadata={"index": idx})
        except Exception as e:
            LOG.warning("outlier detection failed: %s", e)

        return outliers

    # --------------------------------------------------------
    # Gap 감지
    # --------------------------------------------------------
    def detect_gaps(self, candles: List[CandleData], timeframe: str = "1m") -> List[Tuple[datetime, datetime]]:
        if len(candles) < 2:
            return []
        tf_seconds = self._parse_timeframe_seconds(timeframe)
        gap_threshold = tf_seconds * 2
        gaps: List[Tuple[datetime, datetime]] = []
        for i in range(1, len(candles)):
            prev_t = candles[i - 1].time
            curr_t = candles[i].time
            gap_seconds = (curr_t - prev_t).total_seconds()
            if gap_seconds > gap_threshold:
                gaps.append((prev_t, curr_t))
        return gaps

    def _parse_timeframe_seconds(self, timeframe: str) -> int:
        tf_map = {
            "1s": 1,
            "5s": 5,
            "10s": 10,
            "30s": 30,
            "1m": 60,
            "3m": 180,
            "5m": 300,
            "15m": 900,
            "30m": 1800,
            "1h": 3600,
            "4h": 14400,
            "12h": 43200,
            "1d": 86400,
            "1w": 604800,
        }
        return tf_map.get(timeframe, 60)

    # --------------------------------------------------------
    # Seq 연속성 검증
    # --------------------------------------------------------
    def validate_seq_continuity(self, candles: List[CandleData]) -> ValidationResult:
        if len(candles) < 2:
            return ValidationResult(valid=True)
        seqs = [c.seq for c in candles if c.seq is not None]
        if not seqs:
            return ValidationResult(valid=True, warnings=["no seq values"])
        errors: List[str] = []
        for i in range(1, len(seqs)):
            if seqs[i] <= seqs[i - 1]:
                errors.append(f"seq not monotonic: {seqs[i-1]} -> {seqs[i]}")
        return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=[])

    # --------------------------------------------------------
    # 통합 검증
    # --------------------------------------------------------
    async def validate_candles(
        self,
        candles: List[CandleData],
        check_outliers: bool = True,
        check_gaps: bool = True,
        check_seq: bool = True,
    ) -> Dict[str, Any]:
        self.stats["validated"] += len(candles)

        # OHLC checks in parallel threads
        ohlc_results = await asyncio.gather(
            *[asyncio.to_thread(self.validate_ohlc, c) for c in candles]
        )

        outliers = {}
        if check_outliers:
            outliers = await asyncio.to_thread(self.detect_outliers, candles)

        gaps = []
        if check_gaps and candles:
            gaps = await asyncio.to_thread(self.detect_gaps, candles, candles[0].timeframe)

        seq_result = ValidationResult(valid=True)
        if check_seq:
            seq_result = await asyncio.to_thread(self.validate_seq_continuity, candles)

        failed_indices = [i for i, r in enumerate(ohlc_results) if not r.valid]
        warning_indices = [i for i, r in enumerate(ohlc_results) if r.warnings]

        self.stats["passed"] += len(candles) - len(failed_indices)
        self.stats["failed"] += len(failed_indices)
        self.stats["warnings"] += len(warning_indices)

        return {
            "summary": {
                "total": len(candles),
                "passed": len(candles) - len(failed_indices),
                "failed": len(failed_indices),
                "warnings": len(warning_indices),
                "outliers": len(outliers),
                "gaps": len(gaps),
            },
            "failed_candles": [
                {"index": i, "candle": candles[i], "result": ohlc_results[i]} for i in failed_indices
            ],
            "warnings": [
                {"index": i, "candle": candles[i], "warnings": ohlc_results[i].warnings}
                for i in warning_indices
            ],
            "outliers": [{"index": i, "candle": candles[i], "result": result} for i, result in outliers.items()],
            "gaps": gaps,
            "seq_validation": seq_result,
        }

    def get_stats(self) -> Dict[str, int]:
        return dict(self.stats)


# ============================================================
# 호환 함수: stager에서 직접 호출 가능한 단일-캔들 검증기
# ============================================================
def validate_candle_advanced(candle: Union[Dict[str, Any], CandleData]) -> ValidationResult:
    """
    stager.py 등에서 기대하는 동기 함수형 인터페이스 호환성 제공.
    입력: dict 또는 CandleData
    반환: ValidationResult
    """
    try:
        if isinstance(candle, CandleData):
            cd = candle
        else:
            cd = CandleData.from_dict(candle)  # type: ignore
        validator = CandleValidator()
        return validator.validate_ohlc(cd)
    except Exception as e:
        LOG.exception("validate_candle_advanced failed: %s", e)
        return ValidationResult(valid=False, errors=[f"exception:{e}"], warnings=[])


# ============================================================
# 유틸: dict 리스트를 받아 배치 검증(비동기 실행용)
# ============================================================
async def validate_candles_from_dicts(
    candle_dicts: List[Dict[str, Any]],
    zscore_threshold: Optional[float] = None,
) -> Dict[str, Any]:
    """
    dict list -> CandleData list 변환 후 CandleValidator.validate_candles 실행
    """
    cd_list = [CandleData.from_dict(d) for d in candle_dicts]
    validator = CandleValidator(zscore_threshold=zscore_threshold or DEFAULT_ZSCORE_THRESHOLD)
    return await validator.validate_candles(cd_list)


# ============================================================
# 간단한 CLI/테스트 엔트리 (원본 내용 유지, 개선)
# ============================================================
async def _main_test():
    logging.basicConfig(level=logging.INFO)
    validator = CandleValidator(zscore_threshold=DEFAULT_ZSCORE_THRESHOLD)

    # 샘플 생성
    test_candles = [
        CandleData(
            symbol="KRW-BTC",
            timeframe="1m",
            time=datetime(2026, 2, 20, 10, i),
            open=50000000 + i * 1000,
            high=50001000 + i * 1000,
            low=49999000 + i * 1000,
            close=50000500 + i * 1000,
            volume=100.5 + i,
            seq=1000 + i,
        )
        for i in range(20)
    ]

    # 이상 추가
    test_candles.append(
        CandleData(
            symbol="KRW-BTC",
            timeframe="1m",
            time=datetime(2026, 2, 20, 10, 25),
            open=50000000,
            high=49999000,
            low=50001000,
            close=50000500,
            volume=100.5,
            seq=1025,
        )
    )

    result = await validator.validate_candles(test_candles, check_outliers=True, check_gaps=True, check_seq=True)

    print("\n✅ 4단계 - 검증 결과:")
    print(f"  총 캔들: {result['summary']['total']}개")
    print(f"  통과: {result['summary']['passed']}개")
    print(f"  실패: {result['summary']['failed']}개")
    print(f"  경고: {result['summary']['warnings']}개")
    print(f"  이상치: {result['summary']['outliers']}개")
    print(f"  Gap: {result['summary']['gaps']}개")

    if result["failed_candles"]:
        print("\n❌ 실패한 캔들:")
        for item in result["failed_candles"]:
            print(f"  - Index {item['index']}: {item['result'].errors}")

    stats = validator.get_stats()
    print("\n📊 검증 통계:")
    print(f"  총 검증: {stats['validated']}개")
    print(f"  통과: {stats['passed']}개")
    print(f"  실패: {stats['failed']}개")


if __name__ == "__main__":
    asyncio.run(_main_test())


# Public exports
__all__ = [
    "ValidationResult",
    "CandleData",
    "CandleValidator",
    "validate_candle_advanced",
    "validate_candles_from_dicts",
]