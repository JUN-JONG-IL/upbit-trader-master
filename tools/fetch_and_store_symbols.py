# tools/fetch_and_store_symbols.py
import os, sys, time, json
import requests
from pymongo import MongoClient, UpdateOne
from datetime import datetime

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/upbit_trader")
UPBIT_MARKETS_URL = "https://api.upbit.com/v1/market/all"
FILTER_MARKET = os.getenv("FILTER_MARKET", "")  # e.g. "KRW" to keep only KRW- markets, empty=all
BATCH_SIZE = 500

def fetch_markets():
    resp = requests.get(UPBIT_MARKETS_URL, timeout=10)
    resp.raise_for_status()
    return resp.json()

def store_to_mongo(markets, mongo_uri=MONGO_URI):
    client = MongoClient(mongo_uri)
    db = client.get_default_database() or client.get_database("upbit_trader")
    coll = db["metadata"]
    ops = []
    for m in markets:
        market = m.get("market")
        if not market:
            continue
        if FILTER_MARKET:
            # keep only markets that start with e.g. "KRW-" if FILTER_MARKET="KRW"
            if not market.startswith(FILTER_MARKET + "-"):
                continue
        # prepare upsert doc: keep existing fields if present
        doc = {
            "symbol": market,
            "korean_name": m.get("korean_name"),
            "english_name": m.get("english_name"),
            "fetched_at": datetime.utcnow(),
        }
        ops.append(UpdateOne({"symbol": market}, {"$set": doc}, upsert=True))
        if len(ops) >= BATCH_SIZE:
            coll.bulk_write(ops, ordered=False)
            ops = []
    if ops:
        coll.bulk_write(ops, ordered=False)
    return coll.count_documents({})

def main():
    try:
        markets = fetch_markets()
    except Exception as e:
        print("Upbit API fetch failed:", e)
        sys.exit(1)
    try:
        n = store_to_mongo(markets)
        print(f"Stored/Updated symbols in Mongo metadata: {n}")
    except Exception as e:
        print("Mongo store failed:", e)
        sys.exit(2)

if __name__ == "__main__":
    main()