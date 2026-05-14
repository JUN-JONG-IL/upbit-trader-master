#!/usr/bin/env python3
"""
QChartView 사용 패턴 자동 검증

잘못된 Antialiasing 사용 패턴을 자동으로 감지하고 수정 제안
"""

import re
import sys
from pathlib import Path

def check_qchart_usage():
    """QChartView Antialiasing 패턴 검사"""
    errors = []
    warnings = []
    
    # 검사 대상 디렉토리
    src_dirs = [Path("src")]
    
    # 잘못된 패턴
    bad_patterns = [
        (r'\.setRenderHint\(\s*\w+\.Antialiasing\s*\)', 
         "chart_view.Antialiasing 사용 감지 - QPainter.Antialiasing로 수정 필요"),
        (r'\.setRenderHint\(\s*\w+\.painter\(\)\.Antialiasing\s*\)',
         "chart_view.painter().Antialiasing 사용 감지 - QPainter.Antialiasing로 수정 필요")
    ]
    
    for src_dir in src_dirs:
        if not src_dir.exists():
            warnings.append(f"디렉토리 없음: {src_dir}")
            continue
            
        for py_file in src_dir.rglob("*.py"):
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    lines = content.split('\n')
                    
                    for line_num, line in enumerate(lines, 1):
                        for pattern, message in bad_patterns:
                            if re.search(pattern, line):
                                # QPainter.Antialiasing는 올바른 패턴이므로 제외
                                if 'QPainter.Antialiasing' not in line:
                                    errors.append(f"{py_file}:{line_num}: {message}")
                                    errors.append(f"  → {line.strip()}")
            except Exception as e:
                warnings.append(f"파일 읽기 실패: {py_file} - {e}")
    
    # 결과 출력
    if errors:
        print("❌ QChartView 사용 오류 발견:\n")
        for error in errors:
            print(f"  {error}")
        print(f"\n총 {len(errors)//2}개 오류")
        print("\n✅ 수정 방법:")
        print("  1. from PyQt5.QtGui import QPainter")
        print("  2. chart_view.setRenderHint(QPainter.Antialiasing)")
        return 1
    
    if warnings:
        print("⚠️ 경고:\n")
        for warning in warnings:
            print(f"  {warning}")
    
    print("✅ QChartView 사용 패턴 검증 완료 - 문제 없음")
    return 0

if __name__ == "__main__":
    sys.exit(check_qchart_usage())
