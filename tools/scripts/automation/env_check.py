"""
환경 자동 검증 스크립트

목적:
    개발 환경이 프로젝트 요구사항을 충족하는지 자동으로 검증합니다.
    Python 버전, .env 파일, Docker 서비스, 의존성 설치 여부를 확인합니다.

사용법:
    python automation/env_check.py
    
예시:
    # 기본 실행
    python automation/env_check.py
    
    # 상세 모드
    python automation/env_check.py --verbose
    
    # JSON 출력
    python automation/env_check.py --json
    
작성자: Copilot
작성일: 2026-02-01
"""

import sys
import os
import subprocess
import platform
from pathlib import Path
import argparse
import json


class EnvironmentChecker:
    """환경 검증 클래스"""
    
    def __init__(self, verbose=False):
        self.verbose = verbose
        self.results = {
            'python_version': False,
            'env_file': False,
            'env_keys': False,
            'docker': False,
            'dependencies': False,
            'all_passed': False,
            'errors': [],
            'warnings': []
        }
        self.required_python_version = (3, 11, 11)
        self.required_env_keys = [
            'UPBIT_ACCESS_KEY',
            'UPBIT_SECRET_KEY',
            'MONGODB_URI',
            'REDIS_HOST'
        ]
        
    def check_python_version(self):
        """Python 3.11.11 확인"""
        try:
            current_version = sys.version_info[:3]
            
            if self.verbose:
                print(f"🔍 현재 Python 버전: {'.'.join(map(str, current_version))}")
                print(f"📋 필요 Python 버전: {'.'.join(map(str, self.required_python_version))}")
            
            if current_version >= self.required_python_version:
                print("✅ Python 버전 확인 완료")
                self.results['python_version'] = True
                return True
            else:
                error_msg = f"Python 버전 불일치: {'.'.join(map(str, current_version))} (필요: {'.'.join(map(str, self.required_python_version))})"
                print(f"❌ {error_msg}")
                self.results['errors'].append(error_msg)
                return False
                
        except Exception as e:
            error_msg = f"Python 버전 확인 실패: {str(e)}"
            print(f"❌ {error_msg}")
            self.results['errors'].append(error_msg)
            return False
    
    def check_env_file(self):
        """.env 파일 존재 및 필수 키 확인"""
        try:
            env_path = Path('.env')
            
            # .env 파일 존재 확인
            if not env_path.exists():
                error_msg = ".env 파일이 존재하지 않습니다"
                print(f"❌ {error_msg}")
                print("💡 해결 방법: .env.example을 복사하여 .env 생성")
                self.results['errors'].append(error_msg)
                return False
            
            print("✅ .env 파일 존재 확인")
            self.results['env_file'] = True
            
            # .env 파일 내용 읽기
            with open(env_path, 'r', encoding='utf-8') as f:
                env_content = f.read()
            
            # 필수 키 확인
            missing_keys = []
            found_keys = []
            
            for key in self.required_env_keys:
                if key in env_content and f'{key}=' in env_content:
                    # 키가 있고 값이 비어있지 않은지 확인
                    for line in env_content.split('\n'):
                        if line.strip().startswith(f'{key}='):
                            value = line.split('=', 1)[1].strip()
                            if value and value != 'your_key_here' and value != 'your_secret_here':
                                found_keys.append(key)
                            else:
                                missing_keys.append(key)
                            break
                else:
                    missing_keys.append(key)
            
            if found_keys:
                print("✅ 필수 키 확인 완료:")
                for key in found_keys:
                    print(f"   - {key}")
            
            if missing_keys:
                warning_msg = f".env 파일에 다음 키가 누락되었거나 값이 설정되지 않음: {', '.join(missing_keys)}"
                print(f"⚠️ {warning_msg}")
                self.results['warnings'].append(warning_msg)
                self.results['env_keys'] = False
            else:
                self.results['env_keys'] = True
            
            return True
            
        except Exception as e:
            error_msg = f".env 파일 확인 실패: {str(e)}"
            print(f"❌ {error_msg}")
            self.results['errors'].append(error_msg)
            return False
    
    def check_docker(self):
        """Docker 서비스 실행 확인"""
        try:
            # Docker 버전 확인
            result = subprocess.run(
                ['docker', '--version'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                error_msg = "Docker가 설치되지 않았습니다"
                print(f"❌ {error_msg}")
                print("💡 해결 방법: Docker Desktop 설치 - https://www.docker.com/products/docker-desktop")
                self.results['errors'].append(error_msg)
                return False
            
            if self.verbose:
                print(f"🔍 Docker 버전: {result.stdout.strip()}")
            
            # Docker 서비스 실행 확인
            result = subprocess.run(
                ['docker', 'ps'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                warning_msg = "Docker 서비스가 실행되지 않았습니다"
                print(f"⚠️ {warning_msg}")
                print("💡 해결 방법: Docker Desktop 실행")
                self.results['warnings'].append(warning_msg)
                self.results['docker'] = False
                return False
            
            print("✅ Docker 서비스 실행 중")
            self.results['docker'] = True
            return True
            
        except FileNotFoundError:
            error_msg = "Docker가 설치되지 않았습니다 (명령어를 찾을 수 없음)"
            print(f"❌ {error_msg}")
            print("💡 해결 방법: Docker Desktop 설치")
            self.results['errors'].append(error_msg)
            return False
            
        except subprocess.TimeoutExpired:
            warning_msg = "Docker 명령 타임아웃"
            print(f"⚠️ {warning_msg}")
            self.results['warnings'].append(warning_msg)
            return False
            
        except Exception as e:
            warning_msg = f"Docker 확인 실패: {str(e)}"
            print(f"⚠️ {warning_msg}")
            self.results['warnings'].append(warning_msg)
            return False
    
    def check_dependencies(self):
        """requirements.txt 설치 확인"""
        try:
            requirements_path = Path('requirements.txt')
            
            if not requirements_path.exists():
                warning_msg = "requirements.txt 파일이 없습니다"
                print(f"⚠️ {warning_msg}")
                self.results['warnings'].append(warning_msg)
                return False
            
            # requirements.txt 읽기
            with open(requirements_path, 'r', encoding='utf-8') as f:
                requirements = []
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        # 패키지명만 추출 (버전 정보 제외)
                        pkg = line.split('==')[0].split('>=')[0].split('<=')[0].strip()
                        if pkg:
                            requirements.append(pkg)
            
            if self.verbose:
                print(f"🔍 requirements.txt에서 {len(requirements)}개 패키지 발견")
            
            # 설치된 패키지 확인
            result = subprocess.run(
                [sys.executable, '-m', 'pip', 'list', '--format=freeze'],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                warning_msg = "pip list 실행 실패"
                print(f"⚠️ {warning_msg}")
                self.results['warnings'].append(warning_msg)
                return False
            
            installed_packages = set()
            for line in result.stdout.split('\n'):
                if '==' in line:
                    pkg = line.split('==')[0].strip().lower()
                    installed_packages.add(pkg)
            
            # 누락된 패키지 확인
            missing_packages = []
            for pkg in requirements:
                if pkg.lower() not in installed_packages:
                    missing_packages.append(pkg)
            
            if missing_packages:
                warning_msg = f"다음 패키지가 설치되지 않음: {', '.join(missing_packages[:5])}"
                if len(missing_packages) > 5:
                    warning_msg += f" 외 {len(missing_packages) - 5}개"
                print(f"⚠️ {warning_msg}")
                print("💡 해결 방법: pip install -r requirements.txt")
                self.results['warnings'].append(warning_msg)
                self.results['dependencies'] = False
                return False
            
            print(f"✅ requirements.txt 설치 확인 완료 ({len(requirements)}개 패키지)")
            self.results['dependencies'] = True
            return True
            
        except Exception as e:
            warning_msg = f"의존성 확인 실패: {str(e)}"
            print(f"⚠️ {warning_msg}")
            self.results['warnings'].append(warning_msg)
            return False
    
    def run_all_checks(self):
        """모든 검증 실행"""
        print("=" * 60)
        print("🚀 환경 검증 시작")
        print("=" * 60)
        print()
        
        # 각 검증 실행
        checks = [
            ("Python 버전", self.check_python_version),
            (".env 파일", self.check_env_file),
            ("Docker 서비스", self.check_docker),
            ("의존성 설치", self.check_dependencies)
        ]
        
        for name, check_func in checks:
            print(f"\n[{name} 검증]")
            check_func()
        
        # 전체 결과 판정
        all_passed = (
            self.results['python_version'] and
            self.results['env_file'] and
            self.results['env_keys'] and
            self.results['docker'] and
            self.results['dependencies']
        )
        
        self.results['all_passed'] = all_passed
        
        # 결과 요약
        print()
        print("=" * 60)
        if all_passed:
            print("🎉 환경 체크 완료! 모든 조건 만족")
        else:
            print("⚠️ 환경 체크 완료! 일부 조건 미충족")
            
            if self.results['errors']:
                print("\n❌ 에러:")
                for error in self.results['errors']:
                    print(f"   - {error}")
            
            if self.results['warnings']:
                print("\n⚠️ 경고:")
                for warning in self.results['warnings']:
                    print(f"   - {warning}")
            
            print("\n📋 해결 방법:")
            print("   1. Python 3.11.11 설치: https://www.python.org/downloads/")
            print("   2. .env 파일 생성: cp .env.example .env")
            print("   3. Docker Desktop 실행")
            print("   4. 의존성 설치: pip install -r requirements.txt")
        
        print("=" * 60)
        
        return all_passed


def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(
        description="개발 환경 자동 검증 스크립트",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python automation/env_check.py                # 기본 실행
  python automation/env_check.py --verbose      # 상세 모드
  python automation/env_check.py --json         # JSON 출력
        """
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='상세 정보 출력'
    )
    
    parser.add_argument(
        '--json',
        action='store_true',
        help='JSON 형식으로 결과 출력'
    )
    
    args = parser.parse_args()
    
    # 환경 검증 실행
    checker = EnvironmentChecker(verbose=args.verbose)
    all_passed = checker.run_all_checks()
    
    # JSON 출력 옵션
    if args.json:
        print("\n[JSON 결과]")
        print(json.dumps(checker.results, indent=2, ensure_ascii=False))
    
    # 종료 코드
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
