#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
DQN 기반 자동 매매 에이전트
- Stable-Baselines3 활용
- 상태: OHLCV + 기술 지표 + 감성 점수
- 행동: BUY, SELL, HOLD

[Author] Copilot
[Created] 2026-02-06
"""

import logging
import numpy as np
from typing import Dict, Any, Optional, Tuple
import json

logger = logging.getLogger(__name__)


class TradingEnv:
    """
    트레이딩 환경 (Gym-like interface)
    
    강화학습을 위한 트레이딩 시뮬레이션 환경
    """
    
    def __init__(
        self,
        data: np.ndarray,
        initial_balance: float = 1000000.0,
        commission: float = 0.0005
    ):
        """
        초기화
        
        Args:
            data: OHLCV + 지표 데이터 (N x Features)
            initial_balance: 초기 잔고 (원화)
            commission: 거래 수수료 (0.05%)
        """
        self.data = data
        self.initial_balance = initial_balance
        self.commission = commission
        
        # 환경 상태
        self.current_step = 0
        self.balance = initial_balance
        self.position = 0.0  # 보유 코인 수량
        self.entry_price = 0.0
        
        # 공간 정의
        self.n_features = data.shape[1] if len(data.shape) > 1 else 1
        self.action_space_n = 3  # 0: HOLD, 1: BUY, 2: SELL
        
        logger.info(f"[TradingEnv] Initialized with {len(data)} steps, {self.n_features} features")
    
    def reset(self) -> np.ndarray:
        """
        환경 초기화
        
        Returns:
            초기 상태
        """
        self.current_step = 0
        self.balance = self.initial_balance
        self.position = 0.0
        self.entry_price = 0.0
        
        return self._get_observation()
    
    def step(self, action: int) -> Tuple[np.ndarray, float, bool, Dict[str, Any]]:
        """
        행동 실행
        
        Args:
            action: 0 (HOLD), 1 (BUY), 2 (SELL)
            
        Returns:
            (observation, reward, done, info)
        """
        current_price = self._get_current_price()
        
        # 행동 실행
        reward = 0.0
        
        if action == 1:  # BUY
            if self.position == 0 and self.balance > 0:
                # 전량 매수
                amount = self.balance * (1 - self.commission) / current_price
                self.position = amount
                self.entry_price = current_price
                self.balance = 0
                logger.debug(f"[TradingEnv] BUY: {amount:.8f} @ {current_price}")
        
        elif action == 2:  # SELL
            if self.position > 0:
                # 전량 매도
                revenue = self.position * current_price * (1 - self.commission)
                profit = revenue - (self.position * self.entry_price)
                reward = profit / self.initial_balance  # 수익률로 보상
                
                self.balance = revenue
                self.position = 0
                self.entry_price = 0
                logger.debug(f"[TradingEnv] SELL: {revenue:.2f} (profit: {profit:.2f})")
        
        # 다음 스텝으로 이동
        self.current_step += 1
        done = self.current_step >= len(self.data) - 1
        
        # 포트폴리오 가치 계산
        portfolio_value = self.balance + (self.position * current_price)
        
        # 보상 조정: 홀딩 중일 때는 미실현 손익 반영
        if self.position > 0 and action == 0:
            unrealized_profit = (current_price - self.entry_price) * self.position
            reward = unrealized_profit / self.initial_balance * 0.1  # 작은 보상
        
        info = {
            "step": self.current_step,
            "balance": self.balance,
            "position": self.position,
            "portfolio_value": portfolio_value,
            "current_price": current_price
        }
        
        return self._get_observation(), reward, done, info
    
    def _get_observation(self) -> np.ndarray:
        """
        현재 상태 관찰
        
        Returns:
            상태 벡터
        """
        if self.current_step >= len(self.data):
            return np.zeros(self.n_features + 2)
        
        # 시장 데이터 + 포지션 정보
        market_obs = self.data[self.current_step]
        if len(market_obs.shape) == 0:
            market_obs = np.array([market_obs])
        
        position_obs = np.array([
            float(self.position > 0),  # 포지션 보유 여부
            self.balance / self.initial_balance  # 잔고 비율
        ])
        
        return np.concatenate([market_obs, position_obs])
    
    def _get_current_price(self) -> float:
        """
        현재 가격 조회
        
        Returns:
            현재 종가
        """
        if self.current_step >= len(self.data):
            return 0.0
        
        # 첫 번째 컬럼이 종가라고 가정
        price = self.data[self.current_step]
        if len(price.shape) > 0:
            return float(price[0])
        return float(price)


class DQNTrader:
    """
    DQN 기반 트레이더
    
    심층 강화학습을 사용한 자동 매매 에이전트
    """
    
    def __init__(self, use_stable_baselines: bool = False):
        """
        초기화
        
        Args:
            use_stable_baselines: Stable-Baselines3 사용 여부
        """
        self.use_stable_baselines = use_stable_baselines
        self.env = None
        self.model = None
        
        if use_stable_baselines:
            try:
                from stable_baselines3 import DQN
                self.DQN = DQN
                logger.info("[DQNTrader] Stable-Baselines3 available")
            except ImportError:
                logger.warning("[DQNTrader] Stable-Baselines3 not available, using simple agent")
                self.use_stable_baselines = False
    
    def create_env(self, data: np.ndarray, **kwargs) -> TradingEnv:
        """
        트레이딩 환경 생성
        
        Args:
            data: 시장 데이터
            **kwargs: 환경 파라미터
            
        Returns:
            트레이딩 환경
        """
        self.env = TradingEnv(data, **kwargs)
        return self.env
    
    def train(
        self,
        data: np.ndarray,
        timesteps: int = 10000,
        save_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        학습
        
        Args:
            data: 학습 데이터
            timesteps: 학습 타임스텝 수
            save_path: 모델 저장 경로
            
        Returns:
            학습 결과
        """
        if self.env is None:
            self.env = self.create_env(data)
        
        if self.use_stable_baselines and self.DQN:
            # Stable-Baselines3 사용
            logger.info(f"[DQNTrader] Training with Stable-Baselines3 for {timesteps} steps")
            
            # 환경을 Gym 포맷으로 래핑
            # 실제 구현에서는 gym.Env를 상속받아야 함
            logger.warning("[DQNTrader] TradingEnv needs to inherit from gym.Env for SB3")
            
            return {
                "method": "stable_baselines3",
                "timesteps": timesteps,
                "status": "not_implemented"
            }
        else:
            # 간단한 Q-learning 에이전트
            logger.info(f"[DQNTrader] Training with simple Q-learning for {timesteps} steps")
            results = self._train_simple_agent(timesteps)
            
            if save_path:
                self._save_model(save_path)
            
            return results
    
    def _train_simple_agent(self, timesteps: int) -> Dict[str, Any]:
        """
        간단한 Q-learning 에이전트 학습
        
        Args:
            timesteps: 학습 타임스텝
            
        Returns:
            학습 결과
        """
        # Q-table 초기화
        n_states = 100  # 상태 공간을 100개로 이산화
        n_actions = 3
        q_table = np.zeros((n_states, n_actions))
        
        # 하이퍼파라미터
        learning_rate = 0.1
        discount_factor = 0.95
        epsilon = 1.0
        epsilon_decay = 0.995
        epsilon_min = 0.01
        
        total_rewards = []
        
        # 학습 루프
        episodes = timesteps // len(self.env.data)
        
        for episode in range(episodes):
            state = self.env.reset()
            state_idx = self._discretize_state(state, n_states)
            
            episode_reward = 0
            done = False
            
            while not done:
                # Epsilon-greedy 행동 선택
                if np.random.random() < epsilon:
                    action = np.random.randint(0, n_actions)
                else:
                    action = np.argmax(q_table[state_idx])
                
                # 행동 실행
                next_state, reward, done, info = self.env.step(action)
                next_state_idx = self._discretize_state(next_state, n_states)
                
                # Q-value 업데이트
                old_q = q_table[state_idx, action]
                next_max_q = np.max(q_table[next_state_idx])
                new_q = old_q + learning_rate * (reward + discount_factor * next_max_q - old_q)
                q_table[state_idx, action] = new_q
                
                episode_reward += reward
                state_idx = next_state_idx
            
            total_rewards.append(episode_reward)
            epsilon = max(epsilon_min, epsilon * epsilon_decay)
            
            if (episode + 1) % 10 == 0:
                avg_reward = np.mean(total_rewards[-10:])
                logger.info(f"[DQNTrader] Episode {episode + 1}/{episodes}, Avg Reward: {avg_reward:.4f}")
        
        self.model = {"q_table": q_table, "n_states": n_states}
        
        return {
            "method": "simple_q_learning",
            "episodes": episodes,
            "total_rewards": total_rewards,
            "final_avg_reward": float(np.mean(total_rewards[-10:]) if total_rewards else 0)
        }
    
    def _discretize_state(self, state: np.ndarray, n_bins: int) -> int:
        """
        연속 상태를 이산 상태로 변환
        
        Args:
            state: 연속 상태 벡터
            n_bins: 이산화 bin 수
            
        Returns:
            이산 상태 인덱스
        """
        # 간단한 해싱으로 상태 이산화
        normalized = (state - state.min()) / (state.max() - state.min() + 1e-8)
        state_hash = int(np.sum(normalized) * n_bins) % n_bins
        return state_hash
    
    def predict(self, state: np.ndarray) -> int:
        """
        행동 예측
        
        Args:
            state: 현재 상태
            
        Returns:
            행동 (0: HOLD, 1: BUY, 2: SELL)
        """
        if self.model is None:
            logger.warning("[DQNTrader] Model not trained, returning random action")
            return np.random.randint(0, 3)
        
        if "q_table" in self.model:
            # Simple Q-learning
            state_idx = self._discretize_state(state, self.model["n_states"])
            return int(np.argmax(self.model["q_table"][state_idx]))
        else:
            # Stable-Baselines3
            action, _ = self.model.predict(state)
            return int(action)
    
    def _save_model(self, path: str):
        """모델 저장"""
        if self.model and "q_table" in self.model:
            np.savez(path, q_table=self.model["q_table"], n_states=self.model["n_states"])
            logger.info(f"[DQNTrader] Model saved to {path}")
    
    def load_model(self, path: str):
        """모델 로드"""
        try:
            data = np.load(path)
            self.model = {
                "q_table": data["q_table"],
                "n_states": int(data["n_states"])
            }
            logger.info(f"[DQNTrader] Model loaded from {path}")
        except Exception as e:
            logger.error(f"[DQNTrader] Model loading error: {e}")


if __name__ == "__main__":
    # 테스트
    logging.basicConfig(level=logging.INFO)
    
    # 시뮬레이션 데이터 생성 (가격 + 지표)
    n_samples = 1000
    prices = np.random.randn(n_samples).cumsum() + 50000
    volume = np.random.randint(100, 1000, n_samples)
    rsi = np.random.uniform(30, 70, n_samples)
    
    data = np.column_stack([prices, volume, rsi])
    
    # DQN 트레이더 생성 및 학습
    trader = DQNTrader(use_stable_baselines=False)
    trader.create_env(data)
    
    results = trader.train(data, timesteps=5000)
    print(f"Training Results: {results}")
    
    # 예측 테스트
    test_state = trader.env.reset()
    action = trader.predict(test_state)
    print(f"Predicted Action: {['HOLD', 'BUY', 'SELL'][action]}")
