"""
PPO 강화학습 기반 Adaptive Base TF (타임프레임) 최적화

목적: 심볼별 Gap 최소화 + 저장 비용 최소화를 동시에 달성하는
      최적 Base 타임프레임(TF)을 강화학습으로 자동 선택

액션 공간:
  0 → 1s  (1초봉)
  1 → 1m  (1분봉)
  2 → 5m  (5분봉)
  3 → 1h  (1시간봉)

보상 함수:
  reward = -gap_count * 10 - storage_cost * 0.01
"""

from __future__ import annotations

import logging
import random
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

try:
    import gymnasium as gym
    _GYM_AVAILABLE = True
except ImportError:
    try:
        import gym  # type: ignore
        _GYM_AVAILABLE = True
    except ImportError:
        _GYM_AVAILABLE = False
        logger.warning(
            "gymnasium(또는 gym) 패키지가 없습니다. "
            "pip install gymnasium stable-baselines3 을 실행하세요."
        )

try:
    from stable_baselines3 import PPO
    _SB3_AVAILABLE = True
except ImportError:
    _SB3_AVAILABLE = False
    logger.warning("stable-baselines3 패키지가 없습니다.")


# 타임프레임 → 저장 비용 (MB/일 기준, 심볼당)
_TF_STORAGE_MB: dict[str, float] = {
    "1s": 1000.0,
    "1m": 100.0,
    "5m": 20.0,
    "1h": 5.0,
}
_TF_LIST = list(_TF_STORAGE_MB.keys())


class AdaptiveTFEnv:
    """
    심볼별 최적 Base TF 선택 환경

    상태 공간 (10차원):
      [시간(0-23 정규화), 요일(0-6), 변동성, 거래량MA,
       1s Gap, 1m Gap, 5m Gap, 1h Gap, 과거보상MA, 현재TF인덱스]

    Example:
        env = AdaptiveTFEnv()
        obs = env.reset()
        action = env.action_space.sample()
        obs, reward, done, info = env.step(action)
    """

    metadata = {"render_modes": []}

    def __init__(self, symbol: str = "KRW-BTC", seed: int | None = None):
        """
        초기화

        Args:
            symbol: 심볼 (로그/저장용)
            seed:   재현성 시드
        """
        if not _GYM_AVAILABLE:
            raise ImportError(
                "gymnasium 패키지를 설치하세요: pip install gymnasium stable-baselines3"
            )

        import gymnasium as gym  # noqa: F811

        self.symbol = symbol
        self._rng = random.Random(seed)
        self._np_rng = np.random.default_rng(seed)

        self.action_space = gym.spaces.Discrete(len(_TF_LIST))
        self.observation_space = gym.spaces.Box(
            low=0.0, high=1.0, shape=(10,), dtype=np.float32
        )

        self._current_tf_idx = 1  # 기본: 1m
        self._reward_history: list[float] = []

    def reset(self, *, seed: int | None = None, options: dict | None = None) -> tuple[np.ndarray, dict]:
        """환경 초기화"""
        self._current_tf_idx = 1
        self._reward_history = []
        return self._get_obs(), {}

    def step(self, action: int) -> tuple[np.ndarray, float, bool, bool, dict]:
        """
        환경 스텝

        Args:
            action: 타임프레임 선택 (0=1s, 1=1m, 2=5m, 3=1h)

        Returns:
            (obs, reward, terminated, truncated, info)
        """
        selected_tf = _TF_LIST[action]
        self._current_tf_idx = action

        # Gap 수 시뮬레이션 (실제 환경에서는 TimescaleDB 쿼리)
        gap_count = self._simulate_gaps(selected_tf)
        # 저장 비용 계산
        storage_cost = _TF_STORAGE_MB[selected_tf]

        reward = float(-gap_count * 10 - storage_cost * 0.01)
        self._reward_history.append(reward)

        obs = self._get_obs()
        info = {
            "selected_tf": selected_tf,
            "gap_count": gap_count,
            "storage_mb": storage_cost,
            "reward": reward,
        }
        return obs, reward, False, False, info

    def _get_obs(self) -> np.ndarray:
        """현재 상태 벡터 반환 (모두 0~1 정규화)"""
        reward_ma = float(np.mean(self._reward_history[-10:])) if self._reward_history else 0.0
        # reward_ma를 0~1로 변환 (대략 -1000~0 범위)
        reward_ma_norm = max(0.0, min(1.0, (reward_ma + 1000) / 1000))

        obs = np.array(
            [
                self._np_rng.random(),           # 시간 (정규화)
                self._np_rng.random(),           # 요일 (정규화)
                float(self._np_rng.uniform(0, 0.1)),  # 변동성
                float(self._np_rng.uniform(0, 1)),    # 거래량MA
                float(self._np_rng.random()),    # 1s Gap 비율
                float(self._np_rng.random()),    # 1m Gap 비율
                float(self._np_rng.random()),    # 5m Gap 비율
                float(self._np_rng.random()),    # 1h Gap 비율
                reward_ma_norm,                  # 과거 보상 이동평균
                self._current_tf_idx / (len(_TF_LIST) - 1),  # 현재 TF 인덱스
            ],
            dtype=np.float32,
        )
        return obs

    def _simulate_gaps(self, tf: str) -> int:
        """
        Gap 수 시뮬레이션 (실제 환경에서는 TimescaleDB 쿼리로 대체)

        낮은 주기 타임프레임일수록 Gap 발생 가능성 높음
        """
        base_gaps = {"1s": 100, "1m": 20, "5m": 5, "1h": 1}
        return self._rng.randint(0, base_gaps[tf])


def train_adaptive_tf(
    symbol: str = "KRW-BTC",
    total_timesteps: int = 100_000,
    save_path: str | None = None,
) -> Any:
    """
    PPO 강화학습으로 최적 TF 정책 학습

    Args:
        symbol:          학습 대상 심볼
        total_timesteps: 학습 스텝 수
        save_path:       모델 저장 경로 (None 이면 저장 안 함)

    Returns:
        학습된 PPO 모델
    """
    if not _SB3_AVAILABLE:
        raise ImportError("stable-baselines3 패키지를 설치하세요.")

    env = AdaptiveTFEnv(symbol=symbol)
    model = PPO("MlpPolicy", env, verbose=1)
    model.learn(total_timesteps=total_timesteps)

    if save_path:
        model.save(save_path)
        logger.info("PPO 모델 저장: %s", save_path)

    return model


def infer_optimal_tf(model: Any, env: AdaptiveTFEnv) -> str:
    """
    학습된 모델로 최적 TF 추론

    Args:
        model: 학습된 PPO 모델
        env:   AdaptiveTFEnv 인스턴스

    Returns:
        최적 타임프레임 문자열 (예: '1m')
    """
    obs, _ = env.reset()
    action, _ = model.predict(obs, deterministic=True)
    return _TF_LIST[int(action)]


if __name__ == "__main__":
    try:
        model = train_adaptive_tf(total_timesteps=10_000)
        env = AdaptiveTFEnv()
        optimal = infer_optimal_tf(model, env)
        print(f"최적 TF: {optimal}")
    except ImportError as e:
        print(f"필수 패키지 없음: {e}")
