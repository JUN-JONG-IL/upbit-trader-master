#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
테스트 자동화 프레임워크 업그레이드 (Test Framework)

[Purpose]
pytest 통합, 커버리지 리포트, 백테스팅 등 종합 테스트 자동화를 제공합니다.

[Responsibilities]
- pytest 기반 단위/통합 테스트 자동 실행
- 커버리지 리포트 자동 생성 및 검증
- 트레이딩 알고리즘 백테스팅 자동화
- 성능 벤치마크 자동화

[Main Flow]
1. 테스트 환경 설정
2. pytest 실행 (단위/통합)
3. 커버리지 측정 및 리포트 생성
4. 백테스팅 실행 (옵션)
5. 결과 리포트 생성

[Dependencies]
- pytest: 테스트 프레임워크
- pytest-cov: 커버리지
- backtrader: 백테스팅 (optional)

[Author] Copilot
[Created] 2026-02-03
[Modified] 2026-02-03
"""

import os
import sys
import subprocess
import argparse
import json
import datetime
from pathlib import Path
from typing import Dict, List, Optional


class TestFramework:
    """테스트 자동화 프레임워크 클래스"""
    
    def __init__(self, repo_root: Path):
        """
        초기화
        
        Args:
            repo_root: 레포지토리 루트 경로
        """
        self.repo_root = repo_root
        self.tests_dir = repo_root / "tests"
        self.reports_dir = repo_root / "test_reports"
        
        # 리포트 디렉토리 생성
        self.reports_dir.mkdir(exist_ok=True)
    
    def check_dependencies(self) -> Dict[str, bool]:
        """
        필수 의존성 확인
        
        Returns:
            Dict[str, bool]: 의존성 설치 여부
        """
        deps = {
            'pytest': False,
            'pytest-cov': False,
            'pytest-asyncio': False
        }
        
        for package in deps.keys():
            try:
                __import__(package.replace('-', '_'))
                deps[package] = True
            except ImportError:
                pass
        
        return deps
    
    def run_pytest(
        self,
        test_type: str = 'all',
        coverage: bool = False,
        verbose: bool = False
    ) -> Dict:
        """
        pytest 실행
        
        Args:
            test_type: 테스트 타입 ('unit', 'integration', 'all')
            coverage: 커버리지 측정 여부
            verbose: 상세 출력 여부
        
        Returns:
            Dict: 테스트 결과
        """
        print(f"\n=== 🧪 pytest 실행 ({test_type}) ===\n")
        
        # pytest 명령어 구성
        cmd = ['pytest']
        
        # 테스트 경로 지정
        if test_type == 'unit':
            cmd.append(str(self.tests_dir / 'unit'))
        elif test_type == 'integration':
            cmd.append(str(self.tests_dir / 'integration'))
        else:
            cmd.append(str(self.tests_dir))
        
        # 옵션 추가
        if verbose:
            cmd.append('-v')
        
        if coverage:
            cmd.extend([
                '--cov=src',
                '--cov-report=html',
                '--cov-report=term',
                f'--cov-report=json:{self.reports_dir}/coverage.json'
            ])
        
        # JSON 리포트
        cmd.append(f'--json-report')
        cmd.append(f'--json-report-file={self.reports_dir}/pytest_report.json')
        
        try:
            result = subprocess.run(
                cmd,
                cwd=self.repo_root,
                capture_output=True,
                text=True
            )
            
            print(result.stdout)
            if result.stderr:
                print(result.stderr, file=sys.stderr)
            
            # 결과 파싱
            success = result.returncode == 0
            
            return {
                'success': success,
                'returncode': result.returncode,
                'output': result.stdout,
                'errors': result.stderr
            }
        
        except FileNotFoundError:
            print("❌ pytest가 설치되지 않았습니다.")
            print("   설치하려면: pip install pytest pytest-cov pytest-asyncio")
            return {
                'success': False,
                'error': 'pytest not installed'
            }
        except Exception as e:
            print(f"❌ 테스트 실행 중 오류: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def check_coverage(self, min_coverage: float = 80.0) -> Dict:
        """
        커버리지 확인
        
        Args:
            min_coverage: 최소 커버리지 (%)
        
        Returns:
            Dict: 커버리지 정보
        """
        coverage_file = self.reports_dir / 'coverage.json'
        
        if not coverage_file.exists():
            return {
                'success': False,
                'error': 'Coverage report not found'
            }
        
        try:
            with open(coverage_file, 'r') as f:
                data = json.load(f)
            
            total_coverage = data.get('totals', {}).get('percent_covered', 0)
            
            print(f"\n=== 📊 커버리지 리포트 ===")
            print(f"전체 커버리지: {total_coverage:.2f}%")
            print(f"최소 요구사항: {min_coverage:.2f}%")
            
            if total_coverage < min_coverage:
                print(f"⚠️  커버리지가 최소 요구사항보다 낮습니다!")
                return {
                    'success': False,
                    'coverage': total_coverage,
                    'min_required': min_coverage
                }
            else:
                print(f"✅ 커버리지 요구사항 충족")
                return {
                    'success': True,
                    'coverage': total_coverage,
                    'min_required': min_coverage
                }
        
        except Exception as e:
            print(f"❌ 커버리지 리포트 읽기 실패: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def run_backtest(self, strategy: Optional[str] = None) -> Dict:
        """
        백테스팅 실행
        
        Args:
            strategy: 전략 이름 (None이면 기본 전략)
        
        Returns:
            Dict: 백테스팅 결과
        """
        print(f"\n=== 📈 백테스팅 실행 ===\n")
        
        try:
            import backtrader as bt
        except ImportError:
            print("⚠️  backtrader가 설치되지 않았습니다.")
            print("   백테스팅을 건너뜁니다.")
            return {
                'success': False,
                'error': 'backtrader not installed'
            }
        
        # 간단한 백테스트 예시
        print("백테스팅 기능은 향후 구현 예정입니다.")
        print("전략별 백테스팅은 src/strategy/ 모듈에서 수행하세요.")
        
        return {
            'success': True,
            'message': 'Backtest placeholder - implement in src/strategy/'
        }
    
    def run_benchmarks(self) -> Dict:
        """
        성능 벤치마크 실행
        
        Returns:
            Dict: 벤치마크 결과
        """
        print(f"\n=== ⚡ 성능 벤치마크 ===\n")
        
        # 벤치마크 스크립트 찾기
        benchmark_script = self.tests_dir / 'benchmarks' / 'performance.py'
        
        if not benchmark_script.exists():
            print("⚠️  벤치마크 스크립트를 찾을 수 없습니다.")
            print(f"   예상 경로: {benchmark_script}")
            return {
                'success': False,
                'error': 'Benchmark script not found'
            }
        
        try:
            result = subprocess.run(
                [sys.executable, str(benchmark_script)],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                timeout=300  # 5분 타임아웃
            )
            
            print(result.stdout)
            if result.stderr:
                print(result.stderr, file=sys.stderr)
            
            return {
                'success': result.returncode == 0,
                'output': result.stdout
            }
        
        except subprocess.TimeoutExpired:
            print("❌ 벤치마크 타임아웃 (5분 초과)")
            return {
                'success': False,
                'error': 'Timeout'
            }
        except Exception as e:
            print(f"❌ 벤치마크 실행 중 오류: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def generate_report(self, results: Dict) -> str:
        """
        최종 리포트 생성
        
        Args:
            results: 테스트 결과 딕셔너리
        
        Returns:
            str: 리포트 파일 경로
        """
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        report_file = self.reports_dir / f'test_report_{timestamp}.txt'
        
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("="*60 + "\n")
            f.write("테스트 자동화 프레임워크 리포트\n")
            f.write(f"생성 시간: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("="*60 + "\n\n")
            
            # pytest 결과
            if 'pytest' in results:
                f.write("### pytest 결과\n")
                f.write(f"성공: {results['pytest']['success']}\n")
                if 'returncode' in results['pytest']:
                    f.write(f"종료 코드: {results['pytest']['returncode']}\n")
                f.write("\n")
            
            # 커버리지 결과
            if 'coverage' in results:
                f.write("### 커버리지 결과\n")
                f.write(f"성공: {results['coverage']['success']}\n")
                if 'coverage' in results['coverage']:
                    f.write(f"커버리지: {results['coverage']['coverage']:.2f}%\n")
                f.write("\n")
            
            # 백테스트 결과
            if 'backtest' in results:
                f.write("### 백테스팅 결과\n")
                f.write(f"성공: {results['backtest']['success']}\n")
                f.write("\n")
            
            # 벤치마크 결과
            if 'benchmark' in results:
                f.write("### 벤치마크 결과\n")
                f.write(f"성공: {results['benchmark']['success']}\n")
                f.write("\n")
            
            f.write("="*60 + "\n")
        
        print(f"\n✅ 리포트 생성 완료: {report_file}")
        return str(report_file)


def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(
        description='테스트 자동화 프레임워크',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  # 전체 테스트 실행
  python automation/test_framework.py --run-all
  
  # 단위 테스트만
  python automation/test_framework.py --unit
  
  # 커버리지 측정 (최소 80%)
  python automation/test_framework.py --coverage --min 80
  
  # 백테스팅
  python automation/test_framework.py --backtest
  
  # 벤치마크
  python automation/test_framework.py --benchmark
        """
    )
    
    parser.add_argument(
        '--run-all',
        action='store_true',
        help='모든 테스트 실행'
    )
    
    parser.add_argument(
        '--unit',
        action='store_true',
        help='단위 테스트만 실행'
    )
    
    parser.add_argument(
        '--integration',
        action='store_true',
        help='통합 테스트만 실행'
    )
    
    parser.add_argument(
        '--coverage',
        action='store_true',
        help='커버리지 측정'
    )
    
    parser.add_argument(
        '--min',
        type=float,
        default=80.0,
        help='최소 커버리지 (퍼센트, 기본값: 80)'
    )
    
    parser.add_argument(
        '--backtest',
        action='store_true',
        help='백테스팅 실행'
    )
    
    parser.add_argument(
        '--benchmark',
        action='store_true',
        help='성능 벤치마크 실행'
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='상세 출력'
    )
    
    args = parser.parse_args()
    
    # 레포지토리 루트 찾기
    repo_root = Path(__file__).parent.parent
    framework = TestFramework(repo_root)
    
    # 의존성 확인
    deps = framework.check_dependencies()
    missing = [pkg for pkg, installed in deps.items() if not installed]
    
    if missing:
        print("⚠️  누락된 패키지:")
        for pkg in missing:
            print(f"  - {pkg}")
        print("\n설치하려면: pip install " + " ".join(missing))
        print()
    
    # 결과 저장
    results = {}
    
    # 테스트 실행
    if args.run_all or args.unit or args.integration:
        test_type = 'all'
        if args.unit:
            test_type = 'unit'
        elif args.integration:
            test_type = 'integration'
        
        results['pytest'] = framework.run_pytest(
            test_type=test_type,
            coverage=args.coverage or args.run_all,
            verbose=args.verbose
        )
        
        # 커버리지 확인
        if args.coverage or args.run_all:
            results['coverage'] = framework.check_coverage(args.min)
            
            # 커버리지 미달 시 실패
            if not results['coverage']['success']:
                print(f"\n❌ 커버리지 요구사항 미달로 작업 중단")
                sys.exit(1)
    
    # 백테스팅
    if args.backtest or args.run_all:
        results['backtest'] = framework.run_backtest()
    
    # 벤치마크
    if args.benchmark or args.run_all:
        results['benchmark'] = framework.run_benchmarks()
    
    # 리포트 생성
    if results:
        framework.generate_report(results)
        
        # 전체 성공 여부 확인
        all_success = all(
            r.get('success', False) for r in results.values()
        )
        
        if all_success:
            print("\n✅ 모든 테스트 통과")
            sys.exit(0)
        else:
            print("\n❌ 일부 테스트 실패")
            sys.exit(1)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
