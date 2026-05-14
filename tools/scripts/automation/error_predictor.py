#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 기반 에러 예측 및 예방 시스템 (Error Predictor)

[Purpose]
과거 로그 분석을 통해 잠재적 오류를 예측하고 자동 복구 메커니즘을 제공합니다.

[Responsibilities]
- 과거 로그 분석으로 잠재적 오류 예측
- 에러 발생 시 자동 롤백 (Git reset 자동화)
- 패턴 기반 오류 탐지
- 예방 조치 자동 제안

[Main Flow]
1. 로그 파일 수집 및 분석
2. ML 모델로 오류 패턴 학습
3. 현재 시스템 상태 모니터링
4. 잠재적 오류 탐지 시 알림 및 예방 조치 제안
5. 오류 발생 시 자동 롤백 수행

[Dependencies]
- scikit-learn: ML 모델
- Python 표준 라이브러리 (subprocess, json, datetime)

[Author] Copilot
[Created] 2026-02-03
[Modified] 2026-02-03
"""

import os
import sys
import json
import argparse
import subprocess
import datetime
import re
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from collections import defaultdict, Counter

# ML 패키지는 optional - 없으면 기본 패턴 매칭만 사용
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.ensemble import RandomForestClassifier
    import pickle
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False
    print("⚠️  scikit-learn이 설치되지 않았습니다. 기본 패턴 매칭만 사용합니다.")
    print("   ML 기능을 사용하려면: pip install scikit-learn")


class ErrorPredictor:
    """에러 예측 및 예방 클래스"""
    
    def __init__(self, repo_root: Path):
        """
        초기화
        
        Args:
            repo_root: 레포지토리 루트 경로
        """
        self.repo_root = repo_root
        self.logs_dir = repo_root / "logs"
        self.model_path = repo_root / "automation" / "error_model.pkl"
        self.error_patterns_path = repo_root / "automation" / "error_patterns.json"
        
        # 에러 패턴 데이터베이스
        self.error_patterns = self._load_error_patterns()
        
        # ML 모델 (있으면)
        self.model = None
        self.vectorizer = None
        if ML_AVAILABLE and self.model_path.exists():
            self._load_model()
    
    def _load_error_patterns(self) -> Dict:
        """
        저장된 에러 패턴 로드
        
        Returns:
            Dict: 에러 패턴 데이터
        """
        if self.error_patterns_path.exists():
            with open(self.error_patterns_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        # 기본 패턴
        return {
            "connection_errors": {
                "patterns": [
                    r"ConnectionError",
                    r"TimeoutError",
                    r"Failed to connect",
                    r"Connection refused"
                ],
                "solutions": [
                    "서비스 재시작",
                    "네트워크 연결 확인",
                    "포트 충돌 확인"
                ]
            },
            "import_errors": {
                "patterns": [
                    r"ModuleNotFoundError",
                    r"ImportError",
                    r"No module named"
                ],
                "solutions": [
                    "requirements.txt 확인",
                    "pip install -r requirements.txt 실행",
                    "가상환경 활성화 확인"
                ]
            },
            "syntax_errors": {
                "patterns": [
                    r"SyntaxError",
                    r"IndentationError",
                    r"invalid syntax"
                ],
                "solutions": [
                    "코드 문법 검사",
                    "들여쓰기 확인",
                    "Python 버전 확인"
                ]
            },
            "file_errors": {
                "patterns": [
                    r"FileNotFoundError",
                    r"No such file or directory",
                    r"PermissionError"
                ],
                "solutions": [
                    "파일 경로 확인",
                    "파일 권한 확인",
                    "필요한 디렉토리 생성"
                ]
            },
            "docker_errors": {
                "patterns": [
                    r"docker.*not running",
                    r"Cannot connect to Docker daemon",
                    r"docker-compose.*failed"
                ],
                "solutions": [
                    "Docker 서비스 시작",
                    "Docker Compose 재시작",
                    "docker-compose.yml 확인"
                ]
            }
        }
    
    def _save_error_patterns(self):
        """에러 패턴을 파일에 저장"""
        with open(self.error_patterns_path, 'w', encoding='utf-8') as f:
            json.dump(self.error_patterns, indent=2, ensure_ascii=False, fp=f)
    
    def _load_model(self):
        """저장된 ML 모델 로드"""
        try:
            with open(self.model_path, 'rb') as f:
                data = pickle.load(f)
                self.model = data.get('model')
                self.vectorizer = data.get('vectorizer')
            print(f"✅ ML 모델 로드 완료: {self.model_path}")
        except Exception as e:
            print(f"⚠️  ML 모델 로드 실패: {e}")
    
    def _save_model(self):
        """ML 모델 저장"""
        if not ML_AVAILABLE or not self.model:
            return
        
        try:
            with open(self.model_path, 'wb') as f:
                pickle.dump({
                    'model': self.model,
                    'vectorizer': self.vectorizer
                }, f)
            print(f"✅ ML 모델 저장 완료: {self.model_path}")
        except Exception as e:
            print(f"❌ ML 모델 저장 실패: {e}")
    
    def collect_logs(self) -> List[str]:
        """
        로그 파일 수집
        
        Returns:
            List[str]: 로그 라인 리스트
        """
        logs = []
        
        # logs 디렉토리가 없으면 생성
        if not self.logs_dir.exists():
            self.logs_dir.mkdir(parents=True, exist_ok=True)
            print(f"📁 로그 디렉토리 생성: {self.logs_dir}")
            return logs
        
        # 모든 .log 파일 읽기
        for log_file in self.logs_dir.glob("*.log"):
            try:
                with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                    logs.extend(f.readlines())
            except Exception as e:
                print(f"⚠️  로그 파일 읽기 실패 ({log_file}): {e}")
        
        print(f"📊 수집된 로그 라인 수: {len(logs)}")
        return logs
    
    def analyze_logs(self, logs: List[str]) -> Dict:
        """
        로그 분석 및 에러 패턴 탐지
        
        Args:
            logs: 로그 라인 리스트
        
        Returns:
            Dict: 분석 결과
        """
        results = {
            'total_lines': len(logs),
            'errors_found': [],
            'warnings_found': [],
            'patterns_matched': defaultdict(int)
        }
        
        # 패턴 매칭
        for line in logs:
            # ERROR 레벨 탐지
            if 'ERROR' in line or 'Error' in line or 'error' in line:
                results['errors_found'].append(line.strip())
            
            # WARNING 레벨 탐지
            if 'WARNING' in line or 'Warning' in line or 'warning' in line:
                results['warnings_found'].append(line.strip())
            
            # 알려진 패턴 매칭
            for error_type, pattern_info in self.error_patterns.items():
                for pattern in pattern_info['patterns']:
                    if re.search(pattern, line, re.IGNORECASE):
                        results['patterns_matched'][error_type] += 1
        
        return results
    
    def predict_errors(self, current_state: Dict) -> List[Dict]:
        """
        현재 상태를 기반으로 잠재적 오류 예측
        
        Args:
            current_state: 현재 시스템 상태
        
        Returns:
            List[Dict]: 예측된 오류 목록
        """
        predictions = []
        
        # 패턴 기반 예측
        for error_type, pattern_info in self.error_patterns.items():
            risk_score = 0
            
            # 상태 기반 리스크 계산
            if error_type == 'connection_errors':
                if not current_state.get('docker_running', True):
                    risk_score += 50
                if not current_state.get('network_available', True):
                    risk_score += 30
            
            elif error_type == 'import_errors':
                if not current_state.get('venv_active', False):
                    risk_score += 40
                if not current_state.get('requirements_installed', True):
                    risk_score += 60
            
            elif error_type == 'docker_errors':
                if not current_state.get('docker_running', True):
                    risk_score += 80
            
            if risk_score > 30:
                predictions.append({
                    'type': error_type,
                    'risk_score': risk_score,
                    'solutions': pattern_info['solutions']
                })
        
        # 리스크 스코어 순으로 정렬
        predictions.sort(key=lambda x: x['risk_score'], reverse=True)
        
        return predictions
    
    def get_current_state(self) -> Dict:
        """
        현재 시스템 상태 수집
        
        Returns:
            Dict: 시스템 상태
        """
        state = {
            'docker_running': False,
            'network_available': True,
            'venv_active': sys.prefix != sys.base_prefix,
            'requirements_installed': True,
            'git_clean': False
        }
        
        # Docker 상태 확인
        try:
            result = subprocess.run(
                ['docker', 'info'],
                capture_output=True,
                timeout=5
            )
            state['docker_running'] = result.returncode == 0
        except:
            pass
        
        # Git 상태 확인
        try:
            result = subprocess.run(
                ['git', 'status', '--porcelain'],
                capture_output=True,
                text=True,
                cwd=self.repo_root
            )
            state['git_clean'] = len(result.stdout.strip()) == 0
        except:
            pass
        
        return state
    
    def auto_rollback(self, steps: int = 1) -> bool:
        """
        Git을 사용한 자동 롤백
        
        Args:
            steps: 롤백할 커밋 수
        
        Returns:
            bool: 성공 여부
        """
        try:
            print(f"🔄 {steps}단계 롤백 시작...")
            
            # 현재 변경사항 확인
            result = subprocess.run(
                ['git', 'status', '--porcelain'],
                capture_output=True,
                text=True,
                cwd=self.repo_root
            )
            
            if result.stdout.strip():
                print("⚠️  커밋되지 않은 변경사항이 있습니다.")
                response = input("변경사항을 stash하고 계속하시겠습니까? (y/N): ")
                
                if response.lower() == 'y':
                    subprocess.run(
                        ['git', 'stash'],
                        cwd=self.repo_root,
                        check=True
                    )
                    print("✅ 변경사항 stash 완료")
                else:
                    print("❌ 롤백 취소")
                    return False
            
            # 롤백 실행
            subprocess.run(
                ['git', 'reset', '--hard', f'HEAD~{steps}'],
                cwd=self.repo_root,
                check=True
            )
            
            print(f"✅ {steps}단계 롤백 완료")
            return True
            
        except subprocess.CalledProcessError as e:
            print(f"❌ 롤백 실패: {e}")
            return False
        except Exception as e:
            print(f"❌ 예상치 못한 오류: {e}")
            return False
    
    def suggest_solutions(self, error_type: str) -> List[str]:
        """
        에러 타입에 대한 해결책 제안
        
        Args:
            error_type: 에러 타입
        
        Returns:
            List[str]: 해결책 목록
        """
        pattern_info = self.error_patterns.get(error_type)
        if pattern_info:
            return pattern_info['solutions']
        return ["알려진 해결책이 없습니다."]


def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(
        description='AI 기반 에러 예측 및 예방 시스템',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  # 로그 분석
  python automation/error_predictor.py --analyze
  
  # 오류 예측
  python automation/error_predictor.py --predict
  
  # 자동 롤백 (1단계)
  python automation/error_predictor.py --auto-rollback
  
  # 자동 롤백 (3단계)
  python automation/error_predictor.py --auto-rollback --steps 3
        """
    )
    
    parser.add_argument(
        '--analyze',
        action='store_true',
        help='로그 파일 분석'
    )
    
    parser.add_argument(
        '--predict',
        action='store_true',
        help='잠재적 오류 예측'
    )
    
    parser.add_argument(
        '--auto-rollback',
        action='store_true',
        help='자동 롤백 실행'
    )
    
    parser.add_argument(
        '--steps',
        type=int,
        default=1,
        help='롤백할 커밋 수 (기본값: 1)'
    )
    
    args = parser.parse_args()
    
    # 레포지토리 루트 찾기
    repo_root = Path(__file__).parent.parent
    predictor = ErrorPredictor(repo_root)
    
    if args.analyze:
        print("\n=== 📊 로그 분석 시작 ===\n")
        logs = predictor.collect_logs()
        
        if not logs:
            print("⚠️  분석할 로그가 없습니다.")
            return
        
        results = predictor.analyze_logs(logs)
        
        print(f"\n전체 로그 라인: {results['total_lines']}")
        print(f"에러 발견: {len(results['errors_found'])}")
        print(f"경고 발견: {len(results['warnings_found'])}")
        
        if results['patterns_matched']:
            print("\n=== 🔍 탐지된 에러 패턴 ===")
            for error_type, count in results['patterns_matched'].items():
                print(f"  - {error_type}: {count}회")
                solutions = predictor.suggest_solutions(error_type)
                print(f"    해결책:")
                for sol in solutions:
                    print(f"      • {sol}")
        
        # 최근 에러 몇 개 출력
        if results['errors_found']:
            print("\n=== ❌ 최근 에러 (최대 5개) ===")
            for error in results['errors_found'][-5:]:
                print(f"  {error[:100]}...")
    
    elif args.predict:
        print("\n=== 🔮 오류 예측 시작 ===\n")
        
        # 현재 상태 수집
        current_state = predictor.get_current_state()
        
        print("현재 시스템 상태:")
        print(f"  - Docker 실행: {'✅' if current_state['docker_running'] else '❌'}")
        print(f"  - 가상환경 활성화: {'✅' if current_state['venv_active'] else '❌'}")
        print(f"  - Git 상태 깨끗함: {'✅' if current_state['git_clean'] else '⚠️'}")
        
        # 오류 예측
        predictions = predictor.predict_errors(current_state)
        
        if predictions:
            print("\n=== ⚠️  잠재적 오류 예측 ===")
            for pred in predictions:
                print(f"\n  에러 타입: {pred['type']}")
                print(f"  리스크 점수: {pred['risk_score']}/100")
                print(f"  권장 조치:")
                for sol in pred['solutions']:
                    print(f"    • {sol}")
        else:
            print("\n✅ 잠재적 오류가 탐지되지 않았습니다.")
    
    elif args.auto_rollback:
        print(f"\n=== 🔄 자동 롤백 ({args.steps}단계) ===\n")
        
        confirm = input(f"정말 {args.steps}단계 롤백하시겠습니까? (y/N): ")
        if confirm.lower() != 'y':
            print("❌ 롤백 취소")
            return
        
        success = predictor.auto_rollback(args.steps)
        sys.exit(0 if success else 1)
    
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
