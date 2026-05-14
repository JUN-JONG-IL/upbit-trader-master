"""
단계 지시서 자동 파싱 및 작업 추출

목적:
    work_order/N_단계_*.md 파일을 자동으로 파싱하여
    실행 가능한 작업 리스트를 생성합니다.

기능:
    1. 파일 생성 목록 추출
    2. 환경 설정 명령어 추출
    3. 테스트 조건 추출
    4. 검증 기준 추출

작성자: Copilot
작성일: 2026-02-03
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional


class StageParser:
    """단계 지시서 파서"""
    
    def __init__(self, stage: int):
        """
        Args:
            stage: 단계 번호 (예: 2, 3, 11)
        """
        self.stage = stage
        self.stage_docs = self._find_stage_docs()
        self.content = self._read_stage_docs()
        
    def _find_stage_docs(self) -> List[Path]:
        """단계 지시서 파일 찾기"""
        work_order_path = Path('work_order')
        stage_docs = list(work_order_path.glob(f'{self.stage}_단계_*.md'))
        
        if not stage_docs:
            raise FileNotFoundError(f"{self.stage}단계 지시서를 찾을 수 없습니다")
            
        return stage_docs
    
    def _read_stage_docs(self) -> str:
        """단계 지시서 읽기"""
        content = ""
        for doc in self.stage_docs:
            with open(doc, 'r', encoding='utf-8') as f:
                content += f.read() + "\n\n"
        return content
    
    def extract_files_to_create(self) -> List[Dict[str, str]]:
        """
        생성할 파일 목록 자동 추출
        
        Returns:
            List of dicts with 'path' and 'template' keys
        """
        files = []
        
        # JSON 형식으로 명시된 파일 목록 찾기
        json_pattern = r'```json\s*\{[^`]*"files"\s*:\s*\[(.*?)\][^`]*\}\s*```'
        matches = re.findall(json_pattern, self.content, re.DOTALL)
        
        for match in matches:
            try:
                # 파일 목록 JSON 파싱
                files_json = f'[{match}]'
                parsed_files = json.loads(files_json)
                files.extend(parsed_files)
            except json.JSONDecodeError:
                pass
        
        # 마크다운 리스트 형식 파일 목록 찾기
        # 예: - `src/example.py` - 설명
        list_pattern = r'-\s+`([^`]+\.(?:py|sh|md|yaml|yml|txt|json))`'
        list_matches = re.findall(list_pattern, self.content)
        
        for path in list_matches:
            if not any(f['path'] == path for f in files):
                files.append({
                    'path': path,
                    'template': self._guess_template(path)
                })
        
        return files
    
    def _guess_template(self, path: str) -> str:
        """파일 경로에서 템플릿 유형 추측"""
        if path.endswith('.py'):
            if 'test' in path.lower():
                return 'python_test'
            elif 'script' in path.lower():
                return 'python_script'
            else:
                return 'python_module'
        elif path.endswith('.sh'):
            return 'bash_script'
        elif path.endswith('.md'):
            return 'markdown_doc'
        elif path.endswith(('.yaml', '.yml')):
            return 'yaml_config'
        else:
            return 'generic'
    
    def extract_setup_commands(self) -> List[Dict[str, str]]:
        """
        실행할 명령어 자동 추출
        
        Returns:
            List of dicts with 'cmd' and 'description' keys
        """
        commands = []
        
        # JSON 형식으로 명시된 명령어 찾기
        json_pattern = r'```json\s*\{[^`]*"commands"\s*:\s*\[(.*?)\][^`]*\}\s*```'
        matches = re.findall(json_pattern, self.content, re.DOTALL)
        
        for match in matches:
            try:
                commands_json = f'[{match}]'
                parsed_commands = json.loads(commands_json)
                commands.extend(parsed_commands)
            except json.JSONDecodeError:
                pass
        
        # Bash 코드 블록에서 명령어 추출
        bash_pattern = r'```bash\s*\n(.*?)\n```'
        bash_matches = re.findall(bash_pattern, self.content, re.DOTALL)
        
        for bash_code in bash_matches:
            lines = bash_code.strip().split('\n')
            for line in lines:
                line = line.strip()
                # 주석이나 빈 줄 건너뛰기
                if line and not line.startswith('#'):
                    if not any(cmd['cmd'] == line for cmd in commands):
                        commands.append({
                            'cmd': line,
                            'description': f'자동 추출된 명령어: {line[:50]}'
                        })
        
        return commands
    
    def extract_validation_criteria(self) -> List[Dict[str, any]]:
        """
        검증 기준 자동 추출
        
        Returns:
            List of validation test dicts
        """
        tests = []
        
        # JSON 형식으로 명시된 테스트 찾기
        json_pattern = r'```json\s*\{[^`]*"tests"\s*:\s*\[(.*?)\][^`]*\}\s*```'
        matches = re.findall(json_pattern, self.content, re.DOTALL)
        
        for match in matches:
            try:
                tests_json = f'[{match}]'
                parsed_tests = json.loads(tests_json)
                tests.extend(parsed_tests)
            except json.JSONDecodeError:
                pass
        
        # 체크리스트 형식 검증 기준 찾기
        # 예: - [ ] 파일 생성 확인
        checklist_pattern = r'-\s+\[\s*\]\s+(.+)'
        checklist_matches = re.findall(checklist_pattern, self.content)
        
        for item in checklist_matches[:10]:  # 상위 10개만
            if '생성' in item or '확인' in item or '테스트' in item:
                tests.append({
                    'type': 'checklist',
                    'description': item.strip()
                })
        
        return tests
    
    def generate_execution_plan(self) -> Dict:
        """
        실행 계획 JSON 생성
        
        Returns:
            Complete execution plan dictionary
        """
        plan = {
            'stage': self.stage,
            'stage_docs': [str(doc) for doc in self.stage_docs],
            'files_to_create': self.extract_files_to_create(),
            'commands': self.extract_setup_commands(),
            'validation_tests': self.extract_validation_criteria(),
            'metadata': {
                'parser_version': '1.0',
                'generated_at': None  # Will be set by execution engine
            }
        }
        
        return plan
    
    def save_execution_plan(self, output_path: Optional[str] = None) -> str:
        """
        실행 계획을 JSON 파일로 저장
        
        Args:
            output_path: 출력 파일 경로 (None이면 자동 생성)
            
        Returns:
            저장된 파일 경로
        """
        if output_path is None:
            output_path = f'/tmp/stage_{self.stage}_execution_plan.json'
        
        plan = self.generate_execution_plan()
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(plan, f, ensure_ascii=False, indent=2)
        
        return output_path


def main():
    """테스트용 메인 함수"""
    import sys
    
    if len(sys.argv) < 2:
        print("사용법: python stage_parser.py <stage_number>")
        print("예시: python stage_parser.py 2")
        sys.exit(1)
    
    stage = int(sys.argv[1])
    
    try:
        parser = StageParser(stage)
        plan = parser.generate_execution_plan()
        
        print(f"\n{'='*60}")
        print(f"{stage}단계 실행 계획")
        print('='*60)
        
        print(f"\n📁 생성할 파일 ({len(plan['files_to_create'])}개):")
        for file_info in plan['files_to_create']:
            print(f"  - {file_info['path']} ({file_info['template']})")
        
        print(f"\n⚙️ 실행할 명령어 ({len(plan['commands'])}개):")
        for cmd_info in plan['commands'][:5]:  # 처음 5개만 표시
            print(f"  - {cmd_info['cmd'][:60]}")
        
        print(f"\n✅ 검증 기준 ({len(plan['validation_tests'])}개):")
        for test in plan['validation_tests'][:5]:  # 처음 5개만 표시
            print(f"  - {test.get('description', test.get('type', 'N/A'))}")
        
        # JSON 파일 저장
        output_path = parser.save_execution_plan()
        print(f"\n💾 실행 계획 저장됨: {output_path}")
        
    except Exception as e:
        print(f"❌ 오류 발생: {str(e)}")
        sys.exit(1)


if __name__ == '__main__':
    main()
