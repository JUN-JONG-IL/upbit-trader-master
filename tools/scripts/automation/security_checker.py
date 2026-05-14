#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
보안 및 컴플라이언스 자동 체크 (Security Checker)

[Purpose]
API 키 관리, 보안 취약점 스캔, 컴플라이언스 체크를 자동화합니다.

[Responsibilities]
- API 키/비밀 관리 자동화 (dotenv + .gitignore 검증)
- 하드코딩된 비밀 스캔
- 암호화폐 거래 규제 준수 체크리스트
- 보안 취약점 스캔

[Main Flow]
1. .env 파일 존재 및 .gitignore 등록 확인
2. 코드에서 하드코딩된 비밀 스캔
3. 보안 취약점 스캔 (bandit)
4. 컴플라이언스 체크리스트 확인
5. 문제 발견 시 자동 수정 또는 경고

[Dependencies]
- bandit: 보안 취약점 스캔 (optional)
- Python 표준 라이브러리

[Author] Copilot
[Created] 2026-02-03
[Modified] 2026-02-03
"""

import os
import sys
import re
import subprocess
import argparse
from pathlib import Path
from typing import List, Dict, Tuple, Set


class SecurityChecker:
    """보안 및 컴플라이언스 체커 클래스"""
    
    def __init__(self, repo_root: Path):
        """
        초기화
        
        Args:
            repo_root: 레포지토리 루트 경로
        """
        self.repo_root = repo_root
        self.env_file = repo_root / '.env'
        self.gitignore_file = repo_root / '.gitignore'
        
        # 비밀 패턴 (정규식)
        self.secret_patterns = [
            (r'api[_-]?key\s*=\s*["\']([^"\']{10,})["\']', 'API 키'),
            (r'secret[_-]?key\s*=\s*["\']([^"\']{10,})["\']', 'Secret 키'),
            (r'password\s*=\s*["\']([^"\']{5,})["\']', '패스워드'),
            (r'token\s*=\s*["\']([^"\']{10,})["\']', '토큰'),
            (r'access[_-]?key\s*=\s*["\']([^"\']{10,})["\']', 'Access 키'),
            (r'private[_-]?key\s*=\s*["\']([^"\']{10,})["\']', 'Private 키'),
        ]
        
        # 허용된 파일 (환경 설정 파일 등)
        self.allowed_files = {
            '.env.example',
            '.env.template',
            'README.md',
            'SETUP_GUIDE.md'
        }
    
    def check_env_file(self) -> Dict:
        """
        .env 파일 존재 및 설정 확인
        
        Returns:
            Dict: 검사 결과
        """
        print("\n=== 🔑 .env 파일 검사 ===\n")
        
        issues = []
        
        # .env 파일 존재 확인
        if not self.env_file.exists():
            issues.append("❌ .env 파일이 존재하지 않습니다")
            print("❌ .env 파일이 존재하지 않습니다")
            print("   .env.example을 복사하여 .env 파일을 생성하세요")
        else:
            print("✅ .env 파일 존재")
            
            # 필수 환경 변수 확인
            required_vars = [
                'UPBIT_ACCESS_KEY',
                'UPBIT_SECRET_KEY',
                'MONGODB_URI',
                'REDIS_HOST'
            ]
            
            with open(self.env_file, 'r', encoding='utf-8') as f:
                env_content = f.read()
            
            for var in required_vars:
                if var not in env_content:
                    issues.append(f"⚠️  필수 환경 변수 누락: {var}")
                    print(f"⚠️  필수 환경 변수 누락: {var}")
                else:
                    print(f"✅ {var} 설정됨")
        
        return {
            'success': len(issues) == 0,
            'issues': issues
        }
    
    def check_gitignore(self) -> Dict:
        """
        .gitignore에 .env 등록 확인
        
        Returns:
            Dict: 검사 결과
        """
        print("\n=== 📝 .gitignore 검사 ===\n")
        
        issues = []
        
        if not self.gitignore_file.exists():
            issues.append("❌ .gitignore 파일이 존재하지 않습니다")
            print("❌ .gitignore 파일이 존재하지 않습니다")
            return {
                'success': False,
                'issues': issues
            }
        
        with open(self.gitignore_file, 'r', encoding='utf-8') as f:
            gitignore_content = f.read()
        
        # .env 등록 확인
        if '.env' not in gitignore_content:
            issues.append("❌ .gitignore에 .env가 등록되지 않았습니다")
            print("❌ .gitignore에 .env가 등록되지 않았습니다")
        else:
            print("✅ .env가 .gitignore에 등록됨")
        
        # 기타 보안 관련 파일 확인
        security_files = ['*.key', '*.pem', '*.p12', '*.pfx']
        for pattern in security_files:
            if pattern not in gitignore_content:
                issues.append(f"⚠️  .gitignore에 {pattern}이 누락됨")
                print(f"⚠️  .gitignore에 {pattern}이 누락됨")
            else:
                print(f"✅ {pattern}이 .gitignore에 등록됨")
        
        return {
            'success': len(issues) == 0,
            'issues': issues
        }
    
    def scan_hardcoded_secrets(self) -> Dict:
        """
        코드에서 하드코딩된 비밀 스캔
        
        Returns:
            Dict: 스캔 결과
        """
        print("\n=== 🔍 하드코딩된 비밀 스캔 ===\n")
        
        findings = []
        
        # Python 파일만 스캔
        python_files = list(self.repo_root.glob('**/*.py'))
        
        for file_path in python_files:
            # 가상환경, 빌드 디렉토리 등 제외
            if any(skip in str(file_path) for skip in ['venv', 'env', 'build', 'dist', '__pycache__']):
                continue
            
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    
                    for pattern, secret_type in self.secret_patterns:
                        matches = re.finditer(pattern, content, re.IGNORECASE)
                        
                        for match in matches:
                            # 허용된 파일은 제외
                            if file_path.name in self.allowed_files:
                                continue
                            
                            # 주석은 제외
                            line_start = content.rfind('\n', 0, match.start()) + 1
                            line = content[line_start:content.find('\n', match.start())]
                            if line.strip().startswith('#'):
                                continue
                            
                            findings.append({
                                'file': str(file_path.relative_to(self.repo_root)),
                                'type': secret_type,
                                'line': content[:match.start()].count('\n') + 1
                            })
            
            except Exception as e:
                print(f"⚠️  파일 스캔 중 오류 ({file_path}): {e}")
        
        # 결과 출력
        if findings:
            print(f"❌ {len(findings)}개의 하드코딩된 비밀 발견:")
            for finding in findings:
                print(f"  - {finding['file']}:{finding['line']} ({finding['type']})")
        else:
            print("✅ 하드코딩된 비밀이 발견되지 않았습니다")
        
        return {
            'success': len(findings) == 0,
            'findings': findings
        }
    
    def run_bandit(self) -> Dict:
        """
        bandit 보안 스캔 실행
        
        Returns:
            Dict: 스캔 결과
        """
        print("\n=== 🛡️ bandit 보안 스캔 ===\n")
        
        try:
            # bandit 설치 확인
            result = subprocess.run(
                ['bandit', '--version'],
                capture_output=True,
                timeout=5
            )
            
            if result.returncode != 0:
                raise FileNotFoundError("bandit not found")
        
        except (FileNotFoundError, subprocess.TimeoutExpired):
            print("⚠️  bandit이 설치되지 않았습니다")
            print("   설치하려면: pip install bandit")
            return {
                'success': False,
                'error': 'bandit not installed',
                'skipped': True
            }
        
        # bandit 실행
        try:
            result = subprocess.run(
                [
                    'bandit',
                    '-r', 'src',
                    '-f', 'json',
                    '-o', 'bandit_report.json',
                    '--severity-level', 'medium'
                ],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            # 결과 파일 읽기
            report_file = self.repo_root / 'bandit_report.json'
            if report_file.exists():
                import json
                with open(report_file, 'r') as f:
                    report = json.load(f)
                
                issues = report.get('results', [])
                
                print(f"발견된 보안 이슈: {len(issues)}개")
                
                if issues:
                    print("\n상위 5개 이슈:")
                    for issue in issues[:5]:
                        print(f"  - {issue.get('filename')}:{issue.get('line_number')}")
                        print(f"    {issue.get('issue_text')}")
                        print(f"    심각도: {issue.get('issue_severity')}")
                        print()
                
                return {
                    'success': len(issues) == 0,
                    'issues_count': len(issues),
                    'issues': issues
                }
            else:
                return {
                    'success': True,
                    'issues_count': 0
                }
        
        except subprocess.TimeoutExpired:
            print("❌ bandit 스캔 타임아웃")
            return {
                'success': False,
                'error': 'Timeout'
            }
        except Exception as e:
            print(f"❌ bandit 스캔 중 오류: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def check_compliance(self) -> Dict:
        """
        암호화폐 거래 규제 준수 체크리스트
        
        Returns:
            Dict: 체크리스트 결과
        """
        print("\n=== 📋 컴플라이언스 체크리스트 ===\n")
        
        checklist = {
            'API 키 관리': self.env_file.exists(),
            '.gitignore 설정': self.gitignore_file.exists(),
            '로깅 시스템': (self.repo_root / 'logs').exists(),
            '문서화': (self.repo_root / 'README.md').exists(),
        }
        
        all_passed = True
        
        for item, status in checklist.items():
            status_icon = '✅' if status else '❌'
            print(f"{status_icon} {item}")
            if not status:
                all_passed = False
        
        print(f"\n{'✅' if all_passed else '⚠️'} 컴플라이언스 체크: {'통과' if all_passed else '일부 미달'}")
        
        return {
            'success': all_passed,
            'checklist': checklist
        }
    
    def fix_issues(self) -> bool:
        """
        발견된 문제 자동 수정
        
        Returns:
            bool: 수정 성공 여부
        """
        print("\n=== 🔧 문제 자동 수정 ===\n")
        
        fixed = []
        
        # .env 파일이 없으면 .env.example에서 복사
        if not self.env_file.exists():
            env_example = self.repo_root / '.env.example'
            if env_example.exists():
                import shutil
                shutil.copy(env_example, self.env_file)
                fixed.append(".env 파일 생성 (.env.example에서 복사)")
                print("✅ .env 파일 생성")
        
        # .gitignore에 .env 추가
        if self.gitignore_file.exists():
            with open(self.gitignore_file, 'r', encoding='utf-8') as f:
                gitignore_content = f.read()
            
            if '.env' not in gitignore_content:
                with open(self.gitignore_file, 'a', encoding='utf-8') as f:
                    f.write('\n# Environment variables\n.env\n')
                fixed.append(".gitignore에 .env 추가")
                print("✅ .gitignore에 .env 추가")
        
        if fixed:
            print(f"\n✅ {len(fixed)}개 항목 수정 완료")
            for item in fixed:
                print(f"  - {item}")
            return True
        else:
            print("수정할 항목이 없습니다")
            return False


def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(
        description='보안 및 컴플라이언스 자동 체크',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  # 전체 보안 스캔
  python automation/security_checker.py --scan
  
  # 문제 자동 수정
  python automation/security_checker.py --fix
  
  # 컴플라이언스 체크
  python automation/security_checker.py --compliance
  
  # 전체 실행 (스캔 + 수정)
  python automation/security_checker.py --scan --fix
        """
    )
    
    parser.add_argument(
        '--scan',
        action='store_true',
        help='보안 스캔 실행'
    )
    
    parser.add_argument(
        '--fix',
        action='store_true',
        help='발견된 문제 자동 수정'
    )
    
    parser.add_argument(
        '--compliance',
        action='store_true',
        help='컴플라이언스 체크리스트 확인'
    )
    
    args = parser.parse_args()
    
    # 레포지토리 루트 찾기
    repo_root = Path(__file__).parent.parent
    checker = SecurityChecker(repo_root)
    
    all_success = True
    
    if args.scan:
        # .env 파일 검사
        result = checker.check_env_file()
        all_success = all_success and result['success']
        
        # .gitignore 검사
        result = checker.check_gitignore()
        all_success = all_success and result['success']
        
        # 하드코딩된 비밀 스캔
        result = checker.scan_hardcoded_secrets()
        all_success = all_success and result['success']
        
        # bandit 스캔
        result = checker.run_bandit()
        if not result.get('skipped', False):
            all_success = all_success and result['success']
    
    if args.compliance:
        result = checker.check_compliance()
        all_success = all_success and result['success']
    
    if args.fix:
        checker.fix_issues()
    
    if not (args.scan or args.compliance or args.fix):
        parser.print_help()
    else:
        print("\n" + "="*60)
        if all_success:
            print("✅ 모든 보안 검사 통과")
            sys.exit(0)
        else:
            print("❌ 일부 보안 검사 실패")
            print("   --fix 옵션으로 자동 수정을 시도하세요")
            sys.exit(1)


if __name__ == '__main__':
    main()
