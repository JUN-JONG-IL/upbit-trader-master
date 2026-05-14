# -*- coding: utf-8 -*-
"""
CandleStager BATCH_SIZE 및 버퍼 상태 확인
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

print("="*60)
print("🔍 CandleStager 설정 확인")
print("="*60)

# stager.py 파일 읽기
stager_path = Path("src/data_01/pipeline/stager.py")

with open(stager_path, "r", encoding="utf-8") as f:
    content = f.read()

# BATCH_SIZE 찾기
print("\n📊 BATCH_SIZE 설정:")
print("-" * 60)

for line in content.split("\n"):
    if "BATCH_SIZE" in line and "=" in line:
        print(f"  {line.strip()}")

# flush 메서드 확인
print("\n🔧 flush() 메서드:")
print("-" * 60)

lines = content.split("\n")
in_flush = False
indent_level = 0

for i, line in enumerate(lines, 1):
    if "def _flush" in line or "def flush" in line:
        in_flush = True
        indent_level = len(line) - len(line.lstrip())
        print(f"{i:4d} | {line}")
        continue
    
    if in_flush:
        current_indent = len(line) - len(line.lstrip())
        
        if line.strip() == "":
            continue
        
        if current_indent <= indent_level and line.strip():
            break
        
        print(f"{i:4d} | {line}")

print("\n" + "="*60)
print("💡 결론:")
print("="*60)
print("171개 캔들이 수집되었지만:")
print("  - BATCH_SIZE에 도달하지 못하면 버퍼에만 쌓임")
print("  - 수동으로 flush()를 호출하거나")
print("  - 주기적 flush가 필요함")
print("="*60)
