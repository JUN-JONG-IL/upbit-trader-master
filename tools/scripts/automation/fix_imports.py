#!/usr/bin/env python3
"""
[Purpose]
Import 패턴 자동 수정 스크립트 - src. 접두사 제거

[Usage]
python automation/scripts/fix_imports.py              # 전체 프로젝트
python automation/scripts/fix_imports.py <file_path>  # 특정 파일
"""

import os
import re
import sys
from pathlib import Path

def fix_imports_in_file(file_path: Path) -> bool:
    """
    파일에서 src. 접두사 제거
    
    Returns:
        True: 수정됨
        False: 수정 안 됨 (패턴 없음)
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # from src.scanner → from scanner
    # from src.chart.base_chart_engine → from chart.base_chart_engine
    new_content = re.sub(
        r'^(\s*)from\s+src\.([\w.]+)',
        r'\1from \2',
        content,
        flags=re.MULTILINE
    )
    
    if new_content != content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"✅ 수정: {file_path}")
        return True
    
    return False

def fix_imports(target: str = "src") -> int:
    """
    Import 패턴 일괄 수정
    
    Returns:
        수정된 파일 개수
    """
    count = 0
    target_path = Path(target)
    
    if target_path.is_file():
        # 특정 파일만 수정
        if fix_imports_in_file(target_path):
            count = 1
    else:
        # 전체 프로젝트 수정
        for py_file in target_path.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            if fix_imports_in_file(py_file):
                count += 1
    
    print(f"\n📊 총 {count}개 파일 수정 완료")
    return count

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "src"
    fix_imports(target)
