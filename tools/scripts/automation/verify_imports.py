#!/usr/bin/env python3
"""
[Purpose]
Import 패턴 검증 스크립트 - src. 접두사 사용 금지

[Usage]
python automation/scripts/verify_imports.py

[Exit Code]
0: 검증 성공
1: 검증 실패 (src. 접두사 발견)
"""

import os
import re
import sys
from pathlib import Path

def verify_imports(root_dir: str = "src") -> bool:
    """
    src. 접두사 사용하는 import 찾기
    
    Returns:
        True: 검증 성공 (src. 없음)
        False: 검증 실패 (src. 발견)
    """
    errors = []
    pattern = re.compile(r'^\s*from\s+src\.[\w.]+\s+import\s+', re.MULTILINE)
    
    for py_file in Path(root_dir).rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        
        with open(py_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        file_errors = []
        for line_num, line in enumerate(lines, 1):
            # Skip comments and docstrings
            stripped = line.strip()
            if stripped.startswith('#') or stripped.startswith('"""') or stripped.startswith("'''"):
                continue
            if pattern.search(line):
                file_errors.append((line_num, line.strip()))
        
        if file_errors:
            errors.append((str(py_file), file_errors))
    
    if errors:
        print("❌ Import 검증 실패!")
        print(f"다음 {len(errors)}개 파일에서 'from src.' 패턴 발견:\n")
        for file_path, file_errors in errors:
            print(f"  📄 {file_path}")
            for line_num, line in file_errors:
                print(f"     Line {line_num}: {line}")
        print(f"\n총 {sum(len(e[1]) for e in errors)}개 import 수정 필요")
        print("\n✅ 수정 방법:")
        print("  from src.scanner import ... → from scanner import ...")
        print("  from src.chart.base_chart_engine import ... → from chart.base_chart_engine import ...")
        return False
    
    print("✅ Import 검증 성공! (src. 접두사 없음)")
    return True

if __name__ == "__main__":
    success = verify_imports()
    sys.exit(0 if success else 1)
