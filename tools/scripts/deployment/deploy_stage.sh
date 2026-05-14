#!/bin/bash
# 완전 자동화 진입점
# 사용법: ./start_stage.sh 2

# 단계 번호 확인
if [ -z "$1" ]; then
    echo "❌ 사용법: ./start_stage.sh <stage_number>"
    echo "예시: ./start_stage.sh 2"
    exit 1
fi

STAGE=$1

echo ""
echo "========================================"
echo "🚀 ${STAGE}단계 완전 자동화 시작..."
echo "========================================"
echo ""

# PYTHONPATH 설정 (현재 디렉토리를 Python 모듈 경로에 추가)
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

# Python 스크립트 실행
python automation/auto_workflow.py --stage "$STAGE" --auto-approve --create-pr

# 결과 확인
if [ $? -eq 0 ]; then
    echo ""
    echo "========================================"
    echo "✅ 완료! PR이 자동 생성되었습니다."
    echo "========================================"
    echo ""
else
    echo ""
    echo "========================================"
    echo "⚠️ 작업 중 일부 문제가 발생했습니다."
    echo "로그를 확인하세요."
    echo "========================================"
    echo ""
    exit 1
fi
