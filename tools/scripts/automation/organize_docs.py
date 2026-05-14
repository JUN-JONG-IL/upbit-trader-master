#!/usr/bin/env python3
"""
문서 자동 정리 스크립트

루트 디렉토리의 .md 파일을 적절한 위치로 자동 이동
"""

import shutil
from pathlib import Path

def organize_documents():
    """문서 파일 자동 정리"""
    root = Path(".")
    docs_dir = Path("docs")
    
    # 이동 규칙 정의
    move_rules = {
        "*_COMPLETION_REPORT*.md": docs_dir / "reports",
        "*_SUMMARY.md": docs_dir / "summaries",
        "*_GUIDE.md": docs_dir / "guides",
        "IMPORT_*.md": docs_dir / "development",
        "*_FIX_*.md": docs_dir / "development",
        "*_IMPLEMENTATION*.md": docs_dir / "development",
        "RESTRUCTURING_SUMMARY.md": docs_dir / "summaries",
        "DOCUMENTATION_REORGANIZATION_SUMMARY.md": docs_dir / "summaries",
        "FILE_STRUCTURE.md": docs_dir / "architecture",
        "FILE_TREE.md": docs_dir / "architecture",
        "PHASE*.md": docs_dir / "phases",
        "STEPS_*.md": docs_dir / "development",
        "SECURITY_SUMMARY*.md": docs_dir / "reports",
    }
    
    # 예외 파일 (루트에 유지)
    keep_in_root = {"README.md", "LICENSE.md", "CHANGELOG.md", "CONTRIBUTING.md", "LICENSE"}
    
    moved_files = []
    
    for pattern, target_dir in move_rules.items():
        for md_file in root.glob(pattern):
            if md_file.name in keep_in_root:
                continue
            
            # 이미 docs/ 안에 있는 파일은 스킵
            if "docs" in str(md_file.parent):
                continue
            
            # 대상 디렉토리 생성
            target_dir.mkdir(parents=True, exist_ok=True)
            
            # 파일 이동
            target_path = target_dir / md_file.name
            
            # 같은 이름의 파일이 이미 있으면 스킵
            if target_path.exists():
                print(f"⚠️ 이미 존재함, 스킵: {target_path}")
                continue
            
            shutil.move(str(md_file), str(target_path))
            moved_files.append((md_file.name, target_path))
            print(f"✅ {md_file.name} → {target_path}")
    
    if moved_files:
        print(f"\n총 {len(moved_files)}개 파일 정리 완료")
    else:
        print("✅ 정리할 문서 없음")
    
    return 0

if __name__ == "__main__":
    import sys
    sys.exit(organize_documents())
