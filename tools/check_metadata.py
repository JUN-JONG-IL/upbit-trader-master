# tools/check_metadata.py
from pymongo import MongoClient
import os, sys, json

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/upbit_trader")

def main():
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        db = client.get_default_database() or client.get_database("upbit_trader")
        print("Using DB:", db.name)
        cols = db.list_collection_names()
        print("Collections:", cols)
        if "metadata" not in cols:
            print("metadata 컬렉션 없음")
            return
        coll = db["metadata"]
        cnt = coll.count_documents({})
        print("metadata count:", cnt)
        sample = list(coll.find({}, {"symbol": 1}).limit(30))
        print("sample symbols:", [d.get("symbol") for d in sample])
    except Exception as e:
        print("Mongo 연결/조회 실패:", e)
        sys.exit(2)

if __name__ == "__main__":
    main()