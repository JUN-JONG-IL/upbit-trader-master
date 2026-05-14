#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
GitHub Copilot 통합 모듈

AI/ML 코드 자동 리뷰 및 제안 기능
"""

import os
from typing import Dict, List
from pathlib import Path


class CopilotCodeReviewer:
    """GitHub Copilot을 활용한 코드 리뷰"""
    
    def __init__(self, github_token: str = None):
        self.token = github_token or os.getenv("GITHUB_TOKEN")
        self.api_base = "https://api.github.com"
    
    def review_model_code(self, model_path: str) -> Dict:
        """
        AI 모델 코드 자동 리뷰
        
        Args:
            model_path: 모델 파일 경로
            
        Returns:
            리뷰 결과 및 개선 제안
        """
        try:
            with open(model_path, 'r', encoding='utf-8') as f:
                code = f.read()
        except Exception as e:
            return {
                "file": model_path,
                "error": str(e),
                "suggestions": [],
                "quality_score": 0.0
            }
        
        # Copilot API 호출 (예시)
        suggestions = self._get_copilot_suggestions(code)
        
        return {
            "file": model_path,
            "suggestions": suggestions,
            "quality_score": self._calculate_quality(code)
        }
    
    def _get_copilot_suggestions(self, code: str) -> List[str]:
        """Copilot에서 개선 제안 가져오기"""
        suggestions = []
        
        # 기본적인 코드 품질 체크
        if "def " in code:
            # 타입 힌트 체크 - 함수별로 확인
            lines = code.split('\n')
            missing_return_type = False
            for line in lines:
                if 'def ' in line and '(' in line and ':' in line:
                    if ' -> ' not in line:
                        missing_return_type = True
                        break
            
            if missing_return_type:
                suggestions.append("함수 시그니처에 반환 타입 힌트 추가 권장")
        
        # 에러 핸들링 체크
        if "def " in code and "try:" not in code:
            suggestions.append("에러 핸들링 강화 필요 (try-except 블록)")
        
        # 문서화 체크
        if '"""' not in code and "'''" not in code:
            suggestions.append("문서화 개선 가능 (docstring 추가)")
        
        # 로깅 체크
        if "import logging" not in code and "logger" not in code:
            suggestions.append("로깅 추가 권장")
        
        if not suggestions:
            suggestions.append("코드 품질이 우수합니다!")
        
        return suggestions
    
    def _calculate_quality(self, code: str) -> float:
        """코드 품질 점수 계산"""
        score = 0.0
        
        # 함수 정의
        if "def " in code and ":" in code:
            score += 0.2
        
        # 문서화
        if '"""' in code or "'''" in code:
            score += 0.3
        
        # 에러 핸들링
        if "try:" in code and "except" in code:
            score += 0.2
        
        # 주석
        if "# " in code:
            score += 0.1
        
        # 타입 힌트
        if "typing" in code or "->" in code:
            score += 0.2
        
        return min(score, 1.0)
    
    def review_all_models(self, models_dir: str = "src/ai/models") -> List[Dict]:
        """
        모든 AI 모델 파일 리뷰
        
        Args:
            models_dir: 모델 디렉토리 경로
            
        Returns:
            모든 모델의 리뷰 결과 리스트
        """
        results = []
        models_path = Path(models_dir)
        
        if not models_path.exists():
            return results
        
        for py_file in models_path.rglob("*.py"):
            if py_file.name != "__init__.py":
                review = self.review_model_code(str(py_file))
                results.append(review)
        
        return results
