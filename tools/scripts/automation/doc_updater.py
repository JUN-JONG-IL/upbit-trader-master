"""
문서 자동 업데이트 스크립트

목적:
    CHANGELOG.md, README.md, 단계 문서를 자동으로 업데이트합니다.
    작업 완료 후 문서를 자동으로 갱신하여 일관성을 유지합니다.

사용법:
    python automation/doc_updater.py --stage N
    
예시:
    # 2단계 완료 후 문서 업데이트
    python automation/doc_updater.py --stage 2 --summary "환경 구축 완료"
    
    # 특정 폴더 README 생성/업데이트
    python automation/doc_updater.py --folder src/coinlist
    
    # 모든 README 일괄 업데이트
    python automation/doc_updater.py --all-folders
    
작성자: Copilot
작성일: 2026-02-01
"""

import sys
import os
import argparse
import json
from pathlib import Path
from datetime import datetime


class DocUpdater:
    """문서 자동 업데이트 클래스"""
    
    def __init__(self, dry_run=False, verbose=False):
        self.dry_run = dry_run
        self.verbose = verbose
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'files_updated': [],
            'files_created': [],
            'warnings': [],
            'errors': []
        }
        
    def update_changelog(self, stage, summary):
        """CHANGELOG.md 자동 업데이트"""
        try:
            changelog_path = Path('work_order/CHANGELOG.md')
            
            if not changelog_path.exists():
                warning = "work_order/CHANGELOG.md를 찾을 수 없습니다"
                print(f"⚠️ {warning}")
                self.results['warnings'].append(warning)
                return False
            
            # 현재 날짜
            today = datetime.now().strftime('%Y-%m-%d')
            
            # 새 항목 생성
            new_entry = f"""
## [{today}] {stage}단계 완료

### 변경사항
- {summary}

### 작성자
- Copilot

---

"""
            
            if self.dry_run:
                print(f"🔍 드라이런: CHANGELOG.md에 다음 내용 추가 예정:")
                print(new_entry)
                return True
            
            # 파일 읽기
            with open(changelog_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 적절한 위치에 삽입 (파일 시작 부분, 헤더 다음)
            lines = content.split('\n')
            insert_index = 0
            
            # 헤더 찾기 (# 로 시작하는 첫 줄 다음)
            for i, line in enumerate(lines):
                if line.startswith('# '):
                    insert_index = i + 2  # 헤더 + 빈 줄 다음
                    break
            
            # 내용 삽입
            lines.insert(insert_index, new_entry)
            new_content = '\n'.join(lines)
            
            # 파일 쓰기
            with open(changelog_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            print(f"✅ CHANGELOG.md 업데이트 완료")
            self.results['files_updated'].append(str(changelog_path))
            return True
            
        except Exception as e:
            error = f"CHANGELOG.md 업데이트 실패: {str(e)}"
            print(f"❌ {error}")
            self.results['errors'].append(error)
            return False
    
    def update_readme(self, folder_path):
        """README.md 자동 생성/업데이트"""
        try:
            folder = Path(folder_path)
            
            if not folder.exists() or not folder.is_dir():
                error = f"폴더를 찾을 수 없습니다: {folder_path}"
                print(f"❌ {error}")
                self.results['errors'].append(error)
                return False
            
            readme_path = folder / 'README.md'
            
            # README가 이미 있는 경우
            if readme_path.exists():
                print(f"⚠️ {readme_path}가 이미 존재합니다")
                print("   수동 업데이트가 필요합니다")
                self.results['warnings'].append(f'{readme_path} 이미 존재')
                return True
            
            # Python 파일 찾기
            py_files = list(folder.glob('*.py'))
            ui_files = list(folder.glob('*.ui'))
            
            # README 템플릿 생성
            folder_name = folder.name
            today = datetime.now().strftime('%Y-%m-%d')
            
            readme_content = f"""# {folder_name}

> 목적: {folder_name} 모듈
> 작성일: {today}
> 작성자: Copilot

---

## 📌 개요

{folder_name} 모듈의 역할과 기능을 설명합니다.

---

## 📂 파일 목록

"""
            
            # Python 파일 추가
            if py_files:
                readme_content += "### Python 파일\n\n"
                for py_file in sorted(py_files):
                    readme_content += f"#### {py_file.name}\n"
                    readme_content += f"- **목적:** (TODO: 설명 추가)\n"
                    readme_content += f"- **주요 기능:** (TODO: 설명 추가)\n"
                    readme_content += f"- **의존성:** (TODO: 설명 추가)\n\n"
            
            # UI 파일 추가
            if ui_files:
                readme_content += "### UI 파일\n\n"
                for ui_file in sorted(ui_files):
                    readme_content += f"#### {ui_file.name}\n"
                    readme_content += f"- **용도:** (TODO: 설명 추가)\n"
                    readme_content += f"- **연결된 Python 파일:** (TODO: 설명 추가)\n\n"
            
            # 나머지 섹션
            readme_content += """---

## 🔗 관련 문서

- [통합_개발_가이드](../work_order/통합_개발_가이드.md)
- [규칙](../work_order/규칙.md)

---

## 📝 변경 이력

- {today}: 초기 생성 (Copilot)

---

**END OF DOCUMENT**
""".format(today=today)
            
            if self.dry_run:
                print(f"🔍 드라이런: {readme_path} 생성 예정")
                if self.verbose:
                    print(readme_content)
                return True
            
            # 파일 쓰기
            with open(readme_path, 'w', encoding='utf-8') as f:
                f.write(readme_content)
            
            print(f"✅ {readme_path} 생성 완료")
            self.results['files_created'].append(str(readme_path))
            return True
            
        except Exception as e:
            error = f"README.md 생성 실패: {str(e)}"
            print(f"❌ {error}")
            self.results['errors'].append(error)
            return False
    
    def update_stage_doc(self, stage, status="완료"):
        """단계 문서에 완료 표시"""
        try:
            work_order_path = Path('work_order')
            stage_docs = list(work_order_path.glob(f'{stage}_단계_*.md'))
            
            if not stage_docs:
                warning = f"{stage}단계 문서를 찾을 수 없습니다"
                print(f"⚠️ {warning}")
                self.results['warnings'].append(warning)
                return False
            
            stage_doc = stage_docs[0]
            today = datetime.now().strftime('%Y-%m-%d')
            
            # 완료 표시 생성
            completion_mark = f"""
---
**작업 상태: {status}**  
**완료일: {today}**  
**작성자: Copilot**
---
"""
            
            if self.dry_run:
                print(f"🔍 드라이런: {stage_doc.name}에 완료 표시 추가 예정")
                return True
            
            # 파일 읽기
            with open(stage_doc, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 이미 완료 표시가 있는지 확인
            if '**작업 상태:' in content:
                print(f"⚠️ {stage_doc.name}에 이미 완료 표시가 있습니다")
                return True
            
            # 파일 끝에 추가
            new_content = content.rstrip() + '\n\n' + completion_mark
            
            # 파일 쓰기
            with open(stage_doc, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            print(f"✅ {stage_doc.name} 완료 표시 추가")
            self.results['files_updated'].append(str(stage_doc))
            return True
            
        except Exception as e:
            error = f"단계 문서 업데이트 실패: {str(e)}"
            print(f"❌ {error}")
            self.results['errors'].append(error)
            return False
    
    def update_all_folders(self):
        """모든 폴더 README 일괄 업데이트"""
        print("📝 모든 폴더 README 일괄 생성 시작...\n")
        
        # src 폴더 하위 확인
        src_path = Path('src')
        if src_path.exists():
            subdirs = [d for d in src_path.iterdir() if d.is_dir() and not d.name.startswith('.')]
            
            print(f"발견된 폴더: {len(subdirs)}개\n")
            
            for subdir in subdirs:
                readme_path = subdir / 'README.md'
                if not readme_path.exists():
                    print(f"처리 중: {subdir}")
                    self.update_readme(subdir)
                else:
                    print(f"건너뛰기: {subdir} (README 이미 존재)")
        else:
            print("⚠️ src/ 폴더를 찾을 수 없습니다")
        
        return True


def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(
        description="문서 자동 업데이트 스크립트",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python automation/doc_updater.py --stage 2 --summary "환경 구축 완료"
  python automation/doc_updater.py --folder src/coinlist
  python automation/doc_updater.py --all-folders
        """
    )
    
    parser.add_argument(
        '--stage',
        type=int,
        help='완료한 단계 번호'
    )
    
    parser.add_argument(
        '--summary',
        type=str,
        help='작업 요약'
    )
    
    parser.add_argument(
        '--folder',
        type=str,
        help='README를 생성할 폴더 경로'
    )
    
    parser.add_argument(
        '--all-folders',
        action='store_true',
        help='모든 폴더 README 일괄 생성'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='드라이런 (실제 변경 없음)'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='상세 정보 출력'
    )
    
    args = parser.parse_args()
    
    # 문서 업데이터 생성
    updater = DocUpdater(dry_run=args.dry_run, verbose=args.verbose)
    
    success = True
    
    # 작업 수행
    if args.stage:
        print(f"📝 {args.stage}단계 문서 업데이트 시작\n")
        
        # CHANGELOG 업데이트
        if args.summary:
            updater.update_changelog(args.stage, args.summary)
        
        # 단계 문서 업데이트
        updater.update_stage_doc(args.stage)
        
    elif args.folder:
        print(f"📝 폴더 README 생성: {args.folder}\n")
        updater.update_readme(args.folder)
        
    elif args.all_folders:
        updater.update_all_folders()
        
    else:
        parser.print_help()
        sys.exit(1)
    
    # 결과 요약
    print("\n" + "=" * 60)
    print("📊 문서 업데이트 완료")
    print("=" * 60)
    
    if updater.results['files_created']:
        print("\n✅ 생성된 파일:")
        for file in updater.results['files_created']:
            print(f"   - {file}")
    
    if updater.results['files_updated']:
        print("\n✅ 업데이트된 파일:")
        for file in updater.results['files_updated']:
            print(f"   - {file}")
    
    if updater.results['warnings']:
        print("\n⚠️ 경고:")
        for warning in updater.results['warnings']:
            print(f"   - {warning}")
    
    if updater.results['errors']:
        print("\n❌ 에러:")
        for error in updater.results['errors']:
            print(f"   - {error}")
        success = False
    
    print("=" * 60)
    
    # 종료 코드
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
