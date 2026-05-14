"""
Stage 2: Receiver - WebSocket/API 데이터 수신
"""
import asyncio
import json
import logging
from typing import List, Dict, Optional, Callable
import websockets

logger = logging.getLogger(__name__)

class CandleReceiver:
    def __init__(self, stager):
        self.stager = stager
        self.ws_url = "wss://api.upbit.com/websocket/v1"
        self.running = False
    
    async def start(self, symbols: List[str], timeframe: str):
        """WebSocket 연결"""
        self.running = True
        
        async with websockets.connect(self.ws_url) as ws:
            msg = [
                {"ticket": "upbit-trader"},
                {"type": "ticker", "codes": symbols, "isOnlyRealtime": True}
            ]
            await ws.send(json.dumps(msg))
            logger.info(f"🔌 연결: {len(symbols)}개 심볼")
            
            while self.running:
                try:
                    data = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
                    await self._process(data, timeframe)
                except asyncio.TimeoutError:
                    await ws.ping()
    
    async def _process(self, data: Dict, tf: str):
        """메시지 처리"""
        if data.get('type') != 'ticker':
            return
        
        candle = {
            'symbol': data['code'],
            'timeframe': tf,
            'timestamp': int(data['timestamp'] / 1000),
            'open': data.get('opening_price', 0),
            'high': data.get('high_price', 0),
            'low': data.get('low_price', 0),
            'close': data.get('trade_price', 0),
            'volume': data.get('acc_trade_volume_24h', 0),
        }
        await self.stager.stage_candle(candle)
