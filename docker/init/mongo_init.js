// ============================================================
// 기관급 트레이딩 시스템 - MongoDB 초기화 스크립트
// 버전: v8.0  (DB설계.md 기반)
// 실행: mongosh upbit_trader < init/mongo_init.js
// ============================================================

// ============================================================
// 1. metadata 컬렉션 (심볼 정보)
// ============================================================
db.metadata.createIndex({ "symbol": 1, "exchange": 1 }, { unique: true });
db.metadata.createIndex({ "active": 1 });
db.metadata.createIndex({ "korean_name": 1 });
db.metadata.createIndex({ "volume_24h": -1 });

// 샘플 데이터 (업서트 방식으로 중복 삽입 방지)
db.metadata.updateOne(
    { symbol: "KRW-BTC", exchange: "upbit" },
    {
        $setOnInsert: {
            symbol:           "KRW-BTC",
            exchange:         "upbit",
            korean_name:      "비트코인",
            english_name:     "Bitcoin",
            base_currency:    "BTC",
            quote_currency:   "KRW",
            market_warning:   "NONE",
            active:           true,
            listed_at:        new Date("2017-09-25"),
            market_cap:       1000000000000,
            volume_24h:       500000000000,
            base_tf:          "1m",
            created_at:       new Date(),
            updated_at:       new Date()
        }
    },
    { upsert: true }
);

db.metadata.updateOne(
    { symbol: "KRW-ETH", exchange: "upbit" },
    {
        $setOnInsert: {
            symbol:           "KRW-ETH",
            exchange:         "upbit",
            korean_name:      "이더리움",
            english_name:     "Ethereum",
            base_currency:    "ETH",
            quote_currency:   "KRW",
            market_warning:   "NONE",
            active:           true,
            listed_at:        new Date("2017-09-25"),
            market_cap:       500000000000,
            volume_24h:       200000000000,
            base_tf:          "1m",
            created_at:       new Date(),
            updated_at:       new Date()
        }
    },
    { upsert: true }
);

// ============================================================
// 2. priority_settings 컬렉션 (데이터 수집 우선순위 설정)
// ============================================================
db.priority_settings.createIndex({ "user_id": 1 }, { unique: true });

db.priority_settings.updateOne(
    { user_id: "default" },
    {
        $setOnInsert: {
            user_id: "default",
            settings: {
                volume:             false,
                market_cap:         false,
                popularity:         false,
                favorites:          false,
                volatility:         false,
                technical_signals:  false
            },
            logic:      "OR",
            updated_at: new Date()
        }
    },
    { upsert: true }
);

// ============================================================
// 3. user_favorites 컬렉션 (사용자 관심 종목)
// ============================================================
db.user_favorites.createIndex({ "user_id": 1 }, { unique: true });

db.user_favorites.updateOne(
    { user_id: "default" },
    {
        $setOnInsert: {
            user_id:    "default",
            symbols:    ["KRW-BTC", "KRW-ETH"],
            created_at: new Date(),
            updated_at: new Date()
        }
    },
    { upsert: true }
);

print("MongoDB 초기화 완료: metadata, priority_settings, user_favorites");
