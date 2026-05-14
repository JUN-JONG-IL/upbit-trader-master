"""
[Purpose]
SQLite 기반 경량 저장소 (MongoDB 대체)

[Responsibilities]
- 실행 파일 배포 시 MongoDB 대체
- 캔들, 주문 데이터 저장
"""

import sqlite3
from pathlib import Path
from typing import List, Dict, Any


class LiteStorage:
    """경량 저장소 (SQLite)"""
    
    def __init__(self, db_path: str = "upbit_trader.db"):
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_tables()
    
    def _init_tables(self):
        """테이블 초기화"""
        cursor = self.conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS candles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exchange TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                t INTEGER NOT NULL,
                o REAL NOT NULL,
                h REAL NOT NULL,
                l REAL NOT NULL,
                c REAL NOT NULL,
                v REAL NOT NULL,
                is_closed BOOLEAN DEFAULT 0,
                UNIQUE(exchange, symbol, timeframe, t)
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_candles_lookup
            ON candles(exchange, symbol, timeframe, t DESC)
        """)
        
        self.conn.commit()
    
    def insert_candle(self, candle: Dict[str, Any]) -> bool:
        """캔들 삽입"""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO candles
                (exchange, symbol, timeframe, t, o, h, l, c, v, is_closed)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                candle['exchange'],
                candle['symbol'],
                candle['timeframe'],
                candle['t'],
                candle['o'],
                candle['h'],
                candle['l'],
                candle['c'],
                candle['v'],
                candle.get('is_closed', False)
            ))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"캔들 삽입 실패: {e}")
            return False
    
    def get_candles(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
        limit: int = 200
    ) -> List[Dict[str, Any]]:
        """캔들 조회"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT exchange, symbol, timeframe, t, o, h, l, c, v, is_closed
            FROM candles
            WHERE exchange = ? AND symbol = ? AND timeframe = ?
            ORDER BY t DESC
            LIMIT ?
        """, (exchange, symbol, timeframe, limit))
        
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    
    def close(self):
        """연결 종료"""
        self.conn.close()
