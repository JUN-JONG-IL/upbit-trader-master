import pymongo
from datetime import datetime, timezone

client = pymongo.MongoClient("mongodb://localhost:27017")
db = client["upbit_trader"]

# 테스트 데이터 저장
test_data = {
    "user_id": "test_user",
    "collection_settings": {
        "timeframes": ["1m", "5m", "1h"],
        "backfill_period": "7일 (테스트)"
    },
    "ai_ml": {
        "ai_mode": "ON"
    },
    "updated_at": datetime.now(timezone.utc)
}

result = db.ui_settings.update_one(
    {"user_id": "test_user"},
    {"\": test_data},
    upsert=True
)

print(f"✅ 저장 성공: matched={result.matched_count}, modified={result.modified_count}, upserted_id={result.upserted_id}")

# 저장된 데이터 확인
doc = db.ui_settings.find_one({"user_id": "test_user"})
print(f"📦 저장된 데이터: {doc}")

# 전체 문서 개수 확인
count = db.ui_settings.count_documents({})
print(f"📊 전체 UI 설정 문서 개수: {count}")

# 모든 문서 출력
print("📋 전체 UI 설정 목록:")
for doc in db.ui_settings.find():
    user_id = doc.get('user_id', 'N/A')
    ai_mode = doc.get('ai_ml', {}).get('ai_mode', 'N/A')
    print(f"  - user_id: {user_id}, ai_mode: {ai_mode}")
