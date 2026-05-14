#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Ollama AI 어시스턴트
로컬 LLM을 활용한 대화형 AI 어시스턴트
"""

import logging
import json
from typing import Dict, List, Optional

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    logging.warning("Requests not available.")

logger = logging.getLogger(__name__)


class OllamaAssistant:
    """
    Ollama 기반 AI 어시스턴트
    
    로컬 LLM을 활용한 시장 분석 및 조언
    """
    
    def __init__(self,
                 model: str = "llama2",
                 base_url: str = "http://localhost:11434"):
        """
        Args:
            model: Ollama 모델 이름
            base_url: Ollama API URL
        """
        self.model = model
        self.base_url = base_url
        self.conversation_history = []
        
        logger.info(f"Ollama Assistant 초기화: {model}")
    
    def ask(self, question: str, context: Optional[Dict] = None) -> str:
        """
        질문에 대한 답변 생성
        
        Args:
            question: 질문
            context: 컨텍스트 정보 (시장 데이터 등)
        
        Returns:
            str: 답변
        """
        if not REQUESTS_AVAILABLE:
            return "Requests 라이브러리가 설치되지 않았습니다."
        
        try:
            # 프롬프트 구성
            prompt = self._build_prompt(question, context)
            
            # Ollama API 호출
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                answer = result.get("response", "")
                
                # 대화 히스토리에 추가
                self.conversation_history.append({
                    "question": question,
                    "answer": answer,
                    "context": context
                })
                
                return answer
            else:
                logger.error(f"Ollama API 오류: {response.status_code}")
                return f"API 오류: {response.status_code}"
                
        except requests.exceptions.ConnectionError:
            logger.warning("Ollama 서버에 연결할 수 없습니다. Mock 응답 반환.")
            return self._get_mock_response(question)
        except Exception as e:
            logger.error(f"질문 처리 실패: {e}")
            return f"오류: {str(e)}"
    
    def _build_prompt(self, question: str, context: Optional[Dict]) -> str:
        """
        프롬프트 구성
        
        Args:
            question: 질문
            context: 컨텍스트
        
        Returns:
            str: 완성된 프롬프트
        """
        prompt = "You are a cryptocurrency trading assistant. "
        
        if context:
            prompt += "\n\nMarket Context:\n"
            for key, value in context.items():
                prompt += f"- {key}: {value}\n"
        
        prompt += f"\n\nUser Question: {question}\n\n"
        prompt += "Please provide a clear and concise answer:\n"
        
        return prompt
    
    def _get_mock_response(self, question: str) -> str:
        """
        Mock 응답 생성 (Ollama 미사용 시)
        
        Args:
            question: 질문
        
        Returns:
            str: Mock 응답
        """
        question_lower = question.lower()
        
        if "buy" in question_lower or "매수" in question_lower:
            return "현재 시장 상황을 고려할 때, 분할 매수 전략을 권장합니다. 변동성이 높은 구간이므로 한 번에 큰 금액을 투자하기보다는 여러 번에 나누어 진입하는 것이 리스크 관리에 유리합니다."
        
        elif "sell" in question_lower or "매도" in question_lower:
            return "이익 실현 타이밍을 고려 중이시라면, 목표 수익률의 일부를 먼저 실현하고 나머지는 보유하는 분할 매도 전략을 추천합니다."
        
        elif "risk" in question_lower or "리스크" in question_lower or "위험" in question_lower:
            return "리스크 관리를 위해서는 1) 포트폴리오 분산, 2) 손절 라인 설정, 3) 레버리지 사용 자제, 4) 감당 가능한 금액만 투자 등을 실천하시기 바랍니다."
        
        elif "trend" in question_lower or "추세" in question_lower:
            return "현재 시장은 박스권 움직임을 보이고 있습니다. 명확한 상승 또는 하락 추세가 나타날 때까지 관망하거나, 단기 변동성을 활용한 스윙 트레이딩을 고려해볼 수 있습니다."
        
        else:
            return "질문을 이해했습니다. 암호화폐 투자는 높은 변동성과 리스크를 동반하므로, 충분한 조사와 신중한 결정이 필요합니다. 구체적인 질문이 있으시면 말씀해 주세요."
    
    def analyze_market(self, market_data: Dict) -> str:
        """
        시장 데이터 분석
        
        Args:
            market_data: 시장 데이터
        
        Returns:
            str: 분석 결과
        """
        question = f"""
        다음 시장 데이터를 분석하고 투자 조언을 제공해주세요:
        - 현재가: {market_data.get('price', 'N/A')}
        - 24시간 변화율: {market_data.get('change_rate', 'N/A')}%
        - 거래량: {market_data.get('volume', 'N/A')}
        - RSI: {market_data.get('rsi', 'N/A')}
        """
        
        return self.ask(question, market_data)
    
    def get_conversation_history(self) -> List[Dict]:
        """대화 히스토리 반환"""
        return self.conversation_history
    
    def clear_history(self):
        """대화 히스토리 초기화"""
        self.conversation_history = []
        logger.info("대화 히스토리 초기화")


# 싱글톤 인스턴스
_assistant_instance = None


def get_ollama_assistant() -> OllamaAssistant:
    """글로벌 Ollama Assistant 인스턴스 반환"""
    global _assistant_instance
    if _assistant_instance is None:
        _assistant_instance = OllamaAssistant()
    return _assistant_instance
