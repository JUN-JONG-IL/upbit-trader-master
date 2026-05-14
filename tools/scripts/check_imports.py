#!/usr/bin/env python3
"""
Import 경로 검증 스크립트
- src/ 내부에서 'src.' 접두사 사용 여부 체크
"""
import os
import re
import sys


def check_imports(root_dir="src"):
    """Import 경로 검증"""
    errors = []

    for dirpath, dirnames, filenames in os.walk(root_dir):
        # __pycache__ 제외
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]

        for filename in filenames:
            if not filename.endswith(".py"):
                continue

            filepath = os.path.join(dirpath, filename)

            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

            # 'from src.' 또는 'import src.' 패턴 검색
            matches = re.findall(r"(from src\.|import src\.)", content)

            if matches:
                errors.append(f"{filepath}: Found {len(matches)} violations")

    if errors:
        print("❌ Import path violations found:")
        for error in errors:
            print(f"  - {error}")
        return 1
    else:
        print("✅ All imports are valid!")
        return 0


if __name__ == "__main__":
    sys.exit(check_imports())
