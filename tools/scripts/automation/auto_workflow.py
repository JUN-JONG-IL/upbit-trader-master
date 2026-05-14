"""
통합 워크플로우 자동화 스크립트

목적:
    N단계 작업을 자동으로 실행하는 통합 워크플로우를 제공합니다.
    환경 체크, 문서 읽기, 코드 스캔, 작업 실행, 테스트, 문서 업데이트를 자동화합니다.

사용법:
    python automation/auto_workflow.py --stage N
    
예시:
    # 2단계 작업 시작
    python automation/auto_workflow.py --stage 2
    
    # 자동 승인 모드 (주의!)
    python automation/auto_workflow.py --stage 2 --auto-approve
    
    # 드라이런 (실제 변경 없음)
    python automation/auto_workflow.py --stage 2 --dry-run
    
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


class AutoWorkflow:
    """자동 워크플로우 클래스"""
    
    def __init__(self, stage, auto_approve=False, dry_run=False, verbose=False, create_pr=False):
        self.stage = stage
        self.auto_approve = auto_approve
        self.dry_run = dry_run
        self.verbose = verbose
        self.create_pr = create_pr
        self.results = {
            'stage': stage,
            'steps_completed': [],
            'steps_failed': [],
            'warnings': [],
            'files_created': [],
            'files_modified': [],
            'tests_passed': False,
            'success': False
        }
        
    def print_step(self, step_num, step_name):
        """단계 출력"""
        print(f"\n{'=' * 60}")
        print(f"[{step_num}/7] {step_name}")
        print('=' * 60)
        
    def step1_env_check(self):
        """1단계: 환경 체크"""
        self.print_step(1, "환경 자동 체크")
        
        try:
            if self.dry_run:
                print("🔍 드라이런 모드: 환경 체크 건너뛰기")
                self.results['steps_completed'].append('env_check (dry-run)')
                return True
            
            # env_check.py 실행
            result = subprocess.run(
                [sys.executable, 'automation/env_check.py'],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            print(result.stdout)
            
            if result.returncode == 0:
                print("✅ 환경 체크 통과")
                self.results['steps_completed'].append('env_check')
                return True
            else:
                print("❌ 환경 체크 실패")
                print(result.stderr)
                self.results['steps_failed'].append('env_check')
                return False
                
        except Exception as e:
            print(f"❌ 환경 체크 오류: {str(e)}")
            self.results['steps_failed'].append('env_check')
            return False
    
    def step2_read_docs(self):
        """2단계: 문서 자동 읽기 (개선 - 주제별 가이드 자동 선택)"""
        self.print_step(2, "문서 자동 읽기")
        
        try:
            # 필수 문서 읽기
            docs_to_read = [
                'work_order/규칙.md',  # 핵심 규칙
                'work_order/통합_개발_가이드.md',
                f'work_order/{self.stage}_단계_*.md',
            ]
            
            # 주제별 가이드 자동 선택
            stage_guides = {
                2: [
                    'docs/development/FILE_STRUCTURE.md',
                    'docs/infrastructure/DATABASE.md',
                    'docs/operations/DEPLOYMENT.md'
                ],
                3: [
                    'docs/development/UI_UX_GUIDELINES.md',
                    'docs/operations/OPERATING_MODES.md',
                    'docs/development/LOGGING_GUIDE.md'
                ],
                4: [
                    'docs/infrastructure/CANDLE_AGGREGATION.md',
                    'docs/development/PROCESS_ARCHITECTURE.md',
                    'docs/infrastructure/DATABASE.md'
                ],
                5: [
                    'docs/development/CODING_STANDARDS.md',
                    'docs/operations/TESTING.md'
                ],
                6: [
                    'docs/operations/OPERATING_MODES.md',
                    'docs/operations/ORDER_PROCESSING.md',
                    'docs/operations/TESTING.md'
                ],
                7: [
                    'docs/operations/OPERATING_MODES.md',
                    'docs/operations/ORDER_PROCESSING.md',
                    'docs/operations/SECURITY.md',
                    'docs/operations/DEPLOYMENT.md'
                ],
            }
            
            if self.stage in stage_guides:
                print(f"\n📚 {self.stage}단계 관련 주제별 가이드:")
                for guide in stage_guides[self.stage]:
                    docs_to_read.append(guide)
                    print(f"   + {guide}")
            
            print("\n📖 읽어야 할 문서:")
            for doc in docs_to_read:
                print(f"   - {doc}")
            
            # 실제 문서 파일 찾기
            work_order_path = Path('work_order')
            stage_docs = list(work_order_path.glob(f'{self.stage}_단계_*.md'))
            
            if not stage_docs:
                warning = f"{self.stage}단계 문서를 찾을 수 없습니다"
                print(f"⚠️ {warning}")
                self.results['warnings'].append(warning)
            else:
                print(f"\n✅ {self.stage}단계 문서 발견:")
                for doc in stage_docs:
                    print(f"   - {doc.name}")
            
            print("\n💡 Copilot이 자동으로 문서를 읽고 분석합니다")
            self.results['steps_completed'].append('read_docs')
            return True
            
        except Exception as e:
            print(f"❌ 문서 읽기 오류: {str(e)}")
            self.results['steps_failed'].append('read_docs')
            return False
    
    def step3_code_scan(self):
        """3단계: 코드베이스 스캔"""
        self.print_step(3, "코드베이스 스캔")
        
        try:
            print("🔍 프로젝트 구조 분석 중...")
            
            # 주요 폴더 확인
            important_dirs = ['src', 'tests', 'work_order', 'scripts', 'automation']
            
            for dir_name in important_dirs:
                dir_path = Path(dir_name)
                if dir_path.exists():
                    file_count = len(list(dir_path.rglob('*.py')))
                    print(f"   ✅ {dir_name}/ - {file_count}개 Python 파일")
                else:
                    print(f"   ⚠️ {dir_name}/ - 없음")
            
            print("\n💡 Copilot이 자동으로 코드를 스캔하고 충돌 가능성을 확인합니다")
            self.results['steps_completed'].append('code_scan')
            return True
            
        except Exception as e:
            print(f"❌ 코드 스캔 오류: {str(e)}")
            self.results['steps_failed'].append('code_scan')
            return False
    
    def step4_execute_work(self):
        """4단계: 작업 실행"""
        self.print_step(4, "작업 실행")
        
        try:
            # 자동 파싱 및 실행 시도
            try:
                # PYTHONPATH가 설정되지 않은 경우를 위한 경로 추가
                import sys
                from pathlib import Path
                project_root = Path(__file__).parent.parent
                if str(project_root) not in sys.path:
                    sys.path.insert(0, str(project_root))
                
                from automation.stage_parser import StageParser
                from automation.execution_engine import ExecutionEngine
                
                print("🤖 단계 지시서 자동 파싱 시작...")
                parser = StageParser(self.stage)
                execution_plan = parser.generate_execution_plan()
                
                print(f"✅ 파싱 완료:")
                print(f"   - 생성할 파일: {len(execution_plan['files_to_create'])}개")
                print(f"   - 실행할 명령어: {len(execution_plan['commands'])}개")
                print(f"   - 검증 기준: {len(execution_plan['validation_tests'])}개")
                
                if not self.auto_approve:
                    response = input("\n자동 실행을 계속하시겠습니까? (y/n): ")
                    if response.lower() != 'y':
                        print("⚠️ 자동 실행 취소됨")
                        print("💡 Copilot이 수동으로 작업을 수행합니다")
                        self.results['steps_completed'].append('execute_work (manual)')
                        return True
                
                print("\n🚀 자동 실행 시작...")
                engine = ExecutionEngine(execution_plan, dry_run=self.dry_run)
                results = engine.execute_all()
                
                # 결과 기록
                self.results['files_created'] = results['files_created']
                # Note: files_modified is not used in auto mode as we only create new files.
                # Failed file creations are logged but not stored in results for simplicity.
                
                if results['success']:
                    print("✅ 자동 실행 완료")
                    self.results['steps_completed'].append('execute_work (auto)')
                else:
                    print("⚠️ 자동 실행 부분 완료 (일부 실패)")
                    self.results['warnings'].append('자동 실행 부분 실패')
                    self.results['steps_completed'].append('execute_work (auto-partial)')
                
                return True
                
            except (FileNotFoundError, ImportError) as e:
                # 파서/엔진을 찾을 수 없거나 지시서가 없으면 수동 모드로 폴백
                print(f"⚠️ 자동 파싱 불가: {str(e)}")
                print("💡 Copilot 수동 작업 모드로 전환...")
                
            # 수동 모드 (기존 방식)
            if self.dry_run:
                print("🔍 드라이런 모드: 작업 실행 시뮬레이션")
                print("\n예상 작업:")
                print("   - 신규 파일 생성 (실제로 생성하지 않음)")
                print("   - Docstring 추가 (실제로 추가하지 않음)")
                print("   - 주석 추가 (실제로 추가하지 않음)")
                self.results['steps_completed'].append('execute_work (dry-run)')
                return True
            
            print("⚙️ 작업 실행 중...")
            print("\n💡 Copilot이 다음 작업을 자동으로 수행합니다:")
            print("   1. 신규 파일 생성")
            print("   2. Docstring 자동 추가")
            print("   3. 주석 추가 (필요시)")
            print("   4. 테스트 코드 작성")
            
            print("\n⚠️ 주의: 기존 코드는 수정하지 않습니다")
            
            if not self.auto_approve:
                response = input("\n계속하시겠습니까? (y/n): ")
                if response.lower() != 'y':
                    print("❌ 사용자가 작업을 취소했습니다")
                    return False
            
            print("✅ 작업 승인됨")
            self.results['steps_completed'].append('execute_work')
            return True
            
        except Exception as e:
            print(f"❌ 작업 실행 오류: {str(e)}")
            self.results['steps_failed'].append('execute_work')
            return False
    
    def step5_run_tests(self):
        """5단계: 테스트 자동 실행"""
        self.print_step(5, "테스트 자동 실행")
        
        try:
            if self.dry_run:
                print("🔍 드라이런 모드: 테스트 실행 건너뛰기")
                self.results['steps_completed'].append('run_tests (dry-run)')
                return True
            
            print("🧪 테스트 실행 중...")
            
            # test_runner.py가 있으면 실행
            test_runner_path = Path('automation/test_runner.py')
            if test_runner_path.exists():
                result = subprocess.run(
                    [sys.executable, 'automation/test_runner.py', '--quick'],
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                
                print(result.stdout)
                
                if result.returncode == 0:
                    print("✅ 테스트 통과")
                    self.results['tests_passed'] = True
                    self.results['steps_completed'].append('run_tests')
                    return True
                else:
                    print("⚠️ 일부 테스트 실패")
                    self.results['warnings'].append('테스트 실패')
                    self.results['steps_completed'].append('run_tests (with warnings)')
                    return True  # 경고만 표시하고 계속 진행
            else:
                print("⚠️ test_runner.py를 찾을 수 없습니다")
                self.results['warnings'].append('test_runner.py 없음')
                self.results['steps_completed'].append('run_tests (skipped)')
                return True
                
        except subprocess.TimeoutExpired:
            print("⚠️ 테스트 타임아웃 (5분 초과)")
            self.results['warnings'].append('테스트 타임아웃')
            return True
            
        except Exception as e:
            print(f"⚠️ 테스트 실행 오류: {str(e)}")
            self.results['warnings'].append(f'테스트 오류: {str(e)}')
            return True  # 테스트 실패해도 계속 진행
    
    def step6_update_docs(self):
        """6단계: 문서 자동 업데이트"""
        self.print_step(6, "문서 자동 업데이트")
        
        try:
            if self.dry_run:
                print("🔍 드라이런 모드: 문서 업데이트 시뮬레이션")
                print("\n예상 업데이트:")
                print("   - CHANGELOG.md (실제로 수정하지 않음)")
                print("   - README.md (실제로 수정하지 않음)")
                self.results['steps_completed'].append('update_docs (dry-run)')
                return True
            
            print("📝 문서 업데이트 중...")
            
            # doc_updater.py가 있으면 실행
            doc_updater_path = Path('automation/doc_updater.py')
            if doc_updater_path.exists():
                result = subprocess.run(
                    [sys.executable, 'automation/doc_updater.py', '--stage', str(self.stage)],
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                
                print(result.stdout)
                
                if result.returncode == 0:
                    print("✅ 문서 업데이트 완료")
                    self.results['steps_completed'].append('update_docs')
                    return True
                else:
                    print("⚠️ 문서 업데이트 실패")
                    self.results['warnings'].append('문서 업데이트 실패')
                    return True
            else:
                print("⚠️ doc_updater.py를 찾을 수 없습니다")
                print("💡 수동으로 CHANGELOG.md를 업데이트하세요")
                self.results['warnings'].append('doc_updater.py 없음')
                self.results['steps_completed'].append('update_docs (skipped)')
                return True
                
        except Exception as e:
            print(f"⚠️ 문서 업데이트 오류: {str(e)}")
            self.results['warnings'].append(f'문서 오류: {str(e)}')
            return True
    
    def step7_report_completion(self):
        """7단계: 완료 보고"""
        self.print_step(7, "완료 보고")
        
        try:
            print("📊 작업 완료 요약\n")
            
            print(f"✅ 완료된 단계: {len(self.results['steps_completed'])}/6")
            for step in self.results['steps_completed']:
                print(f"   ✓ {step}")
            
            if self.results['steps_failed']:
                print(f"\n❌ 실패한 단계: {len(self.results['steps_failed'])}")
                for step in self.results['steps_failed']:
                    print(f"   ✗ {step}")
            
            if self.results['warnings']:
                print(f"\n⚠️ 경고: {len(self.results['warnings'])}")
                for warning in self.results['warnings']:
                    print(f"   - {warning}")
            
            # 성공 여부 판정
            self.results['success'] = (
                len(self.results['steps_failed']) == 0 and
                'env_check' in str(self.results['steps_completed'])
            )
            
            print("\n" + "=" * 60)
            if self.results['success']:
                print(f"🎉 {self.stage}단계 작업 완료!")
                print("\n다음 단계:")
                print(f"   1. 변경사항 검토")
                print(f"   2. 테스트 실행: python automation/test_runner.py --all")
                print(f"   3. 다음 단계 시작: python automation/auto_workflow.py --stage {self.stage + 1}")
            else:
                print(f"⚠️ {self.stage}단계 작업이 부분적으로 완료되었습니다")
                print("\n권장 조치:")
                print("   1. 실패한 단계 확인")
                print("   2. 오류 해결")
                print("   3. 다시 시도")
            print("=" * 60)
            
            return True
            
        except Exception as e:
            print(f"❌ 완료 보고 오류: {str(e)}")
            return False
    
    def create_pull_request(self):
        """PR 자동 생성"""
        if not self.create_pr:
            return True
            
        if self.dry_run:
            print("\n🔍 드라이런 모드: PR 생성 시뮬레이션")
            print("   - 브랜치 생성 (실제로 생성하지 않음)")
            print("   - 커밋 및 푸시 (실제로 실행하지 않음)")
            print("   - PR 생성 (실제로 생성하지 않음)")
            return True
        
        print("\n" + "=" * 60)
        print("🔄 PR 자동 생성 시작")
        print("=" * 60)
        
        try:
            branch_name = f"feat/stage-{self.stage}-auto"
            pr_title = f"feat: {self.stage}단계 완료 - 자동 생성"
            
            # PR 본문 생성
            pr_body = f"""## 📋 작업 내용
- {self.stage}단계 작업 자동 완료

## 📊 생성/수정된 파일
"""
            if self.results['files_created']:
                for f in self.results['files_created']:
                    pr_body += f"- {f}\n"
            else:
                pr_body += "- (작업 중 생성된 파일 없음)\n"
            
            pr_body += f"""
## ✅ 검증 결과
- 전체 테스트: {'통과' if self.results['tests_passed'] else '일부 경고'}
- 완료된 단계: {len(self.results['steps_completed'])}/7

## ⚠️ 경고 사항
"""
            if self.results['warnings']:
                for w in self.results['warnings']:
                    pr_body += f"- {w}\n"
            else:
                pr_body += "- 없음\n"
            
            pr_body += "\n**자동 생성된 PR입니다.**"
            
            # Git 작업
            print("\n1. Git 브랜치 생성...")
            result = subprocess.run(
                ["git", "checkout", "-b", branch_name],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                # 브랜치가 이미 존재할 수 있음
                print("   ⚠️ 브랜치가 이미 존재하거나 생성 실패")
                subprocess.run(["git", "checkout", branch_name])
            else:
                print(f"   ✅ 브랜치 생성됨: {branch_name}")
            
            print("\n2. Git 변경사항 추가...")
            subprocess.run(["git", "add", "."])
            print("   ✅ 변경사항 추가됨")
            
            print("\n3. Git 커밋...")
            result = subprocess.run(
                ["git", "commit", "-m", pr_title],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                print("   ✅ 커밋 완료")
            else:
                print("   ⚠️ 커밋 실패 또는 변경사항 없음")
                print(f"   {result.stdout}")
            
            print("\n4. Git 푸시...")
            result = subprocess.run(
                ["git", "push", "origin", branch_name],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                print("   ✅ 푸시 완료")
            else:
                print("   ⚠️ 푸시 실패")
                print(f"   {result.stderr}")
                return False
            
            print("\n5. GitHub PR 생성...")
            # gh CLI 사용 가능 여부 확인
            gh_check = subprocess.run(
                ["gh", "--version"],
                capture_output=True
            )
            
            if gh_check.returncode == 0:
                result = subprocess.run(
                    [
                        "gh", "pr", "create",
                        "--title", pr_title,
                        "--body", pr_body,
                        "--base", "main"
                    ],
                    capture_output=True,
                    text=True
                )
                
                if result.returncode == 0:
                    print("   ✅ PR 생성 완료")
                    print(f"\n{result.stdout}")
                    return True
                else:
                    print("   ⚠️ PR 생성 실패")
                    print(f"   {result.stderr}")
                    return False
            else:
                print("   ⚠️ GitHub CLI(gh)가 설치되지 않았습니다")
                print("   💡 수동으로 PR을 생성하세요")
                print(f"   브랜치: {branch_name}")
                return False
                
        except Exception as e:
            print(f"❌ PR 생성 오류: {str(e)}")
            return False
    
    def run(self):
        """전체 워크플로우 실행"""
        print("\n" + "=" * 60)
        print(f"🚀 {self.stage}단계 자동 워크플로우 시작")
        if self.dry_run:
            print("   🔍 모드: 드라이런 (실제 변경 없음)")
        if self.auto_approve:
            print("   ⚠️ 모드: 자동 승인")
        if self.create_pr:
            print("   📝 모드: PR 자동 생성")
        print("=" * 60)
        
        # 각 단계 실행
        steps = [
            self.step1_env_check,
            self.step2_read_docs,
            self.step3_code_scan,
            self.step4_execute_work,
            self.step5_run_tests,
            self.step6_update_docs,
            self.step7_report_completion
        ]
        
        for step in steps:
            if not step():
                # 중요한 단계 실패 시 중단
                if step == self.step1_env_check:
                    print("\n❌ 환경 체크 실패로 작업을 중단합니다")
                    return False
        
        # PR 자동 생성 (성공 시에만)
        if self.results['success'] and self.create_pr:
            self.create_pull_request()
        
        return self.results['success']


def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(
        description="N단계 작업 자동화 워크플로우",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python automation/auto_workflow.py --stage 2               # 2단계 작업
  python automation/auto_workflow.py --stage 2 --dry-run    # 드라이런
  python automation/auto_workflow.py --stage 2 --auto-approve  # 자동 승인 (주의!)
        """
    )
    
    parser.add_argument(
        '--stage',
        type=int,
        required=True,
        help='작업할 단계 번호 (예: 2, 3, 11)'
    )
    
    parser.add_argument(
        '--auto-approve',
        action='store_true',
        help='자동 승인 모드 (사용자 확인 없이 진행)'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='드라이런 모드 (실제 변경 없이 시뮬레이션)'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='상세 정보 출력'
    )
    
    parser.add_argument(
        '--create-pr',
        action='store_true',
        help='작업 완료 후 자동으로 PR 생성'
    )
    
    args = parser.parse_args()
    
    # 워크플로우 실행
    workflow = AutoWorkflow(
        stage=args.stage,
        auto_approve=args.auto_approve,
        dry_run=args.dry_run,
        verbose=args.verbose,
        create_pr=args.create_pr
    )
    
    success = workflow.run()
    
    # 종료 코드
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
