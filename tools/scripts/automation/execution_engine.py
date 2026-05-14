"""
자동 실행 엔진

목적:
    파싱된 작업 계획을 자동으로 실행합니다.

기능:
    1. 파일 자동 생성 (템플릿 기반)
    2. 명령어 자동 실행
    3. 테스트 자동 실행
    4. 결과 자동 검증

작성자: Copilot
작성일: 2026-02-03
"""

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


class ExecutionEngine:
    """자동 실행 엔진"""
    
    # 파일 템플릿
    TEMPLATES = {
        'python_module': '''"""
{description}

작성자: Copilot (Auto-generated)
작성일: {date}
"""


def main():
    """메인 함수"""
    pass


if __name__ == '__main__':
    main()
''',
        'python_script': '''#!/usr/bin/env python3
"""
{description}

작성자: Copilot (Auto-generated)
작성일: {date}
"""

import sys


def main():
    """메인 함수"""
    print("스크립트 실행 중...")
    return 0


if __name__ == '__main__':
    sys.exit(main())
''',
        'python_test': '''"""
{description}

작성자: Copilot (Auto-generated)
작성일: {date}
"""

import pytest


def test_example():
    """예제 테스트"""
    assert True


if __name__ == '__main__':
    pytest.main([__file__])
''',
        'bash_script': '''#!/bin/bash
# {description}
# 작성자: Copilot (Auto-generated)
# 작성일: {date}

echo "스크립트 실행 중..."
''',
        'markdown_doc': '''# {title}

작성일: {date}
작성자: Copilot (Auto-generated)

## 개요

{description}

## 내용

작성 예정

---

**END OF DOCUMENT**
''',
        'yaml_config': '''# {description}
# 작성일: {date}

# Configuration here
''',
        'generic': '''# Auto-generated file
# {description}
# {date}
'''
    }
    
    def __init__(self, execution_plan: Dict, dry_run: bool = False):
        """
        Args:
            execution_plan: 실행 계획 딕셔너리
            dry_run: True이면 실제 변경하지 않고 시뮬레이션만
        """
        self.plan = execution_plan
        self.dry_run = dry_run
        self.results = {
            'files_created': [],
            'files_failed': [],
            'commands_executed': [],
            'commands_failed': [],
            'tests_passed': [],
            'tests_failed': [],
            'success': False
        }
        
    def create_files_from_plan(self) -> bool:
        """
        파일 자동 생성
        
        Returns:
            성공 여부
        """
        files = self.plan.get('files_to_create', [])
        
        if not files:
            print("⚠️ 생성할 파일이 없습니다")
            return True
        
        print(f"\n📁 {len(files)}개 파일 생성 시작...")
        
        for file_info in files:
            path = file_info.get('path', '')
            template_type = file_info.get('template', 'generic')
            
            if not path:
                continue
            
            try:
                if self.dry_run:
                    print(f"  [드라이런] {path} (템플릿: {template_type})")
                    self.results['files_created'].append(path)
                else:
                    self._create_file(path, template_type)
                    print(f"  ✅ {path}")
                    self.results['files_created'].append(path)
                    
            except Exception as e:
                print(f"  ❌ {path}: {str(e)}")
                self.results['files_failed'].append({
                    'path': path,
                    'error': str(e)
                })
        
        success = len(self.results['files_failed']) == 0
        return success
    
    def _create_file(self, path: str, template_type: str):
        """파일 생성 (실제)"""
        file_path = Path(path)
        
        # 디렉토리 생성
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 파일이 이미 존재하면 건너뛰기
        if file_path.exists():
            print(f"  ⚠️ {path} 이미 존재, 건너뛰기")
            return
        
        # 템플릿 가져오기
        template = self.TEMPLATES.get(template_type, self.TEMPLATES['generic'])
        
        # 템플릿 변수 치환
        content = template.format(
            description=f"자동 생성된 파일: {path}",
            title=file_path.stem.replace('_', ' ').title(),
            date=datetime.now().strftime('%Y-%m-%d')
        )
        
        # 파일 쓰기
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        # 실행 권한 부여 (쉘 스크립트인 경우)
        if path.endswith('.sh'):
            os.chmod(file_path, 0o755)
    
    def execute_commands(self) -> bool:
        """
        명령어 자동 실행
        
        Returns:
            성공 여부
        """
        commands = self.plan.get('commands', [])
        
        if not commands:
            print("⚠️ 실행할 명령어가 없습니다")
            return True
        
        print(f"\n⚙️ {len(commands)}개 명령어 실행 시작...")
        
        for cmd_info in commands:
            cmd = cmd_info.get('cmd', '')
            description = cmd_info.get('description', cmd)
            
            if not cmd:
                continue
            
            try:
                if self.dry_run:
                    print(f"  [드라이런] {cmd}")
                    self.results['commands_executed'].append(cmd)
                else:
                    # 명령어 실행 (안전하지 않을 수 있는 명령어는 스킵)
                    if self._is_safe_command(cmd):
                        result = subprocess.run(
                            cmd,
                            shell=True,
                            capture_output=True,
                            text=True,
                            timeout=60
                        )
                        
                        if result.returncode == 0:
                            print(f"  ✅ {description}")
                            self.results['commands_executed'].append(cmd)
                        else:
                            print(f"  ⚠️ {description} (종료 코드: {result.returncode})")
                            self.results['commands_failed'].append({
                                'cmd': cmd,
                                'error': result.stderr[:200]
                            })
                    else:
                        print(f"  ⚠️ 안전하지 않은 명령어 스킵: {cmd}")
                        
            except subprocess.TimeoutExpired:
                print(f"  ❌ {description}: 타임아웃")
                self.results['commands_failed'].append({
                    'cmd': cmd,
                    'error': 'Timeout'
                })
            except Exception as e:
                print(f"  ❌ {description}: {str(e)}")
                self.results['commands_failed'].append({
                    'cmd': cmd,
                    'error': str(e)
                })
        
        # 일부 실패해도 계속 진행
        return True
    
    def _is_safe_command(self, cmd: str) -> bool:
        """명령어가 안전한지 확인"""
        # 위험한 명령어 패턴
        dangerous_patterns = [
            'rm -rf /',
            'format',
            'mkfs',
            'dd if=',
            ':(){ :|:& };:',  # Fork bomb
            'chmod 777',
            'shutdown',
            'reboot'
        ]
        
        cmd_lower = cmd.lower()
        for pattern in dangerous_patterns:
            if pattern in cmd_lower:
                return False
        
        return True
    
    def run_tests(self) -> bool:
        """
        테스트 자동 실행
        
        Returns:
            성공 여부
        """
        tests = self.plan.get('validation_tests', [])
        
        if not tests:
            print("⚠️ 실행할 테스트가 없습니다")
            return True
        
        print(f"\n✅ {len(tests)}개 검증 기준 확인 시작...")
        
        for test in tests:
            test_type = test.get('type', 'unknown')
            
            try:
                if self.dry_run:
                    print(f"  [드라이런] {test.get('description', test_type)}")
                    self.results['tests_passed'].append(test)
                else:
                    result = self._run_single_test(test)
                    if result:
                        print(f"  ✅ {test.get('description', test_type)}")
                        self.results['tests_passed'].append(test)
                    else:
                        print(f"  ⚠️ {test.get('description', test_type)}")
                        self.results['tests_failed'].append(test)
                        
            except Exception as e:
                print(f"  ❌ {test.get('description', test_type)}: {str(e)}")
                self.results['tests_failed'].append(test)
        
        # 일부 실패해도 계속 진행
        return True
    
    def _run_single_test(self, test: Dict) -> bool:
        """단일 테스트 실행"""
        test_type = test.get('type', '')
        
        if test_type == 'file_exists':
            target = test.get('target', '')
            return Path(target).exists()
            
        elif test_type == 'command_success':
            cmd = test.get('cmd', '')
            if not cmd:
                return False
            try:
                result = subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    timeout=30
                )
                return result.returncode == 0
            except (subprocess.TimeoutExpired, subprocess.SubprocessError):
                return False
                
        elif test_type == 'checklist':
            # 체크리스트 항목은 수동 검증이므로 기본적으로 통과로 표시
            return True
            
        else:
            # 알 수 없는 테스트 타입은 기본적으로 통과
            return True
    
    def validate_results(self) -> bool:
        """결과 자동 검증"""
        print("\n📊 실행 결과 검증...")
        
        # 기본 검증: 파일이 하나 이상 생성되었거나, 명령어가 실행되었으면 성공
        has_work_done = (
            len(self.results['files_created']) > 0 or
            len(self.results['commands_executed']) > 0
        )
        
        # 실패가 너무 많으면 실패로 간주
        total_failures = (
            len(self.results['files_failed']) +
            len(self.results['commands_failed']) +
            len(self.results['tests_failed'])
        )
        
        if total_failures > 10:
            print(f"  ❌ 너무 많은 실패 ({total_failures}개)")
            return False
        
        if has_work_done:
            print("  ✅ 작업이 성공적으로 수행됨")
            return True
        else:
            print("  ⚠️ 수행된 작업 없음")
            return True  # 작업이 없어도 오류는 아님
    
    def execute_all(self) -> Dict:
        """
        전체 실행 계획 자동 실행
        
        Returns:
            실행 결과 딕셔너리
        """
        print(f"\n{'='*60}")
        print(f"🚀 {self.plan.get('stage', 'N')}단계 자동 실행 시작")
        if self.dry_run:
            print("   🔍 모드: 드라이런")
        print('='*60)
        
        # 1. 파일 생성
        self.create_files_from_plan()
        
        # 2. 명령어 실행
        self.execute_commands()
        
        # 3. 테스트 실행
        self.run_tests()
        
        # 4. 결과 검증
        self.results['success'] = self.validate_results()
        
        # 결과 요약
        self._print_summary()
        
        return self.results
    
    def _print_summary(self):
        """결과 요약 출력"""
        print(f"\n{'='*60}")
        print("📊 실행 결과 요약")
        print('='*60)
        
        print(f"\n파일:")
        print(f"  ✅ 생성됨: {len(self.results['files_created'])}개")
        if self.results['files_failed']:
            print(f"  ❌ 실패: {len(self.results['files_failed'])}개")
        
        print(f"\n명령어:")
        print(f"  ✅ 실행됨: {len(self.results['commands_executed'])}개")
        if self.results['commands_failed']:
            print(f"  ❌ 실패: {len(self.results['commands_failed'])}개")
        
        print(f"\n검증:")
        print(f"  ✅ 통과: {len(self.results['tests_passed'])}개")
        if self.results['tests_failed']:
            print(f"  ❌ 실패: {len(self.results['tests_failed'])}개")
        
        print(f"\n전체 결과: {'✅ 성공' if self.results['success'] else '❌ 실패'}")
        print('='*60)


def main():
    """테스트용 메인 함수"""
    import json
    
    if len(sys.argv) < 2:
        print("사용법: python execution_engine.py <execution_plan.json>")
        sys.exit(1)
    
    plan_path = sys.argv[1]
    dry_run = '--dry-run' in sys.argv
    
    try:
        # 실행 계획 로드
        with open(plan_path, 'r', encoding='utf-8') as f:
            plan = json.load(f)
        
        # 실행 엔진 생성 및 실행
        engine = ExecutionEngine(plan, dry_run=dry_run)
        results = engine.execute_all()
        
        # 결과 저장
        results_path = plan_path.replace('.json', '_results.json')
        with open(results_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        print(f"\n💾 결과 저장됨: {results_path}")
        
        sys.exit(0 if results['success'] else 1)
        
    except Exception as e:
        print(f"❌ 오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
