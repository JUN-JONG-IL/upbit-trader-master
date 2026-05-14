"""
자동 워크플로우 강화 모듈

목적:
    작업 유형 감지 및 관련 가이드 자동 표시 기능 제공

사용법:
    from automation.workflow_enhancer import detect_task_type, show_relevant_guides

작성자: GitHub Copilot
작성일: 2026-02-03
"""

import re
from pathlib import Path
from typing import Optional, List, Dict


class TaskTypeDetector:
    """작업 유형 감지 클래스"""
    
    # 작업 유형별 키워드
    TASK_KEYWORDS = {
        'ui': ['UI', 'UX', 'Qt', 'QWidget', 'QComboBox', 'QCheckBox', '위젯', '스타일', '레이아웃'],
        'doc': ['문서', 'README', 'Documentation', '가이드', 'md'],
        'code': ['class', 'def', 'import', 'Python', '코드', '구현'],
        'test': ['test', 'pytest', '테스트', 'unittest'],
        'api': ['API', 'endpoint', 'REST', 'WebSocket'],
        'data': ['Database', 'DB', 'Redis', 'MongoDB', '데이터베이스'],
    }
    
    def __init__(self):
        self.guides = {
            'ui': {
                'title': 'UI/UX 작업',
                'files': [
                    'docs/development/UI_STYLE_GUIDE.md',
                ],
                'summary': [
                    '- QComboBox 드롭다운 글씨 안 보이는 현상 방지',
                    '- QCheckBox 호버 시 글씨 사라지는 현상 방지',
                    '- 버튼 색상 구별 가이드',
                ]
            },
            'doc': {
                'title': '문서 작업',
                'files': [
                    'docs/development/REFERENCE_PATH_GUIDE.md',
                ],
                'summary': [
                    '- 올바른 파일 참조 방법',
                    '- 자동 검증 사용법',
                    '- 일반적인 오류 패턴',
                ]
            },
            'code': {
                'title': '코드 작업',
                'files': [
                    'docs/development/CODING_STANDARDS.md',
                ],
                'summary': [
                    '- PEP 8 준수',
                    '- Import 경로 규칙',
                    '- Docstring 작성법',
                ]
            },
            'test': {
                'title': '테스트 작업',
                'files': [
                    'docs/development/TESTING_GUIDE.md',
                ],
                'summary': [
                    '- 단위 테스트 작성법',
                    '- Mock 객체 사용',
                    '- 테스트 실행 방법',
                ]
            },
            'api': {
                'title': 'API 개발',
                'files': [
                    'docs/development/API_DOCUMENTATION.md',
                ],
                'summary': [
                    '- RESTful 설계 원칙',
                    '- API 문서화 방법',
                    '- 엔드포인트 테스트',
                ]
            },
        }
    
    def detect_from_stage_doc(self, stage_file: Path) -> Optional[str]:
        """단계 문서에서 작업 유형 감지"""
        try:
            with open(stage_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 각 작업 유형별 키워드 점수 계산
            scores = {}
            for task_type, keywords in self.TASK_KEYWORDS.items():
                score = 0
                for keyword in keywords:
                    # 키워드 등장 횟수 계산
                    score += len(re.findall(keyword, content, re.IGNORECASE))
                scores[task_type] = score
            
            # 가장 높은 점수의 작업 유형 반환
            if scores:
                max_type = max(scores, key=scores.get)
                if scores[max_type] > 0:
                    return max_type
        except:
            pass
        
        return None
    
    def detect_from_files(self, files: List[str]) -> Optional[str]:
        """파일 목록에서 작업 유형 감지"""
        # 파일 확장자 및 경로 분석
        if any('.ui' in f or 'widget' in f.lower() for f in files):
            return 'ui'
        elif any('.md' in f for f in files):
            return 'doc'
        elif any('test_' in f for f in files):
            return 'test'
        elif any('api' in f.lower() for f in files):
            return 'api'
        elif any('.py' in f for f in files):
            return 'code'
        
        return None
    
    def show_guide(self, task_type: str) -> None:
        """작업 유형에 맞는 가이드 표시"""
        if task_type not in self.guides:
            return
        
        guide = self.guides[task_type]
        
        print(f"\n{'='*60}")
        print(f"📖 {guide['title']} - 필수 참조 가이드")
        print('='*60)
        
        for file in guide['files']:
            if Path(file).exists():
                print(f"\n📄 {file}")
        
        print("\n주요 내용:")
        for item in guide['summary']:
            print(f"  {item}")
        
        print(f"\n💡 위 가이드를 반드시 참조하여 작업하세요!")
        print('='*60)
    
    def show_guide_summary(self, guide_file: str) -> None:
        """가이드 파일의 요약 표시"""
        file_path = Path(guide_file)
        
        if not file_path.exists():
            # docs/ 폴더에서 찾기
            file_path = Path('docs') / 'development' / guide_file
        
        if not file_path.exists():
            print(f"⚠️ 가이드 파일을 찾을 수 없습니다: {guide_file}")
            return
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 첫 번째 섹션만 표시 (제목 + 개요)
            lines = content.split('\n')
            summary_lines = []
            
            for i, line in enumerate(lines[:30]):  # 처음 30줄만
                summary_lines.append(line)
                # 두 번째 ## 헤더를 만나면 중단
                if i > 0 and line.startswith('## '):
                    break
            
            print(f"\n📖 {file_path.name} 요약:")
            print('-' * 60)
            print('\n'.join(summary_lines[:20]))  # 최대 20줄
            print('-' * 60)
            print(f"\n전체 내용: {file_path}")
            
        except Exception as e:
            print(f"⚠️ 가이드 읽기 실패: {e}")


# 전역 함수들
def detect_task_type(stage_file: Path = None, files: List[str] = None) -> Optional[str]:
    """작업 유형 감지"""
    detector = TaskTypeDetector()
    
    if stage_file:
        return detector.detect_from_stage_doc(stage_file)
    elif files:
        return detector.detect_from_files(files)
    
    return None


def show_relevant_guides(task_type: str) -> None:
    """관련 가이드 표시"""
    detector = TaskTypeDetector()
    detector.show_guide(task_type)


def show_guide_summary(guide_file: str) -> None:
    """가이드 요약 표시"""
    detector = TaskTypeDetector()
    detector.show_guide_summary(guide_file)


# 사용 예시
if __name__ == "__main__":
    # 테스트
    print("작업 유형 감지 테스트\n")
    
    # UI 작업 감지
    ui_files = ['src/app/window_main.py', 'src/chart/chart.ui']
    task_type = detect_task_type(files=ui_files)
    print(f"파일 목록: {ui_files}")
    print(f"감지된 작업 유형: {task_type}\n")
    
    if task_type:
        show_relevant_guides(task_type)
