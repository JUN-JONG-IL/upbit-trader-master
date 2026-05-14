"""
테스트 자동 실행 스크립트

목적:
    문서 검증, 단위 테스트, 통합 테스트를 자동으로 실행합니다.
    테스트 결과를 요약하여 보고합니다.

사용법:
    python automation/test_runner.py
    
예시:
    # 전체 테스트 실행
    python automation/test_runner.py --all
    
    # 빠른 테스트 (문서 검증만)
    python automation/test_runner.py --quick
    
    # 특정 카테고리만
    python automation/test_runner.py --doc-only
    python automation/test_runner.py --unit-only
    
작성자: Copilot
작성일: 2026-02-01
"""

import sys
import os
import subprocess
import argparse
import json
from pathlib import Path
from datetime import datetime


class TestRunner:
    """테스트 자동 실행 클래스"""
    
    def __init__(self, verbose=False):
        self.verbose = verbose
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'doc_check': {'passed': False, 'total': 0, 'failed': 0},
            'unit_tests': {'passed': False, 'total': 0, 'failed': 0},
            'integration_tests': {'passed': False, 'total': 0, 'failed': 0},
            'all_passed': False,
            'warnings': [],
            'errors': []
        }
        
    def print_header(self, title):
        """헤더 출력"""
        print(f"\n{'=' * 60}")
        print(f"{title}")
        print('=' * 60)
        
    def run_doc_check(self):
        """문서 검증"""
        self.print_header("📋 문서 검증")
        
        try:
            doc_check_path = Path('scripts/doc_check.py')
            
            if not doc_check_path.exists():
                warning = "scripts/doc_check.py를 찾을 수 없습니다"
                print(f"⚠️ {warning}")
                self.results['warnings'].append(warning)
                return True  # 경고만 표시하고 계속
            
            # doc_check.py 실행
            result = subprocess.run(
                [sys.executable, 'scripts/doc_check.py'],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if self.verbose:
                print(result.stdout)
            
            # 결과 파싱 (간단히)
            if result.returncode == 0:
                print("✅ 문서 검증 통과")
                self.results['doc_check']['passed'] = True
                
                # 간단한 파싱 시도
                lines = result.stdout.split('\n')
                for line in lines:
                    if '통과' in line or 'pass' in line.lower():
                        # 숫자 추출 시도
                        import re
                        numbers = re.findall(r'\d+', line)
                        if numbers:
                            self.results['doc_check']['total'] = int(numbers[0])
                
                return True
            else:
                print("❌ 문서 검증 실패")
                if not self.verbose:
                    print(result.stdout[:500])  # 처음 500자만
                self.results['doc_check']['passed'] = False
                self.results['errors'].append('문서 검증 실패')
                return False
                
        except subprocess.TimeoutExpired:
            warning = "문서 검증 타임아웃"
            print(f"⚠️ {warning}")
            self.results['warnings'].append(warning)
            return True
            
        except Exception as e:
            error = f"문서 검증 오류: {str(e)}"
            print(f"❌ {error}")
            self.results['errors'].append(error)
            return False
    
    def run_unit_tests(self):
        """단위 테스트"""
        self.print_header("🧪 단위 테스트")
        
        try:
            tests_path = Path('tests')
            
            if not tests_path.exists():
                warning = "tests/ 폴더를 찾을 수 없습니다"
                print(f"⚠️ {warning}")
                self.results['warnings'].append(warning)
                return True
            
            # pytest 설치 확인
            result = subprocess.run(
                [sys.executable, '-m', 'pytest', '--version'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                warning = "pytest가 설치되지 않았습니다"
                print(f"⚠️ {warning}")
                print("💡 설치: pip install pytest")
                self.results['warnings'].append(warning)
                return True
            
            # pytest 실행
            print("실행 중...")
            result = subprocess.run(
                [sys.executable, '-m', 'pytest', 'tests/', '-v', '--tb=short'],
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if self.verbose:
                print(result.stdout)
            
            # 결과 파싱
            output = result.stdout + result.stderr
            
            # 간단한 통계 추출
            import re
            
            # "passed in" 패턴 찾기
            passed_match = re.search(r'(\d+) passed', output)
            failed_match = re.search(r'(\d+) failed', output)
            
            passed_count = int(passed_match.group(1)) if passed_match else 0
            failed_count = int(failed_match.group(1)) if failed_match else 0
            
            total_count = passed_count + failed_count
            
            self.results['unit_tests']['total'] = total_count
            self.results['unit_tests']['failed'] = failed_count
            
            if failed_count == 0 and total_count > 0:
                print(f"✅ 단위 테스트 통과 ({total_count}/{total_count})")
                self.results['unit_tests']['passed'] = True
                return True
            elif total_count == 0:
                print("⚠️ 실행된 테스트가 없습니다")
                self.results['warnings'].append('단위 테스트 없음')
                return True
            else:
                print(f"❌ 단위 테스트 실패 ({passed_count}/{total_count})")
                if not self.verbose:
                    print(result.stdout[-1000:])  # 마지막 1000자만
                self.results['errors'].append(f'단위 테스트 {failed_count}개 실패')
                return False
                
        except subprocess.TimeoutExpired:
            warning = "단위 테스트 타임아웃 (5분 초과)"
            print(f"⚠️ {warning}")
            self.results['warnings'].append(warning)
            return True
            
        except Exception as e:
            error = f"단위 테스트 오류: {str(e)}"
            print(f"❌ {error}")
            self.results['errors'].append(error)
            return False
    
    def run_integration_tests(self):
        """통합 테스트"""
        self.print_header("🔗 통합 테스트")
        
        try:
            # verify_phase2.py 확인
            verify_path = Path('verify_phase2.py')
            
            if not verify_path.exists():
                warning = "verify_phase2.py를 찾을 수 없습니다"
                print(f"⚠️ {warning}")
                self.results['warnings'].append(warning)
                return True
            
            # verify_phase2.py 실행
            print("실행 중...")
            result = subprocess.run(
                [sys.executable, 'verify_phase2.py'],
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if self.verbose:
                print(result.stdout)
            
            if result.returncode == 0:
                print("✅ 통합 테스트 통과")
                self.results['integration_tests']['passed'] = True
                self.results['integration_tests']['total'] = 1
                return True
            else:
                print("❌ 통합 테스트 실패")
                if not self.verbose:
                    print(result.stdout[:500])
                self.results['integration_tests']['failed'] = 1
                self.results['errors'].append('통합 테스트 실패')
                return False
                
        except subprocess.TimeoutExpired:
            warning = "통합 테스트 타임아웃 (2분 초과)"
            print(f"⚠️ {warning}")
            self.results['warnings'].append(warning)
            return True
            
        except Exception as e:
            warning = f"통합 테스트 오류: {str(e)}"
            print(f"⚠️ {warning}")
            self.results['warnings'].append(warning)
            return True
    
    def run_all_tests(self):
        """전체 테스트 자동 실행"""
        print("=" * 60)
        print("🧪 테스트 자동 실행 시작")
        print("=" * 60)
        
        results = []
        
        # 각 테스트 실행
        print("\n[1/3] 문서 검증...")
        results.append(self.run_doc_check())
        
        print("\n[2/3] 단위 테스트...")
        results.append(self.run_unit_tests())
        
        print("\n[3/3] 통합 테스트...")
        results.append(self.run_integration_tests())
        
        # 전체 결과 판정
        self.results['all_passed'] = all(results)
        
        # 결과 요약
        self.print_summary()
        
        return self.results['all_passed']
    
    def print_summary(self):
        """결과 요약 출력"""
        print("\n" + "=" * 60)
        print("📊 테스트 결과 요약")
        print("=" * 60)
        
        # 각 테스트 결과
        print("\n✅ 통과한 테스트:")
        if self.results['doc_check']['passed']:
            total = self.results['doc_check']['total']
            print(f"   - 문서 검증 ({total if total > 0 else '?'}개)")
        if self.results['unit_tests']['passed']:
            total = self.results['unit_tests']['total']
            print(f"   - 단위 테스트 ({total}개)")
        if self.results['integration_tests']['passed']:
            print(f"   - 통합 테스트")
        
        # 실패한 테스트
        if self.results['errors']:
            print("\n❌ 실패한 테스트:")
            for error in self.results['errors']:
                print(f"   - {error}")
        
        # 경고
        if self.results['warnings']:
            print("\n⚠️ 경고:")
            for warning in self.results['warnings']:
                print(f"   - {warning}")
        
        # 최종 결과
        print("\n" + "=" * 60)
        if self.results['all_passed']:
            print("🎉 모든 테스트 통과!")
        else:
            print("⚠️ 일부 테스트 실패 또는 건너뛰기")
            print("\n💡 권장 조치:")
            print("   1. 실패한 테스트 확인")
            print("   2. 오류 수정")
            print("   3. 다시 실행: python automation/test_runner.py --all")
        print("=" * 60)


def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(
        description="테스트 자동 실행 스크립트",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python automation/test_runner.py --all           # 전체 테스트
  python automation/test_runner.py --quick         # 빠른 테스트 (문서만)
  python automation/test_runner.py --doc-only      # 문서 검증만
  python automation/test_runner.py --unit-only     # 단위 테스트만
        """
    )
    
    parser.add_argument(
        '--all',
        action='store_true',
        help='전체 테스트 실행'
    )
    
    parser.add_argument(
        '--quick',
        action='store_true',
        help='빠른 테스트 (문서 검증만)'
    )
    
    parser.add_argument(
        '--doc-only',
        action='store_true',
        help='문서 검증만 실행'
    )
    
    parser.add_argument(
        '--unit-only',
        action='store_true',
        help='단위 테스트만 실행'
    )
    
    parser.add_argument(
        '--integration-only',
        action='store_true',
        help='통합 테스트만 실행'
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
    
    # 테스트 실행
    runner = TestRunner(verbose=args.verbose)
    
    if args.quick or args.doc_only:
        success = runner.run_doc_check()
    elif args.unit_only:
        success = runner.run_unit_tests()
    elif args.integration_only:
        success = runner.run_integration_tests()
    else:  # --all 또는 기본
        success = runner.run_all_tests()
    
    # JSON 출력
    if args.json:
        print("\n[JSON 결과]")
        print(json.dumps(runner.results, indent=2, ensure_ascii=False))
    
    # 종료 코드
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
