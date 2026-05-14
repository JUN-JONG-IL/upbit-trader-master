#!/usr/bin/env python3
"""
__init__.py 존재 여부 검증 스크립트
"""
import os
import sys


def check_init_files(root_dir="src"):
    """__init__.py 존재 여부 체크"""
    missing = []

    for dirpath, dirnames, filenames in os.walk(root_dir):
        # __pycache__ 제외
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]

        # Python 파일이 있는 디렉토리만 체크
        py_files = [f for f in filenames if f.endswith(".py") and f != "__init__.py"]

        if py_files and "__init__.py" not in filenames:
            missing.append(dirpath)

    if missing:
        print(f"❌ Missing __init__.py in {len(missing)} directories:")
        for path in missing:
            print(f"  - {path}")
        return 1
    else:
        print("✅ All directories have __init__.py!")
        return 0


if __name__ == "__main__":
    sys.exit(check_init_files())
