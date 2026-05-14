# CHANGELOG
# 2026-03-05 | Copilot | Created: trade module for recent trade display

Version: v1.0
Last Modified: 2026-03-05 | Copilot

# README: src/market/trade

## Purpose
Displays recent trade executions (최근 체결) for a selected trading symbol in real-time.

## Features
- Real-time trade updates via WebSocket
- Trade direction indicator (buy/sell)
- Price and quantity display
- Timestamp for each trade
- Trade aggregation for performance

## Architecture
```
trade/
├── ui/
│   ├── trade.ui              # Qt Designer UI file
│   └── widget_trade.py       # Main widget controller
└── logic/
    └── trade_aggregator.py   # Trade data aggregation
```

## Usage
```python
from src._market.trade import TradeWidget

# Create widget
trade = TradeWidget()

# Update symbol
trade.update_symbol("KRW-BTC")

# Connect to symbol selection from coinlist
coinlist.symbol_selected.connect(trade.update_symbol)
```

## UI Components
- **Trade Table**: Recent trades with timestamp, price, quantity, direction
- **Color Coding**: Green for buy, Red for sell
- **Auto-scroll**: Automatically scrolls to latest trades

## WebSocket Integration
Subscribes to `trade` channel for selected symbol and updates UI on each message.
