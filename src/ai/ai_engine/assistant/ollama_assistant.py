#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Ollama 기반 AI 어시스턴트
- Llama 3.1, Mistral, Gemma 로컬 실행
- 자연어 명령 해석 및 앱 제어

[Author] Copilot
[Created] 2026-02-06
"""

import logging
from typing import Dict, Any, Optional, List
import json

logger = logging.getLogger(__name__)


class OllamaAssistant:
    """
    Ollama AI 어시스턴트
    
    로컬 LLM을 사용하여 자연어 명령 해석 및 트레이딩 앱 제어
    """
    
    def __init__(self, model: str = "llama3.1", api_url: str = "http://localhost:11434"):
        """
        초기화
        
        Args:
            model: 사용할 Ollama 모델 (llama3.1, mistral, gemma 등)
            api_url: Ollama API URL
        """
        self.model = model
        self.api_url = api_url
        self.requests_available = False
        
        try:
            import requests
            self.requests = requests
            self.requests_available = True
            logger.info(f"[OllamaAssistant] Initialized with model: {model}")
        except ImportError:
            logger.warning("[OllamaAssistant] requests library not available")
    
    def chat(self, prompt: str, stream: bool = False) -> str:
        """
        Ollama와 대화
        
        Args:
            prompt: 사용자 프롬프트
            stream: 스트리밍 응답 여부
            
        Returns:
            AI 응답
        """
        if not self.requests_available:
            logger.error("[OllamaAssistant] requests library not available")
            return "Error: requests library not installed"
        
        try:
            url = f"{self.api_url}/api/generate"
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": stream
            }
            
            response = self.requests.post(url, json=payload, timeout=30)
            
            if response.status_code == 200:
                if stream:
                    # 스트리밍 응답 처리
                    full_response = ""
                    for line in response.iter_lines():
                        if line:
                            data = json.loads(line)
                            if "response" in data:
                                full_response += data["response"]
                    return full_response
                else:
                    # 단일 응답
                    data = response.json()
                    return data.get("response", "")
            else:
                logger.error(f"[OllamaAssistant] API error: {response.status_code}")
                return f"Error: API returned status {response.status_code}"
                
        except Exception as e:
            logger.error(f"[OllamaAssistant] Chat error: {e}")
            return f"Error: {str(e)}"
    
    def execute_command(self, command: str) -> Dict[str, Any]:
        """
        자연어 명령 실행
        
        Args:
            command: 자연어 명령 (예: "비트코인 차트 보여줘")
            
        Returns:
            실행 결과 딕셔너리
        """
        command_lower = command.lower()
        
        # 차트 보기 명령
        if "차트" in command:
            symbol = self._extract_symbol(command)
            return {
                "action": "show_chart",
                "symbol": symbol or "KRW-BTC",
                "success": True,
                "message": f"{symbol} 차트를 표시합니다"
            }
        
        # 매수 명령
        elif "매수" in command or "사" in command or "buy" in command_lower:
            symbol = self._extract_symbol(command)
            amount = self._extract_amount(command)
            return {
                "action": "buy",
                "symbol": symbol or "KRW-BTC",
                "amount": amount,
                "success": True,
                "message": f"{symbol} {amount} 매수 신호"
            }
        
        # 매도 명령
        elif "매도" in command or "팔" in command or "sell" in command_lower:
            symbol = self._extract_symbol(command)
            amount = self._extract_amount(command)
            return {
                "action": "sell",
                "symbol": symbol or "KRW-BTC",
                "amount": amount,
                "success": True,
                "message": f"{symbol} {amount} 매도 신호"
            }
        
        # 가격 조회 명령
        elif "가격" in command or "시세" in command or "price" in command_lower:
            symbol = self._extract_symbol(command)
            return {
                "action": "get_price",
                "symbol": symbol or "KRW-BTC",
                "success": True,
                "message": f"{symbol} 가격 조회"
            }
        
        # 잔고 조회 명령
        elif "잔고" in command or "balance" in command_lower:
            return {
                "action": "get_balance",
                "success": True,
                "message": "잔고 조회"
            }
        
        # AI 분석 명령
        elif "분석" in command or "analyze" in command_lower:
            symbol = self._extract_symbol(command)
            return {
                "action": "analyze",
                "symbol": symbol or "KRW-BTC",
                "success": True,
                "message": f"{symbol} AI 분석 시작"
            }
        
        # 알 수 없는 명령
        else:
            return {
                "action": "unknown",
                "success": False,
                "message": f"알 수 없는 명령: {command}",
                "suggestion": "차트, 매수, 매도, 가격, 잔고, 분석 등의 명령을 사용해보세요"
            }
    
    def _extract_symbol(self, command: str) -> Optional[str]:
        """
        명령에서 심볼 추출
        
        Args:
            command: 자연어 명령
            
        Returns:
            심볼 코드 또는 None
        """
        # 코인 이름 매핑
        coin_map = {
            "비트코인": "KRW-BTC",
            "비트": "KRW-BTC",
            "btc": "KRW-BTC",
            "이더리움": "KRW-ETH",
            "이더": "KRW-ETH",
            "eth": "KRW-ETH",
            "리플": "KRW-XRP",
            "xrp": "KRW-XRP",
            "에이다": "KRW-ADA",
            "카르다노": "KRW-ADA",
            "ada": "KRW-ADA",
            "솔라나": "KRW-SOL",
            "sol": "KRW-SOL",
            "도지": "KRW-DOGE",
            "도지코인": "KRW-DOGE",
            "doge": "KRW-DOGE"
        }
        
        command_lower = command.lower()
        
        for name, symbol in coin_map.items():
            if name in command_lower:
                return symbol
        
        return None
    
    def _extract_amount(self, command: str) -> Optional[float]:
        """
        명령에서 금액/수량 추출
        
        Args:
            command: 자연어 명령
            
        Returns:
            금액/수량 또는 None
        """
        import re
        
        # 숫자 패턴 찾기
        patterns = [
            r'(\d+(?:\.\d+)?)\s*만원',  # "10만원"
            r'(\d+(?:\.\d+)?)\s*원',    # "100000원"
            r'(\d+(?:\.\d+)?)\s*개',    # "0.1개"
            r'(\d+(?:\.\d+)?)',          # "100000"
        ]
        
        for pattern in patterns:
            match = re.search(pattern, command)
            if match:
                value = float(match.group(1))
                
                # "만원" 단위 처리
                if "만원" in command:
                    value *= 10000
                
                return value
        
        return None
    
    def get_trading_advice(self, symbol: str, market_data: Dict[str, Any]) -> str:
        """
        트레이딩 조언 생성
        
        Args:
            symbol: 심볼 코드
            market_data: 시장 데이터
            
        Returns:
            AI 생성 조언
        """
        if not self.requests_available:
            return "AI 조언 기능을 사용하려면 requests 라이브러리가 필요합니다"
        
        prompt = f"""
당신은 암호화폐 트레이딩 전문가입니다.

심볼: {symbol}
현재 가격: {market_data.get('price', 'N/A')}
24시간 변동률: {market_data.get('change_rate', 'N/A')}%
거래량: {market_data.get('volume', 'N/A')}

위 데이터를 바탕으로 짧고 명확한 트레이딩 조언을 제공해주세요.
매수/매도/관망 중 하나를 추천하고 그 이유를 간단히 설명해주세요.
"""
        
        try:
            response = self.chat(prompt)
            return response
        except Exception as e:
            logger.error(f"[OllamaAssistant] Advice generation error: {e}")
            return f"조언 생성 중 오류: {str(e)}"
    
    def parse_trading_strategy(self, strategy_text: str) -> Dict[str, Any]:
        """
        자연어 트레이딩 전략 파싱
        
        Args:
            strategy_text: 자연어 전략 설명
            
        Returns:
            파싱된 전략 파라미터
        """
        prompt = f"""
다음 트레이딩 전략을 JSON 형식으로 파싱해주세요:

{strategy_text}

JSON 형식:
{{
    "entry_conditions": ["조건1", "조건2"],
    "exit_conditions": ["조건1", "조건2"],
    "stop_loss": 값,
    "take_profit": 값,
    "position_size": 값
}}
"""
        
        try:
            response = self.chat(prompt)
            # JSON 추출 시도
            import json
            import re
            
            # JSON 블록 찾기
            json_match = re.search(r'\{[^}]+\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))
            
            return {"error": "JSON parsing failed", "raw_response": response}
            
        except Exception as e:
            logger.error(f"[OllamaAssistant] Strategy parsing error: {e}")
            return {"error": str(e)}


if __name__ == "__main__":
    # 테스트
    logging.basicConfig(level=logging.INFO)
    
    assistant = OllamaAssistant(model="llama3.1")
    
    # 명령 실행 테스트
    commands = [
        "비트코인 차트 보여줘",
        "이더리움 10만원 매수해",
        "도지코인 가격 알려줘",
        "내 잔고 확인",
        "비트코인 분석해줘"
    ]
    
    for cmd in commands:
        result = assistant.execute_command(cmd)
        print(f"\n명령: {cmd}")
        print(f"결과: {result}")
