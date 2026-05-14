# Reinforcement Learning Module

강화 학습 기반 트레이딩 에이전트 모듈입니다.

## 📁 구조

```
rl/
├── __init__.py
├── dqn_trader.py      # DQN 트레이딩 에이전트 (기존)
├── ppo_agent.py       # PPO 트레이딩 에이전트 (신규)
└── README.md          # 이 파일
```

## 🚀 기능

### 1. PPO Trading Agent (ppo_agent.py)

**FinRL의 PPO 에이전트 패턴 참조**

Proximal Policy Optimization을 사용한 트레이딩 에이전트입니다.

```python
from rl.ppo_agent import train_ppo_agent, PPOAgent
import pandas as pd

# 가격 데이터 준비
df = pd.DataFrame({
    'close': [100, 102, 101, 103, 105],
    'volume': [1000, 1200, 1100, 1300, 1400],
    'high': [102, 104, 103, 105, 107],
    'low': [98, 100, 99, 101, 103],
})

# 에이전트 학습
agent = train_ppo_agent(df, use_sb3=False)

# 예측
observation = [1.0, 0, 100, 5000, 4]
action, _ = agent.predict(observation)
# action: 0=매도, 1=홀드, 2=매수
```

**특징**:
- ✅ Stable Baselines3 PPO 지원 (선택적)
- ✅ 규칙 기반 대체 구현
- ✅ OpenAI Gym 스타일 환경
- ✅ 모델 저장/로드

**의존성**:
```bash
# PPO 모드 사용 시
pip install stable-baselines3
```

### 2. Trading Environment (TradingEnv)

OpenAI Gym 스타일의 트레이딩 환경입니다.

```python
from rl.ppo_agent import TradingEnv
import pandas as pd

# 환경 생성
env = TradingEnv(df, initial_balance=10000000)

# 초기화
observation = env.reset()

# 스텝 실행
for _ in range(100):
    action = 1  # 홀드
    observation, reward, done, info = env.step(action)
    
    print(f"Total value: {info['total_value']}")
    
    if done:
        break
```

**상태 공간**:
- 잔고 비율 (balance / initial_balance)
- 보유 수량 (position)
- 현재 가격 (close)
- 거래량 (volume)
- 변동성 (high - low)

**행동 공간**:
- 0: 매도
- 1: 홀드
- 2: 매수

**보상**:
- 총 자산 변화 (balance + position * price - initial_balance)

## 🎯 사용 사례

### 1. 백테스팅

```python
from rl.ppo_agent import PPOAgent, TradingEnv
import pandas as pd

# 학습 데이터
train_df = pd.read_csv('train_data.csv')
env = TradingEnv(train_df)

# 에이전트 학습
agent = PPOAgent(use_sb3=True)
agent.train(env, total_timesteps=100000)

# 모델 저장
agent.save('models/ppo_agent.pkl')

# 테스트 데이터로 평가
test_df = pd.read_csv('test_data.csv')
test_env = TradingEnv(test_df)

obs = test_env.reset()
total_reward = 0

while True:
    action, _ = agent.predict(obs)
    obs, reward, done, info = test_env.step(action)
    total_reward += reward
    
    if done:
        break

print(f"Total reward: {total_reward}")
print(f"Final value: {info['total_value']}")
```

### 2. 실시간 트레이딩

```python
from rl.ppo_agent import PPOAgent
import asyncio

async def realtime_trading():
    # 학습된 모델 로드
    agent = PPOAgent(use_sb3=True)
    agent.load('models/ppo_agent.pkl')
    
    while True:
        # 실시간 데이터 수집
        observation = get_current_market_state()
        
        # 행동 예측
        action, _ = agent.predict(observation)
        
        # 행동 실행
        if action == 0:
            execute_sell()
        elif action == 2:
            execute_buy()
        
        await asyncio.sleep(60)  # 1분마다

asyncio.run(realtime_trading())
```

### 3. Ensemble Strategy (향후 구현)

```python
from rl.ppo_agent import PPOAgent
# from rl.a2c_agent import A2CAgent
# from rl.sac_agent import SACAgent

# 여러 에이전트 조합
agents = [
    PPOAgent().load('models/ppo.pkl'),
    # A2CAgent().load('models/a2c.pkl'),
    # SACAgent().load('models/sac.pkl'),
]

# 다수결 투표
def ensemble_predict(observation, agents):
    actions = [agent.predict(observation)[0] for agent in agents]
    # 가장 많이 선택된 행동 반환
    return max(set(actions), key=actions.count)
```

## 🔧 구성

### Fallback 전략

외부 라이브러리 없이도 동작:
- **PPO → 규칙 기반 전략** (추세 추종)

### 규칙 기반 전략

Stable Baselines3 없이도 동작하는 간단한 전략:

```python
def _rule_based_predict(observation):
    price_change = (observation[-1] - observation[-2]) / observation[-2]
    
    if price_change > 0.02:  # 2% 상승
        return 2  # 매수
    elif price_change < -0.02:  # 2% 하락
        return 0  # 매도
    else:
        return 1  # 홀드
```

## 📊 성능

**학습 속도** (CPU):
- 10,000 timesteps: ~5분
- 100,000 timesteps: ~50분

**메모리 사용**:
- 모델: ~10MB
- 환경: ~1MB

## 📚 참조

- **FinRL** (12k ⭐): https://github.com/AI4Finance-Foundation/FinRL
  - `agents/stablebaselines3/models.py`: PPO 에이전트
  - `env/EnvMultipleStock_trade.py`: 트레이딩 환경

- **Stable Baselines3**: https://stable-baselines3.readthedocs.io/
  - PPO, A2C, SAC 알고리즘

## ⚠️ 주의사항

1. **실제 거래 전**:
   - 충분한 백테스팅 필수
   - 리스크 관리 전략 수립
   - 소액으로 테스트

2. **학습 시**:
   - 과적합 방지 (validation set 사용)
   - 적절한 보상 함수 설계
   - Hyperparameter tuning

3. **환경 설정**:
   - 거래 수수료 고려
   - 슬리피지 모델링
   - 현실적인 초기 자본

## 🔜 향후 개선 사항

- [ ] A2C, SAC, DDPG 에이전트 추가
- [ ] Ensemble 전략 구현
- [ ] 멀티 에셋 트레이딩 환경
- [ ] 커스텀 보상 함수
- [ ] Tensorboard 통합
- [ ] 하이퍼파라미터 자동 최적화

## 📝 버전

- **v1.0.0** (2026-02-08): PPO 에이전트 추가
  - Stable Baselines3 통합
  - 규칙 기반 대체 구현
  - OpenAI Gym 환경
