from dotenv import load_dotenv
import os
from pymongo import MongoClient

load_dotenv()

username = os.getenv("MONGO_INITDB_ROOT_USERNAME")
password = os.getenv("MONGO_INITDB_ROOT_PASSWORD")
host = os.getenv("MONGO_HOST", "localhost")
port = os.getenv("MONGO_PORT", "27017")

print(f"연결 시도: mongodb://{username}:***@{host}:{port}/")

try:
    uri = f"mongodb://{username}:{password}@{host}:{port}/"
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    client.admin.command('ping')
    print("✅ MongoDB 연결 성공!")
    
    # metadata 컬렉션 확인
    db = client['trading_db']
    count = db.metadata.count_documents({})
    print(f"✅ metadata 컬렉션: {count}개 문서")
    
except Exception as e:
    print(f"❌ MongoDB 연결 실패: {e}")
