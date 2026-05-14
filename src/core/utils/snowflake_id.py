"""
Snowflake ID 생성기 (트위터 알고리즘)

구조 (64비트):
  - 1 bit:  부호 (항상 0)
  - 41 bits: 타임스탬프 (밀리초, epoch 기준)
  - 10 bits: 워커 ID (datacenter_id 5bit + worker_id 5bit)
  - 12 bits: 시퀀스 번호 (동일 밀리초 내 4096개 ID 생성 가능)

사용법:
    from _core.utils.snowflake_id import id_generator, get_next_id
    new_id = id_generator.generate()        # 기존 API
    new_id = get_next_id()                  # 글로벌 싱글톤 API

환경 변수:
    WORKER_ID (int, 기본값 0): 분산 환경에서 워커 식별자 (0~1023)
"""
import time
import threading
import os


class SnowflakeIDGenerator:
    """
    Twitter Snowflake 알고리즘 기반 64비트 분산 ID 생성기

    호출 방식 두 가지를 모두 지원합니다:
    - 단일 인자: SnowflakeIDGenerator(combined_worker_id)   ← 기존 10비트 API
    - 이중 인자: SnowflakeIDGenerator(datacenter_id, worker_id)  ← v9.0 API
    """

    EPOCH = 1609459200000  # 2021-01-01 00:00:00 UTC

    # 비트 레이아웃
    DATACENTER_ID_BITS = 5
    WORKER_ID_BITS = 5
    SEQUENCE_BITS = 12

    MAX_DATACENTER_ID = (1 << DATACENTER_ID_BITS) - 1   # 31
    MAX_WORKER_ID = (1 << WORKER_ID_BITS) - 1            # 31
    MAX_SEQUENCE = (1 << SEQUENCE_BITS) - 1              # 4095

    # 시프트 오프셋
    WORKER_ID_SHIFT = SEQUENCE_BITS                                         # 12
    DATACENTER_ID_SHIFT = SEQUENCE_BITS + WORKER_ID_BITS                   # 17
    TIMESTAMP_SHIFT = SEQUENCE_BITS + WORKER_ID_BITS + DATACENTER_ID_BITS  # 22

    def __init__(self, datacenter_id: int, worker_id: int = None,
                 epoch: int = None):
        """
        Parameters
        ----------
        datacenter_id : int
            단일 인자 방식: 전체 combined worker_id (0~1023, 기존 API).
            이중 인자 방식: datacenter_id (0~31).
        worker_id : int, optional
            이중 인자 방식일 때만 사용. worker_id (0~31).
        epoch : int, optional
            커스텀 epoch (밀리초). 기본값 2021-01-01 UTC.
        """
        if worker_id is None:
            # 단일 인자 방식 — 기존 호환 (10비트 combined worker_id)
            combined = datacenter_id
            max_combined = (1 << (self.DATACENTER_ID_BITS + self.WORKER_ID_BITS)) - 1
            if not 0 <= combined <= max_combined:
                raise ValueError(f"워커ID는 0~{max_combined} 사이여야 합니다")
            self.datacenter_id = (combined >> self.WORKER_ID_BITS) & self.MAX_DATACENTER_ID
            self.worker_id = combined & self.MAX_WORKER_ID
        else:
            # 이중 인자 방식
            if not 0 <= datacenter_id <= self.MAX_DATACENTER_ID:
                raise ValueError(f"datacenter_id must be between 0 and {self.MAX_DATACENTER_ID}")
            if not 0 <= worker_id <= self.MAX_WORKER_ID:
                raise ValueError(f"worker_id must be between 0 and {self.MAX_WORKER_ID}")
            self.datacenter_id = datacenter_id
            self.worker_id = worker_id

        if epoch is not None:
            self.EPOCH = epoch

        self.sequence = 0
        self.last_timestamp = -1
        self.lock = threading.Lock()

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------

    def _current_millis(self) -> int:
        return int(time.time() * 1000)

    def _wait_next_millis(self, last_timestamp: int) -> int:
        timestamp = self._current_millis()
        while timestamp <= last_timestamp:
            timestamp = self._current_millis()
        return timestamp

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    def generate(self) -> int:
        """고유 ID 생성 (기존 API — generate_id() 위임)"""
        return self.generate_id()

    def generate_id(self) -> int:
        """고유 ID 생성"""
        with self.lock:
            timestamp = self._current_millis()

            if timestamp < self.last_timestamp:
                raise Exception(
                    f"시계가 {self.last_timestamp - timestamp}ms 뒤로 이동했습니다"
                )

            if timestamp == self.last_timestamp:
                self.sequence = (self.sequence + 1) & self.MAX_SEQUENCE
                if self.sequence == 0:
                    timestamp = self._wait_next_millis(self.last_timestamp)
            else:
                self.sequence = 0

            self.last_timestamp = timestamp

            return (
                ((timestamp - self.EPOCH) << self.TIMESTAMP_SHIFT)
                | (self.datacenter_id << self.DATACENTER_ID_SHIFT)
                | (self.worker_id << self.WORKER_ID_SHIFT)
                | self.sequence
            )

    def parse(self, snowflake_id: int) -> dict:
        """Snowflake ID를 분해하여 구성 요소 반환"""
        sequence = snowflake_id & self.MAX_SEQUENCE
        worker_id = (snowflake_id >> self.WORKER_ID_SHIFT) & self.MAX_WORKER_ID
        datacenter_id = (snowflake_id >> self.DATACENTER_ID_SHIFT) & self.MAX_DATACENTER_ID
        timestamp_ms = (snowflake_id >> self.TIMESTAMP_SHIFT) + self.EPOCH
        return {
            "id": snowflake_id,
            "timestamp_ms": timestamp_ms,
            "datacenter_id": datacenter_id,
            "worker_id": worker_id,
            "sequence": sequence,
        }


# ------------------------------------------------------------------
# 글로벌 싱글톤
# ------------------------------------------------------------------

# 기존 API 호환: 환경 변수 WORKER_ID (10비트 combined)로 구성
WORKER_ID = int(os.getenv("WORKER_ID", 0))
id_generator = SnowflakeIDGenerator(WORKER_ID)

# v9.0 API: datacenter_id=0, worker_id=0 기본 싱글톤
# get_next_id() 함수를 통해 사용. 분산 환경에서는
# SnowflakeIDGenerator(datacenter_id, worker_id)로 별도 인스턴스를 생성하세요.
_id_generator = SnowflakeIDGenerator(datacenter_id=0, worker_id=0)


def get_next_id() -> int:
    """전역 Snowflake ID 생성 (datacenter_id=0, worker_id=0 기본값)"""
    return _id_generator.generate_id()
