#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
간단한 Prometheus metrics exporter (HTTP /metrics)
- exposes counters: stager_received, stager_inserted, finalizer_processed, notifier_published, validator_isolated
- Usage: run as a process alongside pipeline
"""

from prometheus_client import start_http_server, Counter, Gauge
import os

# Counters
STAGER_RECEIVED = Counter("stager_received_total", "Total candles received by stager")
STAGER_INSERTED = Counter("stager_inserted_total", "Total candles inserted into staging")
FINALIZER_PROCESSED = Counter("finalizer_processed_total", "Total candles processed by finalizer")
NOTIFIER_PUBLISHED = Counter("notifier_published_total", "Total notifications published to Redis")
VALIDATOR_ISOLATED = Counter("validator_isolated_total", "Total candles isolated by validator")

# Simple function to start exporter on port env METRICS_PORT (default 8001)
def start_metrics_server(port: int = None):
    p = int(port or os.getenv("METRICS_PORT", 8001))
    start_http_server(p)
    print(f"Prometheus metrics server started on :{p}")